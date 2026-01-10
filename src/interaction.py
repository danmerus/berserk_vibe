"""Unified interaction state for UI prompts and selections.

Interaction is a pure data object (no callbacks, no object references).
This makes it serializable for network play and replays.

Resolution of interactions is handled by Game.resolve_interaction().
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Tuple, Dict, Any


class InteractionKind(Enum):
    """Types of interactions that require user input."""
    # Combat-related
    SELECT_DEFENDER = auto()        # Choose defender to intercept attack
    SELECT_COUNTER_SHOT = auto()    # Choose target for counter shot
    SELECT_MOVEMENT_SHOT = auto()   # Choose target for movement shot (optional)

    # Ability targeting
    SELECT_ABILITY_TARGET = auto()  # Choose target for ability
    SELECT_VALHALLA_TARGET = auto() # Choose ally for Valhalla buff

    # Confirmations and choices
    CONFIRM_HEAL = auto()           # Yes/No heal confirmation
    CHOOSE_STENCH = auto()          # Tap or take damage choice
    CHOOSE_EXCHANGE = auto()        # Full attack or reduced attack choice

    # Counter/amount selection
    SELECT_COUNTERS = auto()        # Choose how many counters to use

    # Priority system (instant abilities)
    PRIORITY = auto()               # Priority phase for instant abilities


@dataclass
class Interaction:
    """Represents an active interaction requiring user input.

    This is a pure data object - fully serializable for network/replays.
    No Card object references, no callbacks.

    Resolution is handled by Game.resolve_interaction() based on kind.
    """
    kind: InteractionKind

    # Player who should respond to this interaction
    acting_player: Optional[int] = None     # 1 or 2, or None if either can act

    # Card IDs (not Card objects)
    actor_id: Optional[int] = None          # Card that initiated the interaction
    target_id: Optional[int] = None         # Target card (if applicable)

    # Valid selections (as IDs/positions)
    valid_positions: Tuple[int, ...] = ()   # Valid board positions to click
    valid_card_ids: Tuple[int, ...] = ()    # Valid card IDs to select

    # For numeric choices (counters, damage amounts, etc.)
    selected_amount: int = 0
    min_amount: int = 0
    max_amount: int = 0

    # Additional serializable context
    context: Dict[str, Any] = field(default_factory=dict)

    def can_select_position(self, pos: int) -> bool:
        """Check if a board position is valid for selection."""
        return pos in self.valid_positions

    def can_select_card_id(self, card_id: int) -> bool:
        """Check if a card ID is valid for selection."""
        return card_id in self.valid_card_ids

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
            InteractionKind.SELECT_DEFENDER,      # Can skip to not intercept
            InteractionKind.SELECT_MOVEMENT_SHOT, # Optional shot
        )

    @property
    def requires_amount(self) -> bool:
        """Check if this interaction requires choosing an amount."""
        return self.kind == InteractionKind.SELECT_COUNTERS

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for network/storage."""
        return {
            'kind': self.kind.name,
            'acting_player': self.acting_player,
            'actor_id': self.actor_id,
            'target_id': self.target_id,
            'valid_positions': list(self.valid_positions),
            'valid_card_ids': list(self.valid_card_ids),
            'selected_amount': self.selected_amount,
            'min_amount': self.min_amount,
            'max_amount': self.max_amount,
            'context': self.context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Interaction':
        """Deserialize from dictionary."""
        return cls(
            kind=InteractionKind[data['kind']],
            acting_player=data.get('acting_player'),
            actor_id=data.get('actor_id'),
            target_id=data.get('target_id'),
            valid_positions=tuple(data.get('valid_positions', [])),
            valid_card_ids=tuple(data.get('valid_card_ids', [])),
            selected_amount=data.get('selected_amount', 0),
            min_amount=data.get('min_amount', 0),
            max_amount=data.get('max_amount', 0),
            context=data.get('context', {}),
        )


# Factory functions for cleaner creation
def interaction_select_defender(
    attacker_id: int,
    target_id: int,
    valid_defender_ids: Tuple[int, ...],
    valid_positions: Tuple[int, ...]
) -> Interaction:
    """Create defender selection interaction."""
    return Interaction(
        kind=InteractionKind.SELECT_DEFENDER,
        actor_id=attacker_id,
        target_id=target_id,
        valid_card_ids=valid_defender_ids,
        valid_positions=valid_positions,
    )


def interaction_select_target(
    actor_id: int,
    ability_id: str,
    valid_positions: Tuple[int, ...],
    valid_card_ids: Tuple[int, ...] = ()
) -> Interaction:
    """Create ability target selection interaction."""
    return Interaction(
        kind=InteractionKind.SELECT_ABILITY_TARGET,
        actor_id=actor_id,
        valid_positions=valid_positions,
        valid_card_ids=valid_card_ids,
        context={'ability_id': ability_id},
    )


def interaction_counter_shot(
    shooter_id: int,
    valid_positions: Tuple[int, ...]
) -> Interaction:
    """Create counter shot target selection interaction."""
    return Interaction(
        kind=InteractionKind.SELECT_COUNTER_SHOT,
        actor_id=shooter_id,
        valid_positions=valid_positions,
    )


def interaction_movement_shot(
    shooter_id: int,
    valid_positions: Tuple[int, ...]
) -> Interaction:
    """Create movement shot target selection interaction (optional)."""
    return Interaction(
        kind=InteractionKind.SELECT_MOVEMENT_SHOT,
        actor_id=shooter_id,
        valid_positions=valid_positions,
    )


def interaction_valhalla(
    source_id: int,
    valid_positions: Tuple[int, ...],
    valid_card_ids: Tuple[int, ...]
) -> Interaction:
    """Create Valhalla target selection interaction."""
    return Interaction(
        kind=InteractionKind.SELECT_VALHALLA_TARGET,
        actor_id=source_id,
        valid_positions=valid_positions,
        valid_card_ids=valid_card_ids,
    )


def interaction_confirm_heal(
    healer_id: int,
    target_id: int,
    heal_amount: int
) -> Interaction:
    """Create heal confirmation interaction."""
    return Interaction(
        kind=InteractionKind.CONFIRM_HEAL,
        actor_id=healer_id,
        target_id=target_id,
        context={'heal_amount': heal_amount},
    )


def interaction_choose_stench(
    target_id: int,
    damage_amount: int
) -> Interaction:
    """Create stench choice interaction (tap or damage)."""
    return Interaction(
        kind=InteractionKind.CHOOSE_STENCH,
        target_id=target_id,
        context={'damage_amount': damage_amount},
    )


def interaction_choose_exchange(
    attacker_id: int,
    defender_id: int,
    full_damage: int,
    reduced_damage: int
) -> Interaction:
    """Create exchange choice interaction (full attack or reduced)."""
    return Interaction(
        kind=InteractionKind.CHOOSE_EXCHANGE,
        actor_id=attacker_id,
        target_id=defender_id,
        context={
            'full_damage': full_damage,
            'reduced_damage': reduced_damage,
        },
    )


def interaction_select_counters(
    card_id: int,
    min_counters: int,
    max_counters: int
) -> Interaction:
    """Create counter selection interaction."""
    return Interaction(
        kind=InteractionKind.SELECT_COUNTERS,
        actor_id=card_id,
        min_amount=min_counters,
        max_amount=max_counters,
    )


def interaction_priority(
    dice_context: Dict[str, Any]
) -> Interaction:
    """Create priority phase interaction."""
    return Interaction(
        kind=InteractionKind.PRIORITY,
        context=dice_context,
    )
