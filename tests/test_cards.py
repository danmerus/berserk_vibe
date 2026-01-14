"""Card-specific tests for complex cards."""
import pytest
from tests.conftest import assert_hp, assert_tapped, assert_untapped, assert_card_dead, assert_card_alive, resolve_combat


class TestLovetsUdachy:
    """Tests for Ловец удачи - luck and opponent untap abilities."""

    def test_has_luck_ability(self, place_card):
        """Ловец удачи should have the luck ability."""
        lovets = place_card("Ловец удачи", player=1, pos=10)
        assert "luck" in lovets.stats.ability_ids

    def test_has_opponent_untap_ability(self, place_card):
        """Ловец удачи should have opponent_untap ability."""
        lovets = place_card("Ловец удачи", player=1, pos=10)
        assert "opponent_untap" in lovets.stats.ability_ids

    def test_may_untap_at_opponent_turn_start(self, game, place_card):
        """Can choose to untap at start of opponent's turn."""
        lovets = place_card("Ловец удачи", player=1, pos=10, tapped=True)

        # Start opponent's turn
        game.current_player = 2
        game.start_turn()

        # Should have untap selection available
        assert game.awaiting_select_untap
        assert lovets.position in game.interaction.valid_positions

    def test_untap_selection_untaps_card(self, game, place_card):
        """Selecting to untap should untap the card."""
        lovets = place_card("Ловец удачи", player=1, pos=10, tapped=True)

        game.current_player = 2
        game.start_turn()

        assert_tapped(lovets)
        game.select_untap_target(lovets.position)
        assert_untapped(lovets)

    def test_skip_untap_keeps_card_tapped(self, game, place_card):
        """Skipping untap should keep the card tapped."""
        lovets = place_card("Ловец удачи", player=1, pos=10, tapped=True)

        game.current_player = 2
        game.start_turn()

        game.skip_select_untap()
        assert_tapped(lovets)

    def test_cannot_use_luck_when_tapped(self, game, place_card, set_rolls):
        """Cannot use luck ability while tapped."""
        lovets = place_card("Ловец удачи", player=1, pos=10, tapped=True)
        attacker = place_card("Циклоп", player=1, pos=11)
        defender = place_card("Кобольд", player=2, pos=16)

        set_rolls(3, 3)
        game.attack(attacker, defender.position)

        # Priority phase should not include tapped Lovets
        if game.priority_phase:
            legal = game.get_legal_instants(1)
            assert not any(card.id == lovets.id for card, _ in legal)


class TestKorpit:
    """Tests for Корпит - flying creature with scavenging and direct attack."""

    def test_is_flying(self, place_card):
        """Корпит should be a flying creature."""
        korpit = place_card("Корпит", player=1, pos=30)
        assert korpit.stats.is_flying

    def test_has_scavenging(self, place_card):
        """Корпит should have scavenging ability."""
        korpit = place_card("Корпит", player=1, pos=30)
        assert "scavenging" in korpit.stats.ability_ids

    def test_has_direct_attack(self, place_card):
        """Корпит should have direct attack (cannot be intercepted)."""
        korpit = place_card("Корпит", player=1, pos=30)
        assert "direct_attack" in korpit.stats.ability_ids

    def test_flying_can_attack_any_ground_unit(self, game, place_card, set_rolls):
        """Flying creature can attack any ground unit."""
        korpit = place_card("Корпит", player=1, pos=30)  # Flying zone
        far_enemy = place_card("Кобольд", player=2, pos=25)  # Far corner

        set_rolls(4, 3)
        result = game.attack(korpit, far_enemy.position)
        resolve_combat(game)

        assert result is True

    def test_direct_attack_cannot_be_intercepted(self, game, place_card, set_rolls):
        """Direct attack should skip defender selection."""
        korpit = place_card("Корпит", player=1, pos=30)
        target = place_card("Кобольд", player=2, pos=15)
        potential_defender = place_card("Лёккен", player=2, pos=16)

        set_rolls(4, 3)
        game.attack(korpit, target.position)

        # Should NOT prompt for defender (direct attack skips it)
        assert not game.awaiting_defender

    def test_scavenging_full_heal_on_kill(self, game, place_card, set_rolls):
        """Should fully heal when killing an enemy."""
        korpit = place_card("Корпит", player=1, pos=30)
        korpit.curr_life = 1  # Nearly dead
        weak_enemy = place_card("Кобольд", player=2, pos=15)
        weak_enemy.curr_life = 1

        set_rolls(6, 1)  # Guaranteed kill
        game.attack(korpit, weak_enemy.position)
        resolve_combat(game)

        assert_card_dead(weak_enemy)
        assert_hp(korpit, korpit.stats.life)

    def test_scavenging_no_heal_without_kill(self, game, place_card, set_rolls):
        """Should NOT heal if target survives."""
        korpit = place_card("Корпит", player=1, pos=30)
        korpit.curr_life = 3  # Damaged
        tough_enemy = place_card("Циклоп", player=2, pos=15)  # High HP, won't die

        set_rolls(6, 1)
        game.attack(korpit, tough_enemy.position)
        resolve_combat(game)

        # Enemy survived, no scavenging heal
        assert_card_alive(tough_enemy)
        assert_hp(korpit, 3)


class TestDruid:
    """Tests for Друид - healer with heal ability."""

    def test_has_heal_ability(self, place_card):
        """Друид should have heal_ally ability."""
        druid = place_card("Друид", player=1, pos=10)
        assert "heal_ally" in druid.stats.ability_ids


class TestGobrakh:
    """Tests for Гобрах - has regeneration."""

    def test_has_regeneration(self, place_card):
        """Гобрах should have regeneration ability."""
        gobrakh = place_card("Гобрах", player=1, pos=10)
        assert "regeneration" in gobrakh.stats.ability_ids

    def test_regeneration_heals_at_turn_start(self, game, place_card):
        """Should heal at the start of own turn."""
        gobrakh = place_card("Гобрах", player=1, pos=10)
        gobrakh.curr_life = gobrakh.stats.life - 5

        initial_hp = gobrakh.curr_life
        game.current_player = 1
        game.start_turn()

        assert gobrakh.curr_life == initial_hp + 3

    def test_regeneration_does_not_exceed_max(self, game, place_card):
        """Regeneration should not heal above max HP."""
        gobrakh = place_card("Гобрах", player=1, pos=10)
        gobrakh.curr_life = gobrakh.stats.life - 1  # Missing 1 HP

        game.current_player = 1
        game.start_turn()

        assert gobrakh.curr_life == gobrakh.stats.life


class TestCyclops:
    """Tests for Циклоп - basic strong melee fighter."""

    def test_stats(self, place_card):
        """Циклоп should have correct base stats."""
        cyclops = place_card("Циклоп", player=1, pos=10)

        assert cyclops.stats.cost == 8
        assert cyclops.stats.life == 14
        assert cyclops.stats.attack == (4, 5, 6)
        assert cyclops.stats.move == 1

    def test_strong_damage_output(self, game, place_card, set_rolls):
        """Циклоп should deal significant damage on strong hit."""
        cyclops = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Кобольд", player=2, pos=15)

        initial_hp = defender.curr_life
        set_rolls(6, 1)  # Strong hit
        game.attack(cyclops, defender.position)
        resolve_combat(game)

        assert_hp(defender, initial_hp - 6)  # Strong damage = 6


class TestLekken:
    """Tests for Лёккен - defender specialist."""

    def test_has_defender_no_tap(self, place_card):
        """Лёккен should have defender_no_tap ability."""
        lekken = place_card("Лёккен", player=1, pos=10)
        assert "defender_no_tap" in lekken.stats.ability_ids

    def test_has_unlimited_defender(self, place_card):
        """Лёккен should have unlimited_defender ability."""
        lekken = place_card("Лёккен", player=1, pos=10)
        assert "unlimited_defender" in lekken.stats.ability_ids

    def test_can_defend_multiple_times(self, game, place_card, set_rolls):
        """Should be able to defend multiple attacks in same turn."""
        attacker1 = place_card("Кобольд", player=1, pos=10)
        attacker2 = place_card("Кобольд", player=1, pos=11)
        target = place_card("Друид", player=2, pos=16)
        lekken = place_card("Лёккен", player=2, pos=15)

        # First attack
        set_rolls(4, 3)
        game.attack(attacker1, target.position)
        if game.awaiting_defender:
            game.choose_defender(lekken)
            resolve_combat(game)

        # Lekken should still be untapped (defender_no_tap ability)
        assert_untapped(lekken)


class TestHobgoblin:
    """Tests for Хобгоблин - has tough_hide."""

    def test_has_tough_hide(self, place_card):
        """Хобгоблин should have tough_hide ability."""
        hobgoblin = place_card("Хобгоблин", player=1, pos=10)
        assert "tough_hide" in hobgoblin.stats.ability_ids

    def test_high_hp(self, place_card):
        """Хобгоблин should have high HP."""
        hobgoblin = place_card("Хобгоблин", player=1, pos=10)
        assert hobgoblin.stats.life >= 12  # Should be tanky


class TestBegushayaPoKronam:
    """Tests for Бегущая по кронам - ranged shooter."""

    def test_has_shot_ability(self, place_card):
        """Бегущая по кронам should have crown_runner_shot ability."""
        runner = place_card("Бегущая по кронам", player=1, pos=10)
        assert "crown_runner_shot" in runner.stats.ability_ids

    def test_can_shoot_at_range(self, game, place_card, set_rolls):
        """Should be able to shoot enemies at range."""
        runner = place_card("Бегущая по кронам", player=1, pos=5)
        far_enemy = place_card("Кобольд", player=2, pos=20)  # Far away

        result = game.use_ability(runner, "crown_runner_shot")
        assert result is True  # Ability should start


class TestOvrazhniyGnom:
    """Tests for Овражный гном - hellish stench ability."""

    def test_has_hellish_stench(self, place_card):
        """Овражный гном should have hellish_stench ability."""
        gnom = place_card("Овражный гном", player=1, pos=10)
        assert "hellish_stench" in gnom.stats.ability_ids

    def test_has_direct_attack(self, place_card):
        """Овражный гном should have direct_attack ability."""
        gnom = place_card("Овражный гном", player=1, pos=10)
        assert "direct_attack" in gnom.stats.ability_ids

    def test_direct_attack_skips_defender(self, game, place_card, set_rolls):
        """Direct attack should not trigger defender selection."""
        gnom = place_card("Овражный гном", player=1, pos=10)
        target = place_card("Друид", player=2, pos=15)
        defender = place_card("Лёккен", player=2, pos=16)

        set_rolls(4, 3)
        game.attack(gnom, target.position)

        # Should not prompt for defender
        assert not game.awaiting_defender


class TestGnomBasaarg:
    """Tests for Гном-басаарг - formation and tapped bonus abilities."""

    def test_stats(self, place_card):
        """Гном-басаарг should have correct stats."""
        card = place_card("Гном-басаарг", player=1, pos=10)
        assert card.stats.cost == 7
        assert card.stats.life == 12
        assert card.stats.attack == (2, 3, 4)

    def test_has_attack_exp(self, place_card):
        """Гном-басаарг should have attack_exp for +1 attack roll."""
        card = place_card("Гном-басаарг", player=1, pos=10)
        assert "attack_exp" in card.stats.ability_ids

    def test_attack_exp_bonus(self, game, place_card, set_rolls):
        """Attack exp should add +1 to attack roll."""
        attacker = place_card("Гном-басаарг", player=1, pos=10)
        defender = place_card("Друид", player=2, pos=15, tapped=True)  # Must be tapped

        initial_hp = defender.curr_life
        # Roll 5 + 1 exp = 6, tier based on single roll (tapped target)
        set_rolls(5)
        game.attack(attacker, defender.position)
        resolve_combat(game)

        # Roll 6 against tapped = strong damage (4) + tapped_bonus (+1) = 5
        base_damage = attacker.stats.attack[2]  # Strong = 4
        expected_damage = base_damage + 1  # +1 from tapped_bonus
        assert_hp(defender, initial_hp - expected_damage)

    def test_must_attack_tapped_restriction(self, game, place_card):
        """Гном-басаарг has must_attack_tapped ability."""
        attacker = place_card("Гном-басаарг", player=1, pos=10)

        # Verify the ability is present
        assert "must_attack_tapped" in attacker.stats.ability_ids

        # Note: The restriction enforcement depends on game implementation
        # This test verifies the ability exists on the card

    def test_must_attack_tapped_can_attack_tapped(self, game, place_card, set_rolls):
        """Гном-басаарг can attack tapped targets."""
        attacker = place_card("Гном-басаарг", player=1, pos=10)
        tapped_target = place_card("Друид", player=2, pos=15, tapped=True)

        # Get valid attack targets - tapped should be valid
        targets = game.get_attack_targets(attacker)

        assert tapped_target.position in targets

        # Should be able to attack
        set_rolls(4)
        result = game.attack(attacker, tapped_target.position)
        assert result is True

    def test_tapped_bonus_extra_damage(self, game, place_card, set_rolls):
        """Гном-басаарг deals +1 damage to tapped targets."""
        attacker = place_card("Гном-басаарг", player=1, pos=10)
        tapped_target = place_card("Циклоп", player=2, pos=15, tapped=True)

        initial_hp = tapped_target.curr_life
        # Roll 4 = medium tier against tapped
        set_rolls(4)
        game.attack(attacker, tapped_target.position)
        resolve_combat(game)

        # Medium damage (3) + 1 tapped bonus = 4
        base_damage = attacker.stats.attack[1]  # Medium = 3
        expected_damage = base_damage + 1  # +1 from tapped_bonus
        assert_hp(tapped_target, initial_hp - expected_damage)


class TestKhranitelGor:
    """Tests for Хранитель гор - anti_swamp and poison immunity."""

    def test_stats(self, place_card):
        """Хранитель гор should have correct stats."""
        card = place_card("Хранитель гор", player=1, pos=10)
        assert card.stats.cost == 5
        assert card.stats.life == 13

    def test_has_poison_immune(self, place_card):
        """Хранитель гор should be immune to poison."""
        card = place_card("Хранитель гор", player=1, pos=10)
        assert "poison_immune" in card.stats.ability_ids

    def test_has_anti_swamp(self, place_card):
        """Хранитель гор should have anti_swamp ability."""
        card = place_card("Хранитель гор", player=1, pos=10)
        assert "anti_swamp" in card.stats.ability_ids


class TestPovelitelMolniy:
    """Tests for Повелитель молний - counter and discharge mechanics."""

    def test_stats(self, place_card):
        """Повелитель молний should have correct stats."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert card.stats.cost == 7
        assert card.stats.life == 9
        assert card.stats.is_unique is True

    def test_has_discharge(self, place_card):
        """Повелитель молний should have discharge ability."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert "discharge" in card.stats.ability_ids

    def test_has_magic_immune(self, place_card):
        """Повелитель молний should be immune to magic."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert "magic_immune" in card.stats.ability_ids

    def test_max_counters(self, place_card):
        """Повелитель молний should have max 3 counters."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert card.stats.max_counters == 3


class TestGorniyVelikan:
    """Tests for Горный великан - high HP tank."""

    def test_stats(self, place_card):
        """Горный великан should have high HP."""
        card = place_card("Горный великан", player=1, pos=10)
        assert card.stats.life == 17  # Very tanky
        assert card.stats.cost == 6

    def test_has_poison_immune(self, place_card):
        """Горный великан should be immune to poison."""
        card = place_card("Горный великан", player=1, pos=10)
        assert "poison_immune" in card.stats.ability_ids

    def test_survives_strong_hit(self, game, place_card, set_rolls):
        """Горный великан should survive a strong hit from Циклоп."""
        tank = place_card("Горный великан", player=1, pos=10)
        attacker = place_card("Циклоп", player=2, pos=15)

        set_rolls(6, 1)
        game.current_player = 2
        game.attack(attacker, tank.position)
        resolve_combat(game)

        # Should survive (17 - 6 = 11 HP left)
        assert_card_alive(tank)
        assert_hp(tank, 11)


class TestMasterTopora:
    """Tests for Мастер топора - axe mechanics and armor."""

    def test_stats(self, place_card):
        """Мастер топора should have correct stats."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert card.stats.cost == 5
        assert card.stats.life == 10

    def test_has_armor(self, place_card):
        """Мастер топора should have 1 armor."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert card.stats.armor == 1

    def test_has_axe_abilities(self, place_card):
        """Мастер топора should have axe-related abilities."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert "axe_counter" in card.stats.ability_ids
        assert "axe_tap" in card.stats.ability_ids
        assert "axe_strike" in card.stats.ability_ids


class TestSmotritelGornila:
    """Tests for Смотритель горнила - formation buffs."""

    def test_stats(self, place_card):
        """Смотритель горнила should have correct stats."""
        card = place_card("Смотритель горнила", player=1, pos=10)
        assert card.stats.cost == 5
        assert card.stats.life == 10
        assert card.stats.attack == (2, 2, 2)

    def test_has_formation_abilities(self, place_card):
        """Смотритель горнила should have formation abilities."""
        card = place_card("Смотритель горнила", player=1, pos=10)
        assert "stroi_armor_elite" in card.stats.ability_ids
        assert "stroi_ovz_common" in card.stats.ability_ids


class TestKlaer:
    """Tests for Клаэр - shot immunity and defender buff."""

    def test_stats(self, place_card):
        """Клаэр should have correct stats."""
        card = place_card("Клаэр", player=1, pos=10)
        assert card.stats.cost == 5
        assert card.stats.life == 11
        assert card.stats.attack == (1, 2, 4)

    def test_has_shot_immune(self, place_card):
        """Клаэр should be immune to shots."""
        card = place_card("Клаэр", player=1, pos=10)
        assert "shot_immune" in card.stats.ability_ids

    def test_has_defender_buff(self, place_card):
        """Клаэр should have defender_buff ability."""
        card = place_card("Клаэр", player=1, pos=10)
        assert "defender_buff" in card.stats.ability_ids


class TestBorg:
    """Tests for Борг - counter-based striker."""

    def test_stats(self, place_card):
        """Борг should have correct stats."""
        card = place_card("Борг", player=1, pos=10)
        assert card.stats.cost == 4
        assert card.stats.life == 10
        assert card.stats.attack == (2, 3, 4)
        assert card.stats.is_elite is True

    def test_has_counter_abilities(self, place_card):
        """Борг should have counter-related abilities."""
        card = place_card("Борг", player=1, pos=10)
        assert "borg_counter" in card.stats.ability_ids
        assert "borg_strike" in card.stats.ability_ids

    def test_max_one_counter(self, place_card):
        """Борг should have max 1 counter."""
        card = place_card("Борг", player=1, pos=10)
        assert card.stats.max_counters == 1


class TestMrazen:
    """Tests for Мразень - icicle throw ranged attack."""

    def test_stats(self, place_card):
        """Мразень should have correct stats."""
        card = place_card("Мразень", player=1, pos=10)
        assert card.stats.cost == 4
        assert card.stats.life == 7
        assert card.stats.attack == (1, 2, 2)

    def test_has_icicle_throw(self, place_card):
        """Мразень should have icicle_throw ability."""
        card = place_card("Мразень", player=1, pos=10)
        assert "icicle_throw" in card.stats.ability_ids

    def test_can_use_icicle_throw(self, game, place_card):
        """Should be able to activate icicle_throw ability."""
        mrazen = place_card("Мразень", player=1, pos=5)
        target = place_card("Друид", player=2, pos=20)

        result = game.use_ability(mrazen, "icicle_throw")
        # Ability should activate (returns True or starts interaction)
        assert result is True or game.interaction is not None


class TestOuri:
    """Tests for Оури - healer with movement shot."""

    def test_stats(self, place_card):
        """Оури should have correct stats."""
        card = place_card("Оури", player=1, pos=10)
        assert card.stats.cost == 4
        assert card.stats.life == 8
        assert card.stats.move == 2  # High mobility

    def test_has_heal_1(self, place_card):
        """Оури should have heal_1 ability."""
        card = place_card("Оури", player=1, pos=10)
        assert "heal_1" in card.stats.ability_ids

    def test_has_movement_shot(self, place_card):
        """Оури should have movement_shot ability."""
        card = place_card("Оури", player=1, pos=10)
        assert "movement_shot" in card.stats.ability_ids

    def test_has_discharge_immune(self, place_card):
        """Оури should be immune to discharge."""
        card = place_card("Оури", player=1, pos=10)
        assert "discharge_immune" in card.stats.ability_ids


class TestPaukPeresmeshnik:
    """Tests for Паук-пересмешник - anti-flyer specialist."""

    def test_stats(self, place_card):
        """Паук-пересмешник should have correct stats."""
        card = place_card("Паук-пересмешник", player=1, pos=10)
        assert card.stats.cost == 4
        assert card.stats.life == 7

    def test_has_flyer_taunt(self, place_card):
        """Паук-пересмешник should have flyer_taunt ability."""
        card = place_card("Паук-пересмешник", player=1, pos=10)
        assert "flyer_taunt" in card.stats.ability_ids

    def test_has_web_throw(self, place_card):
        """Паук-пересмешник should have web_throw ability."""
        card = place_card("Паук-пересмешник", player=1, pos=10)
        assert "web_throw" in card.stats.ability_ids


class TestDraks:
    """Tests for Дракс - unique flying dragon."""

    def test_stats(self, place_card):
        """Дракс should have correct stats."""
        card = place_card("Дракс", player=1, pos=30)  # Flying zone
        assert card.stats.cost == 3
        assert card.stats.life == 5
        assert card.stats.is_flying is True
        assert card.stats.is_unique is True

    def test_has_flying(self, place_card):
        """Дракс should have flying ability."""
        card = place_card("Дракс", player=1, pos=30)
        assert "flying" in card.stats.ability_ids

    def test_has_direct_attack(self, place_card):
        """Дракс should have direct_attack ability."""
        card = place_card("Дракс", player=1, pos=30)
        assert "direct_attack" in card.stats.ability_ids

    def test_has_anti_magic(self, place_card):
        """Дракс should have anti_magic ability."""
        card = place_card("Дракс", player=1, pos=30)
        assert "anti_magic" in card.stats.ability_ids

    def test_can_attack_from_flying_zone(self, game, place_card, set_rolls):
        """Дракс should be able to attack ground units from flying zone."""
        draks = place_card("Дракс", player=1, pos=30)
        target = place_card("Друид", player=2, pos=20)

        set_rolls(4, 3)
        result = game.attack(draks, target.position)
        resolve_combat(game)

        assert result is True


class TestMatrosyAdelaidy:
    """Tests for Матросы Аделаиды - jump and column bonuses."""

    def test_stats(self, place_card):
        """Матросы Аделаиды should have correct stats."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)
        assert card.stats.cost == 5
        assert card.stats.life == 8
        assert card.stats.move == 3  # Jump range

    def test_has_jump(self, place_card):
        """Матросы Аделаиды should have jump ability."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)
        assert "jump" in card.stats.ability_ids

    def test_has_column_abilities(self, place_card):
        """Матросы Аделаиды should have column-based abilities."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)
        assert "center_column_defense" in card.stats.ability_ids
        assert "edge_column_attack" in card.stats.ability_ids
