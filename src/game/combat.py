"""Combat system - attacks, damage calculation, dice rolls."""
import random
from typing import List, Tuple, Optional, TYPE_CHECKING

from .base import CombatResult, DiceContext
from ..abilities import get_ability, AbilityType, AbilityTrigger
from ..ability_handlers import get_trigger_handler
from ..interaction import interaction_select_defender, interaction_choose_exchange
from ..commands import evt_dice_rolled

if TYPE_CHECKING:
    from ..card import Card


class CombatMixin:
    """Mixin for combat-related functionality."""

    # =========================================================================
    # DICE ROLLING
    # =========================================================================

    def roll_dice(self) -> int:
        """Roll a D6."""
        if self._pending_rolls:
            return self._pending_rolls.pop(0)
        return random.randint(1, 6)

    def inject_rolls(self, rolls: List[int]):
        """Inject dice rolls for server-authoritative gameplay."""
        self._pending_rolls.extend(rolls)

    def clear_pending_rolls(self):
        """Clear any unused injected rolls."""
        self._pending_rolls.clear()

    def _get_attack_tier(self, roll: int) -> int:
        """Get attack tier from roll. Returns 0=weak, 1=medium, 2=strong."""
        if roll >= 6:
            return 2
        elif roll >= 4:
            return 1
        return 0

    def _get_opposed_tiers(self, roll_diff: int, atk_roll: int = 0) -> Tuple[int, int, bool]:
        """Get attack and counter tiers from roll difference."""
        if roll_diff >= 5:
            return 2, -1, False
        elif roll_diff == 4:
            return 2, 0, True
        elif roll_diff == 3:
            return 1, -1, False
        elif roll_diff == 2:
            return 1, 0, True
        elif roll_diff == 1:
            return 0, -1, False
        elif roll_diff == 0:
            if atk_roll >= 5:
                return -1, 0, False
            else:
                return 0, -1, False
        elif roll_diff == -1:
            return 0, -1, False
        elif roll_diff == -2:
            return -1, -1, False
        elif roll_diff == -3:
            return -1, 0, False
        elif roll_diff == -4:
            return 0, 1, True
        return -1, 1, False

    # =========================================================================
    # DAMAGE CALCULATION
    # =========================================================================

    def calculate_damage_vs_tapped_with_tier(self, atk_roll: int, attacker: 'Card',
                                              defender: 'Card' = None) -> Tuple[int, str, int]:
        """Calculate damage vs tapped card. Returns (damage, tier_name, tier)."""
        tier_names = ["слабая", "средняя", "сильная"]
        tier = self._get_attack_tier(atk_roll)
        damage = attacker.get_effective_attack()[tier] + self._get_positional_damage_modifier(attacker, tier)
        damage += self._get_formation_attack_bonus(attacker)
        if attacker.has_ability("tapped_bonus"):
            damage += 1
        if attacker.has_ability("closed_attack_bonus"):
            damage += 1
        if defender:
            damage += self._get_element_damage_bonus(attacker, defender)
        damage = max(0, damage)
        return damage, tier_names[tier], tier

    def calculate_damage_vs_tapped(self, atk_roll: int, attacker: 'Card',
                                    defender: 'Card' = None) -> int:
        """Calculate damage vs tapped card."""
        damage, _, _ = self.calculate_damage_vs_tapped_with_tier(atk_roll, attacker, defender)
        return damage

    def _get_formation_attack_bonus(self, card: 'Card') -> int:
        """Get formation attack bonus for a card."""
        if not card.in_formation:
            return 0
        bonus = 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_formation and ability.formation_attack_bonus > 0:
                bonus += ability.formation_attack_bonus
        return bonus

    def calculate_damage_with_tier(self, roll_diff: int, attacker: 'Card', defender: 'Card',
                                    defender_can_counter: bool, atk_roll: int = 0) -> Tuple:
        """Calculate damage from opposed roll."""
        tier_names = ["слабая", "средняя", "сильная"]
        atk = attacker.get_effective_attack()
        def_atk = defender.get_effective_attack()

        atk_tier, def_tier, is_exchange = self._get_opposed_tiers(roll_diff, atk_roll)

        if atk_tier >= 0:
            damage_to_defender = atk[atk_tier] + self._get_positional_damage_modifier(attacker, atk_tier)
            damage_to_defender += self._get_element_damage_bonus(attacker, defender)
            damage_to_defender += self._get_formation_attack_bonus(attacker)
            damage_to_defender = max(0, damage_to_defender)
            atk_tier_name = tier_names[atk_tier]
        else:
            damage_to_defender = 0
            atk_tier_name = "промах"

        damage_to_attacker = 0
        def_tier_name = ""
        if defender_can_counter and def_tier >= 0:
            damage_to_attacker = def_atk[def_tier] + self._get_positional_damage_modifier(defender, def_tier)
            damage_to_attacker += self._get_element_damage_bonus(defender, attacker)
            damage_to_attacker += self._get_formation_attack_bonus(defender)
            damage_to_attacker = max(0, damage_to_attacker)
            def_tier_name = tier_names[def_tier]

        return damage_to_defender, damage_to_attacker, atk_tier_name, def_tier_name, atk_tier, def_tier, is_exchange

    def calculate_damage(self, roll_diff: int, attacker: 'Card', defender: 'Card',
                         defender_can_counter: bool, atk_roll: int = 0) -> Tuple[int, int]:
        """Calculate damage from opposed roll."""
        dmg_def, dmg_atk, _, _, _, _, _ = self.calculate_damage_with_tier(
            roll_diff, attacker, defender, defender_can_counter, atk_roll)
        return dmg_def, dmg_atk

    def get_display_attack(self, card: 'Card') -> Tuple[int, int, int]:
        """Get attack values for display, including all bonuses."""
        base = card.get_effective_attack()
        bonuses = [0, 0, 0]
        col = self._get_card_column(card)

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                if ability.is_formation and card.in_formation:
                    for i in range(3):
                        bonuses[i] += ability.formation_attack_bonus

                if ability_id == "edge_column_attack" and col in (0, 4):
                    bonuses[1] += 1
                    bonuses[2] += 1

        return (base[0] + bonuses[0], base[1] + bonuses[1], base[2] + bonuses[2])

    # =========================================================================
    # ATTACK INITIATION
    # =========================================================================

    def attack(self, attacker: 'Card', target_pos: int) -> bool:
        """Initiate attack."""
        self.last_combat = None

        if self.has_blocking_interaction:
            return False

        if not attacker:
            return False

        # Reveal face-down attacker when they act
        if attacker.face_down:
            self.reveal_card(attacker)

        target = self.board.get_card(target_pos)
        if not target:
            return False

        if attacker.can_attack_flyer and target.stats.is_flying:
            attacker.can_attack_flyer = False
            attacker.can_attack_flyer_until_turn = 0
            self.log(f"{attacker.name} использует подготовленную атаку!")

        self.emit_clear_arrows_immediate()
        self.emit_arrow(attacker.position, target_pos, 'attack')

        if target.player == attacker.player:
            if self.friendly_fire_target == target_pos:
                self.friendly_fire_target = None
                self.log(f"{attacker.name} атакует союзника {target.name}!")
                return self._resolve_combat(attacker, target)
            else:
                self.friendly_fire_target = target_pos
                self.log(f"Атаковать союзника {target.name}? Нажмите ещё раз для подтверждения.")
                return True

        self.friendly_fire_target = None

        valid_defenders = []
        has_direct = attacker.has_direct or self._has_direct_attack(attacker)
        if attacker.has_ability("tapped_bonus") and target.tapped:
            has_direct = True
        if has_direct:
            self.log(f"  [{attacker.name}: направленный удар]")
        else:
            valid_defenders = self.board.get_valid_defenders(attacker, target)

        if valid_defenders:
            self.interaction = interaction_select_defender(
                attacker_id=attacker.id,
                target_id=target.id,
                valid_defender_ids=tuple(d.id for d in valid_defenders),
                valid_positions=tuple(d.position for d in valid_defenders if d.position is not None),
                defending_player=target.player,
            )
            self.log(f"{attacker.name} атакует {target.name}!")
            self.log(f"Игрок {target.player}: выберите защитника")
            return True
        else:
            # Reveal face-down target when directly attacked (no defender)
            if target.face_down:
                self.reveal_card(target)
            return self._resolve_combat(attacker, target)

    def choose_defender(self, defender: 'Card') -> bool:
        """Defender player chooses to intercept."""
        if not self.awaiting_defender:
            return False

        if not self.interaction.can_select_card_id(defender.id):
            return False

        attacker = self.get_card_by_id(self.interaction.actor_id)
        if not attacker:
            return False

        # Reveal face-down defender when they intercept
        if defender.face_down:
            self.reveal_card(defender)

        self.log(f"{defender.name} перехватывает атаку!")

        # Redirect arrow to defender
        self.emit_clear_arrows()
        self.emit_arrow(attacker.position, defender.position, 'attack')

        self._process_defender_triggers(defender, attacker)
        self.interaction = None

        result = self._resolve_combat(attacker, defender)

        if defender.is_alive and "defender_no_tap" not in defender.stats.ability_ids:
            defender.tap()

        return result

    def skip_defender(self) -> bool:
        """Defender player chooses not to intercept."""
        if not self.awaiting_defender:
            return False

        attacker = self.get_card_by_id(self.interaction.actor_id)
        target = self.get_card_by_id(self.interaction.target_id)
        if not attacker or not target:
            self.interaction = None
            return False
        self.log("Защита не выставлена.")

        # Reveal face-down target when no defender intercepts
        if target.face_down:
            self.reveal_card(target)

        self.interaction = None
        return self._resolve_combat(attacker, target)

    # =========================================================================
    # COMBAT RESOLUTION
    # =========================================================================

    def _resolve_combat(self, attacker: 'Card', defender: 'Card') -> bool:
        """Resolve combat between attacker and defender."""
        if defender.webbed:
            dealt, _ = self._deal_damage(defender, 0)
            self.last_combat = CombatResult(0, 0, 0, 0, attacker_name=attacker.name, defender_name=defender.name,
                                           attacker_player=attacker.player, defender_player=defender.player)
            attacker.tap()
            self._check_winner()
            return True

        atk_roll = self.roll_dice()
        def_roll = 0 if defender.tapped else self.roll_dice()
        atk_bonus = self._get_attack_dice_bonus(attacker, defender)
        def_bonus = 0 if defender.tapped else self._get_defense_dice_bonus(defender)

        self.log(f"{attacker.name} [{atk_roll}] vs {defender.name} [{def_roll}]")
        self.emit_event(evt_dice_rolled(attacker.id, defender.id, atk_roll, def_roll))

        atk_values = attacker.get_effective_attack()
        atk_is_constant = atk_values[0] == atk_values[1] == atk_values[2]
        def_values = defender.get_effective_attack()
        def_is_constant = def_values[0] == def_values[1] == def_values[2]
        dice_matter = not (atk_is_constant and (defender.tapped or def_is_constant))

        dice_context = DiceContext(
            type='combat',
            attacker_id=attacker.id,
            atk_roll=atk_roll,
            atk_bonus=atk_bonus,
            defender_id=defender.id,
            def_roll=def_roll,
            def_bonus=def_bonus,
            dice_matter=dice_matter,
            defender_was_tapped=defender.tapped,
        )

        if not dice_matter:
            self.log("  [Броски не влияют на исход]")
        elif self._enter_priority_phase(dice_context):
            return True

        return self._finish_combat(dice_context)

    def _finish_combat(self, dice_context: DiceContext, force_reduced: bool = False) -> bool:
        """Finish combat after priority phase."""
        attacker = self.board.get_card_by_id(dice_context.attacker_id)
        defender = self.board.get_card_by_id(dice_context.defender_id)
        if not attacker or not defender:
            self.pending_dice_roll = None
            return False
        atk_roll = dice_context.atk_roll + dice_context.atk_modifier
        atk_bonus = dice_context.atk_bonus
        def_roll = dice_context.def_roll + dice_context.def_modifier
        def_bonus = dice_context.def_bonus

        self.pending_dice_roll = None
        defender_was_tapped = dice_context.defender_was_tapped

        if defender_was_tapped:
            total_roll = atk_roll + atk_bonus
            dmg_to_def, atk_strength, atk_tier = self.calculate_damage_vs_tapped_with_tier(total_roll, attacker, defender)
            dmg_to_atk = 0
            def_strength = ""
            def_tier = -1
            is_exchange = False
        else:
            total_atk = atk_roll + atk_bonus
            roll_diff = total_atk - (def_roll + def_bonus)
            dmg_to_def, dmg_to_atk, atk_strength, def_strength, atk_tier, def_tier, is_exchange = self.calculate_damage_with_tier(
                roll_diff, attacker, defender, True, total_atk
            )

            if is_exchange and not force_reduced and not self.awaiting_exchange_choice and not dice_context.exchange_resolved:
                choosing_player = attacker.player if roll_diff > 0 else defender.player
                self.interaction = interaction_choose_exchange(
                    attacker_id=attacker.id,
                    defender_id=defender.id,
                    full_damage=dmg_to_def,
                    reduced_damage=dmg_to_def - 1 if dmg_to_def > 0 else 0,
                    acting_player=choosing_player,
                )
                self.pending_dice_roll = dice_context
                self.interaction.context['attacker_advantage'] = roll_diff > 0
                self.interaction.context['roll_diff'] = roll_diff
                tier_names = ["слабая", "средняя", "сильная"]

                if roll_diff > 0:
                    reduced_tier = atk_tier - 1
                    self.log(f"Обмен ударами! {atk_strength} + контратака")
                    self.log(f"Можете ослабить до {tier_names[reduced_tier]} без контратаки")
                else:
                    reduced_tier = def_tier - 1
                    self.log(f"Обмен ударами! {def_strength} контратака + {atk_strength} атака")
                    self.log(f"Защитник может ослабить до {tier_names[reduced_tier]} без удара атакующего")
                return False

            if force_reduced and is_exchange:
                tier_names = ["слабая", "средняя", "сильная"]
                if roll_diff > 0:
                    atk_tier -= 1
                    atk_strength = tier_names[atk_tier]
                    atk = attacker.get_effective_attack()
                    dmg_to_def = atk[atk_tier] + self._get_positional_damage_modifier(attacker, atk_tier)
                    dmg_to_def += self._get_formation_attack_bonus(attacker)
                    dmg_to_def = max(0, dmg_to_def)
                    dmg_to_atk = 0
                    def_strength = ""
                    def_tier = -1
                else:
                    def_tier -= 1
                    def_strength = tier_names[def_tier]
                    def_atk = defender.get_effective_attack()
                    dmg_to_atk = def_atk[def_tier] + self._get_positional_damage_modifier(defender, def_tier)
                    dmg_to_atk += self._get_formation_attack_bonus(defender)
                    dmg_to_atk = max(0, dmg_to_atk)
                    dmg_to_def = 0
                    atk_strength = "промах"
                    atk_tier = -1

        # Anti-magic bonus
        anti_magic_bonus = 0
        if attacker.has_ability("anti_magic") and self._has_magic_abilities(defender):
            anti_magic_bonus = 1
            dmg_to_def += 1
            self.log(f"  [{attacker.name}: +1 урон vs магия]")

        initial_dmg_to_def = dmg_to_def
        initial_dmg_to_atk = dmg_to_atk

        # Damage reductions
        def_reduction = self._get_damage_reduction(defender, attacker, atk_tier)
        reduced_def = False
        if def_reduction > 0 and dmg_to_def > 0:
            dmg_to_def = max(0, dmg_to_def - def_reduction)
            if dmg_to_def < initial_dmg_to_def:
                reduced_def = True

        atk_reduction = self._get_damage_reduction(attacker, defender, def_tier)
        reduced_atk = False
        if atk_reduction > 0 and dmg_to_atk > 0:
            dmg_to_atk = max(0, dmg_to_atk - atk_reduction)
            if dmg_to_atk < initial_dmg_to_atk:
                reduced_atk = True

        # Apply damage
        dealt, _ = self._deal_damage(defender, dmg_to_def, source_id=attacker.id)
        attacker.take_damage(dmg_to_atk)
        self.emit_damage(attacker.position, dmg_to_atk, card_id=attacker.id, source_id=defender.id)
        self.emit_clear_arrows()

        self.last_combat = CombatResult(
            attacker_roll=atk_roll, defender_roll=def_roll,
            attacker_damage_dealt=dealt, defender_damage_dealt=dmg_to_atk,
            attacker_bonus=atk_bonus, defender_bonus=def_bonus,
            attacker_name=attacker.name, defender_name=defender.name,
            attacker_player=attacker.player, defender_player=defender.player
        )

        # Log results
        atk_bonus_str = f"+{atk_bonus}" if atk_bonus > 0 else ""
        def_bonus_str = f"+{def_bonus}" if def_bonus > 0 else ""
        strength_str = f" ({atk_strength})" if atk_strength else " (промах)"
        self.log(f"[{atk_roll}{atk_bonus_str}] vs [{def_roll}{def_bonus_str}]{strength_str}")
        if reduced_def:
            self.log(f"  [{defender.name}: {initial_dmg_to_def}-{def_reduction}={dmg_to_def}]")
        if reduced_atk:
            self.log(f"  [{attacker.name}: {initial_dmg_to_atk}-{atk_reduction}={dmg_to_atk}]")
        if dealt > 0:
            self.log(f"  -> {defender.name}: -{dealt} HP")
        elif reduced_def:
            self.log(f"  -> {defender.name}: 0 урона")
        if dmg_to_atk > 0:
            self.log(f"  -> {attacker.name}: -{dmg_to_atk} HP")
        if def_strength:
            self.log(f"  <- контратака: {def_strength}")

        # Post-combat triggers
        if attacker.is_alive:
            self._process_counter_shot(attacker, defender)

        if attacker.is_alive:
            self._process_heal_on_attack(attacker, defender)

        if attacker.is_alive and defender.is_alive:
            attack_hit = atk_tier >= 0
            self._process_hellish_stench(attacker, defender, defender_was_tapped, attack_hit)

        # Handle deaths
        self._handle_death(defender, attacker)

        if not self._handle_death(attacker, defender):
            attacker.tap()

        self._update_forced_attackers()
        self._check_winner()
        return True

    def _process_defender_triggers(self, defender: 'Card', attacker: 'Card' = None):
        """Process ON_DEFEND triggered abilities."""
        ctx = {'attacker': attacker}
        for ability_id in defender.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.trigger != AbilityTrigger.ON_DEFEND:
                continue

            handler = get_trigger_handler(ability_id)
            if handler:
                handler(self, defender, ability, ctx)

    def continue_after_priority(self) -> bool:
        """Continue combat/action after priority phase resolves."""
        if not self.pending_dice_roll:
            return False

        dice_context = self.pending_dice_roll
        if dice_context.type == 'combat':
            return self._finish_combat(dice_context)
        elif dice_context.type == 'ranged':
            return self._finish_ranged_attack(dice_context)
        elif dice_context.type == 'magic':
            return self._finish_magic_attack(dice_context)
        return False

    def resolve_exchange_choice(self, reduce_damage: bool) -> bool:
        """Handle player's choice during exchange."""
        if not self.awaiting_exchange_choice:
            return False

        dice_context = self.pending_dice_roll
        if not dice_context:
            self.interaction = None
            return False
        dice_context.exchange_resolved = True
        self.interaction = None

        if reduce_damage:
            self.log("Выбрано: ослабить удар")
        else:
            self.log("Выбрано: полный удар с контратакой")

        return self._finish_combat(dice_context, force_reduced=reduce_damage)

    @property
    def awaiting_exchange_choice(self) -> bool:
        """Check if waiting for exchange choice."""
        from ..interaction import InteractionKind
        return self.interaction is not None and self.interaction.kind == InteractionKind.CHOOSE_EXCHANGE
