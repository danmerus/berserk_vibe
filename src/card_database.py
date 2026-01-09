"""Card database - card definitions and image mappings."""
from typing import Optional, List

from .constants import CardType, Element
from .card import CardStats


# =============================================================================
# CARD IMAGES - Maps card names to image filenames
# =============================================================================

CARD_IMAGES = {
    # Mountains (Горы)
    "Циклоп": "01-101.jpg",
    "Гном-басаарг": "01-053.jpg",
    "Хобгоблин": "01-100.jpg",
    "Хранитель гор": "01-050.jpg",
    "Повелитель молний": "01-066.jpg",
    "Гобрах": "01-064.jpg",
    "Ледовый охотник": "01-045.jpg",
    "Горный великан": "01-061.jpg",
    "Мастер топора": "01-046.jpg",
    "Костедробитель": "01-062.jpg",
    "Смотритель горнила": "01-048.jpg",
    "Овражный гном": "01-037.jpg",
    # Forest (Лес)
    "Лёккен": "01-085.jpg",
    "Эльфийский воин": "01-097.jpg",
    "Бегущая по кронам": "01-079.jpg",
    "Кобольд": "01-092.jpg",
    "Клаэр": "01-082.jpg",
    "Борг": "01-055.jpg",
    "Ловец удачи": "01-181.jpg",
    "Матросы Аделаиды": "01-182.jpg",
    "Мразень": "01-040.jpg",
    "Друид": "01-073.jpg",
    "Корпит": "01-074.jpg",
    "Оури": "01-076.jpg",
    "Паук-пересмешник": "01-077.jpg",
    "Дракс": "01-070.jpg",
}


def get_card_image(card_name: str) -> Optional[str]:
    """Get image filename for a card."""
    return CARD_IMAGES.get(card_name)


# =============================================================================
# CARD DATABASE - All card definitions
# =============================================================================

CARD_DATABASE = {
    # Mountains cards (Горы)
    "Циклоп": CardStats(
        name="Циклоп",
        cost=8,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=14,
        attack=(4, 5, 6),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["restricted_strike", "magical_strike", "direct_attack", "poison_immune", "magic_immune", "regeneration_1"]
    ),
    "Гном-басаарг": CardStats(
        name="Гном-басаарг",
        cost=7,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        card_class="Гном",
        life=12,
        attack=(2, 3, 4),
        move=1,
        description="",
        ability_ids=["ova_1", "stroi_atk_1", "tapped_bonus", "must_attack_tapped"]
    ),
    "Хобгоблин": CardStats(
        name="Хобгоблин",
        cost=8,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=18,
        attack=(3, 4, 5),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["tough_hide", "direct_attack", "poison_immune"]
    ),
    "Хранитель гор": CardStats(
        name="Хранитель гор",
        cost=5,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=13,
        attack=(2, 2, 3),
        move=1,
        description="",
        ability_ids=["anti_swamp", "poison_immune"]
    ),
    "Повелитель молний": CardStats(
        name="Повелитель молний",
        cost=7,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        card_class="Линунг",
        life=9,
        attack=(2, 2, 3),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["gain_counter", "discharge"],
        max_counters=3
    ),
    "Гобрах": CardStats(
        name="Гобрах",
        cost=7,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=10,
        attack=(4, 4, 5),
        move=2,
        is_elite=True,
        description="",
        ability_ids=["regeneration", "diagonal_defense"]
    ),
    "Ледовый охотник": CardStats(
        name="Ледовый охотник",
        cost=5,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=7,
        attack=(1, 2, 3),
        move=2,
        description="",
        ability_ids=["lunge_2", "valhalla_ova"]
    ),
    "Горный великан": CardStats(
        name="Горный великан",
        cost=6,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=17,
        attack=(2, 3, 5),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["stroi_ovz_1", "poison_immune"]
    ),
    "Мастер топора": CardStats(
        name="Мастер топора",
        cost=5,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        card_class="Гном",
        life=10,
        attack=(2, 3, 3),
        move=1,
        description="",
        ability_ids=["axe_counter", "axe_tap", "axe_strike"],
        max_counters=99,  # Effectively unlimited
        armor=1  # Blocks first 1 non-magical damage per turn
    ),
    "Костедробитель": CardStats(
        name="Костедробитель",
        cost=6,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        card_class="Йордлинг",
        life=12,
        attack=(3, 5, 6),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["ova_1", "ovz_1", "valhalla_strike"]
    ),
    "Смотритель горнила": CardStats(
        name="Смотритель горнила",
        cost=5,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        card_class="Гном",
        life=10,
        attack=(2, 2, 2),
        move=1,
        description="",
        ability_ids=["stroi_armor_elite", "stroi_ovz_common"]
    ),
    "Овражный гном": CardStats(
        name="Овражный гном",
        cost=3,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        card_class="Гном",
        life=6,
        attack=(1, 1, 2),
        move=1,
        description="",
        ability_ids=["hellish_stench", "closed_attack_bonus", "direct_attack"]
    ),

    # Forest cards (Лес)
    "Лёккен": CardStats(
        name="Лёккен",
        cost=6,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=10,
        attack=(2, 2, 3),
        move=1,
        card_class="Страж леса",
        description="",
        ability_ids=["defender_no_tap", "unlimited_defender", "defense_exp", "discharge_immune"]
    ),
    "Эльфийский воин": CardStats(
        name="Эльфийский воин",
        cost=6,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=10,
        attack=(2, 3, 4),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["steppe_defense", "attack_exp", "counter_shot"]
    ),
    "Бегущая по кронам": CardStats(
        name="Бегущая по кронам",
        cost=5,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=9,
        attack=(2, 3, 4),
        move=2,
        description="",
        ability_ids=["crown_runner_shot", "front_row_bonus", "back_row_direct"]
    ),
    "Кобольд": CardStats(
        name="Кобольд",
        cost=5,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=11,
        attack=(2, 3, 4),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["lunge", "heal_on_attack", "shot_immune"]
    ),
    "Клаэр": CardStats(
        name="Клаэр",
        cost=5,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=11,
        attack=(1, 2, 4),
        move=1,
        card_class="Дитя Кронга",
        description="",
        ability_ids=["shot_immune", "defender_buff"]
    ),
    "Борг": CardStats(
        name="Борг",
        cost=4,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=10,
        attack=(2, 3, 4),
        move=1,
        is_elite=True,
        description="",
        ability_ids=["borg_counter", "borg_strike"],
        max_counters=1
    ),
    "Ловец удачи": CardStats(
        name="Ловец удачи",
        cost=5,
        element=Element.NEUTRAL,
        card_type=CardType.CREATURE,
        life=8,
        attack=(1, 2, 3),
        move=1,
        description="",
        ability_ids=["luck"]
    ),
    "Мразень": CardStats(
        name="Мразень",
        cost=4,
        element=Element.MOUNTAINS,
        card_type=CardType.CREATURE,
        life=7,
        attack=(1, 2, 2),
        move=1,
        description="",
        ability_ids=["icicle_throw"]
    ),
    "Друид": CardStats(
        name="Друид",
        cost=4,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=7,
        attack=(1, 2, 2),
        move=1,
        description="",
        ability_ids=["heal_ally", "poison_immune"]
    ),
    "Корпит": CardStats(
        name="Корпит",
        cost=4,
        element=Element.FOREST,
        card_type=CardType.FLYER,
        life=6,
        attack=(1, 2, 2),
        move=0,  # Flying creatures don't move traditionally
        is_flying=True,
        description="",
        ability_ids=["flying", "direct_attack", "scavenging"]
    ),
    "Оури": CardStats(
        name="Оури",
        cost=4,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        card_class="Дитя Кронга",
        life=8,
        attack=(1, 1, 2),
        move=2,
        description="",
        ability_ids=["heal_1", "movement_shot", "discharge_immune"]
    ),
    "Паук-пересмешник": CardStats(
        name="Паук-пересмешник",
        cost=4,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        life=7,
        attack=(1, 2, 2),
        move=1,
        description="",
        ability_ids=["flyer_taunt", "web_throw"]
    ),
    "Дракс": CardStats(
        name="Дракс",
        cost=3,
        element=Element.FOREST,
        card_type=CardType.CREATURE,
        card_class="Дракон",
        life=5,
        attack=(1, 1, 2),
        move=1,
        is_flying=True,
        description="",
        ability_ids=["flying", "direct_attack", "anti_magic"]
    ),
    "Матросы Аделаиды": CardStats(
        name="Матросы Аделаиды",
        cost=5,
        element=Element.NEUTRAL,
        card_type=CardType.CREATURE,
        card_class="Пират",
        life=8,
        attack=(2, 2, 3),
        move=3,  # Jump range
        description="",
        ability_ids=["jump", "center_column_defense", "edge_column_attack"]
    ),
}


def create_starter_deck() -> List[str]:
    """Returns list of card names for Player 1 (Mountains themed)."""
    return [
        "Циклоп",
        "Гном-басаарг",
        "Хобгоблин",
        "Хранитель гор", "Хранитель гор",  # 2x for anti-swamp testing
        "Повелитель молний",
        "Гобрах",
        "Ледовый охотник", "Ледовый охотник",  # 2x for Valhalla testing
        "Горный великан", "Горный великан",  # 2x for formation testing
        "Мастер топора",
        "Костедробитель", "Костедробитель",  # 2x
        "Смотритель горнила",
        "Овражный гном",
        "Ловец удачи",
        "Борг",  # Stun ability testing
        "Мразень", "Мразень",  # 2x for icicle ranged testing
    ]


def create_starter_deck_p2() -> List[str]:
    """Returns list of card names for Player 2 (Forest themed)."""
    return [
        "Лёккен",
        "Эльфийский воин",
        "Бегущая по кронам",
        "Кобольд",
        "Клаэр",
        "Матросы Аделаиды",
        "Друид",
        "Корпит", "Корпит",  # 2x
        "Оури", "Оури",  # 2x
        "Паук-пересмешник",
        "Дракс",
    ]
