"""Headless AI vs AI simulation for testing and benchmarking.

Usage:
    python simulate.py                    # Run 1 game with AI squad building
    python simulate.py -n 100             # Run 100 games
    python simulate.py -p1 random -p2 rulebased  # Specific AI types
    python simulate.py -n 100 --verbose   # Show each game result
    python simulate.py --no-squad         # Use auto-placement instead of AI squads
"""

import argparse
import random
import time
from typing import Tuple, Dict, Any, List
from dataclasses import dataclass

from src.match import MatchServer
from src.ai import RandomAI, RuleBasedAI, build_ai_squad
from src.card import create_card
from src.card_database import CARD_DATABASE
from src.squad_builder import SquadBuilder, HAND_SIZE
from src.constants import GamePhase


@dataclass
class GameResult:
    """Result of a single game."""
    winner: int  # 1 or 2
    turns: int
    duration: float  # seconds
    p1_cards_remaining: int
    p2_cards_remaining: int


def create_ai(ai_type: str, server: MatchServer, player: int):
    """Create AI player of specified type."""
    if ai_type == 'random':
        return RandomAI(server, player)
    elif ai_type == 'rulebased':
        return RuleBasedAI(server, player)
    else:
        raise ValueError(f"Unknown AI type: {ai_type}")


def create_random_deck(rng: random.Random, size: int = 40) -> List[str]:
    """Create a random deck from available cards.

    Args:
        rng: Random number generator
        size: Number of cards in the deck

    Returns:
        List of card names
    """
    all_cards = list(CARD_DATABASE.keys())
    # Create deck with duplicates allowed (up to 4 copies per card)
    deck = []
    card_counts = {}

    while len(deck) < size:
        card = rng.choice(all_cards)
        count = card_counts.get(card, 0)
        if count < 4:  # Max 4 copies per card
            deck.append(card)
            card_counts[card] = count + 1

    return deck


def setup_game_with_ai_squads(server: MatchServer, seed: int = None,
                               debug: bool = False) -> None:
    """Set up game with AI-built squads.

    1. Creates random decks for both players
    2. Draws 15 cards as hand for each
    3. Uses AI to select squads and place cards
    """
    rng = random.Random(seed)

    # Create random decks
    deck_p1 = create_random_deck(rng)
    deck_p2 = create_random_deck(rng)

    if debug:
        print(f"  P1 deck: {len(deck_p1)} cards")
        print(f"  P2 deck: {len(deck_p2)} cards")

    # Build squads using AI
    squad_names_p1, placement_p1 = build_ai_squad(player=1, deck_cards=deck_p1)
    squad_names_p2, placement_p2 = build_ai_squad(player=2, deck_cards=deck_p2)

    if debug:
        print(f"  P1 squad: {len(squad_names_p1)} cards - {squad_names_p1}")
        print(f"  P2 squad: {len(squad_names_p2)} cards - {squad_names_p2}")
        print(f"  P1 positions: {sorted(placement_p1.keys())}")
        print(f"  P2 positions: {sorted(placement_p2.keys())}")

    # Create Game and set up with placed cards
    from src.game import Game
    game = Game()
    server.game = game

    # Collect Card objects from placement dicts
    p1_cards = list(placement_p1.values())
    p2_cards = list(placement_p2.values())

    # Initialize game with placed cards
    game.setup_game_with_placement(p1_cards, p2_cards)


def run_game(p1_type: str = 'rulebased', p2_type: str = 'rulebased',
             max_turns: int = 500, seed: int = None, debug: bool = False,
             use_squad_ai: bool = False) -> GameResult:
    """Run a single AI vs AI game.

    Args:
        p1_type: AI type for player 1 ('random' or 'rulebased')
        p2_type: AI type for player 2 ('random' or 'rulebased')
        max_turns: Maximum turns before declaring draw
        seed: Random seed for reproducibility
        use_squad_ai: If True, use AI squad building instead of auto_place_for_testing

    Returns:
        GameResult with winner, turns, duration, etc.
    """
    start_time = time.time()

    # Set up server and game
    server = MatchServer()

    if use_squad_ai:
        # Use AI squad building for diverse games
        setup_game_with_ai_squads(server, seed=seed, debug=debug)
    else:
        # Use standard auto-placement for testing
        server.setup_game()
        server.game.auto_place_for_testing()

    # Create AIs
    ai1 = create_ai(p1_type, server, player=1)
    ai2 = create_ai(p2_type, server, player=2)

    game = server.game
    action_count = 0
    no_action_count = 0

    if debug:
        print(f"  Game phase: {game.phase}, Turn: {game.turn_number}, Current player: {game.current_player}")

    # Game loop
    while game.phase == GamePhase.MAIN and game.turn_number < max_turns:
        # Find which AI can act
        ai = None
        if ai1.is_my_turn():
            ai = ai1
        elif ai2.is_my_turn():
            ai = ai2

        if ai is None:
            # Neither AI can act - might be stuck
            no_action_count += 1
            if debug and no_action_count == 1:
                print(f"  No AI can act! Phase: {game.phase}, Turn: {game.turn_number}, "
                      f"Current: P{game.current_player}, Interaction: {game.interaction}, "
                      f"Priority: {game.priority_phase}, PriorityPlayer: {game.priority_player}")
                print(f"    ai1.is_my_turn(): {ai1.is_my_turn()}, ai2.is_my_turn(): {ai2.is_my_turn()}")
                if game.interaction:
                    print(f"    Interaction kind: {game.interaction.kind}, acting: {game.interaction.acting_player}")
            if no_action_count > 100:
                if debug:
                    print(f"  Breaking: neither AI can act after {no_action_count} checks")
                break
            continue

        no_action_count = 0

        # Get and execute action
        action = ai.choose_action()
        if action is None:
            # No valid actions - try the other AI
            if debug:
                print(f"  AI P{ai.player} returned None action")
            continue

        if debug and (action_count < 20 or action_count % 1000 == 0):
            print(f"  #{action_count} (T{game.turn_number}): P{ai.player} -> {action.command.type.name} - {action.description}")

        result = server.apply(action.command)
        action_count += 1

        # Safety check for infinite loops
        if action_count > 10000:
            if debug:
                print(f"  Breaking: action count exceeded 10000")
            break

    duration = time.time() - start_time

    # Determine winner
    winner = game.board.check_winner()
    if winner is None:
        winner = 0  # Draw or timeout

    # Count remaining cards
    p1_cards = len(game.board.get_all_cards(1))
    p2_cards = len(game.board.get_all_cards(2))

    return GameResult(
        winner=winner,
        turns=game.turn_number,
        duration=duration,
        p1_cards_remaining=p1_cards,
        p2_cards_remaining=p2_cards
    )


def run_simulation(n_games: int = 1, p1_type: str = 'rulebased',
                   p2_type: str = 'rulebased', verbose: bool = False,
                   debug: bool = False, use_squad_ai: bool = False) -> Dict[str, Any]:
    """Run multiple games and collect statistics.

    Args:
        n_games: Number of games to run
        p1_type: AI type for player 1
        p2_type: AI type for player 2
        verbose: Print each game result
        debug: Print detailed debug info for each action
        use_squad_ai: Use AI squad building for diverse games

    Returns:
        Dictionary with statistics
    """
    results = []
    p1_wins = 0
    p2_wins = 0
    draws = 0
    total_turns = 0
    total_duration = 0.0

    mode_str = "AI squad building" if use_squad_ai else "auto-placement"
    print(f"Running {n_games} game(s): {p1_type} (P1) vs {p2_type} (P2) [{mode_str}]")
    print("-" * 50)

    for i in range(n_games):
        game_seed = i if use_squad_ai else None
        if verbose or debug:
            print(f"Game {i+1} (seed={game_seed}):")
        result = run_game(p1_type, p2_type, debug=debug, use_squad_ai=use_squad_ai, seed=game_seed)
        results.append(result)

        if result.winner == 1:
            p1_wins += 1
        elif result.winner == 2:
            p2_wins += 1
        else:
            draws += 1

        total_turns += result.turns
        total_duration += result.duration

        if verbose:
            winner_str = f"P{result.winner}" if result.winner else "Draw"
            print(f"Game {i+1}: {winner_str} in {result.turns} turns "
                  f"({result.duration:.3f}s) - Cards: P1={result.p1_cards_remaining}, P2={result.p2_cards_remaining}")

    # Calculate statistics
    stats = {
        'games': n_games,
        'p1_type': p1_type,
        'p2_type': p2_type,
        'p1_wins': p1_wins,
        'p2_wins': p2_wins,
        'draws': draws,
        'p1_win_rate': p1_wins / n_games * 100,
        'p2_win_rate': p2_wins / n_games * 100,
        'avg_turns': total_turns / n_games,
        'avg_duration': total_duration / n_games,
        'total_duration': total_duration,
        'games_per_second': n_games / total_duration if total_duration > 0 else 0,
    }

    # Print summary
    print("-" * 50)
    print(f"Results after {n_games} game(s):")
    print(f"  P1 ({p1_type}): {p1_wins} wins ({stats['p1_win_rate']:.1f}%)")
    print(f"  P2 ({p2_type}): {p2_wins} wins ({stats['p2_win_rate']:.1f}%)")
    print(f"  Draws: {draws}")
    print(f"  Avg turns: {stats['avg_turns']:.1f}")
    print(f"  Avg duration: {stats['avg_duration']*1000:.1f}ms per game")
    print(f"  Speed: {stats['games_per_second']:.1f} games/second")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Run AI vs AI simulations')
    parser.add_argument('-n', '--games', type=int, default=1,
                        help='Number of games to run (default: 1)')
    parser.add_argument('-p1', '--player1', type=str, default='rulebased',
                        choices=['random', 'rulebased'],
                        help='AI type for player 1 (default: rulebased)')
    parser.add_argument('-p2', '--player2', type=str, default='rulebased',
                        choices=['random', 'rulebased'],
                        help='AI type for player 2 (default: rulebased)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show each game result')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Show detailed debug info')
    parser.add_argument('--no-squad', action='store_true',
                        help='Disable AI squad building (use auto-placement instead)')

    args = parser.parse_args()

    run_simulation(
        n_games=args.games,
        p1_type=args.player1,
        p2_type=args.player2,
        verbose=args.verbose,
        debug=args.debug,
        use_squad_ai=not args.no_squad
    )


if __name__ == '__main__':
    main()
