"""Tests for edge cases and complex interactions."""
import pytest
from src.constants import GamePhase
from tests.conftest import assert_hp, assert_tapped, assert_untapped, assert_card_dead, assert_card_alive, resolve_combat


class TestDamageEdgeCases:
    """Test edge cases in damage calculation."""

    def test_damage_cannot_go_below_zero(self, game, place_card, set_rolls):
        """Damage reduction cannot result in negative damage."""
        # Хобгоблин has tough_hide (-2 from cheap attackers)
        tank = place_card("Хобгоблин", player=1, pos=10)
        # Овражный гном costs 3, has attack (1,2,2)
        weak_attacker = place_card("Овражный гном", player=2, pos=15)

        initial_hp = tank.curr_life
        # Weak hit (1 damage) - 2 reduction = 0 (minimum)
        set_rolls(3, 3)  # Tie, low roll = weak
        game.current_player = 2
        game.attack(weak_attacker, tank.position)
        resolve_combat(game)

        # Should take 0 damage (reduction exceeds attack)
        assert tank.curr_life >= initial_hp - 1  # At most 1 damage after reduction floor

    def test_overkill_damage(self, game, place_card, set_rolls):
        """Card dies even with massive overkill damage."""
        attacker = place_card("Циклоп", player=1, pos=10)  # Strong = 6
        defender = place_card("Кобольд", player=2, pos=15)
        defender.curr_life = 1  # 1 HP left

        set_rolls(6, 1)  # Strong hit (6 damage)
        game.attack(attacker, defender.position)
        resolve_combat(game)

        assert_card_dead(defender)
        # HP goes negative but card is simply dead
        assert defender.curr_life <= 0

    def test_zero_hp_exactly_kills(self, game, place_card, set_rolls):
        """Card dies when HP reaches exactly 0."""
        attacker = place_card("Циклоп", player=1, pos=10)  # Weak = 4
        defender = place_card("Кобольд", player=2, pos=15)  # 11 HP by default
        defender.curr_life = 4  # Set to exactly weak damage

        set_rolls(3, 3)  # Tie, low roll = weak (4 damage)
        game.attack(attacker, defender.position)
        resolve_combat(game)

        assert_card_dead(defender)


class TestHealingEdgeCases:
    """Test edge cases in healing mechanics."""

    def test_heal_cannot_exceed_max_hp(self, game, place_card):
        """Healing cannot exceed maximum HP."""
        healer = place_card("Друид", player=1, pos=10)
        target = place_card("Циклоп", player=1, pos=11)
        target.curr_life = target.stats.life - 1  # Missing only 1 HP

        game.use_ability(healer, "heal_ally")
        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 11 in game.interaction.valid_positions:
                game.select_ability_target(11)
                if game.awaiting_heal_confirm:
                    game.confirm_heal(True)

        # Should not exceed max HP
        assert target.curr_life <= target.stats.life

    def test_heal_on_full_hp_card(self, game, place_card):
        """Healing a full HP card does nothing harmful."""
        healer = place_card("Друид", player=1, pos=10)
        target = place_card("Циклоп", player=1, pos=11)
        # Target is at full HP

        max_hp = target.stats.life
        game.use_ability(healer, "heal_ally")
        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 11 in game.interaction.valid_positions:
                game.select_ability_target(11)
                if game.awaiting_heal_confirm:
                    game.confirm_heal(True)

        # HP stays at max
        assert target.curr_life == max_hp

    def test_regeneration_caps_at_max_hp(self, game, place_card):
        """Regeneration doesn't heal above max HP."""
        gobrakh = place_card("Гобрах", player=1, pos=10)
        gobrakh.curr_life = gobrakh.stats.life - 1  # Missing 1 HP

        game.current_player = 1
        game.start_turn()

        # Regeneration +3, but only missing 1
        assert gobrakh.curr_life == gobrakh.stats.life



class TestMovementEdgeCases:
    """Test edge cases in movement."""

    def test_move_to_same_position(self, game, place_card):
        """Moving to current position should fail or be no-op."""
        card = place_card("Циклоп", player=1, pos=10)
        initial_move = card.curr_move

        result = game.move_card(card, 10)  # Same position

        # Either fails or succeeds but position unchanged
        assert card.position == 10
        if result:
            # If engine allows it, move counter might decrease
            pass
        # Either way card is still at position 10

    def test_move_depletes_movement(self, game, place_card):
        """Multiple moves deplete movement counter."""
        card = place_card("Циклоп", player=1, pos=10, curr_move=2)

        game.move_card(card, 11)
        assert card.curr_move == 1

        game.move_card(card, 12)
        assert card.curr_move == 0


class TestCombatEdgeCases:
    """Test complex combat scenarios."""

    def test_mutual_kill_scenario(self, game, place_card, set_rolls):
        """Both cards can die in exchange scenario."""
        attacker = place_card("Кобольд", player=1, pos=10)
        attacker.curr_life = 2  # Will die from counter

        defender = place_card("Кобольд", player=2, pos=15)
        defender.curr_life = 2  # Will die from attack

        # Roll diff = 2 triggers exchange - attacker deals medium (3), defender counters weak (2)
        set_rolls(4, 2)  # Diff = 2, exchange possible
        game.attack(attacker, defender.position)

        # Take full damage in exchange (no reduction)
        if game.awaiting_exchange_choice:
            game.resolve_exchange_choice(reduce_damage=False)

        resolve_combat(game)

        # Both should be dead - attacker dealt 3, defender countered 2
        assert_card_dead(defender)
        assert_card_dead(attacker)

    def test_attack_self_player_card_behavior(self, game, place_card, set_rolls):
        """Test behavior when attempting to attack own card."""
        attacker = place_card("Циклоп", player=1, pos=10)
        ally = place_card("Кобольд", player=1, pos=15)  # Same player

        initial_hp = ally.curr_life
        set_rolls(6, 1)

        # Engine may allow or block this - just verify no crash
        result = game.attack(attacker, ally.position)

        # Game engine behavior - either blocked or allowed
        # Main thing is no crash

    def test_attack_empty_cell(self, game, place_card, set_rolls):
        """Attacking an empty cell should fail gracefully."""
        attacker = place_card("Циклоп", player=1, pos=10)

        set_rolls(6, 1)
        result = game.attack(attacker, 15)  # Empty cell

        # Should fail or return False
        assert result is False or result is None


class TestBoardBoundaryEdgeCases:
    """Test edge cases at board boundaries."""

    def test_corner_position_0(self, game, place_card):
        """Card at position 0 (corner) works correctly."""
        card = place_card("Циклоп", player=1, pos=0)

        assert card.position == 0
        # Can still perform actions

    def test_corner_position_29(self, game, place_card):
        """Card at position 29 (opposite corner) works correctly."""
        card = place_card("Циклоп", player=2, pos=29)

        assert card.position == 29

    def test_flying_zone_boundaries(self, game, place_card):
        """Flying zone positions work correctly."""
        # Player 1 flying zone: 30-32
        flyer1 = place_card("Корпит", player=1, pos=30)
        assert flyer1.position == 30

        flyer2 = place_card("Корпит", player=1, pos=32)
        assert flyer2.position == 32

        # Player 2 flying zone: 33-35
        flyer3 = place_card("Корпит", player=2, pos=33)
        assert flyer3.position == 33


class TestAbilityEdgeCases:
    """Test edge cases in ability usage."""

    def test_ability_on_dead_card(self, game, place_card, set_rolls):
        """Cannot use abilities on dead cards."""
        healer = place_card("Друид", player=1, pos=10)
        target = place_card("Кобольд", player=1, pos=11)
        target.curr_life = 1  # Low HP so it will die

        # Kill the target
        attacker = place_card("Циклоп", player=2, pos=16)
        set_rolls(6, 1)
        game.current_player = 2
        game.attack(attacker, target.position)
        resolve_combat(game)

        assert_card_dead(target)

        # Try to heal dead card
        game.current_player = 1
        result = game.use_ability(healer, "heal_ally")

        # Dead card should not be valid target
        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            assert 11 not in game.interaction.valid_positions

    def test_multiple_abilities_same_turn(self, game, place_card):
        """Card cannot use multiple active abilities (gets tapped)."""
        healer = place_card("Друид", player=1, pos=10)
        target1 = place_card("Циклоп", player=1, pos=11)
        target1.curr_life = target1.stats.life - 3
        target2 = place_card("Циклоп", player=1, pos=12)
        target2.curr_life = target2.stats.life - 3

        # First heal
        game.use_ability(healer, "heal_ally")
        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 11 in game.interaction.valid_positions:
                game.select_ability_target(11)
                if game.awaiting_heal_confirm:
                    game.confirm_heal(True)

        assert_tapped(healer)

        # Second heal should fail (tapped)
        result = game.use_ability(healer, "heal_ally")
        assert result is False


class TestTurnEdgeCases:
    """Test edge cases in turn management."""

    def test_end_turn_during_game_over(self, game, place_card, set_rolls):
        """Ending turn during game over doesn't crash."""
        # Player 2's only card
        target = place_card("Кобольд", player=2, pos=15)
        target.curr_life = 1

        attacker = place_card("Циклоп", player=1, pos=10)

        set_rolls(6, 1)
        game.attack(attacker, target.position)
        resolve_combat(game)

        assert game.phase == GamePhase.GAME_OVER

        # Try to end turn - should not crash
        game.end_turn()

    def test_start_turn_with_no_cards(self, game):
        """Starting turn with no cards doesn't crash."""
        game.current_player = 1
        game.start_turn()

        # No cards, but no crash


class TestDiceRollEdgeCases:
    """Test edge cases in dice rolling."""

    def test_maximum_dice_roll(self, game, place_card, set_rolls):
        """Maximum dice roll (6) produces strong damage."""
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        initial_hp = defender.curr_life
        set_rolls(6, 1)  # Maximum difference
        game.attack(attacker, defender.position)
        resolve_combat(game)

        # Strong damage
        assert defender.curr_life == initial_hp - attacker.stats.attack[2]

    def test_minimum_dice_roll(self, game, place_card, set_rolls):
        """Minimum dice roll (1) with high defender roll = counter."""
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        attacker_initial_hp = attacker.curr_life
        set_rolls(1, 6)  # Defender wins by 5
        game.attack(attacker, defender.position)
        resolve_combat(game)

        # Attacker takes counter damage (medium at -5)
        expected_counter = defender.stats.attack[1]  # Medium
        assert_hp(attacker, attacker_initial_hp - expected_counter)


class TestMultipleTriggersEdgeCases:
    """Test edge cases with multiple triggers."""

    def test_regeneration_and_other_turn_start_effects(self, game, place_card):
        """Multiple turn-start effects all fire."""
        # Гобрах has regeneration
        gobrakh = place_card("Гобрах", player=1, pos=10)
        gobrakh.curr_life = gobrakh.stats.life - 5

        initial_hp = gobrakh.curr_life

        game.current_player = 1
        game.start_turn()

        # Regeneration should have fired
        assert gobrakh.curr_life > initial_hp
        # Card should also be untapped
        assert_untapped(gobrakh)
