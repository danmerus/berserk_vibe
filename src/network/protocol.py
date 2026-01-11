"""Network protocol: message types, framing, serialization.

Wire format:
    [4-byte big-endian length][JSON payload]

Message envelope:
    {
        "type": "join" | "cmd" | "update" | "ping" | "pong" | "error" | ...,
        "match_id": "ABC123",  (optional)
        "seq": 42,             (client_seq for commands, server_seq for updates)
        "payload": { ... }     (type-specific data)
    }
"""

import json
import struct
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..commands import Command, Event
    from ..match import CommandResult


class MessageType(Enum):
    """Network message types."""
    # Connection
    HELLO = auto()          # Client → Server: initial handshake
    WELCOME = auto()        # Server → Client: handshake response

    # Lobby
    CREATE_MATCH = auto()   # Client → Server: create new match
    JOIN_MATCH = auto()     # Client → Server: join existing match
    LEAVE_MATCH = auto()    # Client → Server: leave match
    LIST_MATCHES = auto()   # Client → Server: get open matches
    MATCH_LIST = auto()     # Server → Client: list of matches
    MATCH_CREATED = auto()  # Server → Client: match created, here's code
    MATCH_JOINED = auto()   # Server → Client: successfully joined
    MATCH_LEFT = auto()     # Server → Client: left match
    PLAYER_JOINED = auto()  # Server → Client: other player joined
    PLAYER_LEFT = auto()    # Server → Client: other player left

    # Game
    GAME_START = auto()     # Server → Client: game is starting, initial snapshot
    COMMAND = auto()        # Client → Server: game command
    UPDATE = auto()         # Server → Client: events + snapshot after command
    RESYNC = auto()         # Server → Client: full snapshot (on reconnect/desync)
    REQUEST_RESYNC = auto() # Client → Server: request full snapshot
    GAME_OVER = auto()      # Server → Client: game ended

    # Health
    PING = auto()           # Client → Server: keepalive
    PONG = auto()           # Server → Client: keepalive response

    # Errors
    ERROR = auto()          # Server → Client: error message


@dataclass
class Message:
    """Network message envelope."""
    type: MessageType
    match_id: Optional[str] = None
    seq: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_bytes(self) -> bytes:
        """Serialize message to bytes with length prefix."""
        data = {
            'type': self.type.name,
            'match_id': self.match_id,
            'seq': self.seq,
            'payload': self.payload,
        }
        json_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        length = len(json_bytes)
        return struct.pack('>I', length) + json_bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Message':
        """Deserialize message from JSON bytes (without length prefix)."""
        obj = json.loads(data.decode('utf-8'))
        return cls(
            type=MessageType[obj['type']],
            match_id=obj.get('match_id'),
            seq=obj.get('seq', 0),
            payload=obj.get('payload', {}),
        )


# =============================================================================
# FRAME READER/WRITER - handles length-prefixed framing over TCP
# =============================================================================

class FrameReader:
    """Reads length-prefixed frames from a stream.

    Usage:
        reader = FrameReader()
        reader.feed(data_from_socket)
        while True:
            frame = reader.get_frame()
            if frame is None:
                break
            message = Message.from_bytes(frame)
    """

    HEADER_SIZE = 4  # 4 bytes for length (big-endian uint32)
    MAX_FRAME_SIZE = 1024 * 1024  # 1MB max message size

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes):
        """Add received data to buffer."""
        self._buffer.extend(data)

    def get_frame(self) -> Optional[bytes]:
        """Extract next complete frame from buffer, or None if incomplete."""
        if len(self._buffer) < self.HEADER_SIZE:
            return None

        # Read length prefix
        length = struct.unpack('>I', self._buffer[:self.HEADER_SIZE])[0]

        if length > self.MAX_FRAME_SIZE:
            raise ValueError(f"Frame too large: {length} bytes")

        total_size = self.HEADER_SIZE + length
        if len(self._buffer) < total_size:
            return None  # Incomplete frame

        # Extract frame
        frame = bytes(self._buffer[self.HEADER_SIZE:total_size])
        del self._buffer[:total_size]
        return frame

    def get_message(self) -> Optional[Message]:
        """Get next complete message, or None if incomplete."""
        frame = self.get_frame()
        if frame is None:
            return None
        return Message.from_bytes(frame)


class FrameWriter:
    """Writes length-prefixed frames.

    Usage:
        writer = FrameWriter()
        data = writer.pack(message)
        socket.send(data)
    """

    @staticmethod
    def pack(message: Message) -> bytes:
        """Pack message into length-prefixed frame."""
        return message.to_bytes()


# =============================================================================
# MESSAGE BUILDERS - convenience functions for creating messages
# =============================================================================

def msg_hello(player_name: str, content_hash: str) -> Message:
    """Client hello with player name and content hash for version check."""
    return Message(
        type=MessageType.HELLO,
        payload={
            'player_name': player_name,
            'content_hash': content_hash,
        }
    )


def msg_welcome(player_id: str) -> Message:
    """Server welcome response."""
    return Message(
        type=MessageType.WELCOME,
        payload={'player_id': player_id}
    )


def msg_create_match(squad: List[str]) -> Message:
    """Create a new match with given squad."""
    return Message(
        type=MessageType.CREATE_MATCH,
        payload={'squad': squad}
    )


def msg_join_match(match_id: str, squad: List[str]) -> Message:
    """Join an existing match."""
    return Message(
        type=MessageType.JOIN_MATCH,
        match_id=match_id,
        payload={'squad': squad}
    )


def msg_match_created(match_id: str) -> Message:
    """Match created successfully."""
    return Message(
        type=MessageType.MATCH_CREATED,
        match_id=match_id,
    )


def msg_match_joined(match_id: str, player: int, snapshot: Dict[str, Any]) -> Message:
    """Successfully joined match."""
    return Message(
        type=MessageType.MATCH_JOINED,
        match_id=match_id,
        payload={
            'player': player,
            'snapshot': snapshot,
        }
    )


def msg_player_joined(player: int, player_name: str) -> Message:
    """Notify that another player joined."""
    return Message(
        type=MessageType.PLAYER_JOINED,
        payload={
            'player': player,
            'player_name': player_name,
        }
    )


def msg_game_start(snapshot: Dict[str, Any]) -> Message:
    """Game is starting."""
    return Message(
        type=MessageType.GAME_START,
        payload={'snapshot': snapshot}
    )


def msg_command(cmd: 'Command', seq: int) -> Message:
    """Send game command."""
    return Message(
        type=MessageType.COMMAND,
        seq=seq,
        payload={'command': cmd.to_dict()}
    )


def msg_update(result: 'CommandResult', seq: int, snapshot_hash: str) -> Message:
    """Game state update after command."""
    return Message(
        type=MessageType.UPDATE,
        seq=seq,
        payload={
            'accepted': result.accepted,
            'events': [e.to_dict() for e in result.events],
            'snapshot': result.snapshot,
            'snapshot_hash': snapshot_hash,
            'error': result.error,
        }
    )


def msg_resync(snapshot: Dict[str, Any], seq: int) -> Message:
    """Full resync snapshot."""
    return Message(
        type=MessageType.RESYNC,
        seq=seq,
        payload={'snapshot': snapshot}
    )


def msg_game_over(winner: int) -> Message:
    """Game ended."""
    return Message(
        type=MessageType.GAME_OVER,
        payload={'winner': winner}
    )


def msg_ping() -> Message:
    """Keepalive ping."""
    return Message(type=MessageType.PING)


def msg_pong() -> Message:
    """Keepalive pong."""
    return Message(type=MessageType.PONG)


def msg_error(error: str) -> Message:
    """Error message."""
    return Message(
        type=MessageType.ERROR,
        payload={'error': error}
    )


def msg_list_matches() -> Message:
    """Request list of open matches."""
    return Message(type=MessageType.LIST_MATCHES)


def msg_match_list(matches: List[Dict[str, Any]]) -> Message:
    """List of available matches."""
    return Message(
        type=MessageType.MATCH_LIST,
        payload={'matches': matches}
    )
