"""Utility methods for game logic - formations, damage, distances, etc."""
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..card import Card
    from ..abilities import Ability


class HelpersMixin:
    """Mixin providing utility methods used by other game mixins."""

    # =========================================================================
    # POSITION & DISTANCE HELPERS
    # =========================================================================

    def _get_orthogonal_neighbors(self, pos: int) -> List[int]:
        """Get orthogonally adjacent positions (up/down/left/right, not diagonal)."""
        col, row = pos % 5, pos // 5
        neighbors = []
        for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nc, nr = col + dc, row + dr
            if 0 <= nc < 5 and 0 <= nr < 6:
                neighbors.append(nr * 5 + nc)
        return neighbors

    def _get_distance(self, pos1: int, pos2: int) -> int:
        """Get Manhattan distance between two positions."""
        col1, row1 = pos1 % 5, pos1 // 5
        col2, row2 = pos2 % 5, pos2 // 5
        return abs(col1 - col2) + abs(row1 - row2)

    def _get_chebyshev_distance(self, pos1: int, pos2: int) -> int:
        """Get Chebyshev distance (max of horizontal/vertical)."""
        col1, row1 = pos1 % 5, pos1 // 5
        col2, row2 = pos2 % 5, pos2 // 5
        return max(abs(col1 - col2), abs(row1 - row2))

    def _get_card_column(self, card: 'Card') -> int:
        """Get column (0-4) for a card, or -1 if not on ground board."""
        if card.position is None or card.position >= 30:
            return -1
        return card.position % 5

    def _get_card_row(self, card: 'Card') -> int:
        """Get row (0-5) for a card, or -1 if not on ground board."""
        if card.position is None or card.position >= 30:
            return -1
        return card.position // 5

    def _is_in_own_row(self, card: 'Card', row_num: int) -> bool:
        """Check if card is in the Nth row from its home edge (0=home, 1=middle, 2=enemy)."""
        if card.position is None or card.position >= 30:
            return False
        row = card.position // 5
        if card.player == 1:
            return row == row_num  # P1: row 0 is home, row 2 is enemy front
        else:
            return row == (5 - row_num)  # P2: row 5 is home, row 3 is enemy front

    def _get_opposite_position(self, card: 'Card') -> Optional[int]:
        """Get position directly opposite (same column, adjacent row toward enemy)."""
        if card.position is None:
            return None
        col = card.position % 5
        row = card.position // 5
        if card.player == 1:
            opp_row = row + 1  # P1 faces up
        else:
            opp_row = row - 1  # P2 faces down
        if 0 <= opp_row <= 5:
            return opp_row * 5 + col
        return None

    def _is_diagonal_attack(self, attacker: 'Card', defender: 'Card') -> bool:
        """Check if attack is diagonal. Flying attacks are never diagonal."""
        if attacker.position is None or defender.position is None:
            return False
        if attacker.position >= 30 or defender.position >= 30:
            return False
        atk_col, atk_row = attacker.position % 5, attacker.position // 5
        def_col, def_row = defender.position % 5, defender.position // 5
        return atk_col != def_col and atk_row != def_row

    # =========================================================================
    # FORMATION HELPERS
    # =========================================================================

    def _has_formation_ability(self, card: 'Card') -> bool:
        """Check if card has any formation ability."""
        from ..abilities import get_ability
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_formation:
                return True
        return False

    def _has_elite_ally_in_formation(self, card: 'Card') -> bool:
        """Check if card has an elite formation partner."""
        if card.position is None:
            return False
        for neighbor_pos in self._get_orthogonal_neighbors(card.position):
            neighbor = self.board.get_card(neighbor_pos)
            if neighbor and neighbor.player == card.player and neighbor.is_alive:
                if self._has_formation_ability(neighbor) and neighbor.stats.is_elite:
                    return True
        return False

    def _has_common_ally_in_formation(self, card: 'Card') -> bool:
        """Check if card has a common (non-elite) formation partner."""
        if card.position is None:
            return False
        for neighbor_pos in self._get_orthogonal_neighbors(card.position):
            neighbor = self.board.get_card(neighbor_pos)
            if neighbor and neighbor.player == card.player and neighbor.is_alive:
                if self._has_formation_ability(neighbor) and not neighbor.stats.is_elite:
                    return True
        return False

    def recalculate_formations(self):
        """Recalculate formation status for all cards on board."""
        all_cards = self.board.get_all_cards(include_flying=False)

        # Clear and track previous state
        old_state = {}
        for card in all_cards:
            old_state[card.id] = (card.in_formation, card.formation_armor_remaining)
            card.in_formation = False

        # Check each card with formation ability
        for card in all_cards:
            if card.position is None or not card.is_alive:
                continue
            if not self._has_formation_ability(card):
                continue

            for neighbor_pos in self._get_orthogonal_neighbors(card.position):
                neighbor = self.board.get_card(neighbor_pos)
                if neighbor and neighbor.player == card.player and neighbor.is_alive:
                    if self._has_formation_ability(neighbor):
                        card.in_formation = True
                        neighbor.in_formation = True
                        break

        # Update formation armor
        for card in all_cards:
            was_in, _ = old_state.get(card.id, (False, 0))
            if card.in_formation:
                new_bonus = self._get_formation_armor_bonus(card)
                if not was_in or new_bonus != card.formation_armor_max:
                    card.formation_armor_remaining = new_bonus
                    card.formation_armor_max = new_bonus
            else:
                card.formation_armor_remaining = 0
                card.formation_armor_max = 0

    def _get_formation_armor_bonus(self, card: 'Card') -> int:
        """Get armor bonus from formation abilities."""
        from ..abilities import get_ability
        bonus = 0
        if not card.in_formation:
            return 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_formation and ability.formation_armor_bonus > 0:
                if ability.requires_elite_ally:
                    if self._has_elite_ally_in_formation(card):
                        bonus += ability.formation_armor_bonus
                elif ability.requires_common_ally:
                    if self._has_common_ally_in_formation(card):
                        bonus += ability.formation_armor_bonus
                else:
                    bonus += ability.formation_armor_bonus
        return bonus

    # =========================================================================
    # FORCED ATTACK HELPERS
    # =========================================================================

    def _update_forced_attackers(self):
        """Update list of cards that must attack adjacent tapped enemies."""
        self.forced_attackers = {}

        for card in self.board.get_all_cards(self.current_player):
            if not card.is_alive or not card.can_act:
                continue
            if not card.has_ability("must_attack_tapped"):
                continue

            adjacent_tapped = []
            for adj_pos in self.board.get_adjacent_cells(card.position, include_diagonals=True):
                adj_card = self.board.get_card(adj_pos)
                if adj_card and adj_card.player != card.player and adj_card.tapped:
                    adjacent_tapped.append(adj_pos)

            if adjacent_tapped:
                self.forced_attackers[card.id] = adjacent_tapped

    @property
    def has_forced_attack(self) -> bool:
        """True if there's a card that must attack a tapped enemy."""
        return len(self.forced_attackers) > 0

    def get_forced_attacker_card(self, card: 'Card') -> Optional[List[int]]:
        """Get forced attack targets for a card, or None if not a forced attacker."""
        if card.id in self.forced_attackers:
            return self.forced_attackers[card.id]
        return None

    def opponent_has_only_flyers(self, player: int) -> bool:
        """Check if the opponent of given player has only flying creatures left."""
        opponent = 2 if player == 1 else 1
        ground_cards = self.board.get_all_cards(opponent, include_flying=False)
        flying_cards = self.board.get_flying_cards(opponent)
        return len(ground_cards) == 0 and len(flying_cards) > 0

    # =========================================================================
    # DICE & DAMAGE BONUS HELPERS
    # =========================================================================

    def _get_attack_dice_bonus(self, card: 'Card', target: 'Card' = None) -> int:
        """Get dice bonus for attacking."""
        from ..abilities import get_ability, AbilityType
        bonus = card.temp_dice_bonus
        bonus += card.defender_buff_dice
        col = self._get_card_column(card)

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.dice_bonus_attack > 0:
                    if ability.id == "edge_column_attack":
                        if col in (0, 4):
                            bonus += ability.dice_bonus_attack
                    else:
                        bonus += ability.dice_bonus_attack
        return bonus

    def _get_defense_dice_bonus(self, card: 'Card') -> int:
        """Get dice bonus for defending."""
        from ..abilities import get_ability, AbilityType
        bonus = 0
        col = self._get_card_column(card)

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.dice_bonus_defense > 0:
                    bonus += ability.dice_bonus_defense
                elif ability.id == "center_column_defense" and col == 2:
                    bonus += 1
                elif ability.is_formation and card.in_formation and ability.formation_dice_bonus > 0:
                    if ability.requires_elite_ally:
                        if self._has_elite_ally_in_formation(card):
                            bonus += ability.formation_dice_bonus
                    elif ability.requires_common_ally:
                        if self._has_common_ally_in_formation(card):
                            bonus += ability.formation_dice_bonus
                    else:
                        bonus += ability.formation_dice_bonus
        return bonus

    def _get_damage_reduction(self, defender: 'Card', attacker: 'Card', attack_tier: int = -1) -> int:
        """Get damage reduction for defender vs this attacker."""
        from ..abilities import get_ability, AbilityType
        from ..constants import Element
        reduction = 0
        is_diagonal = self._is_diagonal_attack(attacker, defender)
        col = self._get_card_column(defender)

        for ability_id in defender.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.id == "center_column_defense" and col == 2 and attack_tier == 0:
                    reduction += 1
                elif ability.damage_reduction > 0:
                    if ability.id == "diagonal_defense":
                        if is_diagonal:
                            reduction += ability.damage_reduction
                    elif ability.id == "steppe_defense":
                        if attacker.stats.element == Element.PLAINS:
                            reduction += ability.damage_reduction
                    elif ability.cost_threshold == 0 or attacker.stats.cost <= ability.cost_threshold:
                        reduction += ability.damage_reduction
        return reduction

    def _get_element_damage_bonus(self, attacker: 'Card', defender: 'Card') -> int:
        """Get bonus damage from abilities that target specific elements."""
        from ..abilities import get_ability
        from ..constants import Element
        bonus = 0
        for ability_id in attacker.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.bonus_damage_vs_element > 0 and ability.target_element:
                target_elem = getattr(Element, ability.target_element, None)
                if target_elem and defender.stats.element == target_elem:
                    bonus += ability.bonus_damage_vs_element
        return bonus

    def _get_positional_damage_modifier(self, card: 'Card', tier: int) -> int:
        """Get positional damage bonus (e.g., front_row_strong: +1 to strong damage in front row)."""
        from ..abilities import get_ability, AbilityType
        modifier = 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.id == "front_row_strong" and tier == 2:
                    if self._is_in_own_row(card, 2):
                        modifier += 1
        return modifier

    def _has_defensive_ability(self, card: 'Card') -> bool:
        """Check if card has OVA, OVZ, or armor abilities."""
        from ..abilities import get_ability
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                if ability.dice_bonus_attack > 0:
                    return True
                if ability.dice_bonus_defense > 0:
                    return True
                if ability.formation_dice_bonus > 0 and card.in_formation:
                    return True
        if card.stats.armor > 0:
            return True
        if card.in_formation and card.formation_armor_max > 0:
            return True
        return False

    def _get_ranged_defensive_bonus(self, attacker: 'Card', target: 'Card', ability: 'Ability') -> int:
        """Get bonus ranged damage vs cards with OVA/OVZ/armor."""
        if ability and ability.bonus_ranged_vs_defensive > 0:
            if self._has_defensive_ability(target):
                return ability.bonus_ranged_vs_defensive
        return 0

    def _has_magic_abilities(self, card: 'Card') -> bool:
        """Check if card has magical abilities (discharge, magical strike, spell)."""
        from ..abilities import get_ability
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_magic:
                return True
        return False

    def _has_direct_attack(self, card: 'Card') -> bool:
        """Check if card has permanent direct attack."""
        from ..abilities import get_ability, AbilityType
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.grants_direct:
                    return True
        return False

    def _get_hit_damage_reduction(self, defender: 'Card', attacker: 'Card') -> int:
        """Get damage reduction for hit abilities (diagonal_defense, etc.).

        Used for abilities with is_hit=True (lunge, magical_strike, borg_strike, etc.)
        """
        from ..abilities import get_ability, AbilityType
        reduction = 0
        is_diagonal = self._is_diagonal_attack(attacker, defender)

        for ability_id in defender.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.id == "diagonal_defense" and ability.damage_reduction > 0:
                    if is_diagonal:
                        reduction += ability.damage_reduction
        return reduction

    # =========================================================================
    # DEATH & DAMAGE HANDLING
    # =========================================================================

    def _handle_death(self, card: 'Card', killer: Optional['Card'] = None) -> bool:
        """Handle card death, graveyard, and return True if card died."""
        from ..commands import evt_card_died
        from ..board import Board
        if card.is_alive:
            return False
        self.log(f"{card.name} погиб!")
        # Calculate visual index for flying cards BEFORE removing from board
        visual_index = -1
        pos = card.position
        if pos is not None and pos >= Board.FLYING_P1_START:
            if pos < Board.FLYING_P2_START:
                slot_idx = pos - Board.FLYING_P1_START
                flying_zone = self.board.flying_p1
            else:
                slot_idx = pos - Board.FLYING_P2_START
                flying_zone = self.board.flying_p2
            # Count non-None cards before this slot
            visual_index = sum(1 for i in range(slot_idx) if flying_zone[i] is not None)
        # Emit event with position and visual_index before sending to graveyard
        self.emit_event(evt_card_died(card.id, card.position, visual_index))
        card.tapped = False
        if killer and killer.player != card.player:
            card.killed_by_enemy = True
            self._process_kill_triggers(killer, card)
        self.board.send_to_graveyard(card)
        self.recalculate_formations()
        return True

    def _deal_damage(self, target: 'Card', amount: int, is_magical: bool = False,
                     source_id: Optional[int] = None) -> tuple:
        """Deal damage to target. Returns (actual_damage, was_web_blocked)."""
        if target.webbed:
            target.webbed = False
            self.log(f"  -> Паутина блокирует и спадает!")
            self.emit_clear_arrows()
            return 0, True

        if not is_magical and target.formation_armor_remaining > 0:
            absorbed = min(amount, target.formation_armor_remaining)
            target.formation_armor_remaining -= absorbed
            amount -= absorbed
            if absorbed > 0:
                self.log(f"  -> Броня строя поглощает {absorbed} урона")

        actual, armor_absorbed = target.take_damage_with_armor(amount, is_magical)
        if armor_absorbed > 0:
            self.log(f"  -> Броня поглощает {armor_absorbed} урона")

        self.emit_damage(target.position, actual, card_id=target.id, source_id=source_id)
        return actual, False

    def _process_kill_triggers(self, killer: 'Card', victim: 'Card'):
        """Process ON_KILL triggered abilities when killer defeats enemy."""
        from ..abilities import get_ability, AbilityTrigger
        from ..ability_handlers import get_trigger_handler
        if not killer.is_alive:
            return

        ctx = {'victim': victim}
        for ability_id in killer.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.trigger != AbilityTrigger.ON_KILL:
                continue

            handler = get_trigger_handler(ability_id)
            if handler:
                handler(self, killer, ability, ctx)

    def _check_winner(self) -> bool:
        """Check for winner and update game state."""
        from ..commands import evt_game_over
        from ..constants import GamePhase
        winner = self.board.check_winner()
        if winner is not None:
            self.phase = GamePhase.GAME_OVER
            if winner == 0:
                self.log("Ничья!")
            else:
                self.log(f"Победа игрока {winner}!")
            self.emit_event(evt_game_over(winner))
            return True
        return False
