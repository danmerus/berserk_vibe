"""Utility-based AI with lookahead for movement decisions.

This AI uses exhaustive movement combination search:
1. MOVEMENT PHASE (deterministic, exhaustive)
   - Generate all valid movement combinations for all moveable cards
   - Prune dominated positions (blocked cells, obviously bad moves)
   - Score each board configuration
   - Keep top N positions (beam search)

2. ATTACK PHASE (per top position)
   - For each top position, evaluate attack options
   - Use expected damage for scoring

3. COMBINE
   - Total utility = position score + best attack sequence score
   - Pick the move sequence leading to best combined outcome
"""
import random
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field
from copy import deepcopy
from itertools import product

from .base import AIPlayer, AIAction
from ..game import Game
from ..card import Card
from ..board import Board

# Constants for evaluation weights
WEIGHTS = {
    'material': 10.0,        # Card value (cost)
    'hp_ratio': 5.0,         # HP percentage
    'formation': 15.0,       # Formation bonus active
    'position_ability': 12.0, # Row/column ability active
    'attack_opportunity': 8.0, # Can attack enemy
    'threat': -6.0,          # Enemy can attack us
    'advancement': 3.0,      # Row advancement toward enemy
    'center_control': 2.0,   # Center column control
    'kill_potential': 20.0,  # Can kill enemy this turn
    'row_placement': 5.0,    # Correct row for card type
}


def calculate_expected_damage(attacker_attack: tuple, defender_tapped: bool = False) -> float:
    """Calculate expected damage from an attack based on exact dice probabilities.

    Based on _get_opposed_tiers from combat.py:
    roll_diff = atk_roll - def_roll (each d6)

    Probabilities for each diff (out of 36):
    diff >= +5: 1/36  -> Strong attack (tier 2)
    diff == +4: 2/36  -> Strong attack (tier 2), exchange possible
    diff == +3: 3/36  -> Medium attack (tier 1)
    diff == +2: 4/36  -> Medium attack (tier 1), exchange possible
    diff == +1: 5/36  -> Weak attack (tier 0)
    diff == 0:  6/36  -> 4/36 weak attack (atk_roll 1-4), 2/36 no attack (atk_roll 5-6)
    diff == -1: 5/36  -> Weak attack (tier 0)
    diff == -2: 4/36  -> No damage
    diff == -3: 3/36  -> No damage (defender counter)
    diff == -4: 2/36  -> Weak attack (tier 0), exchange
    diff <= -5: 1/36  -> No damage (defender counter)

    Against tapped (no counter): Only attacker rolls d6
    - 1-2: Weak (tier 0), 3-4: Medium (tier 1), 5-6: Strong (tier 2)
    """
    weak, medium, strong = attacker_attack[0], attacker_attack[1], attacker_attack[2]

    if defender_tapped:
        # Against tapped: 1/3 each tier
        return (weak + medium + strong) / 3.0

    # Normal opposed combat based on exact _get_opposed_tiers logic
    # Strong (tier 2): diff >= +4 -> 1/36 + 2/36 = 3/36
    # Medium (tier 1): diff +2 or +3 -> 3/36 + 4/36 = 7/36
    # Weak (tier 0): diff +1, 0 (roll 1-4), -1, -4 -> 5/36 + 4/36 + 5/36 + 2/36 = 16/36
    # No damage: diff 0 (roll 5-6), -2, -3, <= -5 -> 2/36 + 4/36 + 3/36 + 1/36 = 10/36

    prob_strong = 3 / 36
    prob_medium = 7 / 36
    prob_weak = 16 / 36
    # prob_miss = 10 / 36

    return (strong * prob_strong + medium * prob_medium + weak * prob_weak)


def calculate_expected_counter(defender_attack: tuple) -> float:
    """Calculate expected counter damage from defender.

    Counter occurs when:
    diff == 0 (atk_roll 5-6): 2/36 -> Weak counter
    diff == -3: 3/36 -> Weak counter
    diff == -4: 2/36 -> Medium counter (exchange)
    diff <= -5: 1/36 -> Medium counter
    """
    weak, medium, strong = defender_attack[0], defender_attack[1], defender_attack[2]

    # Weak counter: diff 0 (high roll) + diff -3 -> 2/36 + 3/36 = 5/36
    # Medium counter: diff -4 + diff <= -5 -> 2/36 + 1/36 = 3/36
    prob_weak_counter = 5 / 36
    prob_medium_counter = 3 / 36

    return (weak * prob_weak_counter + medium * prob_medium_counter)


def front_row_score(card: Card) -> float:
    """Calculate how suitable a card is for front row placement.

    Higher score = more suitable for front row.
    Based on squad_ai.py logic.
    """
    score = 0.0
    # High HP = tank
    score += card.life * 3
    # High attack = frontline fighter
    score += sum(card.stats.attack) / 3 * 2
    # Ability-based adjustments
    for aid in card.stats.ability_ids:
        if 'defender' in aid:
            score += 20
        if 'tough' in aid or 'armor' in aid:
            score += 15
        # Ranged = back row (negative)
        if 'shot' in aid or 'lunge' in aid:
            score -= 20
        # Healing = back row
        if 'heal' in aid:
            score -= 15
    return score


@dataclass
class CardMoveOptions:
    """All move options for a single card."""
    card_id: int
    current_pos: int
    options: List[int]  # List of positions (including current = stay)


@dataclass
class MoveCombination:
    """A specific combination of moves for all cards."""
    moves: Dict[int, int]  # card_id -> target_position
    score: float = 0.0


@dataclass
class ScoredPosition:
    """A board position with its evaluation score."""
    moves: Dict[int, int]  # card_id -> target_position
    position_score: float
    attack_score: float
    total_score: float
    best_attack: Optional['AIAction'] = None


class UtilityAI(AIPlayer):
    """AI that evaluates positions using exhaustive movement search.

    1. Generates all valid movement combinations for moveable cards
    2. Scores each resulting board position
    3. Uses beam search to keep top N positions
    4. Evaluates attacks from best positions
    5. Picks move sequence with best combined score
    """

    name = "Utility-based"

    def __init__(self, server, player: int, seed: int = None, beam_width: int = 50):
        super().__init__(server, player)
        self.rng = random.Random(seed)
        self.beam_width = beam_width  # Top positions to evaluate for attacks
        self._planned_moves: List[Tuple[int, int]] = []  # [(card_id, target_pos), ...]
        self._planned_attack: Optional[AIAction] = None

    def choose_action(self) -> Optional[AIAction]:
        """Choose the best action using utility evaluation."""
        game = self.game
        if game is None:
            return None

        actions = self.get_valid_actions()
        if not actions:
            return None

        # Handle interactions (use rule-based logic for simplicity)
        if game.interaction:
            self._clear_plan()
            return self._choose_interaction_action(actions)

        # Handle priority phase
        if game.priority_phase:
            return self._choose_priority_action(actions)

        # Main turn logic with movement combination search
        return self._choose_turn_action(actions)

    def _clear_plan(self):
        """Clear any planned moves/attacks."""
        self._planned_moves = []
        self._planned_attack = None

    def _choose_turn_action(self, actions: List[AIAction]) -> Optional[AIAction]:
        """Choose action using exhaustive movement combination search."""
        game = self.game

        # Separate action types
        move_actions = [a for a in actions if a.command.type.name == 'MOVE']
        attack_actions = [a for a in actions if a.command.type.name == 'ATTACK']
        ability_actions = [a for a in actions if a.command.type.name == 'USE_ABILITY']
        end_turn = [a for a in actions if a.command.type.name == 'END_TURN']

        # 1. Forced attacks - must do immediately
        forced = [a for a in attack_actions if 'forced' in a.description]
        if forced:
            self._clear_plan()
            return self._pick_best_attack(forced)

        # 2. Execute any planned moves first
        if self._planned_moves:
            card_id, target_pos = self._planned_moves[0]
            # Find the corresponding move action
            for action in move_actions:
                if action.command.card_id == card_id and action.command.position == target_pos:
                    self._planned_moves.pop(0)
                    return action
            # Move not found (card may have been killed) - replan
            self._clear_plan()

        # 3. Execute planned attack after all moves done
        if self._planned_attack is not None:
            # Find matching attack action
            for action in attack_actions:
                if (action.command.card_id == self._planned_attack.command.card_id and
                    action.command.position == self._planned_attack.command.position):
                    self._planned_attack = None
                    return action
            # Attack not available anymore - continue without it
            self._planned_attack = None

        # 4. No plan - create new plan using movement combination search
        best_position = self._search_best_position(game, move_actions, attack_actions)

        if best_position:
            # Extract move sequence
            for card_id, target_pos in best_position.moves.items():
                card = game.board.get_card_by_id(card_id)
                if card and card.position != target_pos:
                    self._planned_moves.append((card_id, target_pos))
            self._planned_attack = best_position.best_attack

            # Execute first planned move if any
            if self._planned_moves:
                card_id, target_pos = self._planned_moves.pop(0)
                for action in move_actions:
                    if action.command.card_id == card_id and action.command.position == target_pos:
                        return action

            # No moves needed, execute attack
            if self._planned_attack:
                for action in attack_actions:
                    if (action.command.card_id == self._planned_attack.command.card_id and
                        action.command.position == self._planned_attack.command.position):
                        attack = self._planned_attack
                        self._planned_attack = None
                        return attack

        # 5. Fallback: use abilities or end turn
        best_ability = self._pick_best_ability(ability_actions) if ability_actions else None
        if best_ability:
            ability_value = self._evaluate_ability(game, best_ability)
            if ability_value > 0:
                return best_ability

        if end_turn:
            return end_turn[0]

        return self.rng.choice(actions) if actions else None

    def _search_best_position(self, game: Game, move_actions: List[AIAction],
                               attack_actions: List[AIAction]) -> Optional[ScoredPosition]:
        """Search all movement combinations and find the best position."""
        # Get all moveable cards and their options
        card_options = self._get_all_move_options(game, move_actions)

        if not card_options:
            # No moves available - evaluate current position with attacks
            return self._evaluate_current_position(game, attack_actions)

        # Generate all combinations
        all_combinations = self._generate_move_combinations(card_options)

        # Evaluate current position first for comparison
        current_pos = self._evaluate_current_position(game, attack_actions)
        current_attack_count = len(attack_actions)

        # Score each combination and keep top N (beam search)
        scored_positions: List[ScoredPosition] = []

        for combo in all_combinations:
            # Check if this combo actually moves anything
            actual_moves = sum(1 for cid, pos in combo.items()
                             if game.board.get_card_by_id(cid) and
                             game.board.get_card_by_id(cid).position != pos)

            # Simulate this combination
            sim_game = self._simulate_combination(game, combo)
            if sim_game is None:
                continue

            # Score the position
            position_score = self._evaluate_position(sim_game)

            # Count attack opportunities after moving
            attack_score, best_attack = self._evaluate_attacks_from_position(sim_game, game)

            # Significant bonus for moves that change the board state
            if actual_moves > 0:
                # Per-move bonus to encourage exploration
                position_score += 15 * actual_moves

                # Extra bonus if moving toward enemies (advancing)
                for cid, target_pos in combo.items():
                    card = game.board.get_card_by_id(cid)
                    if card and card.position != target_pos and target_pos < 30:
                        curr_row = card.position // 5 if card.position < 30 else -1
                        new_row = target_pos // 5
                        # P1 wants higher rows, P2 wants lower rows
                        if self.player == 1 and new_row > curr_row:
                            position_score += 10  # Advancing bonus
                        elif self.player == 2 and new_row < curr_row:
                            position_score += 10  # Advancing bonus

            scored_positions.append(ScoredPosition(
                moves=combo,
                position_score=position_score,
                attack_score=attack_score,
                total_score=position_score + attack_score,
                best_attack=best_attack
            ))

        # Keep top N by total score
        scored_positions.sort(key=lambda p: p.total_score, reverse=True)
        top_positions = scored_positions[:self.beam_width]

        # Add current position (no moves)
        if current_pos:
            top_positions.append(current_pos)

        # Pick best by total score
        if not top_positions:
            return None

        top_positions.sort(key=lambda p: p.total_score, reverse=True)
        best = top_positions[0]

        # If best position involves moves and has similar attack score to current,
        # prefer moving for better positioning
        if current_pos and best.moves and len(best.moves) > 0:
            # Check if any actual moves
            actual_best_moves = sum(1 for cid, pos in best.moves.items()
                                   if game.board.get_card_by_id(cid) and
                                   game.board.get_card_by_id(cid).position != pos)
            if actual_best_moves == 0:
                # Best "moves" are all stay-in-place, use current position
                return current_pos

        return best

    def _get_all_move_options(self, game: Game, move_actions: List[AIAction]) -> List[CardMoveOptions]:
        """Get all move options for each moveable card."""
        # Group move actions by card
        card_moves: Dict[int, List[int]] = {}
        card_positions: Dict[int, int] = {}

        for action in move_actions:
            card_id = action.command.card_id
            target_pos = action.command.position
            card = game.board.get_card_by_id(card_id)
            if card:
                if card_id not in card_moves:
                    card_moves[card_id] = [card.position]  # Include "stay" option
                    card_positions[card_id] = card.position
                if target_pos not in card_moves[card_id]:
                    card_moves[card_id].append(target_pos)

        # Convert to CardMoveOptions
        result = []
        for card_id, options in card_moves.items():
            result.append(CardMoveOptions(
                card_id=card_id,
                current_pos=card_positions[card_id],
                options=options
            ))

        return result

    def _generate_move_combinations(self, card_options: List[CardMoveOptions]) -> List[Dict[int, int]]:
        """Generate all valid movement combinations."""
        if not card_options:
            return [{}]

        # Limit combinations to avoid explosion
        # If too many options, prune to most promising
        total_combos = 1
        for opt in card_options:
            total_combos *= len(opt.options)

        if total_combos > 5000:
            # Prune: for each card, keep only stay + 2 best advancing moves
            card_options = self._prune_options(card_options)

        # Generate cartesian product
        all_option_lists = [opt.options for opt in card_options]
        all_card_ids = [opt.card_id for opt in card_options]

        combinations = []
        for combo in product(*all_option_lists):
            # Check for conflicts (two cards in same position)
            positions = list(combo)
            if len(positions) != len(set(positions)):
                continue  # Skip invalid - cards would overlap

            move_dict = {card_id: pos for card_id, pos in zip(all_card_ids, combo)}
            combinations.append(move_dict)

        return combinations

    def _prune_options(self, card_options: List[CardMoveOptions]) -> List[CardMoveOptions]:
        """Prune move options to reduce combinatorial explosion."""
        pruned = []
        for opt in card_options:
            if len(opt.options) <= 3:
                pruned.append(opt)
                continue

            # Keep: stay, and up to 2 advancing moves
            current = opt.current_pos
            current_row = current // 5 if current < 30 else -1

            advancing = []
            for pos in opt.options:
                if pos == current:
                    continue
                if pos >= 30:
                    continue  # Flying zone
                pos_row = pos // 5
                # Check if advancing toward enemy
                if self.player == 1 and pos_row > current_row:
                    advancing.append(pos)
                elif self.player == 2 and pos_row < current_row:
                    advancing.append(pos)

            # Keep stay + best 2 advancing
            kept = [current]
            kept.extend(advancing[:2])

            pruned.append(CardMoveOptions(
                card_id=opt.card_id,
                current_pos=opt.current_pos,
                options=kept
            ))

        return pruned

    def _simulate_combination(self, game: Game, moves: Dict[int, int]) -> Optional[Game]:
        """Simulate a combination of moves and return resulting game state."""
        try:
            sim_game = Game.from_dict(game.to_dict())

            for card_id, target_pos in moves.items():
                card = sim_game.board.get_card_by_id(card_id)
                if card and card.position != target_pos:
                    sim_game.board.move_card(card, target_pos)
                    card.curr_move = max(0, card.curr_move - 1)

            sim_game.recalculate_formations()
            return sim_game
        except Exception:
            return None

    def _evaluate_attacks_from_position(self, sim_game: Game,
                                         original_game: Game) -> Tuple[float, Optional[AIAction]]:
        """Evaluate best attack from a simulated position."""
        best_score = 0.0
        best_attack = None

        # Get our cards that can attack
        my_cards = sim_game.board.get_all_cards(self.player)

        for card in my_cards:
            if card.tapped or not card.can_act:
                continue

            # Get attack targets
            targets = sim_game.get_attack_targets(card)
            for target_pos in targets:
                target = sim_game.board.get_card(target_pos)
                if not target or target.player == self.player:
                    continue

                # Score this attack
                score = self._score_attack_opportunity(card, target)
                if score > best_score:
                    best_score = score
                    # Create a pseudo-action for the attack
                    from ..commands import cmd_attack
                    best_attack = AIAction(
                        command=cmd_attack(self.player, card.id, target_pos),
                        description=f"{card.name} attack {target.name}"
                    )

        return best_score, best_attack

    def _score_attack_opportunity(self, attacker: Card, target: Card) -> float:
        """Score an attack opportunity using expected damage."""
        score = 10.0

        atk_values = attacker.get_effective_attack()
        strong_dmg = atk_values[2] if len(atk_values) > 2 else atk_values[-1]

        # Calculate expected damage
        expected_dmg = calculate_expected_damage(atk_values, target.tapped)

        # Kill potential - check both strong damage (possible kill) and expected damage
        if target.curr_life <= strong_dmg:
            score += 30  # Guaranteed kill possible with good roll
        elif target.curr_life <= expected_dmg * 1.5:
            score += 15  # Likely to kill with average+ roll

        if target.tapped:
            score += 8  # Safe attack (no counter)
            # Higher expected damage against tapped
            score += expected_dmg * 0.5

        if target.curr_life <= 5:
            score += 5  # Low HP

        score += target.stats.cost  # Target value

        # Risk assessment using expected counter damage
        if not target.tapped:
            counter_expected = calculate_expected_counter(target.stats.attack)
            if attacker.curr_life <= counter_expected * 2:
                score -= 10  # High risk of dying to counter
            elif attacker.curr_life <= counter_expected * 3:
                score -= 5  # Moderate risk

        return score

    def _evaluate_current_position(self, game: Game,
                                    attack_actions: List[AIAction]) -> Optional[ScoredPosition]:
        """Evaluate the current position without any moves."""
        position_score = self._evaluate_position(game)

        best_attack = self._pick_best_attack(attack_actions) if attack_actions else None
        attack_score = self._evaluate_attack(game, best_attack) if best_attack else 0.0

        return ScoredPosition(
            moves={},
            position_score=position_score,
            attack_score=attack_score,
            total_score=position_score + attack_score,
            best_attack=best_attack
        )

    def _evaluate_position(self, game: Game) -> float:
        """Evaluate a board position from this player's perspective."""
        score = 0.0
        my_cards = game.board.get_all_cards(self.player)
        enemy_cards = game.board.get_all_cards(self.opponent)

        # Material advantage
        my_material = sum(c.stats.cost for c in my_cards)
        enemy_material = sum(c.stats.cost for c in enemy_cards)
        score += (my_material - enemy_material) * WEIGHTS['material']

        # HP advantage
        my_hp = sum(c.curr_life for c in my_cards)
        my_max_hp = sum(c.life for c in my_cards)
        enemy_hp = sum(c.curr_life for c in enemy_cards)
        enemy_max_hp = sum(c.life for c in enemy_cards)

        if my_max_hp > 0 and enemy_max_hp > 0:
            hp_ratio = (my_hp / my_max_hp) - (enemy_hp / enemy_max_hp)
            score += hp_ratio * WEIGHTS['hp_ratio'] * 10

        # Formation bonuses
        for card in my_cards:
            if card.in_formation:
                score += WEIGHTS['formation']

        # Position-based ability bonuses
        for card in my_cards:
            score += self._evaluate_position_abilities(game, card)

        # Attack opportunities
        for card in my_cards:
            if card.can_act:
                targets = game.get_attack_targets(card)
                enemy_targets = [t for t in targets
                               if game.board.get_card(t) and
                               game.board.get_card(t).player != self.player]
                if enemy_targets:
                    score += WEIGHTS['attack_opportunity']
                    # Bonus for kill potential
                    for t in enemy_targets:
                        target = game.board.get_card(t)
                        if target and target.curr_life <= card.stats.attack[2]:
                            score += WEIGHTS['kill_potential']

        # Threats against us
        for card in enemy_cards:
            if not card.tapped:
                targets = game.get_attack_targets(card)
                my_positions = [c.position for c in my_cards]
                threatened = [t for t in targets if t in my_positions]
                score += len(threatened) * WEIGHTS['threat']

        # Board advancement
        for card in my_cards:
            if card.position is not None and card.position < 30:
                row = card.position // 5
                if self.player == 1:
                    advancement = row  # P1 wants higher rows
                else:
                    advancement = 5 - row  # P2 wants lower rows
                score += advancement * WEIGHTS['advancement']

        # Center control
        center_cols = [2, 7, 12, 17, 22, 27]  # Column 2 in each row
        for card in my_cards:
            if card.position in center_cols:
                score += WEIGHTS['center_control']

        # Positioning bonus based on front_row_score and adjacent enemy count
        # Tanks/fighters (high frs) want more adjacent enemies
        # Ranged/healers (low frs) want fewer adjacent enemies
        for card in my_cards:
            if card.position is None or card.position >= 30:
                continue  # Skip flying cards

            # Count adjacent enemy cards
            adjacent_enemies = self._count_adjacent_enemies(game, card.position)

            frs = front_row_score(card)
            # High front_row_score cards should have more adjacent enemies
            # Low front_row_score cards should have fewer adjacent enemies
            if frs > 30:  # Tank/fighter type - wants combat
                score += adjacent_enemies * WEIGHTS['row_placement']
            elif frs < 10:  # Ranged/healer type - wants distance
                score -= adjacent_enemies * WEIGHTS['row_placement']
            # Middle cards (10-30) are neutral

        return score

    def _count_adjacent_enemies(self, game: Game, pos: int) -> int:
        """Count enemy cards adjacent to a position."""
        if pos is None or pos >= 30:
            return 0

        row, col = pos // 5, pos % 5
        count = 0

        # Check all 4 adjacent positions
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < 6 and 0 <= nc < 5:
                adj_pos = nr * 5 + nc
                adj_card = game.board.get_card(adj_pos)
                if adj_card and adj_card.player != self.player:
                    count += 1

        return count

    def _evaluate_position_abilities(self, game: Game, card: Card) -> float:
        """Evaluate bonuses from position-dependent abilities."""
        score = 0.0
        if card.position is None or card.position >= 30:
            return score  # Flying cards handled separately

        row = card.position // 5
        col = card.position % 5

        # Convert to relative row (0=back, 2=front for the player)
        if self.player == 1:
            rel_row = row  # P1: row 0-2 maps to back-front
        else:
            rel_row = 5 - row  # P2: row 5-3 maps to back-front

        from ..abilities import get_ability

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability:
                continue

            # Check row requirements
            if ability.requires_own_row is not None:
                if rel_row == ability.requires_own_row:
                    score += WEIGHTS['position_ability']

            # Check edge column
            if ability.requires_edge_column:
                if col in [0, 4]:
                    score += WEIGHTS['position_ability']

            # Check center column
            if ability.requires_center_column:
                if col == 2:
                    score += WEIGHTS['position_ability']

        return score

    def _evaluate_attack(self, game: Game, action: AIAction) -> float:
        """Evaluate an attack action's value using expected damage."""
        if not action:
            return 0.0

        attacker = game.board.get_card_by_id(action.command.card_id)
        target = game.board.get_card(action.command.position)

        if not attacker or not target:
            return 0.0

        value = 10.0  # Base value for any attack

        # Hidden cards - moderate priority (reveals them)
        if target.face_down:
            return 12.0

        atk_values = attacker.get_effective_attack()
        strong_dmg = atk_values[2] if len(atk_values) > 2 else atk_values[-1]

        # Calculate expected damage
        expected_dmg = calculate_expected_damage(atk_values, target.tapped)

        # Kill potential
        if target.curr_life <= strong_dmg:
            value += 30  # Guaranteed kill possible
        elif target.curr_life <= expected_dmg * 1.5:
            value += 15  # Likely kill

        # Bonus for attacking tapped targets
        if target.tapped:
            value += 8
            value += expected_dmg * 0.5  # Higher expected damage

        # Bonus for low HP targets
        if target.curr_life <= 5:
            value += 5

        # Bonus for high-value targets
        value += target.stats.cost

        # Risk assessment using expected counter
        if not target.tapped:
            counter_expected = calculate_expected_counter(target.stats.attack)
            if attacker.curr_life <= counter_expected * 2:
                value -= 10
            elif attacker.curr_life <= counter_expected * 3:
                value -= 5

        return value

    def _evaluate_ability(self, game: Game, action: AIAction) -> float:
        """Evaluate an ability action's value."""
        if not action:
            return 0.0

        ability_id = action.command.ability_id

        # Healing is valuable if allies are damaged
        if 'heal' in ability_id:
            damaged = [c for c in game.board.get_all_cards(self.player)
                      if c.curr_life < c.life]
            if damaged:
                return 15.0
            return 0.0

        # Damage abilities
        if 'shot' in ability_id or 'lunge' in ability_id:
            return 12.0

        # Counter-gaining
        if 'counter' in ability_id:
            card = game.board.get_card_by_id(action.command.card_id)
            if card and card.counters < card.max_counters:
                return 8.0
            return 0.0

        return 5.0  # Default for other abilities

    def _pick_best_attack(self, attacks: List[AIAction]) -> Optional[AIAction]:
        """Pick the best attack from available options."""
        if not attacks:
            return None

        game = self.game
        best = None
        best_value = float('-inf')

        for action in attacks:
            value = self._evaluate_attack(game, action)
            if value > best_value:
                best_value = value
                best = action

        return best

    def _pick_best_ability(self, abilities: List[AIAction]) -> Optional[AIAction]:
        """Pick the best ability from available options."""
        if not abilities:
            return None

        game = self.game
        best = None
        best_value = float('-inf')

        for action in abilities:
            value = self._evaluate_ability(game, action)
            if value > best_value:
                best_value = value
                best = action

        return best

    def _move_enables_attack(self, game: Game, move_action: AIAction) -> bool:
        """Check if a move enables new attack opportunities."""
        card = game.board.get_card_by_id(move_action.command.card_id)
        if not card:
            return False

        # Current attack targets
        current_targets = game.get_attack_targets(card)
        current_enemies = [t for t in current_targets
                         if game.board.get_card(t) and
                         game.board.get_card(t).player != self.player]

        # Simulate move
        sim_game = self._simulate_move(game, move_action)
        if not sim_game:
            return False

        sim_card = sim_game.board.get_card_by_id(card.id)
        if not sim_card:
            return False

        # New attack targets
        new_targets = sim_game.get_attack_targets(sim_card)
        new_enemies = [t for t in new_targets
                      if sim_game.board.get_card(t) and
                      sim_game.board.get_card(t).player != self.player]

        # Move enables attack if we gain new targets
        return len(new_enemies) > len(current_enemies)

    def _choose_interaction_action(self, actions: List[AIAction]) -> AIAction:
        """Handle interactions using rule-based logic."""
        game = self.game
        inter = game.interaction

        # Defender selection - pick highest HP defender
        if inter.kind.name == 'SELECT_DEFENDER':
            defend_actions = [a for a in actions if 'defend' in a.description]
            if defend_actions:
                best = max(defend_actions,
                          key=lambda a: game.board.get_card_by_id(a.command.card_id).curr_life
                          if game.board.get_card_by_id(a.command.card_id) else 0)
                return best
            skip = [a for a in actions if 'skip' in a.description]
            if skip:
                return skip[0]

        # Ability targets - pick best enemy for damage, best ally for heals
        if inter.kind.name == 'SELECT_ABILITY_TARGET':
            ability_id = inter.context.get('ability_id', '')
            if 'heal' in ability_id:
                # Target most damaged ally
                best = None
                best_damage = -1
                for action in actions:
                    target = game.board.get_card(action.command.position)
                    if target and target.player == self.player:
                        damage = target.life - target.curr_life
                        if damage > best_damage:
                            best = action
                            best_damage = damage
                if best:
                    return best
            else:
                # Target highest value enemy
                best = None
                best_value = -1
                for action in actions:
                    target = game.board.get_card(action.command.position)
                    if target and target.player != self.player:
                        value = target.stats.cost
                        if target.curr_life <= 2:
                            value += 10
                        if value > best_value:
                            best = action
                            best_value = value
                if best:
                    return best

        # Valhalla - buff strongest ally
        if inter.kind.name == 'SELECT_VALHALLA_TARGET':
            best = max(actions,
                      key=lambda a: game.board.get_card_by_id(a.command.card_id).stats.cost
                      if game.board.get_card_by_id(a.command.card_id) else 0)
            return best

        # Counter shot - target enemies only
        if 'shot' in inter.kind.name.lower():
            for action in actions:
                if 'skip' in action.description:
                    continue
                target = game.board.get_card(action.command.position)
                if target and target.player != self.player:
                    return action
            skip = [a for a in actions if 'skip' in a.description]
            if skip:
                return skip[0]

        # Confirmations - generally accept
        if inter.kind.name in ('CONFIRM_HEAL', 'CONFIRM_UNTAP'):
            accept = [a for a in actions if 'accept' in a.description]
            if accept:
                return accept[0]

        return self.rng.choice(actions)

    def _choose_priority_action(self, actions: List[AIAction]) -> AIAction:
        """Handle priority phase."""
        # For now, just pass priority
        pass_actions = [a for a in actions if 'pass' in a.description]
        if pass_actions:
            return pass_actions[0]
        return self.rng.choice(actions)
