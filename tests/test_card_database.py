"""Tests for full card coverage - all cards in the database."""
import pytest
from tests.conftest import assert_hp, assert_tapped, assert_untapped, assert_card_dead, assert_card_alive, resolve_combat


class TestGnomBasaarg:
    """Tests for Гном-басаарг - formation and tapped bonus abilities."""

    def test_has_correct_stats(self, place_card):
        """Гном-басаарг should have correct base stats."""
        card = place_card("Гном-басаарг", player=1, pos=10)

        assert card.stats.cost == 7
        assert card.stats.life == 12
        assert card.stats.attack == (2, 3, 4)
        assert card.stats.move == 1

    def test_has_attack_exp(self, place_card):
        """Гном-басаарг should have attack_exp ability."""
        card = place_card("Гном-басаарг", player=1, pos=10)
        assert "attack_exp" in card.stats.ability_ids

    def test_has_stroi_atk_1(self, place_card):
        """Гном-басаарг should have stroi_atk_1 formation ability."""
        card = place_card("Гном-басаарг", player=1, pos=10)
        assert "stroi_atk_1" in card.stats.ability_ids

    def test_has_tapped_bonus(self, place_card):
        """Гном-басаарг should have tapped_bonus ability."""
        card = place_card("Гном-басаарг", player=1, pos=10)
        assert "tapped_bonus" in card.stats.ability_ids

    def test_has_must_attack_tapped(self, place_card):
        """Гном-басаарг should have must_attack_tapped ability."""
        card = place_card("Гном-басаарг", player=1, pos=10)
        assert "must_attack_tapped" in card.stats.ability_ids


class TestKhranitelGor:
    """Tests for Хранитель гор - anti_swamp and poison_immune."""

    def test_has_correct_stats(self, place_card):
        """Хранитель гор should have correct base stats."""
        card = place_card("Хранитель гор", player=1, pos=10)

        assert card.stats.cost == 5
        assert card.stats.life == 13
        assert card.stats.attack == (2, 2, 3)

    def test_has_anti_swamp(self, place_card):
        """Хранитель гор should have anti_swamp ability."""
        card = place_card("Хранитель гор", player=1, pos=10)
        assert "anti_swamp" in card.stats.ability_ids

    def test_has_poison_immune(self, place_card):
        """Хранитель гор should have poison_immune ability."""
        card = place_card("Хранитель гор", player=1, pos=10)
        assert "poison_immune" in card.stats.ability_ids


class TestPovelitelMolniy:
    """Tests for Повелитель молний - counter and discharge mechanics."""

    def test_has_correct_stats(self, place_card):
        """Повелитель молний should have correct base stats."""
        card = place_card("Повелитель молний", player=1, pos=10)

        assert card.stats.cost == 7
        assert card.stats.life == 9
        assert card.stats.attack == (2, 2, 3)
        assert card.stats.is_elite is True
        assert card.stats.is_unique is True

    def test_has_gain_counter(self, place_card):
        """Повелитель молний should have gain_counter ability."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert "gain_counter" in card.stats.ability_ids

    def test_has_discharge(self, place_card):
        """Повелитель молний should have discharge ability."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert "discharge" in card.stats.ability_ids

    def test_has_magic_immune(self, place_card):
        """Повелитель молний should have magic_immune ability."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert "magic_immune" in card.stats.ability_ids

    def test_has_max_counters(self, place_card):
        """Повелитель молний should have max_counters = 3."""
        card = place_card("Повелитель молний", player=1, pos=10)
        assert card.stats.max_counters == 3


class TestGorniyVelikan:
    """Tests for Горный великан - formation and high HP."""

    def test_has_correct_stats(self, place_card):
        """Горный великан should have correct base stats."""
        card = place_card("Горный великан", player=1, pos=10)

        assert card.stats.cost == 6
        assert card.stats.life == 17  # High HP tank
        assert card.stats.attack == (2, 3, 5)
        assert card.stats.is_elite is True

    def test_has_stroi_ovz_1(self, place_card):
        """Горный великан should have stroi_ovz_1 formation ability."""
        card = place_card("Горный великан", player=1, pos=10)
        assert "stroi_ovz_1" in card.stats.ability_ids

    def test_has_poison_immune(self, place_card):
        """Горный великан should have poison_immune ability."""
        card = place_card("Горный великан", player=1, pos=10)
        assert "poison_immune" in card.stats.ability_ids


class TestMasterTopora:
    """Tests for Мастер топора - axe mechanics and armor."""

    def test_has_correct_stats(self, place_card):
        """Мастер топора should have correct base stats."""
        card = place_card("Мастер топора", player=1, pos=10)

        assert card.stats.cost == 5
        assert card.stats.life == 10
        assert card.stats.attack == (2, 3, 3)

    def test_has_axe_counter(self, place_card):
        """Мастер топора should have axe_counter ability."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert "axe_counter" in card.stats.ability_ids

    def test_has_axe_tap(self, place_card):
        """Мастер топора should have axe_tap ability."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert "axe_tap" in card.stats.ability_ids

    def test_has_axe_strike(self, place_card):
        """Мастер топора should have axe_strike ability."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert "axe_strike" in card.stats.ability_ids

    def test_has_armor(self, place_card):
        """Мастер топора should have armor = 1."""
        card = place_card("Мастер топора", player=1, pos=10)
        assert card.stats.armor == 1


class TestSmotritelGornila:
    """Tests for Смотритель горнила - formation buffs."""

    def test_has_correct_stats(self, place_card):
        """Смотритель горнила should have correct base stats."""
        card = place_card("Смотритель горнила", player=1, pos=10)

        assert card.stats.cost == 5
        assert card.stats.life == 10
        assert card.stats.attack == (2, 2, 2)

    def test_has_stroi_armor_elite(self, place_card):
        """Смотритель горнила should have stroi_armor_elite ability."""
        card = place_card("Смотритель горнила", player=1, pos=10)
        assert "stroi_armor_elite" in card.stats.ability_ids

    def test_has_stroi_ovz_common(self, place_card):
        """Смотритель горнила should have stroi_ovz_common ability."""
        card = place_card("Смотритель горнила", player=1, pos=10)
        assert "stroi_ovz_common" in card.stats.ability_ids


class TestKlaer:
    """Tests for Клаэр - shot immunity and defender buff."""

    def test_has_correct_stats(self, place_card):
        """Клаэр should have correct base stats."""
        card = place_card("Клаэр", player=1, pos=10)

        assert card.stats.cost == 5
        assert card.stats.life == 11
        assert card.stats.attack == (1, 2, 4)

    def test_has_shot_immune(self, place_card):
        """Клаэр should have shot_immune ability."""
        card = place_card("Клаэр", player=1, pos=10)
        assert "shot_immune" in card.stats.ability_ids

    def test_has_defender_buff(self, place_card):
        """Клаэр should have defender_buff ability."""
        card = place_card("Клаэр", player=1, pos=10)
        assert "defender_buff" in card.stats.ability_ids


class TestBorg:
    """Tests for Борг - counter system."""

    def test_has_correct_stats(self, place_card):
        """Борг should have correct base stats."""
        card = place_card("Борг", player=1, pos=10)

        assert card.stats.cost == 4
        assert card.stats.life == 10
        assert card.stats.attack == (2, 3, 4)
        assert card.stats.is_elite is True

    def test_has_borg_counter(self, place_card):
        """Борг should have borg_counter ability."""
        card = place_card("Борг", player=1, pos=10)
        assert "borg_counter" in card.stats.ability_ids

    def test_has_borg_strike(self, place_card):
        """Борг should have borg_strike ability."""
        card = place_card("Борг", player=1, pos=10)
        assert "borg_strike" in card.stats.ability_ids

    def test_has_max_counters(self, place_card):
        """Борг should have max_counters = 1."""
        card = place_card("Борг", player=1, pos=10)
        assert card.stats.max_counters == 1


class TestMrazen:
    """Tests for Мразень - icicle throw."""

    def test_has_correct_stats(self, place_card):
        """Мразень should have correct base stats."""
        card = place_card("Мразень", player=1, pos=10)

        assert card.stats.cost == 4
        assert card.stats.life == 7
        assert card.stats.attack == (1, 2, 2)

    def test_has_icicle_throw(self, place_card):
        """Мразень should have icicle_throw ability."""
        card = place_card("Мразень", player=1, pos=10)
        assert "icicle_throw" in card.stats.ability_ids


class TestOuri:
    """Tests for Оури - heal and movement shot."""

    def test_has_correct_stats(self, place_card):
        """Оури should have correct base stats."""
        card = place_card("Оури", player=1, pos=10)

        assert card.stats.cost == 4
        assert card.stats.life == 8
        assert card.stats.attack == (1, 1, 2)
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
        """Оури should have discharge_immune ability."""
        card = place_card("Оури", player=1, pos=10)
        assert "discharge_immune" in card.stats.ability_ids


class TestPaukPeresmeshnik:
    """Tests for Паук-пересмешник - flyer taunt and web."""

    def test_has_correct_stats(self, place_card):
        """Паук-пересмешник should have correct base stats."""
        card = place_card("Паук-пересмешник", player=1, pos=10)

        assert card.stats.cost == 4
        assert card.stats.life == 7
        assert card.stats.attack == (1, 2, 2)

    def test_has_flyer_taunt(self, place_card):
        """Паук-пересмешник should have flyer_taunt ability."""
        card = place_card("Паук-пересмешник", player=1, pos=10)
        assert "flyer_taunt" in card.stats.ability_ids

    def test_has_web_throw(self, place_card):
        """Паук-пересмешник should have web_throw ability."""
        card = place_card("Паук-пересмешник", player=1, pos=10)
        assert "web_throw" in card.stats.ability_ids


class TestDraks:
    """Tests for Дракс - flying dragon with anti-magic."""

    def test_has_correct_stats(self, place_card):
        """Дракс should have correct base stats."""
        card = place_card("Дракс", player=1, pos=30)  # Flying zone

        assert card.stats.cost == 3
        assert card.stats.life == 5
        assert card.stats.attack == (1, 1, 2)
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


class TestMatrosyAdelaidy:
    """Tests for Матросы Аделаиды - jump and column bonuses."""

    def test_has_correct_stats(self, place_card):
        """Матросы Аделаиды should have correct base stats."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)

        assert card.stats.cost == 5
        assert card.stats.life == 8
        assert card.stats.attack == (2, 2, 3)
        assert card.stats.move == 3  # Jump range

    def test_has_jump(self, place_card):
        """Матросы Аделаиды should have jump ability."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)
        assert "jump" in card.stats.ability_ids

    def test_has_center_column_defense(self, place_card):
        """Матросы Аделаиды should have center_column_defense ability."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)
        assert "center_column_defense" in card.stats.ability_ids

    def test_has_edge_column_attack(self, place_card):
        """Матросы Аделаиды should have edge_column_attack ability."""
        card = place_card("Матросы Аделаиды", player=1, pos=10)
        assert "edge_column_attack" in card.stats.ability_ids


# =============================================================================
# PREVIOUSLY TESTED CARDS - Verify key abilities still work
# =============================================================================

class TestCyclopsVerify:
    """Verify Циклоп abilities."""

    def test_has_all_abilities(self, place_card):
        """Циклоп should have all expected abilities."""
        card = place_card("Циклоп", player=1, pos=10)

        assert "restricted_strike" in card.stats.ability_ids
        assert "magical_strike" in card.stats.ability_ids
        assert "direct_attack" in card.stats.ability_ids
        assert "poison_immune" in card.stats.ability_ids
        assert "magic_immune" in card.stats.ability_ids
        assert "regeneration_1" in card.stats.ability_ids


class TestLekkenVerify:
    """Verify Лёккен abilities."""

    def test_has_all_abilities(self, place_card):
        """Лёккен should have all expected abilities."""
        card = place_card("Лёккен", player=1, pos=10)

        assert "defender_no_tap" in card.stats.ability_ids
        assert "unlimited_defender" in card.stats.ability_ids
        assert "defense_exp" in card.stats.ability_ids
        assert "discharge_immune" in card.stats.ability_ids


class TestKoboldVerify:
    """Verify Кобольд abilities."""

    def test_has_all_abilities(self, place_card):
        """Кобольд should have all expected abilities."""
        card = place_card("Кобольд", player=1, pos=10)

        assert "lunge" in card.stats.ability_ids
        assert "heal_on_attack" in card.stats.ability_ids
        assert "shot_immune" in card.stats.ability_ids


class TestKorpitVerify:
    """Verify Корпит abilities."""

    def test_has_all_abilities(self, place_card):
        """Корпит should have all expected abilities."""
        card = place_card("Корпит", player=1, pos=30)

        assert "flying" in card.stats.ability_ids
        assert "direct_attack" in card.stats.ability_ids
        assert "scavenging" in card.stats.ability_ids
        assert card.stats.is_flying is True


class TestBegushayaPoKronamVerify:
    """Verify Бегущая по кронам abilities."""

    def test_has_all_abilities(self, place_card):
        """Бегущая по кронам should have all expected abilities."""
        card = place_card("Бегущая по кронам", player=1, pos=10)

        assert "crown_runner_shot" in card.stats.ability_ids
        assert "front_row_bonus" in card.stats.ability_ids
        assert "back_row_direct" in card.stats.ability_ids


class TestElfiyskiyVoinVerify:
    """Verify Эльфийский воин abilities."""

    def test_has_all_abilities(self, place_card):
        """Эльфийский воин should have all expected abilities."""
        card = place_card("Эльфийский воин", player=1, pos=10)

        assert "steppe_defense" in card.stats.ability_ids
        assert "attack_exp" in card.stats.ability_ids
        assert "counter_shot" in card.stats.ability_ids


class TestLovetsUdachyVerify:
    """Verify Ловец удачи abilities."""

    def test_has_all_abilities(self, place_card):
        """Ловец удачи should have all expected abilities."""
        card = place_card("Ловец удачи", player=1, pos=10)

        assert "luck" in card.stats.ability_ids
        assert "lunge" in card.stats.ability_ids
        assert "opponent_untap" in card.stats.ability_ids


class TestHobgoblinVerify:
    """Verify Хобгоблин abilities."""

    def test_has_all_abilities(self, place_card):
        """Хобгоблин should have all expected abilities."""
        card = place_card("Хобгоблин", player=1, pos=10)

        assert "tough_hide" in card.stats.ability_ids
        assert "direct_attack" in card.stats.ability_ids
        assert "poison_immune" in card.stats.ability_ids


class TestGobrakhVerify:
    """Verify Гобрах abilities."""

    def test_has_all_abilities(self, place_card):
        """Гобрах should have all expected abilities."""
        card = place_card("Гобрах", player=1, pos=10)

        assert "regeneration" in card.stats.ability_ids
        assert "diagonal_defense" in card.stats.ability_ids


class TestLedoviyOkhotnikVerify:
    """Verify Ледовый охотник abilities."""

    def test_has_all_abilities(self, place_card):
        """Ледовый охотник should have all expected abilities."""
        card = place_card("Ледовый охотник", player=1, pos=10)

        assert "lunge_2" in card.stats.ability_ids
        assert "lunge_front_buff" in card.stats.ability_ids
        assert "valhalla_ova" in card.stats.ability_ids


class TestKostedrobitelVerify:
    """Verify Костедробитель abilities."""

    def test_has_all_abilities(self, place_card):
        """Костедробитель should have all expected abilities."""
        card = place_card("Костедробитель", player=1, pos=10)

        assert "attack_exp" in card.stats.ability_ids
        assert "defense_exp" in card.stats.ability_ids
        assert "valhalla_strike" in card.stats.ability_ids


class TestDruidVerify:
    """Verify Друид abilities."""

    def test_has_all_abilities(self, place_card):
        """Друид should have all expected abilities."""
        card = place_card("Друид", player=1, pos=10)

        assert "heal_ally" in card.stats.ability_ids
        assert "poison_immune" in card.stats.ability_ids


class TestOvrazhniyGnomVerify:
    """Verify Овражный гном abilities."""

    def test_has_all_abilities(self, place_card):
        """Овражный гном should have all expected abilities."""
        card = place_card("Овражный гном", player=1, pos=10)

        assert "hellish_stench" in card.stats.ability_ids
        assert "closed_attack_bonus" in card.stats.ability_ids
        assert "direct_attack" in card.stats.ability_ids
