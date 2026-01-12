"""Player session and connection state management."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from enum import Enum, auto

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter


class SessionState(Enum):
    """Player session states."""
    CONNECTED = auto()      # Just connected, not yet authenticated
    AUTHENTICATED = auto()  # Hello/welcome complete
    IN_LOBBY = auto()       # In lobby, not in match
    IN_MATCH = auto()       # In a match
    DISCONNECTED = auto()   # Connection lost


@dataclass
class PlayerSession:
    """Represents a connected player's session.

    Tracks connection state, player info, and handles communication.
    """
    reader: 'StreamReader'
    writer: 'StreamWriter'
    player_id: str = ""
    player_name: str = ""
    state: SessionState = SessionState.CONNECTED

    # Match info (set when in match)
    match_id: Optional[str] = None
    player_number: int = 0  # 1 or 2

    # Sequence tracking for idempotency
    last_client_seq: int = 0
    server_seq: int = 0

    # Heartbeat
    last_ping: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)

    # Address for logging
    _address: str = ""

    def __post_init__(self):
        peername = self.writer.get_extra_info('peername')
        if peername:
            self._address = f"{peername[0]}:{peername[1]}"

    @property
    def address(self) -> str:
        return self._address

    @property
    def is_alive(self) -> bool:
        """Check if connection is still alive based on heartbeat."""
        return time.time() - self.last_pong < 15.0  # 15 second timeout

    def next_server_seq(self) -> int:
        """Get next server sequence number."""
        self.server_seq += 1
        return self.server_seq

    def is_duplicate_command(self, client_seq: int) -> bool:
        """Check if command is duplicate (already processed)."""
        if client_seq <= self.last_client_seq:
            return True
        self.last_client_seq = client_seq
        return False

    async def send(self, data: bytes):
        """Send data to client."""
        try:
            self.writer.write(data)
            await self.writer.drain()
        except (ConnectionError, OSError):
            self.state = SessionState.DISCONNECTED
            raise

    async def close(self):
        """Close the connection."""
        self.state = SessionState.DISCONNECTED
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


@dataclass
class MatchSession:
    """Represents an active match between two players.

    Holds the MatchServer and player sessions.
    """
    match_id: str
    host_session: Optional[PlayerSession] = None
    guest_session: Optional[PlayerSession] = None
    server: Optional['MatchServer'] = None  # type: ignore

    # Match state
    is_started: bool = False
    is_finished: bool = False
    winner: int = 0

    # Ready states
    host_ready: bool = False
    guest_ready: bool = False

    # Squad selections (stored until both ready)
    host_squad: list = field(default_factory=list)
    guest_squad: list = field(default_factory=list)
    host_placed_cards: list = field(default_factory=list)
    guest_placed_cards: list = field(default_factory=list)

    # Creation time for cleanup
    created_at: float = field(default_factory=time.time)

    # Draw offer state (which player offered, 0 = no offer)
    draw_offered_by: int = 0

    @property
    def is_full(self) -> bool:
        """Check if match has both players."""
        return self.host_session is not None and self.guest_session is not None

    @property
    def is_empty(self) -> bool:
        """Check if match has no players."""
        return self.host_session is None and self.guest_session is None

    @property
    def player_count(self) -> int:
        """Number of connected players."""
        count = 0
        if self.host_session and self.host_session.state != SessionState.DISCONNECTED:
            count += 1
        if self.guest_session and self.guest_session.state != SessionState.DISCONNECTED:
            count += 1
        return count

    def get_session(self, player: int) -> Optional[PlayerSession]:
        """Get session for player number (1 or 2)."""
        if player == 1:
            return self.host_session
        elif player == 2:
            return self.guest_session
        return None

    def get_opponent_session(self, player: int) -> Optional[PlayerSession]:
        """Get opponent's session."""
        return self.get_session(3 - player)  # 1 -> 2, 2 -> 1

    def remove_player(self, session: PlayerSession):
        """Remove a player from the match."""
        if self.host_session == session:
            self.host_session = None
        elif self.guest_session == session:
            self.guest_session = None

    @property
    def both_ready(self) -> bool:
        """Check if both players are ready."""
        return self.host_ready and self.guest_ready

    def set_ready(self, player: int, ready: bool = True):
        """Set a player's ready state."""
        if player == 1:
            self.host_ready = ready
        elif player == 2:
            self.guest_ready = ready

    def is_ready(self, player: int) -> bool:
        """Check if a player is ready."""
        if player == 1:
            return self.host_ready
        elif player == 2:
            return self.guest_ready
        return False

    def to_dict(self) -> dict:
        """Serialize for match list."""
        return {
            'match_id': self.match_id,
            'host_name': self.host_session.player_name if self.host_session else None,
            'player_count': self.player_count,
            'is_started': self.is_started,
        }
