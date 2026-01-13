"""Command processing - central entry point for all player commands."""
from typing import List, Tuple, TYPE_CHECKING

from ..constants import GamePhase
from ..commands import Command, CommandType, Event

if TYPE_CHECKING:
    pass


class CommandsMixin:
    """Mixin for command processing."""

    def process_command(self, cmd: Command, server_only: bool = False) -> Tuple[bool, List[Event]]:
        """Process a player command. Returns (success, events)."""
        # Game over - no commands accepted
        if self.phase == GamePhase.GAME_OVER:
            return False, self.pop_events()

        # Validate player is allowed to act
        if self.priority_phase and cmd.player != self.priority_player:
            return False, self.pop_events()

        if self.phase == GamePhase.MAIN and not self.priority_phase:
            if self.interaction:
                expected_player = self.interaction.acting_player
                if expected_player and cmd.player != expected_player:
                    return False, self.pop_events()
            elif cmd.player != self.current_player:
                return False, self.pop_events()

        # Card ownership validation
        own_card_commands = (
            CommandType.MOVE, CommandType.ATTACK,
            CommandType.USE_ABILITY, CommandType.USE_INSTANT,
            CommandType.PREPARE_FLYER_ATTACK,
        )
        if cmd.card_id is not None and cmd.type in own_card_commands:
            card = self.board.get_card_by_id(cmd.card_id)
            if not card:
                return False, self.pop_events()
            if card.player != cmd.player:
                return False, self.pop_events()

        if cmd.target_id is not None:
            target = self.board.get_card_by_id(cmd.target_id)
            if not target:
                return False, self.pop_events()

        # Route by command type
        if cmd.type == CommandType.MOVE:
            if cmd.card_id is not None and cmd.position is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card and card.can_act:
                    card_valid_moves = self.board.get_valid_moves(card)
                    if cmd.position in card_valid_moves:
                        return self.move_card(card, cmd.position), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.ATTACK:
            if cmd.card_id is not None and cmd.position is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    card_valid_attacks = self.get_attack_targets(card)
                    if cmd.position in card_valid_attacks:
                        return self.attack(card, cmd.position), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.PREPARE_FLYER_ATTACK:
            if cmd.card_id is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    return self.prepare_flyer_attack(card), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.USE_ABILITY:
            if cmd.card_id is not None and cmd.ability_id:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    return self.use_ability(card, cmd.ability_id), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.USE_INSTANT:
            if cmd.card_id is not None and cmd.ability_id and cmd.option:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    return self.use_instant_ability(card, cmd.ability_id, cmd.option), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CONFIRM:
            if cmd.confirmed is not None:
                if self.awaiting_heal_confirm:
                    self.confirm_heal_on_attack(cmd.confirmed)
                    return True, self.pop_events()
                if self.awaiting_untap_confirm:
                    self.confirm_untap(cmd.confirmed)
                    return True, self.pop_events()
                if self.awaiting_exchange_choice:
                    return self.resolve_exchange_choice(reduce_damage=not cmd.confirmed), self.pop_events()
                if self.awaiting_stench_choice:
                    return self.resolve_stench_choice(tap=cmd.confirmed), self.pop_events()
                if self.awaiting_counter_selection:
                    return self.confirm_counter_selection(), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CANCEL:
            if self.awaiting_ability_target or self.awaiting_counter_selection:
                self.cancel_ability()
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CHOOSE_POSITION:
            if cmd.position is not None:
                # Defender uses card_id validation, others use position
                if self.awaiting_defender:
                    card = self.board.get_card(cmd.position)
                    if card and self.interaction.can_select_card_id(card.id):
                        return self.choose_defender(card), self.pop_events()
                # Generic position selection for all other types
                elif self.interaction and self.interaction.is_board_selection:
                    if self.resolve_position_selection(cmd.position):
                        return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CHOOSE_CARD:
            if cmd.card_id is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card and self.awaiting_defender:
                    if self.interaction.can_select_card_id(cmd.card_id):
                        return self.choose_defender(card), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CHOOSE_AMOUNT:
            if cmd.amount is not None and self.awaiting_counter_selection:
                self.set_counter_selection(cmd.amount)
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.PASS_PRIORITY:
            if self.awaiting_priority:
                if self.pass_priority():
                    self.continue_after_priority()
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.SKIP:
            # Generic skip handler for all skippable interactions
            if self.skip_current_interaction():
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.END_TURN:
            if self.phase == GamePhase.MAIN and not self.awaiting_defender:
                self.end_turn()
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CONCEDE:
            from ..commands import evt_game_over
            self.phase = GamePhase.GAME_OVER
            self.winner = 3 - cmd.player
            self.log(f"Игрок {cmd.player} сдался!")
            self.emit_event(evt_game_over(self.winner))
            return True, self.pop_events()

        return False, self.pop_events()
