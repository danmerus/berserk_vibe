"""Unified interaction state for UI prompts and selections."""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional, Sequence, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .card import Card


class InteractionKind(Enum):
    """Types of interactions that require user input."""
    SELECT_DEFENDER = auto()       # Choose defender to intercept attack
    SELECT_ABILITY_TARGET = auto() # Choose target for ability
    SELECT_COUNTER_SHOT = auto()   # Choose target for counter shot
    SELECT_MOVEMENT_SHOT = auto()  # Choose target for movement shot (optional)
    SELECT_VALHALLA_TARGET = auto() # Choose ally for Valhalla buff
    CONFIRM_HEAL = auto()          # Yes/No heal confirmation
    CHOOSE_STENCH = auto()         # Tap or take damage choice
    CHOOSE_EXCHANGE = auto()       # Full attack or reduced attack choice
    PRIORITY = auto()              # Priority phase for instant abilities
    SELECT_COUNTERS = auto()       # Choose how many counters to use


@dataclass
class Interaction:
    """Represents an active interaction requiring user input.

    Consolidates all the various awaiting_*/pending_* flags into a single
    state object that can be easily checked and managed.
    """
    kind: InteractionKind

    # Context data - varies by interaction type
    actor: Optional['Card'] = None         # Card that initiated the interaction
    target: Optional['Card'] = None        # Target card (if applicable)
    valid_positions: Sequence[int] = field(default_factory=list)  # Valid board positions to click
    valid_cards: Sequence['Card'] = field(default_factory=list)   # Valid cards to select

    # For numeric choices (counters, damage amounts, etc.)
    amount: int = 0
    min_amount: int = 0
    max_amount: int = 0

    # Additional context stored as dict for flexibility
    context: dict = field(default_factory=dict)

    # Callbacks - set by Game when creating interaction
    on_select_position: Optional[Callable[[int], bool]] = None
    on_select_card: Optional[Callable[['Card'], bool]] = None
    on_confirm: Optional[Callable[[bool], bool]] = None  # For yes/no choices
    on_cancel: Optional[Callable[[], None]] = None

    def can_select_position(self, pos: int) -> bool:
        """Check if a board position is valid for selection."""
        return pos in self.valid_positions

    def can_select_card(self, card: 'Card') -> bool:
        """Check if a card is valid for selection."""
        return card in self.valid_cards

    @property
    def is_board_selection(self) -> bool:
        """Check if this interaction requires clicking a board position."""
        return self.kind in (
            InteractionKind.SELECT_DEFENDER,
            InteractionKind.SELECT_ABILITY_TARGET,
            InteractionKind.SELECT_COUNTER_SHOT,
            InteractionKind.SELECT_MOVEMENT_SHOT,
            InteractionKind.SELECT_VALHALLA_TARGET,
        )

    @property
    def is_choice(self) -> bool:
        """Check if this interaction is a binary choice (yes/no, etc.)."""
        return self.kind in (
            InteractionKind.CONFIRM_HEAL,
            InteractionKind.CHOOSE_STENCH,
            InteractionKind.CHOOSE_EXCHANGE,
        )

    @property
    def is_skippable(self) -> bool:
        """Check if this interaction can be skipped/cancelled."""
        return self.kind in (
            InteractionKind.SELECT_DEFENDER,  # Can skip to not intercept
            InteractionKind.SELECT_MOVEMENT_SHOT,  # Optional shot
        )
