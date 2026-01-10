"""Squad builder for selecting cards before battle."""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .card_database import CARD_DATABASE
from .constants import Element


# Crystal amounts per player
PLAYER1_GOLD = 24
PLAYER1_SILVER = 22
PLAYER2_GOLD = 25
PLAYER2_SILVER = 23

# Limits
MAX_FLYING_COST = 15
HAND_SIZE = 15
MULLIGAN_COST = 1  # Gold crystals


@dataclass
class SquadBuilder:
    """Manages squad selection state."""

    player: int  # 1 or 2
    deck_cards: List[str] = field(default_factory=list)  # Full deck (card names)

    def __post_init__(self):
        """Initialize crystals and state."""
        # Set crystal amounts based on player
        if self.player == 1:
            self.gold = PLAYER1_GOLD
            self.silver = PLAYER1_SILVER
        else:
            self.gold = PLAYER2_GOLD
            self.silver = PLAYER2_SILVER

        # Current hand (раздача) - list of card names
        self.hand: List[str] = []

        # Selected squad - list of card names
        self.squad: List[str] = []

        # Track how crystals were spent on each card
        # card_index -> (gold_spent, silver_spent)
        self.squad_costs: List[Tuple[int, int]] = []

        # Remaining deck (after drawing hand)
        self.remaining_deck: List[str] = []

        # Mulligan count
        self.mulligan_count = 0

        # Draw initial hand
        self.draw_hand()

    def draw_hand(self):
        """Shuffle deck and draw HAND_SIZE cards."""
        # Put hand back into remaining deck
        all_cards = self.remaining_deck + self.hand
        if not all_cards:
            all_cards = self.deck_cards.copy()

        random.shuffle(all_cards)

        self.hand = all_cards[:HAND_SIZE]
        self.remaining_deck = all_cards[HAND_SIZE:]

    def mulligan(self) -> bool:
        """Mulligan (reshuffle and redraw) for 1 gold crystal.

        Returns True if successful, False if not enough gold.
        """
        if self.gold < MULLIGAN_COST:
            return False

        self.mulligan_count += 1

        # Reset crystals to initial values minus all mulligan costs
        if self.player == 1:
            self.gold = PLAYER1_GOLD - (self.mulligan_count * MULLIGAN_COST)
            self.silver = PLAYER1_SILVER
        else:
            self.gold = PLAYER2_GOLD - (self.mulligan_count * MULLIGAN_COST)
            self.silver = PLAYER2_SILVER

        # Return squad cards to hand first
        self.hand.extend(self.squad)
        self.squad.clear()
        self.squad_costs.clear()

        # Redraw
        self.draw_hand()
        return True

    def get_elements_in_squad(self) -> Set[Element]:
        """Get set of elements present in squad (excluding NEUTRAL)."""
        elements = set()
        for card_name in self.squad:
            stats = CARD_DATABASE.get(card_name)
            if stats and stats.element != Element.NEUTRAL:
                elements.add(stats.element)
        return elements

    def get_element_penalty(self) -> int:
        """Calculate gold crystal penalty for multiple elements."""
        elements = self.get_elements_in_squad()
        if len(elements) <= 1:
            return 0
        return len(elements) - 1

    def get_flying_cost(self) -> int:
        """Get total cost spent on flying creatures."""
        total = 0
        for i, card_name in enumerate(self.squad):
            stats = CARD_DATABASE.get(card_name)
            if stats and stats.is_flying:
                gold, silver = self.squad_costs[i]
                total += gold + silver
        return total

    def get_available_gold(self) -> int:
        """Get available gold crystals (penalty already paid when cards added)."""
        return self.gold

    def get_available_silver(self) -> int:
        """Get available silver crystals."""
        return self.silver

    def can_add_card(self, card_name: str) -> Tuple[bool, str]:
        """Check if a card can be added to squad.

        Returns (can_add, reason).
        """
        stats = CARD_DATABASE.get(card_name)
        if not stats:
            return False, "Карта не найдена"

        # Check unique constraint - only one copy of unique card in squad
        if stats.is_unique and card_name in self.squad:
            return False, "Уникальная карта уже в отряде"

        cost = stats.cost
        is_elite = stats.is_elite
        is_flying = stats.is_flying

        # Calculate available crystals
        available_gold = self.get_available_gold()
        available_silver = self.get_available_silver()

        # Check element penalty if adding new element
        new_element_penalty = 0
        if stats.element != Element.NEUTRAL:
            current_elements = self.get_elements_in_squad()
            if stats.element not in current_elements and len(current_elements) > 0:
                new_element_penalty = 1

        effective_gold = available_gold - new_element_penalty

        if is_elite:
            # Elite cards can only be paid with gold
            if effective_gold < cost:
                return False, "Недостаточно золотых кристаллов"
        else:
            # Common cards can use gold + silver
            if effective_gold + available_silver < cost:
                return False, "Недостаточно кристаллов"

        # Check flying limit
        if is_flying:
            current_flying_cost = self.get_flying_cost()
            if current_flying_cost + cost > MAX_FLYING_COST:
                return False, f"Лимит летающих ({MAX_FLYING_COST} кристаллов)"

        return True, ""

    def add_card(self, card_name: str, prefer_silver: bool = True) -> bool:
        """Add a card from hand to squad.

        Args:
            card_name: Name of card to add
            prefer_silver: If True, use silver crystals first for common cards

        Returns True if successful.
        """
        if card_name not in self.hand:
            return False

        can_add, _ = self.can_add_card(card_name)
        if not can_add:
            return False

        stats = CARD_DATABASE[card_name]
        cost = stats.cost
        is_elite = stats.is_elite

        # Calculate payment
        gold_to_spend = 0
        silver_to_spend = 0

        # Apply element penalty first
        new_element_penalty = 0
        if stats.element != Element.NEUTRAL:
            current_elements = self.get_elements_in_squad()
            if stats.element not in current_elements and len(current_elements) > 0:
                new_element_penalty = 1

        if is_elite:
            # Elite: all gold
            gold_to_spend = cost
        else:
            # Common: prefer silver or gold based on flag
            # Clamp to 0 to prevent negative values causing wrong calculations
            available_gold = max(0, self.get_available_gold() - new_element_penalty)
            available_silver = self.get_available_silver()

            if prefer_silver:
                silver_to_spend = min(cost, available_silver)
                gold_to_spend = cost - silver_to_spend
            else:
                gold_to_spend = min(cost, available_gold)
                silver_to_spend = cost - gold_to_spend

        # Apply penalty
        self.gold -= new_element_penalty

        # Pay for card
        self.gold -= gold_to_spend
        self.silver -= silver_to_spend

        # Move card from hand to squad
        self.hand.remove(card_name)
        self.squad.append(card_name)
        self.squad_costs.append((gold_to_spend, silver_to_spend))

        return True

    def remove_card(self, card_name: str) -> bool:
        """Remove a card from squad back to hand.

        Returns True if successful.
        """
        if card_name not in self.squad:
            return False

        idx = self.squad.index(card_name)
        gold_spent, silver_spent = self.squad_costs[idx]

        # Refund crystals
        self.gold += gold_spent
        self.silver += silver_spent

        # Check if removing this card removes an element penalty
        # (We need to recalculate after removal)
        old_elements = self.get_elements_in_squad()

        # Move card back to hand
        self.squad.pop(idx)
        self.squad_costs.pop(idx)
        self.hand.append(card_name)

        # Refund element penalty if applicable
        stats = CARD_DATABASE.get(card_name)
        if stats and stats.element != Element.NEUTRAL:
            new_elements = self.get_elements_in_squad()
            if stats.element in old_elements and stats.element not in new_elements:
                # This element is no longer in squad, refund penalty
                if len(old_elements) > 1:
                    self.gold += 1

        return True

    def get_hand_cards(self) -> List[Tuple[str, bool, str]]:
        """Get hand cards with add eligibility.

        Returns list of (card_name, can_add, reason).
        """
        result = []
        for card_name in self.hand:
            can_add, reason = self.can_add_card(card_name)
            result.append((card_name, can_add, reason))

        # Sort by cost descending, then by name
        def sort_key(item):
            card_name = item[0]
            stats = CARD_DATABASE[card_name]
            return (-stats.cost, card_name)

        return sorted(result, key=sort_key)

    def get_squad_cards(self) -> List[Tuple[str, int, int]]:
        """Get squad cards with crystal costs.

        Returns list of (card_name, gold_spent, silver_spent).
        """
        result = []
        for i, card_name in enumerate(self.squad):
            gold, silver = self.squad_costs[i]
            result.append((card_name, gold, silver))

        # Sort by cost descending, then by name
        def sort_key(item):
            card_name = item[0]
            stats = CARD_DATABASE[card_name]
            return (-stats.cost, card_name)

        return sorted(result, key=sort_key)

    def get_squad_total_cost(self) -> Tuple[int, int]:
        """Get total crystals spent on squad (gold, silver)."""
        total_gold = sum(g for g, s in self.squad_costs)
        total_silver = sum(s for g, s in self.squad_costs)
        return total_gold, total_silver

    def is_valid(self) -> bool:
        """Check if squad is valid (at least 1 card)."""
        return len(self.squad) > 0

    def finalize(self) -> List[str]:
        """Finalize squad selection and return squad card names."""
        # Return unused hand cards to deck (not needed for game, but clean)
        return self.squad.copy()
