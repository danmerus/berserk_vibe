"""Player state management for network-ready game architecture.

PlayerState encapsulates server-side player-specific state.
UI state (selection, valid moves/attacks) is managed client-side by UIState.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any

from .card import Card


@dataclass
class PlayerState:
    """Per-player server state container.

    This contains only authoritative game state, not UI state.
    UI state (selection, valid moves, attack mode) is in UIState (client-side).
    """
    player: int  # 1 or 2

    # Cards in hand (during SETUP phase)
    hand: List[Card] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for network transmission."""
        return {
            'player': self.player,
            'hand_ids': [c.id for c in self.hand],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], cards_by_id: Dict[int, Card] = None) -> 'PlayerState':
        """Deserialize from dictionary.

        Args:
            data: Serialized state
            cards_by_id: Optional mapping of card IDs to Card objects for hand reconstruction
        """
        state = cls(player=data['player'])

        # Reconstruct hand if cards_by_id provided
        if cards_by_id:
            state.hand = [cards_by_id[cid] for cid in data.get('hand_ids', []) if cid in cards_by_id]

        return state
