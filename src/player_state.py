"""Player state management for network-ready game architecture.

PlayerState encapsulates all player-specific state that would be
maintained per-client in a networked game.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .card import Card


@dataclass
class PlayerState:
    """Per-player state container.

    In a networked game:
    - Server maintains authoritative PlayerState for each player
    - Client has local PlayerState for UI responsiveness
    - Commands from client update server state
    - Events from server sync client state

    In hotseat mode:
    - Game maintains two PlayerState instances
    - current_player determines which is active
    """
    player: int  # 1 or 2

    # Cards in hand (during SETUP phase)
    hand: List[Card] = field(default_factory=list)

    # Selection state (UI state, not game state)
    selected_card_id: Optional[int] = None
    valid_moves: List[int] = field(default_factory=list)
    valid_attacks: List[int] = field(default_factory=list)
    attack_mode: bool = False

    def clear_selection(self):
        """Clear all selection state."""
        self.selected_card_id = None
        self.valid_moves = []
        self.valid_attacks = []
        self.attack_mode = False

    def select_card(self, card_id: int, moves: List[int] = None, attacks: List[int] = None):
        """Select a card and set valid actions."""
        self.selected_card_id = card_id
        self.valid_moves = moves or []
        self.valid_attacks = attacks or []
        self.attack_mode = False

    def toggle_attack_mode(self, attacks: List[int] = None) -> bool:
        """Toggle attack mode. Returns new state."""
        if self.attack_mode:
            self.attack_mode = False
            self.valid_attacks = []
        else:
            self.attack_mode = True
            self.valid_attacks = attacks or []
        return self.attack_mode

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for network transmission."""
        return {
            'player': self.player,
            'hand_ids': [c.id for c in self.hand],
            'selected_card_id': self.selected_card_id,
            'valid_moves': self.valid_moves,
            'valid_attacks': self.valid_attacks,
            'attack_mode': self.attack_mode,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], cards_by_id: Dict[int, Card] = None) -> 'PlayerState':
        """Deserialize from dictionary.

        Args:
            data: Serialized state
            cards_by_id: Optional mapping of card IDs to Card objects for hand reconstruction
        """
        state = cls(player=data['player'])
        state.selected_card_id = data.get('selected_card_id')
        state.valid_moves = data.get('valid_moves', [])
        state.valid_attacks = data.get('valid_attacks', [])
        state.attack_mode = data.get('attack_mode', False)

        # Reconstruct hand if cards_by_id provided
        if cards_by_id:
            state.hand = [cards_by_id[cid] for cid in data.get('hand_ids', []) if cid in cards_by_id]

        return state
