"""Game server: lobby, matchmaking, and game session management.

Handles:
- Player connections (TCP + TLS)
- Lobby (create/join matches)
- Match sessions (routes commands to MatchServer)
- Heartbeat and reconnection
"""

import asyncio
import ssl
import logging
import secrets
import time
from dataclasses import replace
from typing import Dict, Optional
from pathlib import Path

from .protocol import (
    Message, MessageType, FrameReader,
    msg_welcome, msg_error, msg_pong, msg_match_created, msg_match_joined,
    msg_player_joined, msg_game_start, msg_update, msg_resync, msg_game_over,
    msg_match_list, msg_player_ready_status, msg_chat, msg_draw_offered,
)
from .session import PlayerSession, MatchSession, SessionState
from ..match import MatchServer, get_content_hash
from ..commands import Command, Event

logger = logging.getLogger(__name__)


class GameServer:
    """Main game server handling lobby and matches.

    Usage:
        server = GameServer(host='0.0.0.0', port=7777)
        await server.start()
    """

    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 7777,
        certfile: Optional[str] = None,
        keyfile: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile

        # Active sessions and matches
        self.sessions: Dict[str, PlayerSession] = {}  # player_id -> session
        self.matches: Dict[str, MatchSession] = {}    # match_id -> match

        # Server state
        self._server: Optional[asyncio.Server] = None
        self._running = False
        self._content_hash = get_content_hash()

    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for TLS."""
        if not self.certfile or not self.keyfile:
            return None

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.certfile, self.keyfile)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    async def start(self):
        """Start the server."""
        ssl_ctx = self._create_ssl_context()

        self._server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
            ssl=ssl_ctx,
        )

        self._running = True
        addr = self._server.sockets[0].getsockname()
        tls_status = "with TLS" if ssl_ctx else "without TLS"
        logger.info(f"Server started on {addr[0]}:{addr[1]} {tls_status}")

        # Start background tasks
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._cleanup_loop())

        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        """Stop the server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Close all sessions
        for session in list(self.sessions.values()):
            await session.close()

        logger.info("Server stopped")

    # =========================================================================
    # CONNECTION HANDLING
    # =========================================================================

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        """Handle a new client connection."""
        session = PlayerSession(reader=reader, writer=writer)
        logger.info(f"New connection from {session.address}")

        try:
            await self._connection_loop(session)
        except ConnectionError:
            logger.info(f"Connection lost: {session.address}")
        except Exception as e:
            logger.error(f"Error handling {session.address}: {e}")
        finally:
            await self._handle_disconnect(session)

    async def _connection_loop(self, session: PlayerSession):
        """Main loop for handling a client connection."""
        frame_reader = FrameReader()

        while self._running:
            # Read data from socket
            try:
                data = await asyncio.wait_for(
                    session.reader.read(4096),
                    timeout=30.0  # Read timeout
                )
            except asyncio.TimeoutError:
                # No data, but connection might still be alive
                continue

            if not data:
                break  # Connection closed

            # Feed data to frame reader
            frame_reader.feed(data)

            # Process complete messages
            while True:
                msg = frame_reader.get_message()
                if msg is None:
                    break
                await self._handle_message(session, msg)

    async def _handle_disconnect(self, session: PlayerSession):
        """Handle client disconnect."""
        logger.info(f"Disconnected: {session.address} ({session.player_name})")

        session.state = SessionState.DISCONNECTED

        # Remove from sessions
        if session.player_id in self.sessions:
            del self.sessions[session.player_id]

        # Handle match cleanup
        if session.match_id and session.match_id in self.matches:
            match = self.matches[session.match_id]
            match.remove_player(session)

            # Notify opponent
            opponent = match.get_opponent_session(session.player_number)
            if opponent:
                try:
                    from .protocol import msg_player_joined
                    # TODO: Add PLAYER_LEFT message
                    pass
                except Exception:
                    pass

            # Clean up empty match
            if match.is_empty:
                del self.matches[session.match_id]
                logger.info(f"Match {session.match_id} removed (empty)")

        await session.close()

    # =========================================================================
    # MESSAGE ROUTING
    # =========================================================================

    async def _handle_message(self, session: PlayerSession, msg: Message):
        """Route message to appropriate handler."""
        # Update activity timestamp on any message
        session.last_pong = time.time()

        handlers = {
            MessageType.HELLO: self._handle_hello,
            MessageType.PING: self._handle_ping,
            MessageType.CREATE_MATCH: self._handle_create_match,
            MessageType.JOIN_MATCH: self._handle_join_match,
            MessageType.LEAVE_MATCH: self._handle_leave_match,
            MessageType.LIST_MATCHES: self._handle_list_matches,
            MessageType.PLAYER_READY: self._handle_player_ready,
            MessageType.PLACEMENT_DONE: self._handle_placement_done,
            MessageType.COMMAND: self._handle_command,
            MessageType.REQUEST_RESYNC: self._handle_resync_request,
            MessageType.CHAT: self._handle_chat,
            MessageType.DRAW_OFFER: self._handle_draw_offer,
            MessageType.DRAW_ACCEPT: self._handle_draw_accept,
        }

        handler = handlers.get(msg.type)
        if handler:
            try:
                await handler(session, msg)
            except Exception as e:
                logger.error(f"Error handling {msg.type}: {e}")
                await self._send(session, msg_error(str(e)))
        else:
            logger.warning(f"Unknown message type: {msg.type}")

    async def _send(self, session: PlayerSession, msg: Message):
        """Send message to a session."""
        try:
            await session.send(msg.to_bytes())
        except ConnectionError:
            session.state = SessionState.DISCONNECTED

    # =========================================================================
    # HANDLER: CONNECTION
    # =========================================================================

    async def _handle_hello(self, session: PlayerSession, msg: Message):
        """Handle client hello/handshake."""
        player_name = msg.payload.get('player_name', 'Player')
        content_hash = msg.payload.get('content_hash', '')

        # Version check
        if content_hash and content_hash != self._content_hash:
            await self._send(session, msg_error(
                f"Version mismatch. Server: {self._content_hash}, Client: {content_hash}"
            ))
            await session.close()
            return

        # Assign player ID
        session.player_id = secrets.token_hex(8)
        session.player_name = player_name
        session.state = SessionState.IN_LOBBY

        self.sessions[session.player_id] = session

        await self._send(session, msg_welcome(session.player_id))
        logger.info(f"Player authenticated: {player_name} ({session.player_id})")

    async def _handle_ping(self, session: PlayerSession, msg: Message):
        """Handle ping - respond with pong."""
        session.last_pong = time.time()  # Update activity timestamp
        await self._send(session, msg_pong())

    # =========================================================================
    # HANDLER: LOBBY
    # =========================================================================

    async def _handle_create_match(self, session: PlayerSession, msg: Message):
        """Handle create match request."""
        if session.state != SessionState.IN_LOBBY:
            await self._send(session, msg_error("Not in lobby"))
            return

        squad = msg.payload.get('squad', [])
        placed_cards = msg.payload.get('placed_cards', [])

        # Generate match ID (6 chars, easy to type)
        match_id = secrets.token_hex(3).upper()
        while match_id in self.matches:
            match_id = secrets.token_hex(3).upper()

        # Create match session
        match = MatchSession(
            match_id=match_id,
            host_session=session,
            host_squad=squad,
            host_placed_cards=placed_cards,
        )
        self.matches[match_id] = match

        # Update session
        session.match_id = match_id
        session.player_number = 1
        session.state = SessionState.IN_MATCH

        await self._send(session, msg_match_created(match_id))
        logger.info(f"Match created: {match_id} by {session.player_name}")

    async def _handle_join_match(self, session: PlayerSession, msg: Message):
        """Handle join match request."""
        if session.state != SessionState.IN_LOBBY:
            await self._send(session, msg_error("Not in lobby"))
            return

        match_id = msg.match_id
        if not match_id:
            match_id = msg.payload.get('match_id', '').upper()

        squad = msg.payload.get('squad', [])
        placed_cards = msg.payload.get('placed_cards', [])

        # Find match
        match = self.matches.get(match_id)
        if not match:
            await self._send(session, msg_error(f"Match not found: {match_id}"))
            return

        if match.is_full:
            await self._send(session, msg_error("Match is full"))
            return

        if match.is_started:
            await self._send(session, msg_error("Match already started"))
            return

        # Join as guest
        match.guest_session = session
        match.guest_squad = squad
        match.guest_placed_cards = placed_cards
        session.match_id = match_id
        session.player_number = 2
        session.state = SessionState.IN_MATCH

        # Notify both players that they're in the ready phase
        # Send each player info about both players
        for player_num in [1, 2]:
            player_session = match.get_session(player_num)
            if player_session:
                opponent = match.get_opponent_session(player_num)
                # Send match joined confirmation
                await self._send(player_session, msg_match_joined(
                    match_id,
                    player_num,
                    {},  # No snapshot yet - game not started
                ))
                # Send opponent info
                if opponent:
                    await self._send(player_session, msg_player_joined(
                        3 - player_num,
                        opponent.player_name,
                    ))

        logger.info(f"Match {match_id}: {session.player_name} joined, waiting for ready")

    async def _handle_leave_match(self, session: PlayerSession, msg: Message):
        """Handle leave match request."""
        if session.state != SessionState.IN_MATCH:
            return

        match = self.matches.get(session.match_id)
        if match:
            match.remove_player(session)

            # Notify opponent
            opponent = match.get_opponent_session(session.player_number)
            if opponent:
                # TODO: Send player left notification
                pass

            # Clean up empty match
            if match.is_empty:
                del self.matches[session.match_id]

        session.match_id = None
        session.player_number = 0
        session.state = SessionState.IN_LOBBY

    async def _handle_list_matches(self, session: PlayerSession, msg: Message):
        """Handle request for list of open matches."""
        open_matches = [
            m.to_dict() for m in self.matches.values()
            if not m.is_full and not m.is_started
        ]
        await self._send(session, msg_match_list(open_matches))

    async def _handle_player_ready(self, session: PlayerSession, msg: Message):
        """Handle player ready signal - just broadcast status, don't start game yet."""
        if session.state != SessionState.IN_MATCH:
            await self._send(session, msg_error("Not in match"))
            return

        match = self.matches.get(session.match_id)
        if not match:
            await self._send(session, msg_error("Match not found"))
            return

        if match.is_started:
            return  # Already started, ignore

        # Set this player as ready
        match.set_ready(session.player_number, True)
        logger.info(f"Match {match.match_id}: Player {session.player_number} ({session.player_name}) is ready")

        # Notify both players of ready status (clients will transition to deck selection when both ready)
        for player_num in [1, 2]:
            player_session = match.get_session(player_num)
            if player_session:
                await self._send(player_session, msg_player_ready_status(
                    session.player_number,
                    True,
                    session.player_name,
                ))

    async def _handle_placement_done(self, session: PlayerSession, msg: Message):
        """Handle placement data from a player after deck/squad/placement phase."""
        if session.state != SessionState.IN_MATCH:
            await self._send(session, msg_error("Not in match"))
            return

        match = self.matches.get(session.match_id)
        if not match:
            await self._send(session, msg_error("Match not found"))
            return

        if match.is_started:
            return  # Already started, ignore

        placed_cards = msg.payload.get('placed_cards', [])

        # Store placement for this player
        if session.player_number == 1:
            match.host_placed_cards = placed_cards
            logger.info(f"Match {match.match_id}: Host placement received")
        else:
            match.guest_placed_cards = placed_cards
            logger.info(f"Match {match.match_id}: Guest placement received")

        # If both placements received, start the game
        if match.host_placed_cards and match.guest_placed_cards:
            await self._start_match(match)

    # =========================================================================
    # HANDLER: GAME
    # =========================================================================

    async def _start_match(self, match: MatchSession):
        """Start a match when both players are ready."""
        if not match.is_full:
            return

        # Create game server
        match.server = MatchServer()

        # Use placement data if available, otherwise auto-place
        if match.host_placed_cards and match.guest_placed_cards:
            # Convert dicts back to Card objects
            from ..card import Card
            p1_cards = [Card.from_dict(d) for d in match.host_placed_cards]
            p2_cards = [Card.from_dict(d) for d in match.guest_placed_cards]
            match.server.setup_with_placement(p1_cards, p2_cards)
        else:
            match.server.setup_game(match.host_squad, match.guest_squad)

        match.is_started = True

        # Send game start to both players
        for player_num in [1, 2]:
            session = match.get_session(player_num)
            if session:
                snapshot = match.server.get_snapshot(for_player=player_num)
                await self._send(session, msg_game_start(snapshot))

        logger.info(f"Match {match.match_id} started")

    async def _handle_command(self, session: PlayerSession, msg: Message):
        """Handle game command from client."""
        if session.state != SessionState.IN_MATCH:
            await self._send(session, msg_error("Not in match"))
            return

        match = self.matches.get(session.match_id)
        if not match or not match.server:
            await self._send(session, msg_error("Match not found"))
            return

        # Check for duplicate command
        if session.is_duplicate_command(msg.seq):
            logger.warning(f"Duplicate command seq={msg.seq} from {session.player_name}")
            return

        # Deserialize and validate command
        cmd_data = msg.payload.get('command', {})
        try:
            cmd = Command.from_dict(cmd_data)
        except Exception as e:
            await self._send(session, msg_error(f"Invalid command: {e}"))
            return

        # Force player number from session (security) - Command is frozen, so create new one
        cmd = replace(cmd, player=session.player_number)

        # Process command
        result = match.server.apply(cmd, include_snapshot=True)
        snapshot_hash = match.server.get_state_hash()

        # Send update to command sender
        seq = session.next_server_seq()
        await self._send(session, msg_update(result, seq, snapshot_hash))

        # Broadcast to opponent if command was accepted
        if result.accepted:
            opponent = match.get_opponent_session(session.player_number)
            if opponent:
                # Get opponent's view of the snapshot
                opponent_snapshot = match.server.get_snapshot(for_player=opponent.player_number)
                opponent_result = type(result)(
                    accepted=result.accepted,
                    events=result.events,
                    snapshot=opponent_snapshot,
                    error=result.error,
                )
                opp_seq = opponent.next_server_seq()
                await self._send(opponent, msg_update(opponent_result, opp_seq, snapshot_hash))

        # Check for game over
        if match.server.game and match.server.game.winner:
            match.is_finished = True
            match.winner = match.server.game.winner
            await self._broadcast_match(match, msg_game_over(match.winner))
            logger.info(f"Match {match.match_id} ended, winner: P{match.winner}")

    async def _handle_resync_request(self, session: PlayerSession, msg: Message):
        """Handle resync request - send full snapshot."""
        if session.state != SessionState.IN_MATCH:
            return

        match = self.matches.get(session.match_id)
        if not match or not match.server:
            return

        snapshot = match.server.get_snapshot(for_player=session.player_number)
        seq = session.next_server_seq()
        await self._send(session, msg_resync(snapshot, seq))

    async def _handle_chat(self, session: PlayerSession, msg: Message):
        """Handle chat message - broadcast to all players in match."""
        if session.state != SessionState.IN_MATCH:
            return

        match = self.matches.get(session.match_id)
        if not match:
            return

        text = msg.payload.get('text', '')
        if not text:
            return

        # Use the session's player_name and player_number for security (not what client sent)
        chat_msg = msg_chat(text, session.player_name, session.player_number)

        # Broadcast to all players in the match (including sender)
        await self._broadcast_match(match, chat_msg)
        logger.debug(f"Chat [{match.match_id}] {session.player_name}: {text}")

    async def _handle_draw_offer(self, session: PlayerSession, msg: Message):
        """Handle draw offer - notify opponent."""
        if session.state != SessionState.IN_MATCH:
            return

        match = self.matches.get(session.match_id)
        if not match or not match.is_started:
            return

        # Can't offer draw if there's already an offer from us
        if match.draw_offered_by == session.player_number:
            return

        # If opponent already offered, this is effectively an accept
        if match.draw_offered_by != 0 and match.draw_offered_by != session.player_number:
            await self._handle_draw_accept(session, msg)
            return

        # Record the offer
        match.draw_offered_by = session.player_number

        # Notify opponent
        opponent = match.get_opponent_session(session.player_number)
        if opponent:
            await self._send(opponent, msg_draw_offered(session.player_number))

        logger.info(f"Match {match.match_id}: Player {session.player_number} offered draw")

    async def _handle_draw_accept(self, session: PlayerSession, msg: Message):
        """Handle draw accept - end game in draw."""
        if session.state != SessionState.IN_MATCH:
            return

        match = self.matches.get(session.match_id)
        if not match or not match.is_started:
            return

        # Can only accept if opponent offered
        if match.draw_offered_by == 0 or match.draw_offered_by == session.player_number:
            return

        # End game in draw
        match.is_finished = True
        match.winner = 0  # 0 = draw
        await self._broadcast_match(match, msg_game_over(0))
        logger.info(f"Match {match.match_id} ended in draw (accepted by P{session.player_number})")

    async def _broadcast_match(self, match: MatchSession, msg: Message):
        """Broadcast message to all players in a match."""
        for player_num in [1, 2]:
            session = match.get_session(player_num)
            if session and session.state == SessionState.IN_MATCH:
                await self._send(session, msg)

    # =========================================================================
    # BACKGROUND TASKS
    # =========================================================================

    async def _heartbeat_loop(self):
        """Send periodic heartbeat checks."""
        while self._running:
            await asyncio.sleep(5)

            for session in list(self.sessions.values()):
                if not session.is_alive:
                    logger.warning(f"Session timeout: {session.player_name}")
                    await self._handle_disconnect(session)

    async def _cleanup_loop(self):
        """Clean up stale matches."""
        while self._running:
            await asyncio.sleep(60)

            now = time.time()
            stale_matches = [
                mid for mid, match in self.matches.items()
                if match.is_empty or (not match.is_started and now - match.created_at > 300)
            ]

            for mid in stale_matches:
                del self.matches[mid]
                logger.info(f"Cleaned up stale match: {mid}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def run_server(
    host: str = '0.0.0.0',
    port: int = 7777,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
):
    """Run the game server."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
    )

    server = GameServer(host, port, certfile, keyfile)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server interrupted")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Berserk Game Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=7777, help='Port to listen on')
    parser.add_argument('--cert', help='TLS certificate file')
    parser.add_argument('--key', help='TLS key file')

    args = parser.parse_args()
    run_server(args.host, args.port, args.cert, args.key)
