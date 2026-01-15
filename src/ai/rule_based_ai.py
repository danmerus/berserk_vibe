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

if TYPE_CHECKING:
    from ..match import MatchServer


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

        # Hidden cards (face_down) - we don't know their real stats
        # Don't prioritize them as kills since HP=1 is fake
        if target.face_down:
            return 80  # Moderate priority - attack reveals them

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

        # Other abilities
        return 70

    def _score_movement(self, action: AIAction) -> int:
        """Score a movement action."""
        game = self.game
        cmd = action.command

        card = game.board.get_card_by_id(cmd.card_id)
        if not card:
            return 5

        from_pos = card.position
        to_pos = cmd.position

        # Check if card has ranged attack ability
        has_ranged = any(
            'shot' in aid or 'lunge' in aid
            for aid in card.stats.ability_ids
        )

        # Don't move if card can attack from current position
        current_targets = game.get_attack_targets(card)
        enemy_targets = [t for t in current_targets
                        if game.board.get_card(t) and
                        game.board.get_card(t).player != self.player]
        if enemy_targets:
            # Already in attack range - low priority to move
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

        if new_enemy_targets and not enemy_targets:
            # Move enables new attacks - high priority!
            return 85

        # Cards with ranged abilities shouldn't prioritize advancing
        # They can attack from distance
        if has_ranged:
            return 10

        # Score based on advancing toward enemy
        # When no attacks available, advancing should beat end_turn (50)
        if self.player == 1:
            # P1 wants to move to higher rows (toward P2)
            from_row = from_pos // 5
            to_row = to_pos // 5
            if to_row > from_row:
                return 60  # Advancing - higher than end_turn
            elif to_row < from_row:
                return 3  # Retreating
        else:
            # P2 wants to move to lower rows (toward P1)
            from_row = from_pos // 5
            to_row = to_pos // 5
            if to_row < from_row:
                return 60  # Advancing - higher than end_turn
            elif to_row > from_row:
                return 3  # Retreating

        return 15  # Lateral movement

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

        # Counter/movement shot - pick highest value target
        if 'shot' in inter.kind.name.lower():
            best = None
            best_value = -1
            for action in actions:
                if 'skip' in action.description:
                    continue
                target = game.board.get_card(action.command.position)
                if target:
                    value = target.stats.cost
                    # Bonus for low HP targets (potential kill)
                    if target.curr_life <= 2:
                        value += 10
                    if value > best_value:
                        best = action
                        best_value = value
            if best:
                return best

        # Ability target selection (lunge, heals, etc.)
        if inter.kind.name == 'SELECT_ABILITY_TARGET':
            ability_id = inter.context.get('ability_id', '')
            # Damage abilities (lunge, shot) - target enemies
            if 'lunge' in ability_id or 'shot' in ability_id or 'damage' in ability_id:
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
            # Heal abilities - target damaged allies
            elif 'heal' in ability_id:
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
