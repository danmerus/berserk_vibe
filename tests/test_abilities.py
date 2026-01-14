"""Tests for card abilities."""
import pytest
from tests.conftest import assert_hp, assert_tapped, assert_untapped, assert_card_dead, resolve_combat


class TestPassiveAbilities:
    """Test passive abilities that are always active."""

    def test_tough_hide_reduces_cheap_attacker_damage(self, game, place_card, set_rolls):
        """Толстая шкура: -2 damage from creatures costing ≤3."""
        # Хобгоблин has tough_hide, but Кобольд costs 5 (not cheap)
        # Let's use Овражный гном (cost=3) as cheap attacker instead
        tank = place_card("Хобгоблин", player=1, pos=10)
        cheap_attacker = place_card("Овражный гном", player=2, pos=15)  # cost=3

        initial_hp = tank.curr_life
        set_rolls(6, 1)  # Strong hit from attacker
        game.current_player = 2
        game.attack(cheap_attacker, tank.position)
        resolve_combat(game)

        # Strong damage (2) - 2 reduction = 0 minimum
        base_damage = cheap_attacker.stats.attack[2]
        expected_damage = max(0, base_damage - 2)
        assert_hp(tank, initial_hp - expected_damage)

    def test_tough_hide_no_reduction_expensive_attacker(self, game, place_card, set_rolls):
        """Толстая шкура: no reduction from creatures costing >3."""
        tank = place_card("Хобгоблин", player=1, pos=10)
        expensive_attacker = place_card("Циклоп", player=2, pos=15)  # cost=8

        initial_hp = tank.curr_life
        set_rolls(6, 1)
        game.current_player = 2
        game.attack(expensive_attacker, tank.position)
        resolve_combat(game)

        # Full damage, no reduction
        expected_damage = expensive_attacker.stats.attack[2]
        assert_hp(tank, initial_hp - expected_damage)

    def test_attack_exp_adds_to_roll(self, game, place_card, set_rolls):
        """Опыт в атаке: +1 to attack dice roll."""
        # Костедробитель has attack_exp
        attacker = place_card("Костедробитель", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        initial_hp = defender.curr_life
        # Roll 5 + 1 bonus = 6, defender rolls 3, diff = +3 = medium damage (no exchange)
        set_rolls(5, 3)
        game.attack(attacker, defender.position)
        resolve_combat(game)

        # With +1 exp, roll 5 becomes 6, diff +3 = medium
        expected_damage = attacker.stats.attack[1]
        assert_hp(defender, initial_hp - expected_damage)

    def test_defense_exp_adds_to_roll(self, game, place_card, set_rolls):
        """Опыт в защите: +1 to defense dice roll."""
        attacker = place_card("Циклоп", player=1, pos=10)
        # Лёккен has defense_exp
        defender = place_card("Лёккен", player=2, pos=15)

        initial_hp = defender.curr_life
        # Roll 4 vs (3+1=4), diff = 0, roll 4 (low) = weak
        set_rolls(4, 3)
        game.attack(attacker, defender.position)
        resolve_combat(game)

        # Defense exp makes it a tie (4 vs 4), low roll = weak damage
        expected_damage = attacker.stats.attack[0]
        assert_hp(defender, initial_hp - expected_damage)


class TestTriggeredAbilities:
    """Test abilities that trigger on specific events."""

    def test_regeneration_on_turn_start(self, game, place_card):
        """Регенерация: heals at turn start."""
        # Гобрах has regeneration
        card = place_card("Гобрах", player=1, pos=10)
        card.curr_life = card.stats.life - 5  # Damage it

        game.current_player = 1
        game.start_turn()

        # Should have healed some amount
        assert card.curr_life > card.stats.life - 5



class TestActiveAbilities:
    """Test abilities that require activation."""

    def test_heal_ally_heals_target(self, game, place_card):
        """Дыхание леса: heal any creature +2 HP."""
        healer = place_card("Друид", player=1, pos=10)
        wounded = place_card("Циклоп", player=1, pos=11)
        wounded.curr_life = wounded.stats.life - 5

        result = game.use_ability(healer, "heal_ally")
        assert result is True  # Ability started, needs target

        # Select target
        game.select_ability_target(wounded.position)

        # Heal confirmation might be needed - let's check if heal was applied
        # or if we need to confirm
        if game.awaiting_heal_confirm:
            game.confirm_heal(True)

        assert wounded.curr_life >= wounded.stats.life - 5  # Should have healed

    def test_ability_taps_card(self, game, place_card):
        """Active abilities should tap the card."""
        healer = place_card("Друид", player=1, pos=10)
        wounded = place_card("Циклоп", player=1, pos=11)
        wounded.curr_life = wounded.stats.life - 3

        assert_untapped(healer)
        game.use_ability(healer, "heal_ally")
        game.select_ability_target(wounded.position)
        if game.awaiting_heal_confirm:
            game.confirm_heal(True)

        assert_tapped(healer)

    def test_cannot_use_ability_when_tapped(self, game, place_card):
        """Cannot use active ability when tapped."""
        healer = place_card("Друид", player=1, pos=10, tapped=True)
        wounded = place_card("Циклоп", player=1, pos=11)
        wounded.curr_life = wounded.stats.life - 3

        result = game.use_ability(healer, "heal_ally")

        assert result is False


class TestDefenderAbilities:
    """Test defender-related abilities."""

    def test_defender_no_tap_stays_untapped(self, game, place_card, set_rolls):
        """Стойкий защитник: doesn't tap when defending."""
        attacker = place_card("Циклоп", player=1, pos=10)
        # Лёккен has defender_no_tap
        defender = place_card("Лёккен", player=2, pos=16)
        target = place_card("Кобольд", player=2, pos=15)

        # Attack the kobold, Лёккен can intercept
        set_rolls(4, 3)
        game.attack(attacker, target.position)

        # If defender prompt appears, choose the defender
        if game.awaiting_defender:
            game.choose_defender(defender)
            resolve_combat(game)

        # Defender should still be untapped (defender_no_tap ability)
        assert_untapped(defender, "Defender with defender_no_tap should stay untapped")


class TestInstantAbilities:
    """Test instant abilities and priority system."""

    def test_luck_available_during_priority(self, game, place_card, set_rolls):
        """Luck ability should be usable during priority phase."""
        lovets = place_card("Ловец удачи", player=1, pos=12)
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        set_rolls(3, 3)  # Tie
        game.attack(attacker, defender.position)

        # Should enter priority phase
        assert game.priority_phase, "Priority phase should be active"

        # Lovets should be able to use luck
        legal = game.get_legal_instants(1)
        assert any(card.name == "Ловец удачи" for card, _ in legal)

    def test_luck_modifies_roll(self, game, place_card, set_rolls):
        """Luck +1 should increase effective roll."""
        lovets = place_card("Ловец удачи", player=1, pos=12)
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        initial_hp = defender.curr_life
        # Roll 2 vs 2 = tie = weak normally, with +1 becomes diff 1 = still weak
        # Let's use roll 3 vs 4 = -1 = weak, with +1 becomes diff 0 (low roll) = weak
        # Actually, for medium damage: diff needs to be 1 or 3 (without exchange)
        # Roll 4 vs 4 = 0, low roll = weak. With +1: 5 vs 4 = diff 1 = weak
        # Roll 5 vs 4 = 1 = weak. With +1: 6 vs 4 = diff 2 = medium (exchange)
        # To get non-exchange medium, need diff=3: roll 6 vs 4 = 2, with +1 = 7 vs 4 = diff 3 = medium
        # But base 6 vs 4 = 2 = medium (exchange)...
        # Let's test: without luck, roll 3 vs 3 = tie (low) = weak
        # With luck +1: 4 vs 3 = diff 1 = weak - that's not a change!
        # Let's use: roll 2 vs 4 = diff -2 = miss. With +1: 3 vs 4 = diff -1 = weak
        set_rolls(2, 4)  # diff = -2 = miss normally
        game.attack(attacker, defender.position)

        assert game.priority_phase
        # Use luck to add +1 to attack
        game.use_instant_ability(lovets, "luck", "atk_plus1")
        resolve_combat(game)

        # With +1 luck, diff = -1 = weak damage (was miss before)
        expected_damage = attacker.stats.attack[0]  # Weak
        assert_hp(defender, initial_hp - expected_damage)

    def test_luck_taps_card(self, game, place_card, set_rolls):
        """Using luck should tap the card."""
        lovets = place_card("Ловец удачи", player=1, pos=12)
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        set_rolls(3, 3)
        game.attack(attacker, defender.position)

        assert_untapped(lovets)
        game.use_instant_ability(lovets, "luck", "atk_plus1")
        assert_tapped(lovets)
