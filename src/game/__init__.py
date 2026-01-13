"""
Game package - Game state management and logic.

The Game class is split into multiple mixins for maintainability:
- base.py: Core initialization, serialization, events
- helpers.py: Utility methods (positions, formations, damage bonuses)
- setup.py: Game setup, placement, turn management
- combat.py: Combat system, damage calculation, dice
- abilities.py: Ability usage, targeting, ranged/magic attacks
- triggers.py: Combat triggers (counter shot, heal, stench)
- priority.py: Priority system, instant abilities
- movement.py: Card movement, flyer attacks
- commands.py: Command processing

The Game class inherits from all mixins and GameBase.
"""
from typing import Optional, List, TYPE_CHECKING

# Import base and mixins
from .base import GameBase, CombatResult, DiceContext, StackItem
from .helpers import HelpersMixin
from .setup import SetupMixin
from .combat import CombatMixin
from .abilities import AbilitiesMixin
from .triggers import TriggersMixin
from .priority import PriorityMixin
from .movement import MovementMixin
from .commands import CommandsMixin

if TYPE_CHECKING:
    from ..card import Card


# Re-export for backward compatibility
__all__ = ['Game', 'CombatResult', 'DiceContext', 'StackItem']


class Game(
    GameBase,
    HelpersMixin,
    SetupMixin,
    CombatMixin,
    AbilitiesMixin,
    TriggersMixin,
    PriorityMixin,
    MovementMixin,
    CommandsMixin
):
    """Main game state and logic - combines all functionality via mixins."""

    def __init__(self):
        # Initialize base class first (sets up core state)
        super().__init__()
