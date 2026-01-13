"""Combat triggers - counter shot, movement shot, heal on attack, stench."""
from typing import Optional, TYPE_CHECKING

from ..abilities import get_ability
from ..interaction import (
    InteractionKind, interaction_counter_shot, interaction_movement_shot,
    interaction_confirm_heal, interaction_choose_stench
)

if TYPE_CHECKING:
    from ..card import Card


class TriggersMixin:
    """Mixin for combat-triggered abilities."""

    # =========================================================================
    # COUNTER SHOT
    # =========================================================================

    def _process_counter_shot(self, attacker: 'Card', original_target: 'Card'):
        """Process counter_shot ability."""
        if "counter_shot" not in attacker.stats.ability_ids:
            return

        if attacker.position is None:
            return

        valid_targets = []
        for card in self.board.get_all_cards():
            if not card.is_alive or card.position is None or card == attacker:
                continue
            if self._get_chebyshev_distance(attacker.position, card.position) >= 2:
                valid_targets.append(card.position)

        for flying_card in self.board.get_flying_cards():
            if flying_card.is_alive and flying_card.position not in valid_targets:
                valid_targets.append(flying_card.position)

        if not valid_targets:
            return

        self.interaction = interaction_counter_shot(
            shooter_id=attacker.id,
            valid_positions=tuple(valid_targets),
            acting_player=attacker.player,
        )
        self.log(f"{attacker.name}: выберите цель для выстрела")

    def select_counter_shot_target(self, pos: int) -> bool:
        """Player selects target for counter shot."""
        if not self.awaiting_counter_shot:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        attacker = self.get_card_by_id(self.interaction.actor_id)
        target = self.board.get_card(pos)

        if not target:
            return False

        self.emit_arrow(attacker.position, target.position, 'shot')

        if "shot_immune" in target.stats.ability_ids:
            self.log(f"{target.name} защищён от выстрелов!")
            self.emit_clear_arrows()
        else:
            ability = get_ability("counter_shot")
            damage = ability.damage_amount if ability else 2
            dealt, _ = self._deal_damage(target, damage)
            if dealt > 0:
                self.log(f"  -> {attacker.name} выстрел: {target.name} -{dealt} HP")
            self._handle_death(target, attacker)
            self._check_winner()
            self.emit_clear_arrows()

        self.interaction = None
        return True

    @property
    def awaiting_counter_shot(self) -> bool:
        """Check if waiting for counter shot target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_COUNTER_SHOT

    # =========================================================================
    # MOVEMENT SHOT
    # =========================================================================

    def _process_movement_shot(self, card: 'Card'):
        """Process movement_shot ability."""
        if "movement_shot" not in card.stats.ability_ids:
            return
        if card.position is None or card.tapped:
            return

        has_expensive_ally = False
        for adj_pos in self.board.get_adjacent_cells(card.position, include_diagonals=False):
            adj_card = self.board.get_card(adj_pos)
            if adj_card and adj_card.player == card.player and adj_card.stats.cost >= 7:
                has_expensive_ally = True
                break

        if not has_expensive_ally:
            return

        valid_targets = []
        for target_card in self.board.get_all_cards(include_flying=False):
            if not target_card.is_alive or target_card.position is None or target_card == card:
                continue
            if target_card.player == card.player:
                continue
            manhattan = self._get_distance(card.position, target_card.position)
            chebyshev = self._get_chebyshev_distance(card.position, target_card.position)
            if manhattan <= 3 and chebyshev >= 2:
                valid_targets.append(target_card.position)

        for target_card in self.board.get_flying_cards():
            if target_card.is_alive and target_card.player != card.player and target_card.position not in valid_targets:
                valid_targets.append(target_card.position)

        if not valid_targets:
            return

        self.interaction = interaction_movement_shot(
            shooter_id=card.id,
            valid_positions=tuple(valid_targets),
            acting_player=card.player,
        )
        self.log(f"{card.name}: можно выстрелить (необязательно)")

    def select_movement_shot_target(self, pos: int) -> bool:
        """Player selects target for movement shot."""
        if not self.awaiting_movement_shot:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        shooter = self.get_card_by_id(self.interaction.actor_id)
        target = self.board.get_card(pos)

        if not target or not shooter:
            return False

        self.emit_arrow(shooter.position, target.position, 'shot')

        if "shot_immune" in target.stats.ability_ids:
            self.log(f"{target.name} защищён от выстрелов!")
            self.emit_clear_arrows()
        else:
            dealt, _ = self._deal_damage(target, 1)
            if dealt > 0:
                self.log(f"  -> {shooter.name} выстрел: {target.name} -{dealt} HP")
            self._handle_death(target, shooter)
            self._check_winner()
            self.emit_clear_arrows()

        self.interaction = None
        return True

    def skip_movement_shot(self):
        """Skip the movement shot opportunity."""
        if self.awaiting_movement_shot:
            shooter = self.get_card_by_id(self.interaction.actor_id)
            if shooter:
                self.log(f"{shooter.name}: выстрел пропущен")
            self.interaction = None

    @property
    def awaiting_movement_shot(self) -> bool:
        """Check if waiting for movement shot target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_MOVEMENT_SHOT

    # =========================================================================
    # HEAL ON ATTACK
    # =========================================================================

    def _process_heal_on_attack(self, attacker: 'Card', target: 'Card'):
        """Process heal_on_attack ability."""
        if "heal_on_attack" not in attacker.stats.ability_ids:
            return
        if not attacker.is_alive or attacker.position is None:
            return

        front_offset = 5 if attacker.player == 1 else -5
        front_pos = attacker.position + front_offset

        if front_pos < 0 or front_pos >= 30:
            return

        front_card = self.board.get_card(front_pos)
        if not front_card:
            return

        heal_amount = front_card.stats.attack[1]
        if heal_amount <= 0:
            return
        if attacker.curr_life >= attacker.life:
            return

        self.interaction = interaction_confirm_heal(
            healer_id=attacker.id,
            target_id=front_card.id,
            heal_amount=heal_amount,
            acting_player=attacker.player,
        )
        self.log(f"{attacker.name}: лечиться на {heal_amount}? (напротив: {front_card.name})")

    def confirm_heal_on_attack(self, accept: bool) -> bool:
        """Player confirms or declines optional heal."""
        if not self.awaiting_heal_confirm:
            return False
        attacker = self.get_card_by_id(self.interaction.actor_id)
        heal_amount = self.interaction.context.get('heal_amount', 0)
        if not attacker:
            return False
        if accept and attacker.is_alive:
            healed = attacker.heal(heal_amount)
            if healed > 0:
                self.emit_heal(attacker.position, healed, card_id=attacker.id, source_id=attacker.id)
                self.log(f"  -> {attacker.name} +{healed} HP")
        else:
            self.log(f"  -> {attacker.name} отказался от лечения")
        self.interaction = None
        return True

    @property
    def awaiting_heal_confirm(self) -> bool:
        """Check if waiting for heal confirmation."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.CONFIRM_HEAL

    # =========================================================================
    # HELLISH STENCH
    # =========================================================================

    def _process_hellish_stench(self, attacker: 'Card', target: 'Card',
                                 was_target_tapped: bool, attack_hit: bool):
        """Process hellish_stench ability."""
        if "hellish_stench" not in attacker.stats.ability_ids:
            return
        if was_target_tapped:
            return
        if not attack_hit:
            return
        if not target.is_alive or target.position is None:
            return
        if target.tapped:
            return

        ability = get_ability("hellish_stench")
        damage = ability.damage_amount if ability else 2

        self.interaction = interaction_choose_stench(
            target_id=target.id,
            damage_amount=damage,
            acting_player=target.player,
        )
        self.interaction.context['attacker_id'] = attacker.id
        self.log(f"{attacker.name}: Адское зловоние! {target.name} закрывается или получает {damage} урона")

    def resolve_stench_choice(self, tap: bool) -> bool:
        """Target's controller chooses: tap or take damage."""
        if not self.awaiting_stench_choice:
            return False

        attacker = self.get_card_by_id(self.interaction.context.get('attacker_id'))
        target = self.get_card_by_id(self.interaction.target_id)
        damage = self.interaction.context.get('damage_amount', 2)

        if not target:
            self.interaction = None
            return False

        if tap:
            target.tap()
            self.log(f"  -> {target.name} закрывается от зловония")
        else:
            dealt, _ = self._deal_damage(target, damage)
            self.log(f"  -> {target.name} получил {dealt} урона от зловония")
            self._handle_death(target, attacker)
            self._check_winner()

        self.interaction = None
        return True

    @property
    def awaiting_stench_choice(self) -> bool:
        """Check if waiting for stench choice."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.CHOOSE_STENCH
