"""Ability system - usage, targeting, ranged/magic attacks."""
from typing import List, Optional, TYPE_CHECKING

from .base import CombatResult, DiceContext
from ..abilities import get_ability, AbilityType, TargetType, EffectType
from ..ability_handlers import get_handler, get_targeter
from ..interaction import (
    InteractionKind, interaction_select_target, interaction_select_counters
)

if TYPE_CHECKING:
    from ..card import Card
    from ..abilities import Ability


class AbilitiesMixin:
    """Mixin for ability system."""

    def get_usable_abilities(self, card: 'Card') -> List['Ability']:
        """Get list of active abilities the card can use right now."""
        usable =  []

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.ability_type != AbilityType.ACTIVE:
                continue

            if ability.is_instant and self.priority_phase:
                if card.player == self.priority_player and not card.tapped:
                    if card.can_use_ability(ability_id):
                        usable.append(ability)
            else:
                if card.can_act and card.player == self.current_player:
                    if card.can_use_ability(ability_id):
                        usable.append(ability)

        return usable

    def get_ability_display_text(self, card: 'Card', ability: 'Ability') -> str:
        """Get dynamic display text for an ability."""
        if ability.id.startswith("lunge"):
            dmg = ability.damage_amount if ability.damage_amount > 0 else 1
            return f"Удар через ряд {dmg}"

        if ability.ranged_damage and ability.id != "lunge":
            bonus = card.temp_ranged_bonus
            dmg = ability.ranged_damage
            d0, d1, d2 = dmg[0] + bonus, dmg[1] + bonus, dmg[2] + bonus
            ranged_name = "Метание" if ability.ranged_type == "throw" else "Выстрел"
            return f"{ranged_name} {d0}-{d1}-{d2}"

        if ability.heal_amount > 0:
            return f"{ability.name} +{ability.heal_amount} HP"

        if ability.id == "magical_strike" and ability.magic_damage:
            dmg = ability.magic_damage
            if dmg[0] == dmg[1] == dmg[2]:
                return f"Магический удар {dmg[0]}"
            else:
                return f"Магический удар {dmg[0]}-{dmg[1]}-{dmg[2]}"

        return ability.name

    def use_ability(self, card: 'Card', ability_id: str) -> bool:
        """Start using an ability."""
        self.last_combat = None

        if self.priority_phase:
            return False

        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return False

        ability = get_ability(ability_id)
        if not ability or ability.ability_type != AbilityType.ACTIVE:
            return False

        if not card.can_use_ability(ability_id):
            self.log(f"{ability.name} на перезарядке!")
            return False

        # Reveal face-down card when it acts
        if card.face_down:
            self.reveal_card(card)

        # Axe strike counter selection
        if ability.id == "axe_strike":
            if card.counters <= 0:
                targets = self._get_ability_targets(card, ability)
                if not targets:
                    self.log("Нет доступных целей!")
                    return False
                self.interaction = interaction_select_target(
                    actor_id=card.id,
                    ability_id=ability.id,
                    valid_positions=tuple(targets),
                    acting_player=card.player,
                )
                self.interaction.context['counters_spent'] = 0
                self.log(f"Выберите цель для {ability.name} (0 фишек)")
                return True
            self.interaction = interaction_select_counters(
                card_id=card.id,
                min_counters=0,
                max_counters=card.counters,
                acting_player=card.player,
            )
            self.interaction.context['ability_id'] = ability_id
            self.log(f"Выберите количество фишек (0-{card.counters})")
            return True

        if ability.target_type == TargetType.SELF:
            return self._execute_ability(card, ability, card)

        if ability.target_type in (TargetType.ENEMY, TargetType.ALLY, TargetType.ANY):
            targets = self._get_ability_targets(card, ability)
            if not targets:
                self.log("Нет доступных целей!")
                return False

            self.interaction = interaction_select_target(
                actor_id=card.id,
                ability_id=ability.id,
                valid_positions=tuple(targets),
                acting_player=card.player,
            )
            self.log(f"Выберите цель для {ability.name}")
            return True

        return False

    def _get_ability_targets(self, card: 'Card', ability: 'Ability') -> List[int]:
        """Get valid target positions for an ability."""
        if ability.range == 0:
            return [card.position] if card.position is not None else []

        if card.position is None:
            return []

        base_targets = self._get_base_ability_targets(card, ability)

        custom_targeter = get_targeter(ability.id)
        if custom_targeter:
            return custom_targeter(self, card, ability, base_targets)

        return base_targets

    def _get_base_ability_targets(self, card: 'Card', ability: 'Ability') -> List[int]:
        """Get base targets filtered by range and target_type."""
        targets = []

        if ability.range == 1:
            cells = self.board.get_adjacent_cells(card.position, include_diagonals=True)
        else:
            cells = set()
            for pos in range(30):
                dist = self._get_distance(card.position, pos)
                chebyshev = self._get_chebyshev_distance(card.position, pos)
                if dist <= ability.range and chebyshev >= ability.min_range:
                    cells.add(pos)
            cells = list(cells)

        for pos in cells:
            target_card = self.board.get_card(pos)
            if target_card is None:
                continue

            if ability.target_type == TargetType.ENEMY and target_card.player != card.player:
                targets.append(pos)
            elif ability.target_type == TargetType.ALLY and target_card.player == card.player and target_card != card:
                targets.append(pos)
            elif ability.target_type == TargetType.ANY:
                targets.append(pos)

        if ability.can_target_flying:
            for flying_card in self.board.get_flying_cards():
                if flying_card.position is not None and flying_card.position not in targets:
                    if ability.target_type == TargetType.ENEMY and flying_card.player != card.player:
                        targets.append(flying_card.position)
                    elif ability.target_type == TargetType.ALLY and flying_card.player == card.player and flying_card != card:
                        targets.append(flying_card.position)
                    elif ability.target_type == TargetType.ANY:
                        targets.append(flying_card.position)

        return targets

    def select_ability_target(self, pos: int) -> bool:
        """Select a target for the pending ability."""
        if not self.awaiting_ability_target:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        target = self.board.get_card(pos)
        if not target:
            return False

        card = self.get_card_by_id(self.interaction.actor_id)
        ability_id = self.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        if not card or not ability:
            return False

        result = self._execute_ability(card, ability, target)
        self.cancel_ability()
        return result

    @property
    def awaiting_ability_target(self) -> bool:
        """Check if waiting for ability target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_ABILITY_TARGET

    def _execute_ability(self, card: 'Card', ability: 'Ability', target: 'Card') -> bool:
        """Execute an ability on a target."""
        # Reveal face-down target when targeted by ability
        if target.face_down:
            self.reveal_card(target)

        handler = get_handler(ability.id)
        if handler:
            return handler(self, card, target, ability)

        if ability.effect_type == EffectType.APPLY_WEBBED:
            if card != target:
                self.emit_arrow(card.position, target.position, 'ability')
            target.webbed = True
            self.log(f"{card.name} использует {ability.name}: {target.name} опутан!")
            self.emit_clear_arrows()
            card.tap()
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
            return True

        if ability.heal_amount > 0:
            if card != target:
                self.emit_arrow(card.position, target.position, 'heal')
            healed = target.heal(ability.heal_amount)
            self.log(f"{card.name} использует {ability.name}: {target.name} +{healed} HP")
            self.emit_heal(target.position, healed, card_id=target.id, source_id=card.id)
            self.emit_clear_arrows()

        if ability.ranged_damage:
            return self._ranged_attack(card, target, ability)

        if ability.ability_type == AbilityType.ACTIVE and ability.heal_amount > 0:
            card.tap()
            card.put_ability_on_cooldown(ability.id, ability.cooldown)

        return True

    def cancel_ability(self):
        """Cancel pending ability targeting."""
        if self.awaiting_ability_target or self.awaiting_counter_selection:
            self.interaction = None

    # =========================================================================
    # COUNTER SELECTION
    # =========================================================================

    @property
    def awaiting_counter_selection(self) -> bool:
        """Check if waiting for counter selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_COUNTERS

    @property
    def counter_selection_card(self) -> Optional['Card']:
        """Get the card for counter selection."""
        if self.awaiting_counter_selection and self.interaction:
            return self.get_card_by_id(self.interaction.actor_id)
        return None

    def set_counter_selection(self, count: int):
        """Set the number of counters to spend."""
        if not self.awaiting_counter_selection or not self.interaction:
            return
        card = self.get_card_by_id(self.interaction.actor_id)
        if not card:
            return
        max_counters = card.counters
        self.interaction.selected_amount = max(0, min(count, max_counters))

    def confirm_counter_selection(self) -> bool:
        """Confirm counter selection and proceed to target selection."""
        if not self.awaiting_counter_selection or not self.interaction:
            return False

        card = self.get_card_by_id(self.interaction.actor_id)
        ability_id = self.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        counters_spent = self.interaction.selected_amount

        if not card or not ability:
            self.cancel_ability()
            return False

        targets = self._get_ability_targets(card, ability)
        if not targets:
            self.log("Нет доступных целей!")
            self.cancel_ability()
            return False

        self.interaction = interaction_select_target(
            actor_id=card.id,
            ability_id=ability.id,
            valid_positions=tuple(targets),
            acting_player=card.player,
        )
        self.interaction.context['counters_spent'] = counters_spent
        self.log(f"Выберите цель для {ability.name} ({counters_spent} фишек)")
        return True

    # =========================================================================
    # LUNGE ATTACK
    # =========================================================================

    def _lunge_attack(self, attacker: 'Card', target: 'Card', ability: 'Ability') -> bool:
        """Execute a lunge attack (fixed damage, no counter)."""
        self.emit_arrow(attacker.position, target.position, 'attack')
        self.log(f"{attacker.name} бьёт через ряд")

        damage = ability.damage_amount if ability.damage_amount > 0 else 1
        dealt, webbed = self._deal_damage(target, damage)

        self.last_combat = CombatResult(
            attacker_roll=0, defender_roll=0,
            attacker_damage_dealt=dealt, defender_damage_dealt=0,
            attacker_name=attacker.name, defender_name=target.name,
            attacker_player=attacker.player, defender_player=target.player
        )

        if not webbed:
            self.emit_clear_arrows()
            self.log(f"  -> {target.name} получил {dealt} урона")
            if attacker.has_ability("lunge_front_buff"):
                self._apply_lunge_front_buff(attacker)
            self._process_heal_on_attack(attacker, target)

        self._handle_death(target, attacker)
        attacker.tap()
        self._check_winner()
        return True

    def _apply_lunge_front_buff(self, attacker: 'Card'):
        """Apply dice roll buff to allied creature in front."""
        from ..abilities import get_ability
        if attacker.position is None:
            return

        ability = get_ability("lunge_front_buff")
        if not ability:
            return

        col = attacker.position % 5
        row = attacker.position // 5

        if attacker.player == 1:
            front_row = row + 1
        else:
            front_row = row - 1

        if front_row < 0 or front_row > 5:
            return

        front_pos = front_row * 5 + col
        front_card = self.board.get_card(front_pos)

        if front_card and front_card.player == attacker.player:
            bonus = ability.ally_dice_bonus
            front_card.temp_dice_bonus += bonus
            self.log(f"  -> {front_card.name} получил ОвА (+{bonus} к броску)")

    # =========================================================================
    # RANGED ATTACK
    # =========================================================================

    def _ranged_attack(self, attacker: 'Card', target: 'Card', ability: 'Ability' = None) -> bool:
        """Execute a ranged attack."""
        ranged_type = ability.ranged_type if ability else "shot"
        arrow_type = 'throw' if ranged_type == "throw" else 'shot'
        self.emit_arrow(attacker.position, target.position, arrow_type)

        if ranged_type == "shot" and "shot_immune" in target.stats.ability_ids:
            self.log(f"{target.name} защищён от выстрелов!")
            self.emit_clear_arrows()
            attacker.tap()
            return True

        atk_roll = self.roll_dice()

        dice_context = DiceContext(
            type='ranged',
            attacker_id=attacker.id,
            atk_roll=atk_roll,
            target_id=target.id,
            ability_id=ability.id,
            ranged_type=ranged_type,
        )

        if self._enter_priority_phase(dice_context):
            return True

        return self._finish_ranged_attack(dice_context)

    def _finish_ranged_attack(self, dice_context: DiceContext) -> bool:
        """Finish ranged attack after priority phase."""
        attacker = self.board.get_card_by_id(dice_context.attacker_id)
        target = self.board.get_card_by_id(dice_context.target_id)
        if not attacker or not target:
            return False
        ability = get_ability(dice_context.ability_id) if dice_context.ability_id else None
        ranged_type = dice_context.ranged_type

        atk_roll = dice_context.atk_roll + dice_context.atk_modifier
        atk_roll = max(1, min(6, atk_roll))

        tier = self._get_attack_tier(atk_roll)
        tier_names = ["слабый", "средний", "сильный"]

        if ability and ability.ranged_damage:
            base_damage = ability.ranged_damage[tier]
        else:
            base_damage = attacker.get_effective_attack()[tier]

        defensive_bonus = self._get_ranged_defensive_bonus(attacker, target, ability)
        damage = base_damage + attacker.temp_ranged_bonus + defensive_bonus
        dealt, webbed = self._deal_damage(target, damage)

        self.last_combat = CombatResult(
            attacker_roll=atk_roll, defender_roll=0,
            attacker_damage_dealt=dealt, defender_damage_dealt=0,
            attacker_name=attacker.name, defender_name=target.name,
            attacker_player=attacker.player, defender_player=target.player
        )

        total_bonus = attacker.temp_ranged_bonus + defensive_bonus
        bonus_str = f" (+{total_bonus})" if total_bonus > 0 else ""
        action_verb = "метает в" if ranged_type == "throw" else "стреляет в"
        self.log(f"{attacker.name} {action_verb} {target.name} [{atk_roll}] - {tier_names[tier]}{bonus_str}")
        if not webbed:
            self.emit_clear_arrows()
            self.log(f"  -> {target.name} получил {dealt} урона")

        self._handle_death(target, attacker)
        attacker.tap()
        self._check_winner()
        return True

    # =========================================================================
    # MAGIC ATTACK
    # =========================================================================

    def _magic_attack(self, attacker: 'Card', target: 'Card', ability_id: str,
                       counters_spent: int = 0) -> bool:
        """Execute a magic attack with dice roll."""
        self.emit_arrow(attacker.position, target.position, 'magic')
        ability = get_ability(ability_id)

        if "magic_immune" in target.stats.ability_ids:
            self.log(f"{attacker.name} магический удар!")
            self.log(f"  -> {target.name}: защита от магии!")
            self.emit_clear_arrows()
            if counters_spent > 0:
                attacker.counters -= counters_spent
            self.last_combat = CombatResult(0, 0, 0, 0, attacker_name=attacker.name, defender_name=target.name,
                                           attacker_player=attacker.player, defender_player=target.player)
            attacker.tap()
            self._check_winner()
            return True

        atk_roll = self.roll_dice()

        dice_context = DiceContext(
            type='magic',
            attacker_id=attacker.id,
            atk_roll=atk_roll,
            target_id=target.id,
            ability_id=ability_id,
            extra={'counters_spent': counters_spent} if counters_spent > 0 else None,
        )

        if self._enter_priority_phase(dice_context):
            return True

        return self._finish_magic_attack(dice_context)

    def _finish_magic_attack(self, dice_context: DiceContext) -> bool:
        """Finish magic attack after priority phase."""
        attacker = self.board.get_card_by_id(dice_context.attacker_id)
        target = self.board.get_card_by_id(dice_context.target_id)
        if not attacker or not target:
            return False

        ability = get_ability(dice_context.ability_id) if dice_context.ability_id else None
        counters_spent = dice_context.extra.get('counters_spent', 0) if dice_context.extra else 0

        atk_roll = dice_context.atk_roll + dice_context.atk_modifier
        atk_roll = max(1, min(6, atk_roll))

        tier = self._get_attack_tier(atk_roll)
        tier_names = ["слабый", "средний", "сильный"]

        if ability and ability.magic_damage:
            base_damage = ability.magic_damage[tier]
        else:
            base_damage = 2

        counter_bonus = 0
        if ability and ability.magic_counter_bonus > 0 and counters_spent > 0:
            counter_bonus = ability.magic_counter_bonus * counters_spent
            attacker.counters -= counters_spent

        total_damage = base_damage + counter_bonus

        # Apply hit damage reduction (diagonal_defense, etc.)
        hit_reduction = self._get_hit_damage_reduction(target, attacker)
        initial_damage = total_damage
        if hit_reduction > 0 and total_damage > 0:
            total_damage = max(0, total_damage - hit_reduction)

        if counter_bonus > 0:
            self.log(f"{attacker.name} маг. удар [{atk_roll}] - {tier_names[tier]}: {base_damage}+{counters_spent} = {initial_damage}")
        else:
            self.log(f"{attacker.name} магический удар [{atk_roll}] - {tier_names[tier]}")

        if hit_reduction > 0 and total_damage < initial_damage:
            self.log(f"  [{target.name}: {initial_damage}-{hit_reduction}={total_damage}]")

        dealt, webbed = self._deal_damage(target, total_damage, is_magical=True)
        if not webbed:
            self.emit_clear_arrows()
            self.log(f"  -> {target.name}: -{dealt} HP (магия)")

        self.last_combat = CombatResult(
            attacker_roll=atk_roll, defender_roll=0,
            attacker_damage_dealt=dealt, defender_damage_dealt=0,
            attacker_name=attacker.name, defender_name=target.name,
            attacker_player=attacker.player, defender_player=target.player
        )
        self._handle_death(target, attacker)
        attacker.tap()
        self._check_winner()
        return True
