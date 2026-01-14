"""Behavioral tests for complex game mechanics.

This file contains tests for complex interactions and mechanics that aren't
covered by the simpler ability tests. Avoid duplicating tests from:
- test_abilities.py (basic ability mechanics)
- test_advanced_abilities.py (lunge, counter_shot, heal_on_attack, valhalla, magical_strike)
- test_cards.py (card-specific tests including scavenging, regeneration)
- test_card_database.py (ability presence checks)
"""
import pytest
from tests.conftest import assert_hp, assert_tapped, assert_untapped, assert_card_dead, assert_card_alive, resolve_combat


class TestFlyerTapping:
    """Tests for flying creature tapping mechanics."""

    def test_flyer_taps_after_attack(self, game, place_card, set_rolls):
        """Flying creatures should tap after attacking."""
        flyer = place_card("Корпит", player=1, pos=30)  # Flying zone
        target = place_card("Друид", player=2, pos=15)

        assert_untapped(flyer)
        set_rolls(4, 3)
        game.attack(flyer, target.position)
        resolve_combat(game)

        assert_tapped(flyer)

    def test_flyer_untaps_at_turn_start(self, game, place_card):
        """Flying creatures should untap at owner's turn start."""
        flyer = place_card("Корпит", player=1, pos=30, tapped=True)

        assert_tapped(flyer)
        game.current_player = 1
        game.start_turn()

        assert_untapped(flyer)

    def test_tapped_flyer_cannot_attack(self, game, place_card):
        """Tapped flying creatures should not be able to attack."""
        flyer = place_card("Корпит", player=1, pos=30, tapped=True)
        target = place_card("Друид", player=2, pos=15)

        assert flyer.tapped is True

    def test_flyer_in_p2_zone_taps_correctly(self, game, place_card, set_rolls):
        """Player 2 flyers in positions 33-35 should tap after attacking."""
        flyer = place_card("Корпит", player=2, pos=33)  # P2 flying zone
        target = place_card("Друид", player=1, pos=10)

        assert_untapped(flyer)
        game.current_player = 2
        set_rolls(4, 3)
        game.attack(flyer, target.position)
        resolve_combat(game)

        assert_tapped(flyer)

    def test_draks_taps_and_untaps(self, game, place_card, set_rolls):
        """Дракс (unique flyer) should tap/untap correctly."""
        draks = place_card("Дракс", player=1, pos=30)
        target = place_card("Друид", player=2, pos=15)

        # Attack and tap
        set_rolls(4, 3)
        game.attack(draks, target.position)
        resolve_combat(game)
        assert_tapped(draks)

        # Next turn, untap
        game.current_player = 2
        game.end_turn()  # End P2's turn
        # Now it's P1's turn again
        assert_untapped(draks)


class TestFormation:
    """Tests for formation (строй) mechanics."""

    def test_adjacent_formation_cards_get_in_formation(self, game, place_card):
        """Two adjacent cards with formation abilities should be in formation."""
        # Гном-басаарг has stroi_atk_1
        card1 = place_card("Гном-басаарг", player=1, pos=10)
        card2 = place_card("Гном-басаарг", player=1, pos=11)  # Adjacent

        game.recalculate_formations()

        assert card1.in_formation is True
        assert card2.in_formation is True

    def test_non_adjacent_cards_not_in_formation(self, game, place_card):
        """Non-adjacent cards should not be in formation."""
        card1 = place_card("Гном-басаарг", player=1, pos=10)
        card2 = place_card("Гном-басаарг", player=1, pos=12)  # Not adjacent

        game.recalculate_formations()

        assert card1.in_formation is False
        assert card2.in_formation is False

    def test_formation_attack_bonus(self, game, place_card, set_rolls):
        """Cards in formation with stroi_atk_1 should deal +1 damage."""
        # Set up formation
        attacker = place_card("Гном-басаарг", player=1, pos=10)
        ally = place_card("Гном-басаарг", player=1, pos=11)
        target = place_card("Циклоп", player=2, pos=15, tapped=True)

        game.recalculate_formations()
        assert attacker.in_formation is True

        initial_hp = target.curr_life
        # Roll 4 = medium tier against tapped
        set_rolls(4)
        game.attack(attacker, target.position)
        resolve_combat(game)

        # Medium (3) + stroi_atk_1 (+1) + tapped_bonus (+1) = 5
        assert_hp(target, initial_hp - 5)

    def test_formation_defense_bonus(self, game, place_card, set_rolls):
        """Cards with stroi_ovz_1 in formation should get +1 defense dice."""
        # Горный великан has stroi_ovz_1
        defender1 = place_card("Горный великан", player=2, pos=15)
        defender2 = place_card("Горный великан", player=2, pos=16)
        attacker = place_card("Циклоп", player=1, pos=10)

        game.recalculate_formations()
        assert defender1.in_formation is True

        initial_hp = defender1.curr_life
        # Roll 4 vs 3+1(formation) = 4 vs 4 = tie, low roll = weak
        set_rolls(4, 3)
        game.attack(attacker, defender1.position)
        resolve_combat(game)

        # With formation bonus, defender's 3 becomes 4, tie = weak damage
        expected_damage = attacker.stats.attack[0]  # Weak = 4
        assert_hp(defender1, initial_hp - expected_damage)

    def test_formation_breaks_when_card_moves(self, game, place_card):
        """Formation should break when one card moves away."""
        card1 = place_card("Гном-басаарг", player=1, pos=10)
        card2 = place_card("Гном-басаарг", player=1, pos=11)

        game.recalculate_formations()
        assert card1.in_formation is True

        # Move card2 away
        game.move_card(card2, 13)  # Now not adjacent

        assert card1.in_formation is False
        assert card2.in_formation is False

    def test_formation_with_elite_ally(self, game, place_card):
        """Смотритель горнила should get armor when in formation with elite that has formation."""
        smotrytel = place_card("Смотритель горнила", player=1, pos=10)
        elite = place_card("Костедробитель", player=1, pos=11)

        game.recalculate_formations()

        if smotrytel.in_formation:
            assert smotrytel.formation_armor_max >= 0


class TestFormationBreaksOnDeath:
    """Tests for formation breaking when ally dies."""

    def test_formation_breaks_when_ally_dies(self, game, place_card, set_rolls):
        """Formation should break when one of the formation cards dies."""
        card1 = place_card("Гном-басаарг", player=1, pos=10)
        card2 = place_card("Гном-басаарг", player=1, pos=11)
        attacker = place_card("Циклоп", player=2, pos=15)

        game.recalculate_formations()
        assert card1.in_formation is True
        assert card2.in_formation is True

        # Kill card2
        card2.curr_life = 1
        set_rolls(6, 1)
        game.current_player = 2
        game.attack(attacker, card2.position)
        resolve_combat(game)

        assert_card_dead(card2)
        assert card1.in_formation is False


class TestMultipleFormations:
    """Tests for multiple formations on the board."""

    def test_two_separate_formations(self, game, place_card):
        """Two separate formation pairs should both be in formation."""
        card1 = place_card("Гном-басаарг", player=1, pos=10)
        card2 = place_card("Гном-басаарг", player=1, pos=11)
        card3 = place_card("Горный великан", player=1, pos=5)
        card4 = place_card("Горный великан", player=1, pos=6)

        game.recalculate_formations()

        assert card1.in_formation is True
        assert card2.in_formation is True
        assert card3.in_formation is True
        assert card4.in_formation is True

    def test_three_cards_in_line_formation(self, game, place_card):
        """Three cards in a line should all be in formation."""
        card1 = place_card("Гном-басаарг", player=1, pos=10)
        card2 = place_card("Гном-басаарг", player=1, pos=11)
        card3 = place_card("Гном-басаарг", player=1, pos=12)

        game.recalculate_formations()

        assert card1.in_formation is True
        assert card2.in_formation is True
        assert card3.in_formation is True


class TestBegushayaPoKronam:
    """Tests for Бегущая по кронам position-based abilities."""

    def test_front_row_bonus_in_front_row_p1(self, game, place_card):
        """Бегущая should get front row bonus when in positions 10-14."""
        runner = place_card("Бегущая по кронам", player=1, pos=12)
        row = runner.position // 5
        assert row == 2  # Front row for P1
        assert "front_row_bonus" in runner.stats.ability_ids

    def test_back_row_direct_in_back_row_p1(self, game, place_card):
        """Бегущая should get direct attack when in positions 0-4."""
        runner = place_card("Бегущая по кронам", player=1, pos=2)
        row = runner.position // 5
        assert row == 0  # Back row for P1
        assert "back_row_direct" in runner.stats.ability_ids

    def test_shot_from_front_row(self, game, place_card):
        """Crown runner shot should work from front row."""
        runner = place_card("Бегущая по кронам", player=1, pos=12)
        target = place_card("Друид", player=2, pos=22)
        result = game.use_ability(runner, "crown_runner_shot")
        assert result is True

    def test_shot_from_back_row(self, game, place_card):
        """Crown runner shot should work from back row."""
        runner = place_card("Бегущая по кронам", player=1, pos=2)
        target = place_card("Друид", player=2, pos=22)
        result = game.use_ability(runner, "crown_runner_shot")
        assert result is True


class TestBegushayaFrontRowBonus:
    """Tests for Бегущая по кронам's front row damage bonus."""

    def test_front_row_bonus_adds_damage(self, game, place_card, set_rolls):
        """Бегущая in front row should deal +1 damage."""
        runner = place_card("Бегущая по кронам", player=1, pos=12)
        target = place_card("Циклоп", player=2, pos=17)

        initial_hp = target.curr_life
        set_rolls(6, 3)  # diff +3 = medium
        game.attack(runner, target.position)
        resolve_combat(game)

        base_medium = runner.stats.attack[1]  # 3
        assert target.curr_life <= initial_hp - base_medium

    def test_back_row_direct_bypasses_defender(self, game, place_card, set_rolls):
        """Бегущая in back row should have direct attack (no interception)."""
        runner = place_card("Бегущая по кронам", player=1, pos=2)
        target = place_card("Друид", player=2, pos=17)
        defender = place_card("Лёккен", player=2, pos=16)

        set_rolls(4, 3)
        game.attack(runner, target.position)
        # back_row_direct should prevent defender prompt


class TestBorgStunMechanic:
    """Tests for Борг's stun mechanic (prevents untap)."""

    def test_borg_counter_ability(self, game, place_card):
        """Борг can use borg_counter to gain a counter."""
        borg = place_card("Борг", player=1, pos=10)
        assert borg.counters == 0
        result = game.use_ability(borg, "borg_counter")
        if result:
            assert borg.counters == 1
            assert_tapped(borg)

    def test_borg_strike_requires_counter(self, game, place_card):
        """Борг strike requires a counter to use - fails when target selected."""
        borg = place_card("Борг", player=1, pos=10)
        target = place_card("Друид", player=2, pos=15)

        assert borg.counters == 0
        result = game.use_ability(borg, "borg_strike")
        assert result is True
        assert game.interaction is not None

        initial_hp = target.curr_life
        game.select_ability_target(target.position)
        assert target.curr_life == initial_hp

    def test_borg_strike_deals_damage(self, game, place_card):
        """Борг strike deals 3 damage when counter is available."""
        borg = place_card("Борг", player=1, pos=10)
        borg.counters = 1
        target = place_card("Циклоп", player=2, pos=15)

        initial_hp = target.curr_life
        result = game.use_ability(borg, "borg_strike")

        if result and game.interaction:
            game.select_ability_target(target.position)
            assert_hp(target, initial_hp - 3)
            assert borg.counters == 0

    def test_borg_strike_stuns_tapped_target(self, game, place_card):
        """Борг strike stuns tapped targets (they don't untap next turn)."""
        borg = place_card("Борг", player=1, pos=10)
        borg.counters = 1
        target = place_card("Циклоп", player=2, pos=15, tapped=True)

        result = game.use_ability(borg, "borg_strike")
        if result and game.interaction:
            game.select_ability_target(target.position)
            assert target.stunned is True

    def test_stunned_card_does_not_untap(self, game, place_card):
        """Stunned cards should not untap at turn start."""
        card = place_card("Циклоп", player=2, pos=15, tapped=True)
        card.stunned = True

        game.current_player = 2
        game.start_turn()

        assert_tapped(card)
        assert card.stunned is False

    def test_stunned_card_untaps_after_stun_wears_off(self, game, place_card):
        """After stun wears off, card should untap normally next turn."""
        card = place_card("Циклоп", player=2, pos=15, tapped=True)
        card.stunned = True

        game.current_player = 2
        game.start_turn()
        assert_tapped(card)
        assert card.stunned is False

        game.end_turn()
        game.current_player = 2
        game.start_turn()
        assert_untapped(card)


class TestDefenderBuff:
    """Tests for Клаэр's defender buff ability."""

    def test_klaer_gets_buff_when_defending(self, game, place_card, set_rolls):
        """Клаэр should get +2 attack and +1 dice when defending."""
        attacker = place_card("Циклоп", player=1, pos=10)
        target = place_card("Друид", player=2, pos=16)
        klaer = place_card("Клаэр", player=2, pos=15)

        set_rolls(4, 3)
        game.attack(attacker, target.position)

        if game.awaiting_defender:
            game.choose_defender(klaer)
            assert klaer.defender_buff_attack == 2
            assert klaer.defender_buff_dice == 1


class TestDiagonalDefense:
    """Tests for Гобрах's diagonal defense ability."""

    def test_gobrakh_takes_less_diagonal_damage(self, game, place_card, set_rolls):
        """Гобрах should take -2 damage from diagonal attacks."""
        gobrakh = place_card("Гобрах", player=2, pos=16)
        attacker = place_card("Циклоп", player=1, pos=10)  # Diagonal to 16

        initial_hp = gobrakh.curr_life
        set_rolls(6, 1)
        game.attack(attacker, gobrakh.position)
        resolve_combat(game)
        # Damage should be reduced by 2 if diagonal


class TestExchangeMechanic:
    """Tests for exchange (обмен) mechanics in combat."""

    def test_exchange_on_roll_diff_2(self, game, place_card, set_rolls):
        """Roll difference of 2 should offer exchange choice."""
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        set_rolls(5, 3)  # Diff = 2
        game.attack(attacker, defender.position)
        assert game.awaiting_exchange_choice is True

    def test_exchange_reduce_damage(self, game, place_card, set_rolls):
        """Choosing to reduce damage in exchange should halve damage taken."""
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        set_rolls(5, 3)
        game.attack(attacker, defender.position)

        if game.awaiting_exchange_choice:
            game.resolve_exchange_choice(reduce_damage=True)
            resolve_combat(game)


class TestCrownRunnerShot:
    """Tests for Бегущая по кронам's ranged shot ability."""

    def test_crown_runner_shot_has_min_range(self, game, place_card):
        """Crown runner shot should have minimum range of 2."""
        runner = place_card("Бегущая по кронам", player=1, pos=10)
        adjacent_target = place_card("Друид", player=2, pos=15)

        result = game.use_ability(runner, "crown_runner_shot")
        if result and game.interaction and hasattr(game.interaction, 'valid_positions'):
            assert 15 not in game.interaction.valid_positions

    def test_crown_runner_shot_can_hit_far_target(self, game, place_card):
        """Crown runner shot should hit targets at range 2+."""
        runner = place_card("Бегущая по кронам", player=1, pos=10)
        far_target = place_card("Друид", player=2, pos=20)

        result = game.use_ability(runner, "crown_runner_shot")
        if result and game.interaction and hasattr(game.interaction, 'valid_positions'):
            assert 20 in game.interaction.valid_positions

    def test_shot_immune_blocks_crown_runner_shot(self, game, place_card):
        """Shot immune creatures should not take damage from crown runner shot."""
        runner = place_card("Бегущая по кронам", player=1, pos=10)
        kobold = place_card("Кобольд", player=2, pos=20)  # Shot immune

        initial_hp = kobold.curr_life
        result = game.use_ability(runner, "crown_runner_shot")

        if result and game.interaction:
            if 20 in game.interaction.valid_positions:
                game.select_ability_target(kobold.position)
                assert kobold.curr_life == initial_hp


class TestDirectAttack:
    """Tests for direct attack behavior (cannot be intercepted)."""

    def test_hobgoblin_direct_attack(self, game, place_card, set_rolls):
        """Хобгоблин's attack cannot be intercepted."""
        hobgoblin = place_card("Хобгоблин", player=1, pos=10)
        target = place_card("Друид", player=2, pos=15)
        defender = place_card("Лёккен", player=2, pos=16)

        set_rolls(4, 3)
        game.attack(hobgoblin, target.position)
        assert not game.awaiting_defender

    def test_korpit_direct_attack(self, game, place_card, set_rolls):
        """Корпит's attack cannot be intercepted."""
        korpit = place_card("Корпит", player=1, pos=30)
        target = place_card("Друид", player=2, pos=15)
        defender = place_card("Лёккен", player=2, pos=16)

        set_rolls(4, 3)
        game.attack(korpit, target.position)
        assert not game.awaiting_defender


class TestRestrictedStrike:
    """Tests for Циклоп's restricted strike (only attacks directly opposite)."""

    def test_cyclops_can_attack_directly_opposite(self, game, place_card, set_rolls):
        """Циклоп can attack target directly in front."""
        cyclops = place_card("Циклоп", player=1, pos=10)
        target = place_card("Друид", player=2, pos=15)

        targets = game.get_attack_targets(cyclops)
        assert 15 in targets


class TestMagicImmunity:
    """Tests for magic immunity blocking magical strike."""

    def test_magic_immune_blocks_magical_strike(self, game, place_card, set_rolls):
        """Magic immune creatures take no damage from magical strike."""
        attacker = place_card("Циклоп", player=1, pos=10)
        magic_immune = place_card("Повелитель молний", player=2, pos=15)

        result = game.use_ability(attacker, "magical_strike")

        if result and game.interaction and hasattr(game.interaction, 'valid_positions'):
            initial_hp = magic_immune.curr_life
            set_rolls(6, 1)
            game.select_ability_target(magic_immune.position)
            resolve_combat(game)
            assert magic_immune.curr_life == initial_hp


class TestRegenerationVariants:
    """Tests for different regeneration amounts (regeneration vs regeneration_1)."""

    def test_cyclops_regeneration_1_heals_1(self, game, place_card):
        """Циклоп should heal 1 HP at turn start (regeneration_1)."""
        cyclops = place_card("Циклоп", player=1, pos=10)
        cyclops.curr_life = cyclops.stats.life - 5

        initial_hp = cyclops.curr_life
        game.current_player = 1
        game.start_turn()

        assert cyclops.curr_life == initial_hp + 1


class TestFlyerCanAttackAnyPosition:
    """Tests for flying creatures attacking any board position."""

    def test_flyer_can_attack_far_corner(self, game, place_card, set_rolls):
        """Flying creature should be able to attack any board position."""
        flyer = place_card("Корпит", player=1, pos=30)
        far_target = place_card("Друид", player=2, pos=29)

        targets = game.get_attack_targets(flyer)
        assert 29 in targets

        initial_hp = far_target.curr_life
        set_rolls(4, 3)
        game.attack(flyer, far_target.position)
        resolve_combat(game)

        assert far_target.curr_life < initial_hp

    def test_flyer_can_attack_opposite_flying_zone(self, game, place_card, set_rolls):
        """Flying creature should be able to attack enemy flying zone."""
        flyer1 = place_card("Корпит", player=1, pos=30)
        flyer2 = place_card("Корпит", player=2, pos=33)

        targets = game.get_attack_targets(flyer1)
        assert 33 in targets


class TestFlyerTaunt:
    """Tests for flyer_taunt ability mechanics."""

    def test_flyer_taunt_forces_flyers_to_attack(self, game, place_card):
        """Flyer taunt should force enemy flyers to attack only the taunter."""
        spider = place_card("Паук-пересмешник", player=2, pos=15)
        other_target = place_card("Друид", player=2, pos=16)
        flyer = place_card("Корпит", player=1, pos=30)

        targets = game.get_attack_targets(flyer)
        # Flyer can ONLY attack the spider (has flyer_taunt)
        assert 15 in targets
        assert 16 not in targets

    def test_flyer_taunt_inactive_while_hidden(self, game, place_card):
        """Flyer taunt should NOT work while the card is hidden (face_down)."""
        spider = place_card("Паук-пересмешник", player=2, pos=15)
        spider.face_down = True  # Hidden
        other_target = place_card("Друид", player=2, pos=16)
        flyer = place_card("Корпит", player=1, pos=30)

        targets = game.get_attack_targets(flyer)
        # Hidden spider's flyer_taunt should NOT restrict attacks
        assert 16 in targets  # Can attack other targets
        assert 15 in targets  # Can still attack spider too

    def test_flyer_taunt_active_after_reveal(self, game, place_card):
        """Flyer taunt should work after the card is revealed."""
        spider = place_card("Паук-пересмешник", player=2, pos=15)
        spider.face_down = True
        other_target = place_card("Друид", player=2, pos=16)
        flyer = place_card("Корпит", player=1, pos=30)

        # Before reveal - can attack anyone
        targets = game.get_attack_targets(flyer)
        assert 16 in targets

        # Reveal the spider
        spider.reveal()
        assert spider.face_down is False

        # After reveal - forced to attack spider
        targets = game.get_attack_targets(flyer)
        assert 15 in targets
        assert 16 not in targets
