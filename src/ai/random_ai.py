"""Random AI - picks random valid actions.

This is the simplest AI implementation, useful for:
- Testing that the AI framework works
- Providing an easy opponent
- Baseline for comparing smarter AI implementations
"""
import random
from typing import Optional, TYPE_CHECKING

from .base import AIPlayer, AIAction

if TYPE_CHECKING:
    from ..match import MatchServer


class RandomAI(AIPlayer):
    """AI that picks random valid actions.

    Prioritizes:
    1. Handling interactions (must respond)
    2. Random action from available options
    """

    name = "Random"

    def __init__(self, server: 'MatchServer', player: int, seed: int = None):
        """Initialize random AI.

        Args:
            server: The match server
            player: Player number (1 or 2)
            seed: Optional random seed for reproducibility
        """
        super().__init__(server, player)
        self.rng = random.Random(seed)

    def choose_action(self) -> Optional[AIAction]:
        """Choose a random valid action."""
        actions = self.get_valid_actions()

        if not actions:
            return None

        return self.rng.choice(actions)
