"""AI module for computer opponents.

Provides AI players that can play the game autonomously.
AI players use filtered game state (can't see hidden cards).

Usage:
    from src.ai import RuleBasedAI
    from src.match import MatchServer

    server = MatchServer()
    server.setup_game()

    ai = RuleBasedAI(server, player=2)

    # In game loop:
    while game.phase != GamePhase.GAME_OVER:
        if ai.is_my_turn():
            ai.take_turn()
        else:
            # Human player's turn
            ...
"""

from .base import AIPlayer, AIAction
from .random_ai import RandomAI
from .rule_based_ai import RuleBasedAI
from .squad_ai import (
    score_card,
    select_squad_greedy,
    select_squad_optimized,
    place_cards_heuristic,
    build_ai_squad,
)

__all__ = [
    'AIPlayer', 'AIAction', 'RandomAI', 'RuleBasedAI',
    'score_card', 'select_squad_greedy', 'select_squad_optimized',
    'place_cards_heuristic', 'build_ai_squad',
]
