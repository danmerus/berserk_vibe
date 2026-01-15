"""Rule-based AI - uses simple heuristics to make decisions.

This AI plays much faster than RandomAI by:
- Ending turn when no valuable actions remain
- Prioritizing attacks that can kill
- Avoiding useless movements
- Making smart defender/interaction choices
"""
import random
from typing import Optional, List, TYPE_CHECKING

from .base import AIPlayer, AIAction
from ..card import Card

if TYPE_CHECKING:
    from ..match import MatchServer


def front_row_score(card: Card) -> float:
    """Calculate how suitable a card is for front row / close to enemies.

    Higher score = more suitable for being close to enemies (tank/fighter).
    Lower score = should stay back (ranged/healer).
    """
    score = 0.0
    # High HP = tanky, wants to be in front
    score += card.life * 2
    # High attack = frontline fighter
    score += sum(card.stats.attack) / 3 * 1.5
    # Ability-based adjustments
    for aid in card.stats.ability_ids:
        if 'defender' in aid:
            score += 25  # Defenders WANT to be in front
        if 'tough' in aid or 'armor' in aid:
            score += 20  # Damage reduction = front line
        if 'unlimited_defender' in aid:
            score += 15
        # Ranged = back row (negative)
        if 'shot' in aid:
            score -= 25
        if 'lunge' in aid:
            score -= 15
        # Healing = back row
        if 'heal' in aid:
            score -= 20
        # Low cost creatures are expendable - front
        if card.stats.cost <= 3:
            score += 10
    return score


def is_key_defender(card: Card) -> bool:
    """Check if card is a key defender that should stay untapped.

    Key defenders have defender_no_tap or unlimited_defender abilities,
    or are specifically Лёккен (the best defender in the game).
    """
    # Лёккен is the most important defender - never tap if possible
    if 'ёккен' in card.name.lower():
        return True

    for aid in card.stats.ability_ids:
        if 'defender_no_tap' in aid:
            return True
        if 'unlimited_defender' in aid:
            return True
    return False


def has_ranged_ability(card: Card) -> bool:
    """Check if card has ranged attack abilities (shot/lunge)."""
    for aid in card.stats.ability_ids:
        if 'shot' in aid or 'lunge' in aid:
            return True
    return False


def has_heal_ability(card: Card) -> bool:
    """Check if card has healing abilities."""
    for aid in card.stats.ability_ids:
        if 'heal' in aid:
            return True
    return False


def should_maximize_distance(card: Card) -> bool:
    """Check if card should try to stay far from enemies."""
    return has_ranged_ability(card) or has_heal_ability(card)


def get_optimal_range(card: Card) -> tuple:
    """Get the optimal distance range for a card based on its abilities.

    Returns (min_dist, max_dist) where the card should try to stay.
    For melee cards: (1, 1) - be adjacent
    For ranged cards: (min_range, max_range) - stay within ability range
    """
    from ..abilities import get_ability

    best_min = 1
    best_max = 1  # Default: melee

    for aid in card.stats.ability_ids:
        ability = get_ability(aid)
        if ability and ability.range > 1:
            # Found a ranged ability
            min_r = ability.min_range if ability.min_range > 0 else 1
            max_r = min(ability.range, 10)  # Cap at 10 for sanity
            # Use the best (longest) range we find
            if max_r > best_max:
                best_min = min_r
                best_max = max_r

    return (best_min, best_max)


class RuleBasedAI(AIPlayer):
    """AI that uses simple rules to make decisions.

    Priority order:
    1. Handle forced attacks (must do)
    2. Kill attacks (can kill an enemy)
    3. Good attacks (damage without dying)
    4. Use beneficial abilities
    5. Strategic movement (advance toward enemy)
    6. End turn (when nothing valuable left)
    """

    name = "Rule-based"

    def __init__(self, server: 'MatchServer', player: int, seed: int = None):
        super().__init__(server, player)
        self.rng = random.Random(seed)

    def choose_action(self) -> Optional[AIAction]:
        """Choose the best action based on rules."""
        game = self.game
        if game is None:
            return None

        actions = self.get_valid_actions()
        if not actions:
            return None

        # Handle interactions with smart choices
        if game.interaction:
            return self._choose_interaction_action(actions)

        # Handle priority phase
        if game.priority_phase:
            return self._choose_priority_action(actions)

        # Normal turn - score and pick best action
        scored_actions = [(self._score_action(a), a) for a in actions]
        scored_actions.sort(key=lambda x: x[0], reverse=True)

        # Get all actions with the highest score
        best_score = scored_actions[0][0]
        best_actions = [a for score, a in scored_actions if score == best_score]

        # Pick randomly among equally good actions
        return self.rng.choice(best_actions)

    def _score_action(self, action: AIAction) -> int:
        """Score an action. Higher is better."""
        game = self.game
        cmd = action.command
        desc = action.description.lower()

        # Forced attacks - must do
        if 'forced' in desc:
            return 1000

        # End turn - low priority but not zero
        if cmd.type.name == 'END_TURN':
            # End turn early if we have no attacks and limited moves
            attack_actions = [a for a in self.get_valid_actions()
                             if a.command.type.name == 'ATTACK']
            if not attack_actions:
                return 50  # No attacks available, end turn is reasonable
            return 1  # Still have attacks, don't end yet

        # Attacks
        if cmd.type.name == 'ATTACK':
            return self._score_attack(action)

        # Abilities
        if cmd.type.name == 'USE_ABILITY':
            return self._score_ability(action)

        # Movement
        if cmd.type.name == 'MOVE':
            return self._score_movement(action)

        # Prepare flyer attack
        if cmd.type.name == 'PREPARE_FLYER_ATTACK':
            return 80  # Good if opponent has only flyers

        return 10  # Default

    def _score_attack(self, action: AIAction) -> int:
        """Score an attack action."""
        game = self.game
        cmd = action.command

        attacker = game.board.get_card_by_id(cmd.card_id)
        target = game.board.get_card(cmd.position)

        if not attacker or not target:
            return 50

        score = 100  # Base attack score

        # KEY DEFENDER PENALTY: Prefer not to tap key defenders unless valuable
        # Key defenders (Лёккен, defender_no_tap, unlimited_defender) are more valuable untapped
        if is_key_defender(attacker):
            # Check if this is a guaranteed kill
            atk_values = attacker.get_effective_attack()
            strong_dmg = atk_values[2] if len(atk_values) > 2 else atk_values[-1]
            if target.curr_life <= strong_dmg:
                # Guaranteed kill - worth it, minimal penalty
                score -= 20
            elif target.tapped:
                # Safe attack on tapped target - small penalty
                score -= 40
            else:
                # Risky attack that taps our defender - moderate penalty
                score -= 80

        # Hidden cards (face_down) - we don't know their real stats
        # Don't prioritize them as kills since HP=1 is fake
        if target.face_down:
            return max(score - 20, 10)  # Moderate priority - attack reveals them

        # Bonus for potential kill (target HP <= attacker's strong damage)
        atk_values = attacker.get_effective_attack()
        strong_dmg = atk_values[2] if len(atk_values) > 2 else atk_values[-1]
        if target.curr_life <= strong_dmg:
            score += 200  # High priority kill

        # Bonus for attacking tapped targets (no counter)
        if target.tapped:
            score += 50

        # Bonus for attacking low HP targets
        if target.curr_life <= 5:
            score += 30

        # Bonus for attacking high value targets
        score += target.stats.cost * 2

        # Penalty if attacker might die (low HP attacker vs untapped defender)
        if not target.tapped and attacker.curr_life <= 5:
            score -= 30

        return score

    def _score_ability(self, action: AIAction) -> int:
        """Score an ability action."""
        game = self.game
        cmd = action.command
        ability_id = cmd.ability_id

        # Healing abilities - only use if allies are damaged
        if 'heal' in ability_id:
            card = game.board.get_card_by_id(cmd.card_id)
            if card:
                # Only heal if there are damaged allies
                damaged = [c for c in game.board.get_all_cards(self.player)
                          if c.curr_life < c.life]
                if damaged:
                    return 120
            # No damaged allies - don't waste heal
            return 5

        # Ranged/shot/lunge abilities - only use if enemy targets exist
        if 'shot' in ability_id or 'lunge' in ability_id:
            card = game.board.get_card_by_id(cmd.card_id)
            if card:
                from ..abilities import get_ability
                ability = get_ability(ability_id)
                if ability:
                    targets = game._get_ability_targets(card, ability)
                    # Check if any targets are enemies
                    enemy_targets = [t for t in targets
                                    if game.board.get_card(t) and
                                    game.board.get_card(t).player != self.player]
                    if enemy_targets:
                        return 90
            # No enemy targets - don't use
            return 5

        # Counter-gaining abilities - check if max counters reached
        from ..abilities import get_ability, EffectType
        ability = get_ability(ability_id)
        if ability and ability.effect_type == EffectType.GAIN_COUNTER:
            card = game.board.get_card_by_id(cmd.card_id)
            if card and card.max_counters > 0 and card.counters >= card.max_counters:
                return 1  # Already at max counters - very low priority

        # Other abilities
        return 70

    def _get_distance_to_nearest_enemy(self, pos: int) -> int:
        """Calculate Manhattan distance from position to nearest enemy.

        Returns large number if no enemies exist.
        """
        game = self.game
        if pos is None or pos >= 30:  # Flying zone - use special handling
            return 100

        row = pos // 5
        col = pos % 5

        min_dist = 100
        enemy_player = 2 if self.player == 1 else 1

        for enemy in game.board.get_all_cards(enemy_player):
            if enemy.position is None or enemy.position >= 30:
                continue  # Skip flying enemies for ground distance
            enemy_row = enemy.position // 5
            enemy_col = enemy.position % 5
            dist = abs(row - enemy_row) + abs(col - enemy_col)
            min_dist = min(min_dist, dist)

        return min_dist

    def _count_adjacent_enemies(self, pos: int) -> int:
        """Count enemy cards adjacent to a position (orthogonal only)."""
        if pos is None or pos >= 30:
            return 0

        game = self.game
        row, col = pos // 5, pos % 5
        count = 0

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < 6 and 0 <= nc < 5:
                adj_pos = nr * 5 + nc
                adj_card = game.board.get_card(adj_pos)
                if adj_card and adj_card.player != self.player:
                    count += 1

        return count

    def _has_formation_ability(self, card) -> bool:
        """Check if card has a formation ability."""
        from ..abilities import get_ability
        for aid in card.stats.ability_ids:
            ability = get_ability(aid)
            if ability and ability.is_formation:
                return True
        return False

    def _count_formation_allies_at(self, pos: int) -> int:
        """Count adjacent allies with formation abilities at a position."""
        if pos is None or pos >= 30:
            return 0
        game = self.game
        row, col = pos // 5, pos % 5
        count = 0
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < 6 and 0 <= nc < 5:
                adj_pos = nr * 5 + nc
                adj_card = game.board.get_card(adj_pos)
                if adj_card and adj_card.player == self.player and self._has_formation_ability(adj_card):
                    count += 1
        return count

    def _score_movement(self, action: AIAction) -> int:
        """Score a movement action based on distance to enemies, formations, and card role."""
        game = self.game
        cmd = action.command

        card = game.board.get_card_by_id(cmd.card_id)
        if not card:
            return 5

        from_pos = card.position
        to_pos = cmd.position

        # Calculate card's front-row suitability
        frs = front_row_score(card)
        is_tank = frs > 35  # High FRS = tank/fighter, wants enemies
        is_ranged_type = frs < 15  # Low FRS = ranged/healer, wants distance

        # Check if card should maximize distance (ranged/heal abilities)
        wants_distance = should_maximize_distance(card)

        # Check if card has formation ability
        has_formation = self._has_formation_ability(card)

        # Calculate distances for later use
        current_dist = self._get_distance_to_nearest_enemy(from_pos)
        new_dist = self._get_distance_to_nearest_enemy(to_pos)

        # RANGE-AWARE POSITIONING for ranged/heal cards
        # These cards want to stay within their optimal attack range
        if wants_distance:
            min_range, max_range = get_optimal_range(card)

            # Check if new position is in optimal range
            in_optimal_new = min_range <= new_dist <= max_range
            in_optimal_curr = min_range <= current_dist <= max_range

            if in_optimal_new and not in_optimal_curr:
                # Moving INTO optimal range - excellent!
                return 80
            elif in_optimal_new and in_optimal_curr:
                # Staying in optimal range - neutral movement
                return 30
            elif not in_optimal_new and in_optimal_curr:
                # Moving OUT of optimal range - bad!
                return 5
            elif new_dist < min_range:
                # Too close! Move away
                if new_dist > current_dist:
                    return 60  # Getting farther (toward optimal)
                else:
                    return 3  # Getting even closer - very bad
            elif new_dist > max_range:
                # Too far! But for unlimited range (99), this is fine
                if max_range >= 10:
                    # Unlimited range - staying far is OK
                    return 40
                else:
                    # Limited range - need to get closer
                    if new_dist < current_dist:
                        return 55  # Getting closer to optimal
                    else:
                        return 15  # Getting even farther - bad

        # Formation considerations - high priority to maintain/create formations
        if has_formation:
            current_formation_allies = self._count_formation_allies_at(from_pos)
            new_formation_allies = self._count_formation_allies_at(to_pos)

            # Penalty for breaking formation
            if current_formation_allies > 0 and new_formation_allies == 0:
                return 2  # Very low - don't break formation

            # Bonus for creating/improving formation
            if new_formation_allies > current_formation_allies:
                return 75  # High priority to form up

        # Don't move if card can attack from current position (for non-ranged)
        if not wants_distance:
            current_targets = game.get_attack_targets(card)
            enemy_targets = [t for t in current_targets
                            if game.board.get_card(t) and
                            game.board.get_card(t).player != self.player]
            if enemy_targets:
                # Already in attack range - low priority to move
                # Unless moving improves formation
                if has_formation:
                    new_allies = self._count_formation_allies_at(to_pos)
                    if new_allies > self._count_formation_allies_at(from_pos):
                        return 60  # Formation improvement worth considering
                return 5

        # Check if move brings us into attack range
        # Temporarily simulate the move
        old_pos = card.position
        card.position = to_pos
        new_targets = game.get_attack_targets(card)
        card.position = old_pos

        new_enemy_targets = [t for t in new_targets
                           if game.board.get_card(t) and
                           game.board.get_card(t).player != self.player]

        current_targets = game.get_attack_targets(card)
        current_enemy_targets = [t for t in current_targets
                                if game.board.get_card(t) and
                                game.board.get_card(t).player != self.player]

        if new_enemy_targets and not current_enemy_targets:
            # Move enables new attacks - high priority!
            # But even higher for tanks, lower for ranged
            if is_tank:
                return 90
            elif wants_distance:
                return 40  # Ranged can attack from new position but shouldn't rush
            return 85

        # Adjacent enemy heuristic based on card type
        # Tanks want more adjacent enemies, ranged want fewer
        current_adj = self._count_adjacent_enemies(from_pos)
        new_adj = self._count_adjacent_enemies(to_pos)

        adj_bonus = 0
        if is_tank:
            # Tanks gain bonus for moves that increase adjacent enemies
            adj_bonus = (new_adj - current_adj) * 12
        elif is_ranged_type:
            # Ranged cards gain bonus for moves that decrease adjacent enemies
            adj_bonus = (current_adj - new_adj) * 10

        # Calculate row advancement
        from_row = from_pos // 5
        to_row = to_pos // 5

        # Determine if this is row advancement toward enemy
        if self.player == 1:
            row_advancement = to_row - from_row  # P1 wants higher rows
        else:
            row_advancement = from_row - to_row  # P2 wants lower rows

        base_score = 20  # Default score

        if row_advancement > 0:
            # Advancing toward enemy row
            if is_tank:
                base_score = 70  # Tanks want to advance aggressively
            elif is_ranged_type:
                base_score = 15  # Ranged shouldn't rush forward
            else:
                base_score = 65  # Normal advancement
        elif row_advancement < 0:
            # Retreating
            if is_ranged_type:
                base_score = 45  # Ranged WANT to retreat
            else:
                base_score = 3  # Very low priority for non-ranged

        # Lateral movement (same row) - use distance to pick best column
        if row_advancement == 0:
            if new_dist < current_dist:
                # Lateral move closer to enemy
                if is_tank:
                    base_score = 60  # Tanks want to close distance
                elif is_ranged_type:
                    base_score = 10  # Ranged shouldn't get closer
                else:
                    base_score = 55
            elif new_dist > current_dist:
                # Lateral move away from enemy
                if is_ranged_type:
                    base_score = 50  # Ranged want to kite away
                else:
                    base_score = 10

        return max(1, base_score + adj_bonus)

    def _choose_interaction_action(self, actions: List[AIAction]) -> AIAction:
        """Choose best action for an interaction."""
        game = self.game
        inter = game.interaction

        # Defender selection - defend with best available defender
        if inter.kind.name == 'SELECT_DEFENDER':
            # Find defender actions (not skip)
            defend_actions = [a for a in actions if 'defend' in a.description]
            if defend_actions:
                # Pick defender with highest HP
                best = None
                best_hp = -1
                for action in defend_actions:
                    card = game.board.get_card_by_id(action.command.card_id)
                    if card and card.curr_life > best_hp:
                        best = action
                        best_hp = card.curr_life
                if best:
                    return best
            # Skip if no good defenders
            skip_actions = [a for a in actions if 'skip' in a.description]
            if skip_actions:
                return skip_actions[0]

        # Valhalla - buff the strongest ally
        if inter.kind.name == 'SELECT_VALHALLA_TARGET':
            best = None
            best_value = -1
            for action in actions:
                card = game.board.get_card_by_id(action.command.card_id)
                if card:
                    value = card.stats.cost + card.curr_life
                    if value > best_value:
                        best = action
                        best_value = value
            if best:
                return best

        # Counter/movement shot - pick highest value ENEMY target
        if 'shot' in inter.kind.name.lower():
            best = None
            best_value = -1
            for action in actions:
                if 'skip' in action.description:
                    continue
                target = game.board.get_card(action.command.position)
                # Only target enemies!
                if target and target.player != self.player:
                    value = target.stats.cost
                    # Bonus for low HP targets (potential kill)
                    if target.curr_life <= 2:
                        value += 10
                    if value > best_value:
                        best = action
                        best_value = value
            if best:
                return best
            # No enemy targets - skip the shot
            skip_actions = [a for a in actions if 'skip' in a.description]
            if skip_actions:
                return skip_actions[0]

        # Ability target selection (lunge, heals, etc.)
        if inter.kind.name == 'SELECT_ABILITY_TARGET':
            ability_id = inter.context.get('ability_id', '')

            # Check if this is a heal ability
            is_heal = 'heal' in ability_id

            if is_heal:
                # Heal abilities - target damaged allies
                best = None
                best_damage = -1
                for action in actions:
                    target = game.board.get_card(action.command.position)
                    if target and target.player == self.player:
                        damage_taken = target.life - target.curr_life
                        if damage_taken > best_damage:
                            best = action
                            best_damage = damage_taken
                if best:
                    return best
            else:
                # All other abilities - target enemies only
                best = None
                best_value = -1
                for action in actions:
                    target = game.board.get_card(action.command.position)
                    if target and target.player != self.player:
                        # Prefer enemies with low HP (potential kill)
                        value = target.stats.cost
                        if target.curr_life <= 2:
                            value += 10
                        if value > best_value:
                            best = action
                            best_value = value
                if best:
                    return best
                # No enemy targets - try to skip
                skip_actions = [a for a in actions if 'skip' in a.description or 'cancel' in a.description]
                if skip_actions:
                    return skip_actions[0]

        # Heal confirmation - always accept
        if inter.kind.name == 'CONFIRM_HEAL':
            accept = [a for a in actions if 'accept' in a.description]
            if accept:
                return accept[0]

        # Stench - prefer tap over damage if card is valuable
        if inter.kind.name == 'CHOOSE_STENCH':
            # Tap to avoid damage
            tap_action = [a for a in actions if 'tap' in a.description]
            if tap_action:
                return tap_action[0]

        # Exchange - prefer full damage if we're winning the trade
        if inter.kind.name == 'CHOOSE_EXCHANGE':
            # Take full damage for more aggression
            full = [a for a in actions if 'full' in a.description]
            if full:
                return full[0]

        # Default: random choice
        return self.rng.choice(actions)

    def _choose_priority_action(self, actions: List[AIAction]) -> AIAction:
        """Choose action during priority phase."""
        # For now, just pass priority (don't use luck ability)
        # Could be smarter about when to use luck
        pass_actions = [a for a in actions if 'pass' in a.description]
        if pass_actions:
            return pass_actions[0]
        return self.rng.choice(actions)
