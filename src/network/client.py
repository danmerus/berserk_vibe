"""Network client for connecting to game server.

Usage:
    client = NetworkClient()
    await client.connect('localhost', 7777)
    await client.hello('PlayerName')
    await client.create_match(['Циклоп', 'Гобрах', ...])
    # or
    await client.join_match('ABC123', ['Лёккен', ...])

    # Send game commands
    await client.send_command(cmd)

    # Poll for updates
    updates = client.get_pending_updates()
"""

import asyncio
import ssl
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from enum import Enum, auto
from queue import Queue, Empty
import threading

from .protocol import (
    Message, MessageType, FrameReader,
    msg_hello, msg_ping, msg_create_match, msg_join_match,
    msg_command, msg_list_matches, msg_player_ready, msg_leave_match,
    msg_chat, msg_draw_offer, msg_draw_accept, msg_request_resync,
)
from ..match import get_content_hash, CommandResult
from ..commands import Command, Event
from ..game import Game

logger = logging.getLogger(__name__)


class ClientState(Enum):
    """Client connection state."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    IN_LOBBY = auto()
    IN_MATCH = auto()
    ERROR = auto()


@dataclass
class NetworkClient:
    """Network client for multiplayer game.

    Runs network I/O in a background thread to not block the game loop.
    Uses queues for thread-safe communication.
    """

    # Connection
    host: str = ""
    port: int = 7777
    use_tls: bool = False
    certfile: Optional[str] = None  # For certificate pinning

    # State
    state: ClientState = ClientState.DISCONNECTED
    player_id: str = ""
    player_name: str = ""
    match_id: str = ""
    player_number: int = 0
    error_message: str = ""

    # Game state (updated from server)
    game: Optional[Game] = None
    opponent_name: str = ""

    # Internal
    _reader: Optional[asyncio.StreamReader] = None
    _writer: Optional[asyncio.StreamWriter] = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[threading.Thread] = None
    _running: bool = False

    # Command tracking
    _command_seq: int = 0
    _server_seq: int = 0
    _last_command_time: float = 0.0  # Time of last command sent
    _last_update_time: float = 0.0  # Time of last update received from server
    _pending_response: bool = False  # True if waiting for server response
    _resync_requested: bool = False  # True if we already requested resync for this timeout

    # Thread-safe queues
    _outgoing: Queue = field(default_factory=Queue)
    _incoming: Queue = field(default_factory=Queue)

    # Callbacks (called from main thread via poll)
    on_connected: Optional[Callable[[], None]] = None
    on_disconnected: Optional[Callable[[str], None]] = None
    on_error: Optional[Callable[[str], None]] = None
    on_match_created: Optional[Callable[[str], None]] = None
    on_match_joined: Optional[Callable[[int, dict], None]] = None
    on_player_joined: Optional[Callable[[int, str], None]] = None
    on_ready_status: Optional[Callable[[int, bool, str], None]] = None  # player, is_ready, name
    on_game_start: Optional[Callable[[dict], None]] = None
    on_update: Optional[Callable[[CommandResult], None]] = None
    on_game_over: Optional[Callable[[int], None]] = None
    on_match_list: Optional[Callable[[List[dict]], None]] = None
    on_chat: Optional[Callable[[str, str, int], None]] = None  # player_name, text, player_number
    on_draw_offered: Optional[Callable[[int], None]] = None  # player_number who offered
    on_player_left: Optional[Callable[[int, str, str], None]] = None  # player_number, player_name, reason
    on_resync: Optional[Callable[[dict], None]] = None  # Called when server sends full resync
    on_resync_requested: Optional[Callable[[], None]] = None  # Called when client requests resync (timeout)
    on_lobby_status: Optional[Callable[[int], None]] = None  # user_count

    # Lobby state
    lobby_user_count: int = 0

    def __post_init__(self):
        self._outgoing = Queue()
        self._incoming = Queue()

    # =========================================================================
    # PUBLIC API (called from main thread)
    # =========================================================================

    def connect(self, host: str, port: int, player_name: str, use_tls: bool = False):
        """Start connection to server (non-blocking)."""
        if self._running:
            return

        self.host = host
        self.port = port
        self.player_name = player_name
        self.use_tls = use_tls
        self.state = ClientState.CONNECTING
        self.error_message = ""

        # Start network thread
        self._running = True
        self._thread = threading.Thread(target=self._run_network_thread, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Disconnect from server."""
        self._running = False
        self._queue_message(None)  # Signal to stop

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        self.state = ClientState.DISCONNECTED

    def create_match(self, squad: List[str], placed_cards: List[dict] = None):
        """Create a new match."""
        if self.state != ClientState.IN_LOBBY:
            return
        self._queue_message(msg_create_match(squad, placed_cards))

    def join_match(self, match_id: str, squad: List[str], placed_cards: List[dict] = None):
        """Join an existing match."""
        if self.state != ClientState.IN_LOBBY:
            return
        self._queue_message(msg_join_match(match_id, squad, placed_cards))

    def list_matches(self):
        """Request list of open matches."""
        if self.state != ClientState.IN_LOBBY:
            return
        self._queue_message(msg_list_matches())

    def send_ready(self):
        """Signal that this player is ready to start."""
        if self.state != ClientState.IN_MATCH:
            return
        self._queue_message(msg_player_ready())

    def send_placement_done(self, placed_cards: List[dict]):
        """Send placement data after deck/squad/placement phase."""
        if self.state != ClientState.IN_MATCH:
            return
        from .protocol import msg_placement_done
        self._queue_message(msg_placement_done(placed_cards))

    def leave_match(self):
        """Leave current match."""
        if self.state != ClientState.IN_MATCH:
            return
        self._queue_message(msg_leave_match())
        self.state = ClientState.IN_LOBBY
        self.match_id = ""
        self.player_number = 0
        self.game = None

    def send_command(self, cmd: Command):
        """Send a game command."""
        if self.state != ClientState.IN_MATCH:
            return

        self._command_seq += 1
        self._last_command_time = time.time()
        self._pending_response = True
        self._resync_requested = False
        self._queue_message(msg_command(cmd, self._command_seq))

    def send_chat(self, text: str):
        """Send a chat message (works in lobby or match)."""
        if self.state not in (ClientState.IN_LOBBY, ClientState.IN_MATCH, ClientState.CONNECTED):
            return
        self._queue_message(msg_chat(text, self.player_name))

    def send_draw_offer(self):
        """Offer a draw to opponent."""
        if self.state != ClientState.IN_MATCH:
            return
        self._queue_message(msg_draw_offer())

    def send_draw_accept(self):
        """Accept a draw offer."""
        if self.state != ClientState.IN_MATCH:
            return
        self._queue_message(msg_draw_accept())

    def request_resync(self):
        """Request full game state resync from server.

        Call this if you suspect the client is out of sync with the server.
        """
        if self.state != ClientState.IN_MATCH:
            return
        logger.info("Requesting resync from server")
        self._queue_message(msg_request_resync())

    # Timeout for command response before auto-resync (seconds)
    COMMAND_TIMEOUT = 3.0
    # Timeout for any server activity before auto-resync (seconds)
    INACTIVITY_TIMEOUT = 15.0

    def poll(self):
        """Process pending messages from network thread.

        Call this from your game loop to handle callbacks.
        """
        while True:
            try:
                msg_type, data = self._incoming.get_nowait()
            except Empty:
                break

            self._handle_incoming(msg_type, data)

        # Check for command timeout and auto-resync
        self._check_command_timeout()

    def _check_command_timeout(self):
        """Check if a command has timed out and request resync if needed."""
        if self._resync_requested:
            return
        if self.state != ClientState.IN_MATCH:
            return

        now = time.time()

        # Check for pending command timeout
        if self._pending_response:
            elapsed = now - self._last_command_time
            if elapsed >= self.COMMAND_TIMEOUT:
                logger.warning(f"Command timed out after {elapsed:.1f}s, requesting resync")
                self._resync_requested = True
                if self.on_resync_requested:
                    self.on_resync_requested()
                self.request_resync()
                return

        # Check for general inactivity (no updates from server)
        if self._last_update_time > 0:
            inactivity = now - self._last_update_time
            if inactivity >= self.INACTIVITY_TIMEOUT:
                logger.warning(f"No server activity for {inactivity:.1f}s, requesting resync")
                self._resync_requested = True
                if self.on_resync_requested:
                    self.on_resync_requested()
                self.request_resync()

    def _queue_message(self, msg: Optional[Message]):
        """Queue message for sending."""
        self._outgoing.put(msg)

    def _handle_incoming(self, msg_type: str, data: Any):
        """Handle incoming message in main thread."""
        if msg_type == 'connected':
            self.state = ClientState.IN_LOBBY
            if self.on_connected:
                self.on_connected()

        elif msg_type == 'disconnected':
            self.state = ClientState.DISCONNECTED
            if self.on_disconnected:
                self.on_disconnected(data)

        elif msg_type == 'error':
            self.error_message = data
            if self.on_error:
                self.on_error(data)

        elif msg_type == 'match_created':
            self.match_id = data
            if self.on_match_created:
                self.on_match_created(data)

        elif msg_type == 'match_joined':
            self.match_id = data['match_id']
            self.player_number = data['player']
            self.state = ClientState.IN_MATCH
            # Reconstruct game from snapshot
            if data.get('snapshot'):
                self.game = Game.from_dict(data['snapshot'])
            if self.on_match_joined:
                self.on_match_joined(data['player'], data.get('snapshot', {}))

        elif msg_type == 'player_joined':
            self.opponent_name = data.get('player_name', '')
            if self.on_player_joined:
                self.on_player_joined(data['player'], data.get('player_name', ''))

        elif msg_type == 'player_left':
            self.opponent_name = ''
            left_player = data.get('player', 0)
            # When opponent leaves during a game, the remaining player wins
            if self.game and left_player != 0 and left_player != self.player_number:
                from ..constants import GamePhase
                self.game.winner = self.player_number  # We win
                self.game.phase = GamePhase.GAME_OVER
                if self.on_game_over:
                    self.on_game_over(self.player_number)
            if self.on_player_left:
                self.on_player_left(
                    left_player,
                    data.get('player_name', ''),
                    data.get('reason', 'disconnected'),
                )

        elif msg_type == 'ready_status':
            if self.on_ready_status:
                self.on_ready_status(
                    data.get('player', 0),
                    data.get('is_ready', False),
                    data.get('player_name', ''),
                )

        elif msg_type == 'game_start':
            self.state = ClientState.IN_MATCH
            self._last_update_time = time.time()
            if data.get('snapshot'):
                self.game = Game.from_dict(data['snapshot'])
            if self.on_game_start:
                self.on_game_start(data.get('snapshot', {}))

        elif msg_type == 'update':
            # Response received, clear pending state
            self._pending_response = False
            self._resync_requested = False
            self._last_update_time = time.time()
            # Reconstruct CommandResult
            result = CommandResult(
                accepted=data.get('accepted', False),
                events=[Event.from_dict(e) for e in data.get('events', [])],
                snapshot=data.get('snapshot'),
                error=data.get('error'),
            )
            # Update local game state
            if result.snapshot:
                self.game = Game.from_dict(result.snapshot)
            if self.on_update:
                self.on_update(result)

        elif msg_type == 'resync':
            # Resync received, clear pending state
            self._pending_response = False
            self._resync_requested = False
            self._last_update_time = time.time()
            if data.get('snapshot'):
                self.game = Game.from_dict(data['snapshot'])
                if self.on_resync:
                    self.on_resync(data['snapshot'])

        elif msg_type == 'game_over':
            # Update game state
            winner = data.get('winner', 0)
            if self.game:
                from src.constants import GamePhase
                self.game.phase = GamePhase.GAME_OVER
                self.game.winner = winner
            if self.on_game_over:
                self.on_game_over(winner)

        elif msg_type == 'match_list':
            if self.on_match_list:
                self.on_match_list(data.get('matches', []))

        elif msg_type == 'chat':
            if self.on_chat:
                self.on_chat(data.get('player_name', ''), data.get('text', ''), data.get('player_number', 0))

        elif msg_type == 'draw_offered':
            if self.on_draw_offered:
                self.on_draw_offered(data.get('player_number', 0))

        elif msg_type == 'lobby_status':
            self.lobby_user_count = data.get('user_count', 0)
            if self.on_lobby_status:
                self.on_lobby_status(self.lobby_user_count)

    # =========================================================================
    # NETWORK THREAD
    # =========================================================================

    def _run_network_thread(self):
        """Run the async network loop in background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._network_main())
        except Exception as e:
            logger.error(f"Network thread error: {e}")
            self._incoming.put(('error', str(e)))
        finally:
            self._loop.close()
            self._loop = None

    async def _network_main(self):
        """Main async network loop."""
        try:
            await self._connect()

            # Create shared frame_reader to preserve buffered data between handshake and receive loop
            frame_reader = FrameReader()
            await self._handshake(frame_reader)

            # Start tasks (pass frame_reader to receive loop)
            recv_task = asyncio.create_task(self._receive_loop(frame_reader))
            send_task = asyncio.create_task(self._send_loop())
            ping_task = asyncio.create_task(self._ping_loop())

            # Wait for any task to complete (error or shutdown)
            done, pending = await asyncio.wait(
                [recv_task, send_task, ping_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()

        except Exception as e:
            logger.error(f"Network error: {e}")
            self._incoming.put(('error', str(e)))
        finally:
            await self._cleanup()

    async def _connect(self):
        """Establish connection to server."""
        ssl_ctx = None
        if self.use_tls:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if self.certfile:
                # Certificate pinning
                ssl_ctx.load_verify_locations(self.certfile)
                ssl_ctx.verify_mode = ssl.CERT_REQUIRED
            else:
                # No verification (development only!)
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, ssl=ssl_ctx),
            timeout=10.0,
        )

        logger.info(f"Connected to {self.host}:{self.port}")

    async def _handshake(self, frame_reader: FrameReader):
        """Perform hello/welcome handshake."""
        content_hash = get_content_hash()
        hello = msg_hello(self.player_name, content_hash)
        await self._send_message(hello)

        # Wait for welcome (use shared frame_reader to preserve buffered data)
        msg = await self._receive_message(frame_reader)
        if msg.type == MessageType.WELCOME:
            self.player_id = msg.payload.get('player_id', '')
            self._incoming.put(('connected', None))
        elif msg.type == MessageType.ERROR:
            raise ConnectionError(msg.payload.get('error', 'Handshake failed'))
        else:
            raise ConnectionError(f"Unexpected response: {msg.type}")

    async def _receive_loop(self, frame_reader: FrameReader):
        """Loop receiving messages from server."""
        # First process any messages already buffered from handshake
        while True:
            msg = frame_reader.get_message()
            if msg is None:
                break
            await self._handle_server_message(msg)

        # Then continue reading new data
        while self._running:
            data = await self._reader.read(4096)
            if not data:
                self._incoming.put(('disconnected', 'Connection closed'))
                break

            frame_reader.feed(data)

            while True:
                msg = frame_reader.get_message()
                if msg is None:
                    break
                await self._handle_server_message(msg)

    async def _send_loop(self):
        """Loop sending queued messages to server."""
        while self._running:
            # Check queue with timeout to allow shutdown
            try:
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._outgoing.get(timeout=0.1)
                )
            except Empty:
                continue
            except RuntimeError:
                # Executor shut down during exit
                break

            if msg is None:
                break  # Shutdown signal

            try:
                await self._send_message(msg)
            except Exception:
                break  # Connection error

    async def _ping_loop(self):
        """Send periodic pings."""
        while self._running:
            await asyncio.sleep(5)
            try:
                await self._send_message(msg_ping())
            except Exception:
                break

    async def _send_message(self, msg: Message):
        """Send message to server."""
        self._writer.write(msg.to_bytes())
        await self._writer.drain()

    async def _receive_message(self, frame_reader: FrameReader) -> Message:
        """Receive single message from server using shared frame_reader."""
        # First check if there's already a complete message in the buffer
        msg = frame_reader.get_message()
        if msg:
            return msg

        # Need to read more data
        while True:
            data = await self._reader.read(4096)
            if not data:
                raise ConnectionError("Connection closed")

            frame_reader.feed(data)
            msg = frame_reader.get_message()
            if msg:
                return msg

    async def _handle_server_message(self, msg: Message):
        """Handle message from server."""
        if msg.type == MessageType.PONG:
            pass  # Keepalive response, ignore

        elif msg.type == MessageType.ERROR:
            self._incoming.put(('error', msg.payload.get('error', 'Unknown error')))

        elif msg.type == MessageType.MATCH_CREATED:
            self._incoming.put(('match_created', msg.match_id))

        elif msg.type == MessageType.MATCH_JOINED:
            self._incoming.put(('match_joined', {
                'match_id': msg.match_id,
                'player': msg.payload.get('player', 0),
                'snapshot': msg.payload.get('snapshot'),
            }))

        elif msg.type == MessageType.PLAYER_JOINED:
            self._incoming.put(('player_joined', {
                'player': msg.payload.get('player', 0),
                'player_name': msg.payload.get('player_name', ''),
            }))

        elif msg.type == MessageType.PLAYER_LEFT:
            self._incoming.put(('player_left', {
                'player': msg.payload.get('player', 0),
                'player_name': msg.payload.get('player_name', ''),
                'reason': msg.payload.get('reason', 'disconnected'),
            }))

        elif msg.type == MessageType.PLAYER_READY_STATUS:
            self._incoming.put(('ready_status', {
                'player': msg.payload.get('player', 0),
                'is_ready': msg.payload.get('is_ready', False),
                'player_name': msg.payload.get('player_name', ''),
            }))

        elif msg.type == MessageType.GAME_START:
            self._incoming.put(('game_start', {
                'snapshot': msg.payload.get('snapshot'),
            }))

        elif msg.type == MessageType.UPDATE:
            self._server_seq = msg.seq
            self._incoming.put(('update', msg.payload))

        elif msg.type == MessageType.RESYNC:
            self._server_seq = msg.seq
            self._incoming.put(('resync', {
                'snapshot': msg.payload.get('snapshot'),
            }))

        elif msg.type == MessageType.GAME_OVER:
            self._incoming.put(('game_over', {
                'winner': msg.payload.get('winner', 0),
            }))

        elif msg.type == MessageType.MATCH_LIST:
            self._incoming.put(('match_list', {
                'matches': msg.payload.get('matches', []),
            }))

        elif msg.type == MessageType.CHAT:
            self._incoming.put(('chat', {
                'player_name': msg.payload.get('player_name', ''),
                'text': msg.payload.get('text', ''),
                'player_number': msg.payload.get('player_number', 0),
            }))

        elif msg.type == MessageType.DRAW_OFFERED:
            self._incoming.put(('draw_offered', {
                'player_number': msg.payload.get('player_number', 0),
            }))

        elif msg.type == MessageType.LOBBY_STATUS:
            self._incoming.put(('lobby_status', {
                'user_count': msg.payload.get('user_count', 0),
            }))

        else:
            logger.warning(f"Unhandled message type: {msg.type}")

    async def _cleanup(self):
        """Clean up connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

        self._reader = None
        self._writer = None
        self._incoming.put(('disconnected', 'Connection closed'))
