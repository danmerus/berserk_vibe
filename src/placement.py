"""Placement phase logic for initial card placement."""
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict

from .card import Card, CardStats, create_card
from .card_database import CARD_DATABASE


# Placement zones by priority for each player
# Player 1: bottom side (rows 0-2, positions 0-14)
P1_ZONE_1 = {1, 2, 3, 6, 7, 8, 11, 12, 13}  # 3x3 center
P1_ZONE_2 = {5, 0, 9, 4}  # Front + middle row edges
P1_ZONE_3 = {10, 14}  # Back row edges

# Player 2: top side (rows 3-5, positions 15-29)
P2_ZONE_1 = {15, 16, 17, 18, 19, 21, 22, 23, 26, 27, 28}  # Front row + center of others
P2_ZONE_2 = {20, 24, 25, 29}  # Edges of back rows


@dataclass
class PlacementState:
    """Manages placement phase state."""

    player: int  # 1 or 2
    squad_cards: List[str] = field(default_factory=list)  # Card names to place

    def __post_init__(self):
        """Initialize placement state."""
        # Cards waiting to be placed (as Card objects)
        self.unplaced_cards: List[Card] = []
        # Use player-based offset for globally unique IDs (P1: 1-100, P2: 101-200)
        # Start at 1 to avoid ID 0 being treated as falsy in truthiness checks
        base_id = (self.player - 1) * 100 + 1

        # Create card objects from squad names
        for i, name in enumerate(self.squad_cards):
            card = create_card(name, player=self.player, card_id=base_id + i)
            self.unplaced_cards.append(card)

        # Sort by cost descending for display
        self.unplaced_cards.sort(key=lambda c: -c.stats.cost)

        # Placed cards: position -> Card
        self.placed_cards: Dict[int, Card] = {}

        # Currently dragging
        self.dragging_card: Optional[Card] = None
        self.drag_offset_x: int = 0
        self.drag_offset_y: int = 0

    def get_legal_positions(self) -> Set[int]:
        """Get set of positions where cards can be placed."""
        occupied = set(self.placed_cards.keys())

        if self.player == 1:
            # Check zones in priority order
            zone1_available = P1_ZONE_1 - occupied
            if zone1_available:
                return zone1_available

            zone2_available = P1_ZONE_2 - occupied
            if zone2_available:
                return zone2_available

            return P1_ZONE_3 - occupied
        else:
            # Player 2
            zone1_available = P2_ZONE_1 - occupied
            if zone1_available:
                return zone1_available

            return P2_ZONE_2 - occupied

    def get_all_player_positions(self) -> Set[int]:
        """Get all positions on player's side."""
        if self.player == 1:
            return set(range(15))  # 0-14
        else:
            return set(range(15, 30))  # 15-29

    def get_opponent_positions(self) -> Set[int]:
        """Get all positions on opponent's side (for showing unplaced cards)."""
        if self.player == 1:
            return set(range(15, 30))  # 15-29
        else:
            return set(range(15))  # 0-14

    def place_card(self, card: Card, position: int) -> bool:
        """Place a card at a position.

        Returns True if successful.
        """
        if position not in self.get_legal_positions():
            return False

        if card not in self.unplaced_cards:
            return False

        self.unplaced_cards.remove(card)
        self.placed_cards[position] = card
        card.position = position
        return True

    def unplace_card(self, position: int) -> Optional[Card]:
        """Remove a card from a position and return it to unplaced.

        Returns the card if successful, None otherwise.
        """
        if position not in self.placed_cards:
            return None

        card = self.placed_cards.pop(position)
        card.position = None
        self.unplaced_cards.append(card)
        # Re-sort by cost
        self.unplaced_cards.sort(key=lambda c: -c.stats.cost)
        return card

    def start_drag(self, card: Card, offset_x: int, offset_y: int):
        """Start dragging a card."""
        self.dragging_card = card
        self.drag_offset_x = offset_x
        self.drag_offset_y = offset_y

    def stop_drag(self):
        """Stop dragging."""
        self.dragging_card = None

    def is_complete(self) -> bool:
        """Check if all cards have been placed."""
        return len(self.unplaced_cards) == 0

    def get_placed_cards(self) -> List[Card]:
        """Get all placed cards."""
        return list(self.placed_cards.values())

    def finalize(self) -> List[Card]:
        """Finalize placement and return all cards with positions set."""
        return self.get_placed_cards()
