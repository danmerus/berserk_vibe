"""Match protocol skeleton for network-ready game architecture.

This module provides a clean abstraction layer between game logic and transport.
Currently runs locally, but designed for easy network swap later.

Architecture:
    MatchServer: Authoritative game state, processes commands, emits events
    MatchClient: Sends commands, receives events/snapshots, manages local UI

Usage (local):
    server = MatchServer()
    server.setup_game()

    client1 = LocalMatchClient(server, player=1)
    client2 = LocalMatchClient(server, player=2)

    # Client sends command
    result = client1.send_command(cmd_move(1, card_id, position))
    # result.accepted, result.events, result.snapshot

Usage (future network):
    # Server side
    server = MatchServer()
    network_handler = NetworkServerHandler(server)

    # Client side
    client = NetworkMatchClient(host, port, player=1)
    result = client.send_command(cmd)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from .game import Game
from .commands import Command, Event, CommandType
from .ui_state import GameClient


@dataclass
class CommandResult:
    """Result of processing a command."""
    accepted: bool
    events: List[Event] = field(default_factory=list)
    snapshot: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for network transport."""
        return {
            'accepted': self.accepted,
            'events': [e.to_dict() for e in self.events],
            'snapshot': self.snapshot,
            'error': self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommandResult':
        """Deserialize from network."""
        return cls(
            accepted=data['accepted'],
            events=[Event.from_dict(e) for e in data.get('events', [])],
            snapshot=data.get('snapshot'),
            error=data.get('error'),
        )


class MatchServer:
    """Authoritative game server.

    Responsibilities:
    - Owns the authoritative Game state
    - Validates and processes commands
    - Emits events for state changes
    - Provides state snapshots on request

    This class is transport-agnostic - it just processes commands and returns results.
    """

    # Commands that remote clients can send
    ALLOWED_COMMANDS = frozenset([
        CommandType.MOVE,
        CommandType.ATTACK,
        CommandType.USE_ABILITY,
        CommandType.USE_INSTANT,
        CommandType.PREPARE_FLYER_ATTACK,
        CommandType.CONFIRM,
        CommandType.CANCEL,
        CommandType.CHOOSE_POSITION,
        CommandType.CHOOSE_CARD,
        CommandType.CHOOSE_AMOUNT,
        CommandType.PASS_PRIORITY,
        CommandType.SKIP,
        CommandType.END_TURN,
    ])

    def __init__(self):
        self.game: Optional[Game] = None
        self.command_log: List[Command] = []  # For replay support

    def setup_game(self, p1_squad: list = None, p2_squad: list = None):
        """Initialize a new game."""
        self.game = Game()
        self.game.setup_game(p1_squad, p2_squad)
        self.command_log = []

    def setup_with_placement(self, p1_cards: list, p2_cards: list):
        """Initialize game with pre-placed cards."""
        self.game = Game()
        self.game.setup_game_with_placement(p1_cards, p2_cards)
        self.command_log = []

    def apply(self, cmd: Command, include_snapshot: bool = True) -> CommandResult:
        """Process a command and return the result.

        Args:
            cmd: The command to process
            include_snapshot: Whether to include full game state in result

        Returns:
            CommandResult with accepted status, events, and optional snapshot
        """
        if self.game is None:
            return CommandResult(accepted=False, error="No game in progress")

        # Validate command type is allowed from remote clients
        if cmd.type not in self.ALLOWED_COMMANDS:
            return CommandResult(
                accepted=False,
                error=f"Command type {cmd.type} not allowed from client"
            )

        # Process command (server_only=True rejects UI commands)
        accepted, events = self.game.process_command(cmd, server_only=True)

        # Log accepted commands for replay
        if accepted:
            self.command_log.append(cmd)

        # Build result
        result = CommandResult(
            accepted=accepted,
            events=events,
        )

        if include_snapshot:
            # Filter snapshot for the player who sent the command
            result.snapshot = self.get_snapshot(for_player=cmd.player)

        return result

    def get_snapshot(self, for_player: Optional[int] = None) -> Dict[str, Any]:
        """Get current game state snapshot for sync.

        Args:
            for_player: If provided (1 or 2), filter snapshot to only show
                        what that player should see. If None, returns full
                        server state (for internal use only).
        """
        if self.game is None:
            return {}
        if for_player is not None:
            return self.game.snapshot_for_player(for_player)
        return self.game.to_dict(include_ui_state=False)

    def get_state_hash(self) -> str:
        """Get a hash of current state for validation."""
        import hashlib
        import json
        snapshot = self.get_snapshot()
        state_str = json.dumps(snapshot, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:16]


class LocalMatchClient:
    """Local client that communicates directly with server.

    For hotseat/local play where server and client are in same process.
    Wraps GameClient for UI state management.
    """

    def __init__(self, server: MatchServer, player: int):
        self.server = server
        self.player = player
        self._game_client: Optional[GameClient] = None

    @property
    def game_client(self) -> Optional[GameClient]:
        """Get the GameClient for UI state management."""
        if self._game_client is None and self.server.game is not None:
            self._game_client = GameClient(self.server.game, self.player)
        return self._game_client

    @property
    def game(self) -> Optional[Game]:
        """Direct access to game state (local only - wouldn't exist in network client)."""
        return self.server.game

    def send_command(self, cmd: Command) -> CommandResult:
        """Send a command to the server."""
        result = self.server.apply(cmd)

        # Update local UI state after command
        if self.game_client:
            self.game_client.refresh_selection()

        return result

    def sync_from_snapshot(self, snapshot: Dict[str, Any]):
        """Sync local state from server snapshot.

        In local mode this is typically a no-op since we share the Game object.
        However, this method is implemented for testing and validation purposes.

        In network mode, this would be the primary way to update local state.
        """
        # In local mode, we share the Game object directly so no sync needed.
        # The snapshot is provided for validation/debugging but not applied.
        pass


class NetworkMatchClient:
    """Network client that communicates with remote server.

    This is a base implementation for future network play.
    Currently provides the interface for local testing.
    """

    def __init__(self, player: int):
        self.player = player
        self._local_game: Optional[Game] = None  # Local copy for rendering
        self._game_client: Optional[GameClient] = None

    @property
    def game(self) -> Optional[Game]:
        """Get local game copy (reconstructed from snapshots)."""
        return self._local_game

    @property
    def game_client(self) -> Optional[GameClient]:
        """Get the GameClient for UI state management."""
        return self._game_client

    def sync_from_snapshot(self, snapshot: Dict[str, Any]):
        """Reconstruct local game state from server snapshot.

        Preserves UI state (selection, arrows, floating text) across updates.
        This is the core sync mechanism for network play.
        """
        if not snapshot:
            return

        # Reconstruct game from snapshot
        self._local_game = Game.from_dict(snapshot)

        if self._game_client is None:
            # First sync - create GameClient
            self._game_client = GameClient(self._local_game, self.player)
        else:
            # Subsequent syncs - preserve UI state, just update game reference
            self._game_client.game = self._local_game
            self._game_client.refresh_selection()

    def apply_events(self, events: List[Event]):
        """Apply events to update local UI state (visuals, arrows, etc.)."""
        if self._game_client:
            self._game_client.apply_events(events)

    def process_result(self, result: 'CommandResult'):
        """Process a command result with correct ordering: snapshot first, then events.

        This ensures:
        1. Game state is authoritative from snapshot
        2. Events provide animation data (arrows, damage numbers at correct positions)
        """
        if result.snapshot:
            self.sync_from_snapshot(result.snapshot)
        if result.events:
            self.apply_events(result.events)


# Future: Full NetworkMatchClient would add:
#   - async connect(host, port)
#   - async send_command(cmd) -> CommandResult
#   - async listen_for_updates() for server push
#
# class NetworkMatchClient:
#     """Network client that communicates with remote server."""
#
#     def __init__(self, host: str, port: int, player: int):
#         self.host = host
#         self.port = port
#         self.player = player
#         self.local_game: Optional[Game] = None  # Local copy for rendering
#         self.game_client: Optional[GameClient] = None
#
#     async def connect(self):
#         """Connect to server and get initial state."""
#         ...
#
#     async def send_command(self, cmd: Command) -> CommandResult:
#         """Send command to server, receive result."""
#         # Serialize cmd, send over network
#         # Receive result, deserialize
#         # Sync local state from snapshot
#         ...
#
#     def sync_from_snapshot(self, snapshot: Dict[str, Any]):
#         """Reconstruct local Game from server snapshot."""
#         self.local_game = Game.from_dict(snapshot)
#         self.game_client = GameClient(self.local_game, self.player)


def create_local_match() -> Tuple[MatchServer, LocalMatchClient, LocalMatchClient]:
    """Helper to create a local hotseat match.

    Returns:
        (server, client_p1, client_p2)
    """
    server = MatchServer()
    client_p1 = LocalMatchClient(server, player=1)
    client_p2 = LocalMatchClient(server, player=2)
    return server, client_p1, client_p2


def get_content_hash() -> str:
    """Get a combined hash of all game content for version verification.

    Used in network handshake to ensure client and server have matching:
    - Card definitions (stats, abilities)
    - Ability definitions (effects, triggers)

    If hashes don't match, client and server are incompatible.
    """
    from .card_database import get_card_database_hash
    from .abilities import get_ability_registry_hash
    import hashlib

    card_hash = get_card_database_hash()
    ability_hash = get_ability_registry_hash()

    # Combine hashes
    combined = f"{card_hash}:{ability_hash}"
    return hashlib.md5(combined.encode()).hexdigest()[:16]


def verify_content_hash(remote_hash: str) -> bool:
    """Verify that remote content hash matches local.

    Args:
        remote_hash: Content hash from remote server/client

    Returns:
        True if compatible, False if mismatch
    """
    return get_content_hash() == remote_hash
