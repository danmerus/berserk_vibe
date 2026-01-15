"""Base class for AI players.

AI players interface with the game through a filtered view - they cannot
see opponent's hidden (face-down) cards, just like human players.

The AI receives game state snapshots filtered for their player number,
ensuring fair play.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from ..game import Game
from ..commands import Command
from ..interaction import InteractionKind

if TYPE_CHECKING:
    from ..match import MatchServer


@dataclass
class AIAction:
    """Represents a possible action the AI can take."""
    command: Command
    description: str = ""

    def __repr__(self):
        return f"AIAction({self.command.type.name}, {self.description})"


class AIPlayer(ABC):
    """Base class for AI opponents.

    AI players observe game state through filtered snapshots (can't see
    opponent's hidden cards) and issue commands just like human players.

    Subclasses implement choose_action() to decide what to do.
    """

    def __init__(self, server: 'MatchServer', player: int):
        """Initialize AI player.

        Args:
            server: The match server to send commands to
            player: Player number (1 or 2)
        """
        self.server = server
        self.player = player
        self._cached_game: Optional[Game] = None

    @property
    def game(self) -> Optional[Game]:
        """Get filtered game state (reconstructed from snapshot).

        This ensures AI can't see opponent's hidden cards.
        """
        if self.server.game is None:
            return None

        # Get filtered snapshot for this player
        snapshot = self.server.get_snapshot(for_player=self.player)
        # Reconstruct game from filtered snapshot
        self._cached_game = Game.from_dict(snapshot)
        return self._cached_game

    @property
    def opponent(self) -> int:
        """Get opponent's player number."""
        return 2 if self.player == 1 else 1

    def is_my_turn(self) -> bool:
        """Check if it's this AI's turn to act."""
        game = self.server.game
        if game is None:
            return False

        # Check if game is in playable state
        from ..constants import GamePhase
        if game.phase != GamePhase.MAIN:
            return False

        # Check for interaction requiring our response
        if game.interaction:
            return game.interaction.acting_player == self.player

        # Check for priority phase
        if game.priority_phase:
            return game.priority_player == self.player

        # Normal turn
        return game.current_player == self.player

    def get_valid_actions(self) -> List[AIAction]:
        """Get all valid actions the AI can take right now.

        Returns list of AIAction objects representing legal moves.
        """
        game = self.game
        if game is None:
            return []

        actions = []

        # Handle interactions first (these take priority)
        if game.interaction and game.interaction.acting_player == self.player:
            actions.extend(self._get_interaction_actions(game))
            return actions  # Must handle interaction before anything else

        # Handle priority phase
        if game.priority_phase and game.priority_player == self.player:
            actions.extend(self._get_priority_actions(game))
            return actions

        # Normal turn actions
        if game.current_player == self.player:
            actions.extend(self._get_movement_actions(game))
            actions.extend(self._get_attack_actions(game))
            actions.extend(self._get_ability_actions(game))
            actions.extend(self._get_turn_actions(game))

        return actions

    def _get_interaction_actions(self, game: Game) -> List[AIAction]:
        """Get valid actions for current interaction."""
        from ..commands import (
            cmd_choose_card, cmd_choose_position, cmd_confirm,
            cmd_skip, cmd_choose_amount
        )

        actions = []
        inter = game.interaction

        if inter.kind == InteractionKind.SELECT_DEFENDER:
            # Can choose a defender or skip
            for card_id in inter.valid_card_ids:
                card = game.board.get_card_by_id(card_id)
                name = card.name if card else f"card_{card_id}"
                actions.append(AIAction(
                    cmd_choose_card(self.player, card_id),
                    f"defend with {name}"
                ))
            if inter.is_skippable:
                actions.append(AIAction(
                    cmd_skip(self.player),
                    "skip defense"
                ))

        elif inter.kind == InteractionKind.SELECT_VALHALLA_TARGET:
            # Must choose an ally for valhalla buff
            for card_id in inter.valid_card_ids:
                card = game.board.get_card_by_id(card_id)
                name = card.name if card else f"card_{card_id}"
                actions.append(AIAction(
                    cmd_choose_card(self.player, card_id),
                    f"valhalla buff {name}"
                ))

        elif inter.kind == InteractionKind.SELECT_COUNTER_SHOT:
            # Must choose target for counter shot
            for pos in inter.valid_positions:
                card = game.board.get_card(pos)
                name = card.name if card else f"pos_{pos}"
                actions.append(AIAction(
                    cmd_choose_position(self.player, pos),
                    f"counter shot {name}"
                ))

        elif inter.kind == InteractionKind.SELECT_MOVEMENT_SHOT:
            # Optional shot - can choose target or skip
            for pos in inter.valid_positions:
                card = game.board.get_card(pos)
                name = card.name if card else f"pos_{pos}"
                actions.append(AIAction(
                    cmd_choose_position(self.player, pos),
                    f"movement shot {name}"
                ))
            if inter.is_skippable:
                actions.append(AIAction(
                    cmd_skip(self.player),
                    "skip shot"
                ))

        elif inter.kind == InteractionKind.SELECT_ABILITY_TARGET:
            # Choose target for ability
            for pos in inter.valid_positions:
                card = game.board.get_card(pos)
                name = card.name if card else f"pos_{pos}"
                actions.append(AIAction(
                    cmd_choose_position(self.player, pos),
                    f"target {name}"
                ))

        elif inter.kind == InteractionKind.SELECT_UNTAP:
            # Choose card to untap or skip
            for pos in inter.valid_positions:
                card = game.board.get_card(pos)
                name = card.name if card else f"pos_{pos}"
                actions.append(AIAction(
                    cmd_choose_position(self.player, pos),
                    f"untap {name}"
                ))
            if inter.is_skippable:
                actions.append(AIAction(
                    cmd_skip(self.player),
                    "skip untap"
                ))

        elif inter.kind in (InteractionKind.CONFIRM_HEAL, InteractionKind.CONFIRM_UNTAP):
            # Yes/No choice
            actions.append(AIAction(
                cmd_confirm(self.player, True),
                "accept"
            ))
            actions.append(AIAction(
                cmd_confirm(self.player, False),
                "decline"
            ))

        elif inter.kind == InteractionKind.CHOOSE_STENCH:
            # Tap (True) or take damage (False)
            actions.append(AIAction(
                cmd_confirm(self.player, True),
                "tap to avoid stench"
            ))
            actions.append(AIAction(
                cmd_confirm(self.player, False),
                "take stench damage"
            ))

        elif inter.kind == InteractionKind.CHOOSE_EXCHANGE:
            # Full damage (True) or reduced (False)
            actions.append(AIAction(
                cmd_confirm(self.player, True),
                "full damage exchange"
            ))
            actions.append(AIAction(
                cmd_confirm(self.player, False),
                "reduced damage"
            ))

        elif inter.kind == InteractionKind.SELECT_COUNTERS:
            # Choose amount of counters
            for amount in range(inter.min_amount, inter.max_amount + 1):
                actions.append(AIAction(
                    cmd_choose_amount(self.player, amount),
                    f"use {amount} counters"
                ))

        return actions

    def _get_priority_actions(self, game: Game) -> List[AIAction]:
        """Get valid actions during priority phase."""
        from ..commands import cmd_pass_priority, cmd_use_instant

        actions = []

        # Can always pass priority
        actions.append(AIAction(
            cmd_pass_priority(self.player),
            "pass priority"
        ))

        # Check for instant abilities (luck)
        my_cards = game.board.get_all_cards(self.player)
        for card in my_cards:
            if card.can_act and card.has_ability("luck"):
                # Luck can modify dice: atk/def + plus1/minus1/reroll
                for target in ["atk", "def"]:
                    for action in ["plus1", "minus1", "reroll"]:
                        option = f"{target}_{action}"
                        actions.append(AIAction(
                            cmd_use_instant(self.player, card.id, "luck", option),
                            f"{card.name} luck {option}"
                        ))

        return actions

    def _get_movement_actions(self, game: Game) -> List[AIAction]:
        """Get valid movement actions."""
        from ..commands import cmd_move

        actions = []
        my_cards = game.board.get_all_cards(self.player)

        for card in my_cards:
            if card.can_act and card.curr_move > 0:
                valid_moves = game.board.get_valid_moves(card)
                for pos in valid_moves:
                    actions.append(AIAction(
                        cmd_move(self.player, card.id, pos),
                        f"move {card.name} to {pos}"
                    ))

        return actions

    def _get_attack_actions(self, game: Game) -> List[AIAction]:
        """Get valid attack actions."""
        from ..commands import cmd_attack, cmd_prepare_flyer_attack

        actions = []
        my_cards = game.board.get_all_cards(self.player)

        # Check for forced attacks first
        if game.has_forced_attack:
            # Must attack with a specific card
            for card_id, targets in game.forced_attackers.items():
                card = game.board.get_card_by_id(card_id)
                if card and card.player == self.player and card.can_act:
                    for target_pos in targets:
                        target = game.board.get_card(target_pos)
                        name = target.name if target else f"pos_{target_pos}"
                        actions.append(AIAction(
                            cmd_attack(self.player, card.id, target_pos),
                            f"{card.name} forced attack {name}"
                        ))
            if actions:
                return actions  # Only forced attacks allowed when we have them

        # Normal attacks (exclude allies)
        for card in my_cards:
            if card.can_act:
                targets = game.get_attack_targets(card, include_allies=False)
                for target_pos in targets:
                    target = game.board.get_card(target_pos)
                    if target and target.player != self.player:  # Double check - don't attack allies
                        actions.append(AIAction(
                            cmd_attack(self.player, card.id, target_pos),
                            f"{card.name} attack {target.name}"
                        ))

        # Prepare flyer attack (when opponent has only flyers)
        for card in my_cards:
            if game.can_prepare_flyer_attack(card):
                actions.append(AIAction(
                    cmd_prepare_flyer_attack(self.player, card.id),
                    f"{card.name} prepare flyer attack"
                ))

        return actions

    def _get_ability_actions(self, game: Game) -> List[AIAction]:
        """Get valid ability actions."""
        from ..commands import cmd_use_ability
        from ..abilities import ABILITIES, AbilityType, TargetType

        actions = []
        my_cards = game.board.get_all_cards(self.player)

        for card in my_cards:
            if not card.can_act:
                continue

            for ability_id in card.stats.ability_ids:
                ability = ABILITIES.get(ability_id)
                if not ability or ability.ability_type != AbilityType.ACTIVE:
                    continue

                # Check if ability can be used
                if not card.can_use_ability(ability_id):
                    continue

                # For abilities that need targets, check if valid targets exist
                # For self-targeting abilities, no target needed
                if ability.target_type == TargetType.SELF:
                    actions.append(AIAction(
                        cmd_use_ability(self.player, card.id, ability_id),
                        f"{card.name} use {ability_id}"
                    ))
                else:
                    # Ability needs target - verify targets exist before adding
                    targets = game._get_ability_targets(card, ability)
                    if targets:
                        actions.append(AIAction(
                            cmd_use_ability(self.player, card.id, ability_id),
                            f"{card.name} use {ability_id}"
                        ))

        return actions

    def _get_turn_actions(self, game: Game) -> List[AIAction]:
        """Get turn management actions (end turn)."""
        from ..commands import cmd_end_turn

        actions = []

        # Can end turn if no forced attacks
        if not game.has_forced_attack:
            actions.append(AIAction(
                cmd_end_turn(self.player),
                "end turn"
            ))

        return actions

    def execute_action(self, action: AIAction) -> bool:
        """Execute an action and return success status."""
        result = self.server.apply(action.command)
        return result.accepted

    @abstractmethod
    def choose_action(self) -> Optional[AIAction]:
        """Choose an action to take. Subclasses must implement this.

        Returns:
            AIAction to execute, or None if no action should be taken
        """
        pass

    def take_turn(self) -> bool:
        """Take one action if it's our turn.

        Returns:
            True if an action was taken, False otherwise
        """
        if not self.is_my_turn():
            return False

        action = self.choose_action()
        if action is None:
            return False

        return self.execute_action(action)
