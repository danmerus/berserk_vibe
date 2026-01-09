"""Ability system for cards."""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .card import Card
    from .game import Game


class AbilityType(Enum):
    """Types of abilities."""
    ACTIVE = auto()      # Requires activation, uses action
    PASSIVE = auto()     # Always active
    TRIGGERED = auto()   # Triggers on specific events


class AbilityTrigger(Enum):
    """When triggered abilities activate."""
    ON_TURN_START = auto()
    ON_ATTACK = auto()
    ON_DEFEND = auto()
    ON_TAKE_DAMAGE = auto()
    ON_DEAL_DAMAGE = auto()
    ON_DEATH = auto()
    ON_KILL = auto()     # Triggers when killing enemy in combat
    VALHALLA = auto()    # Triggers from graveyard if killed by enemy
    ON_DICE_ROLL = auto()  # Can respond to dice rolls


class TargetType(Enum):
    """What the ability targets."""
    SELF = auto()
    ALLY = auto()
    ENEMY = auto()
    ANY = auto()
    NONE = auto()


class EffectType(Enum):
    """Data-driven effect types for simple abilities."""
    NONE = auto()              # No automatic effect (needs custom handler)
    HEAL_TARGET = auto()       # Heal target by heal_amount
    HEAL_SELF = auto()         # Heal self by heal_amount
    FULL_HEAL_SELF = auto()    # Heal self to max HP
    BUFF_ATTACK = auto()       # Add damage_bonus to target's temp_attack_bonus
    BUFF_RANGED = auto()       # Add damage_bonus to card's temp_ranged_bonus
    BUFF_DICE = auto()         # Add dice_bonus_attack to target's temp_dice_bonus
    GRANT_DIRECT = auto()      # Set card's has_direct = True
    GAIN_COUNTER = auto()      # Increment card's counters by 1
    APPLY_WEBBED = auto()      # Set target's webbed = True


@dataclass
class Ability:
    """Base ability definition."""
    id: str                    # Unique ID
    name: str                  # Display name
    description: str           # What it does
    ability_type: AbilityType
    target_type: TargetType = TargetType.NONE
    range: int = 0             # 0 = self, 1 = adjacent, 2+ = ranged
    min_range: int = 0         # Minimum range (for ranged attacks that can't hit adjacent)
    cooldown: int = 0          # Turns between uses (0 = no cooldown)
    trigger: Optional[AbilityTrigger] = None

    # Data-driven effect type (for simple abilities without custom handlers)
    effect_type: EffectType = EffectType.NONE

    # For active abilities with simple effects
    heal_amount: int = 0
    damage_amount: int = 0
    ranged_damage: Optional[Tuple[int, int, int]] = None  # Custom damage for ranged (weak, med, strong)
    ranged_type: str = "shot"  # "shot" (Выстрел) or "throw" (Метание)
    grants_direct: bool = False  # Ranged ignores defenders

    # Dice and damage bonuses (explicit fields replacing overloaded bonus_attack)
    dice_bonus_attack: int = 0   # ОвА - added to attack dice roll
    dice_bonus_defense: int = 0  # ОвЗ - added to defense dice roll
    damage_bonus: int = 0        # Flat damage bonus to attacks

    # DEPRECATED: Use dice_bonus_attack, dice_bonus_defense, or damage_bonus instead
    bonus_attack: int = 0

    # For defensive passives
    damage_reduction: int = 0  # Reduce incoming damage by this amount
    cost_threshold: int = 0    # Only applies vs attackers with cost <= this (0 = any)

    # Conditional damage bonus (vs specific element)
    bonus_damage_vs_element: int = 0  # Extra damage vs target element
    target_element: Optional[str] = None  # Element name to get bonus against (e.g., "SWAMPS")

    # Conditional ranged bonus (vs cards with defensive abilities)
    bonus_ranged_vs_defensive: int = 0  # Extra ranged damage vs cards with OVA/OVZ/armor

    # For UI display
    status_text: str = ""      # Short text for status panel (e.g., "регенерация +3")

    # Instant ability (внезапное действие) - can be used during priority windows
    is_instant: bool = False   # If true, can be used during opponent's turn / in response

    # Formation (Строй) ability - bonus when orthogonally adjacent to allies with same ability
    is_formation: bool = False
    formation_damage_reduction: int = 0  # Damage reduction when in formation
    formation_attack_bonus: int = 0      # Attack bonus when in formation
    formation_dice_bonus: int = 0        # Dice bonus (ОвА/ОвЗ) when in formation
    formation_armor_bonus: int = 0       # Armor bonus when in formation
    requires_elite_ally: bool = False    # Only active when in formation with elite ally
    requires_common_ally: bool = False   # Only active when in formation with common ally

    # =============================================================================
    # PRECONDITIONS - declarative checks for ability activation
    # =============================================================================

    # Counter preconditions
    requires_counters: int = 0           # Minimum counters needed to use ability
    spends_counters: bool = False        # If true, ability consumes counters (amount = requires_counters)

    # Position preconditions (for card using ability)
    requires_own_row: int = 0            # Must be in this row (1=front, 2=middle, 3=back), 0=any
    requires_edge_column: bool = False   # Must be in column 0 or 4 (flanks)
    requires_center_column: bool = False # Must be in column 2 (center)

    # Target preconditions
    target_must_be_tapped: bool = False  # Target must be tapped/closed
    target_not_flying: bool = False      # Target cannot be flying (for web_throw)

    # Card state preconditions
    requires_damaged: bool = False       # Card must be damaged (curr_life < life)
    requires_formation: bool = False     # Card must be in formation (for triggered abilities)


# =============================================================================
# PREDEFINED ABILITIES
# =============================================================================

ABILITY_HEAL_SELF = Ability(
    id="heal_self",
    name="Исцеление",
    description="Восстановить 3 здоровья",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.SELF,
    effect_type=EffectType.HEAL_SELF,
    heal_amount=3,
)

ABILITY_HEAL_ALLY = Ability(
    id="heal_ally",
    name="Дыхание леса",
    description="Излечить существо на 2 HP",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,
    range=99,  # No range limit for воздействие
    effect_type=EffectType.HEAL_TARGET,
    heal_amount=2,
)

ABILITY_HEAL_1 = Ability(
    id="heal_1",
    name="Лечение",
    description="Излечить существо на 1 HP",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,
    range=99,
    effect_type=EffectType.HEAL_TARGET,
    heal_amount=1,
)

# Movement-triggered shot (Оури) - when moving adjacent to ally costing 7+
ABILITY_MOVEMENT_SHOT = Ability(
    id="movement_shot",
    name="Выстрел при движении",
    description="При ходе к союзнику 7+: выстрел 1, дальность 3",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_TURN_START,  # Placeholder - needs special handling
    damage_amount=1,
    range=3,
    status_text="выстрел при движении",
)

# Бегущая по кронам specific ranged shot (1-2-2 damage)
ABILITY_CROWN_RUNNER_SHOT = Ability(
    id="crown_runner_shot",
    name="Выстрел",
    description="Выстрел 1-2-2 (не вблизи)",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,
    range=99,
    min_range=2,
    ranged_damage=(1, 2, 2),
)

# Удар через ряд (Lunge) - attack through one cell vertically/horizontally
# Goes through empty/friendly cells, NOT through enemies
# Deals fixed damage (default 1, can be specified per card)
# Target cannot counter
ABILITY_LUNGE = Ability(
    id="lunge",
    name="Удар через ряд",
    description="Удар через клетку (фикс. урон)",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,  # Can target allies too
    range=2,
    min_range=2,  # Must be exactly 2 cells away
    damage_amount=1,  # Default lunge damage
)

# Ледовый охотник's lunge - deals 2 fixed damage
ABILITY_LUNGE_2 = Ability(
    id="lunge_2",
    name="Удар через ряд",
    description="Удар через клетку (2 урона)",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,
    range=2,
    min_range=2,
    damage_amount=2,  # Fixed 2 damage
)

# Опыт в атаке - +1 to attack dice roll (passive)
ABILITY_ATTACK_EXP = Ability(
    id="attack_exp",
    name="Опыт в атаке",
    description="+1 к броску при атаке",
    ability_type=AbilityType.PASSIVE,
    dice_bonus_attack=1,
    status_text="опыт в атаке",
)

# Row bonus triggers for Бегущая по кронам
ABILITY_FRONT_ROW_BONUS = Ability(
    id="front_row_bonus",
    name="Бонус первого ряда",
    description="+1 к выстрелам в первом ряду",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_TURN_START,
    effect_type=EffectType.BUFF_RANGED,
    damage_bonus=1,  # +1 to ranged damage
    requires_own_row=1,  # Only activates in first row
)

ABILITY_BACK_ROW_DIRECT = Ability(
    id="back_row_direct",
    name="Прямой выстрел",
    description="Прямой урон в третьем ряду",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_TURN_START,
    effect_type=EffectType.GRANT_DIRECT,
    grants_direct=True,
    requires_own_row=3,  # Only activates in third row
)

ABILITY_REGENERATION = Ability(
    id="regeneration",
    name="Регенерация",
    description="Восстанавливает 3 HP в начале хода",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_TURN_START,
    effect_type=EffectType.HEAL_SELF,
    heal_amount=3,
    status_text="регенерация +3",
    requires_damaged=True,  # Only activates if damaged
)

# Tough hide - reduces damage from cheap creatures
ABILITY_TOUGH_HIDE = Ability(
    id="tough_hide",
    name="Толстая шкура",
    description="-2 урона от существ ≤3 кристаллов",
    ability_type=AbilityType.PASSIVE,
    damage_reduction=2,
    cost_threshold=3,  # Only vs creatures costing 3 or less
    status_text="-2 от дешёвых",
)

# Direct attack - melee attacks cannot be redirected by defenders
ABILITY_DIRECT_ATTACK = Ability(
    id="direct_attack",
    name="Направленный удар",
    description="Атака не может быть перенаправлена",
    ability_type=AbilityType.PASSIVE,
    grants_direct=True,
    status_text="направленный",
)

# Poison immunity - cannot be poisoned
ABILITY_POISON_IMMUNE = Ability(
    id="poison_immune",
    name="Защита от отравления",
    description="Не может быть отравлен",
    ability_type=AbilityType.PASSIVE,
    status_text="иммунитет к яду",
)

# Diagonal defense - reduces damage from diagonal attacks
ABILITY_DIAGONAL_DEFENSE = Ability(
    id="diagonal_defense",
    name="Защита от диагонали",
    description="-2 от ударов по диагонали",
    ability_type=AbilityType.PASSIVE,
    damage_reduction=2,
    status_text="-2 от диагонали",
)

# Restricted strike - can only attack card directly opposite
ABILITY_RESTRICTED_STRIKE = Ability(
    id="restricted_strike",
    name="Ограниченный удар",
    description="Атакует только карту напротив",
    ability_type=AbilityType.PASSIVE,
    status_text="только напротив",
)

# Magical strike - tap to deal 2 magical damage (ignores reductions)
# Can target ANY adjacent creature (allies or enemies)
ABILITY_MAGICAL_STRIKE = Ability(
    id="magical_strike",
    name="Магический удар",
    description="Нанести 2 магического урона",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,
    range=1,
    damage_amount=2,
)

# Center column bonus - +1 defense, -1 incoming weak damage when in center column
ABILITY_CENTER_COLUMN_DEFENSE = Ability(
    id="center_column_defense",
    name="Оборона в центре",
    description="В центре: +1 ОвЗ, -1 от слабых ударов",
    ability_type=AbilityType.PASSIVE,
    # Note: reduction handled in _get_damage_reduction with attack_tier
    status_text="центр: +1 ОвЗ",
)

# Edge column bonus - +1 attack dice, +1 medium/strong damage when in edge columns
ABILITY_EDGE_COLUMN_ATTACK = Ability(
    id="edge_column_attack",
    name="Атака с флангов",
    description="На флангах: +1 ОвА, +1 средний/сильный удар",
    ability_type=AbilityType.PASSIVE,
    dice_bonus_attack=1,
    status_text="фланг: +1 ОвА",
)

# Jump movement - can jump over obstacles
ABILITY_JUMP = Ability(
    id="jump",
    name="Прыжок",
    description="Может перепрыгивать через существ",
    ability_type=AbilityType.PASSIVE,
    range=3,  # Jump range
    status_text="прыжок",
)

# Gain counter - tap to gain a token/counter (for discharge)
ABILITY_GAIN_COUNTER = Ability(
    id="gain_counter",
    name="Получить фишку",
    description="Получить фишку (макс 3)",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.SELF,
    effect_type=EffectType.GAIN_COUNTER,
    status_text="фишка",
)

# Discharge - deal 2 damage (+3 per token), lose 1 token, unlimited range
ABILITY_DISCHARGE = Ability(
    id="discharge",
    name="Разряд",
    description="Разряд 2 (+3 за каждую фишку)",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,  # Can target any creature
    range=99,  # Unlimited range
    min_range=2,  # Cannot target adjacent/diagonal (ranged attack)
    damage_amount=2,  # Base damage
    status_text="разряд",
)

# Magic protection (zom) - immune to spells, magical strikes, and discharges
ABILITY_MAGIC_IMMUNE = Ability(
    id="magic_immune",
    name="Защита от магии",
    description="Защита от заклинаний, магических ударов и разрядов",
    ability_type=AbilityType.PASSIVE,
    status_text="защита от магии",
)

# Regeneration +1 - heals 1 HP at start of turn
ABILITY_REGENERATION_1 = Ability(
    id="regeneration_1",
    name="Регенерация",
    description="Восстанавливает 1 HP в начале хода",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_TURN_START,
    effect_type=EffectType.HEAL_SELF,
    heal_amount=1,
    status_text="регенерация +1",
    requires_damaged=True,  # Only activates if damaged
)

# Valhalla: give ally ОвА+1 (Ледовый охотник)
ABILITY_VALHALLA_OVA = Ability(
    id="valhalla_ova",
    name="Вальхалла",
    description="Союзник получает ОвА+1",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.VALHALLA,
    dice_bonus_attack=1,  # +1 to dice roll
    status_text="Вальхалла",
)

# Steppe defense - reduces damage from steppe creatures by 1
ABILITY_STEPPE_DEFENSE = Ability(
    id="steppe_defense",
    name="Защита от степи",
    description="-1 от атак степных существ",
    ability_type=AbilityType.PASSIVE,
    damage_reduction=1,
    status_text="-1 от степи",
)

# Counter shot - when attacking (hit or miss), also deals 2 ranged damage
ABILITY_COUNTER_SHOT = Ability(
    id="counter_shot",
    name="Ответный выстрел",
    description="При ударе — выстрел на 2",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_ATTACK,
    damage_amount=2,
    status_text="выстрел при ударе",
)

# Heal on attack - heals for target's medium damage value when attacking
ABILITY_HEAL_ON_ATTACK = Ability(
    id="heal_on_attack",
    name="Исцеление при ударе",
    description="При атаке лечится на средний урон цели",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_ATTACK,
    status_text="лечение при ударе",
)

# Zov (shot protection) - immune to shots and their effects
ABILITY_SHOT_IMMUNE = Ability(
    id="shot_immune",
    name="Защита от выстрелов",
    description="Не получает урона и эффектов от выстрелов",
    ability_type=AbilityType.PASSIVE,
    status_text="защита от выстрелов",
)

# Defender doesn't tap - when acting as defender, doesn't close/tap
ABILITY_DEFENDER_NO_TAP = Ability(
    id="defender_no_tap",
    name="Стойкий защитник",
    description="Выступая защитником, не закрывается",
    ability_type=AbilityType.PASSIVE,
    status_text="не закрывается",
)

# Unlimited defender - can defend any number of times per turn
ABILITY_UNLIMITED_DEFENDER = Ability(
    id="unlimited_defender",
    name="Многократная защита",
    description="Может защищать любое число раз за ход",
    ability_type=AbilityType.PASSIVE,
    status_text="защитник",
)

# Defense experience - +1 to dice roll when defending (ovz)
ABILITY_DEFENSE_EXP = Ability(
    id="defense_exp",
    name="Опыт в защите",
    description="+1 к броску при защите",
    ability_type=AbilityType.PASSIVE,
    dice_bonus_defense=1,
    status_text="опыт в защите",
)

# Discharge protection - immune to discharges (zor)
ABILITY_DISCHARGE_IMMUNE = Ability(
    id="discharge_immune",
    name="Защита от разрядов",
    description="Не получает урона от разрядов",
    ability_type=AbilityType.PASSIVE,
    status_text="защита от разрядов",
)

# Defender buff - when becoming defender, gain +2 attack and ОвА+1
ABILITY_DEFENDER_BUFF = Ability(
    id="defender_buff",
    name="Ярость защитника",
    description="При защите: +2 к удару и ОвА+1",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_DEFEND,
    damage_bonus=2,  # +2 to attack damage
    dice_bonus_attack=1,  # +1 to dice roll
    status_text="ярость защитника",
)

# Scavenging - when killing enemy, fully heals and removes poison
ABILITY_SCAVENGING = Ability(
    id="scavenging",
    name="Трупоедство",
    description="При убийстве врага: полное исцеление",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_KILL,
    effect_type=EffectType.FULL_HEAL_SELF,
    status_text="трупоедство",
)

# Flying marker - indicates card goes in flying zone
# Note: This is a passive marker, flying mechanics are handled by is_flying in CardStats
ABILITY_FLYING = Ability(
    id="flying",
    name="Летающий",
    description="Располагается в зоне полёта, атакует любую карту",
    ability_type=AbilityType.PASSIVE,
    status_text="летающий",
)

# Anti-magic - +1 damage against creatures with discharge/magic/spell
ABILITY_ANTI_MAGIC = Ability(
    id="anti_magic",
    name="Пожиратель магии",
    description="+1 урон против существ с разрядом или магией",
    ability_type=AbilityType.PASSIVE,
    status_text="антимагия",
)

# Flyer taunt - flying enemies can only attack this creature
ABILITY_FLYER_TAUNT = Ability(
    id="flyer_taunt",
    name="Приманка летунов",
    description="Летуны могут атаковать только это существо",
    ability_type=AbilityType.PASSIVE,
    status_text="приманка летунов",
)

# Web throw - applies web status to enemy at range 2
ABILITY_WEB_THROW = Ability(
    id="web_throw",
    name="Паутина",
    description="Опутать врага (дистанция 2): не действует, при атаке блокирует и снимается",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ENEMY,
    range=2,
    effect_type=EffectType.APPLY_WEBBED,
    status_text="паутина",
    target_not_flying=True,  # Cannot target flying creatures
)

# Luck (Удача) - instant ability to modify dice rolls
# Can adjust any dice roll by +1/-1 or reroll. Taps the card.
ABILITY_LUCK = Ability(
    id="luck",
    name="Удача",
    description="Внезапное: изменить бросок на +1/-1 или перебросить",
    ability_type=AbilityType.ACTIVE,
    trigger=AbilityTrigger.ON_DICE_ROLL,  # Legal when dice are rolled
    target_type=TargetType.SELF,
    is_instant=True,  # Can be used during priority windows
    status_text="удача",
)

# Formation (Строй) abilities - bonuses when orthogonally adjacent to ally with same ability
# Строй -1: reduces damage by 1 when in formation
ABILITY_STROI_DMG_1 = Ability(
    id="stroi_dmg_1",
    name="Строй",
    description="В строю: -1 к урону",
    ability_type=AbilityType.PASSIVE,
    is_formation=True,
    formation_damage_reduction=1,
    status_text="строй -1 урон",
)

# Строй ОвЗ+1: +1 defense dice when in formation
ABILITY_STROI_OVZ_1 = Ability(
    id="stroi_ovz_1",
    name="Строй",
    description="В строю: +1 ОвЗ",
    ability_type=AbilityType.PASSIVE,
    is_formation=True,
    formation_dice_bonus=1,  # Used for defense
    status_text="строй ОвЗ+1",
)

# Строй +1 атака: +1 attack damage when in formation
ABILITY_STROI_ATK_1 = Ability(
    id="stroi_atk_1",
    name="Строй",
    description="В строю: +1 к атаке",
    ability_type=AbilityType.PASSIVE,
    is_formation=True,
    formation_attack_bonus=1,
    status_text="строй +1 атака",
)

# Строй с элитным: armor 2 when in formation with elite ally
ABILITY_STROI_ARMOR_ELITE = Ability(
    id="stroi_armor_elite",
    name="Строй",
    description="В строю с элитным: броня 2",
    ability_type=AbilityType.PASSIVE,
    is_formation=True,
    formation_armor_bonus=2,
    requires_elite_ally=True,
    status_text="строй броня",
)

# Строй с рядовым: ОвЗ+2 when in formation with common ally
ABILITY_STROI_OVZ_COMMON = Ability(
    id="stroi_ovz_common",
    name="Строй",
    description="В строю с рядовым: ОвЗ+2",
    ability_type=AbilityType.PASSIVE,
    is_formation=True,
    formation_dice_bonus=2,
    requires_common_ally=True,
    status_text="строй ОвЗ+2",
)

# Valhalla: give ally +1 strike (Костедробитель)
ABILITY_VALHALLA_STRIKE = Ability(
    id="valhalla_strike",
    name="Вальхалла",
    description="Союзник получает +1 к удару",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.VALHALLA,
    damage_bonus=1,  # +1 to attack damage
    status_text="Вальхалла",
)

# Борг: tap to gain counter (max 1)
ABILITY_BORG_COUNTER = Ability(
    id="borg_counter",
    name="Накопить фишку",
    description="Повернуть: получить фишку",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.SELF,
    effect_type=EffectType.GAIN_COUNTER,
    status_text="фишка",
)

# Борг: spend counter for 3 fixed damage, stun if target is tapped
ABILITY_BORG_STRIKE = Ability(
    id="borg_strike",
    name="Особый удар",
    description="Фишка: 3 урона, оглушение",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,
    range=1,  # Adjacent only
    damage_amount=3,
    status_text="особый удар",
    requires_counters=1,  # Needs 1 counter to use
    spends_counters=True,  # Consumes the counter
)

# Гном-басаарг: +1 strike and direct vs tapped enemies
# Note: grants_direct is NOT set here - the conditional check is in game.py attack code
ABILITY_TAPPED_BONUS = Ability(
    id="tapped_bonus",
    name="Охотник на закрытых",
    description="Против закрытых: +1 удар, напрямую",
    ability_type=AbilityType.PASSIVE,
    damage_bonus=1,  # +1 damage vs tapped (applied conditionally in game.py)
    status_text="+1 vs закрытых",
)

# Гном-басаарг: must attack tapped enemies if able
ABILITY_MUST_ATTACK_TAPPED = Ability(
    id="must_attack_tapped",
    name="Охота на закрытых",
    description="Обязан атаковать соседнего закрытого врага",
    ability_type=AbilityType.PASSIVE,
    status_text="охота",
)

# Мастер топора: gain counter at turn start (formation ability)
ABILITY_AXE_COUNTER = Ability(
    id="axe_counter",
    name="Накопление",
    description="В начале хода в строю: +1 фишка",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_TURN_START,
    effect_type=EffectType.GAIN_COUNTER,
    is_formation=True,  # Formation ability - needs adjacent ally with formation
    status_text="накопление",
    requires_formation=True,  # Only triggers when in formation
)

# Мастер топора: tap to gain counter (active)
ABILITY_AXE_TAP = Ability(
    id="axe_tap",
    name="Накопить фишку",
    description="Отыграть: +1 фишка",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.SELF,
    effect_type=EffectType.GAIN_COUNTER,
    status_text="накопление",
)

# Мастер топора: spend counters for magical strike (0-1-2 + 1 per counter)
ABILITY_AXE_STRIKE = Ability(
    id="axe_strike",
    name="Магический удар",
    description="Магический удар 0-1-2 (+1 за фишку)",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,  # Can target allies too
    range=1,  # Melee range
    status_text="маг. удар",
)

# Anti-swamp: +2 damage vs swamp creatures
ABILITY_ANTI_SWAMP = Ability(
    id="anti_swamp",
    name="Враг болот",
    description="+2 к удару по существам болот",
    ability_type=AbilityType.PASSIVE,
    bonus_damage_vs_element=2,
    target_element="SWAMPS",
    status_text="+2 vs болота",
)

# Icicle throw: ranged 1-2-2 at range 3, +1 vs cards with OVA/OVZ/armor
# Throw attacks cannot target adjacent squares (min_range=2)
ABILITY_ICICLE_THROW = Ability(
    id="icicle_throw",
    name="Сосулька",
    description="Метание 1-2-2 (дальность 3), +1 vs ОВА/ОВЗ/броня",
    ability_type=AbilityType.ACTIVE,
    target_type=TargetType.ANY,  # Can target allies too
    range=3,
    min_range=2,  # Cannot target adjacent squares
    ranged_damage=(1, 2, 2),
    ranged_type="throw",
    bonus_ranged_vs_defensive=1,
    status_text="метание дальность 3",
)

# Овражный гном: +1 attack vs tapped (closed) creatures
ABILITY_CLOSED_ATTACK_BONUS = Ability(
    id="closed_attack_bonus",
    name="Бьёт лежачих",
    description="+1 к удару по закрытым существам",
    ability_type=AbilityType.PASSIVE,
    damage_bonus=1,  # Applied conditionally in game.py when target is tapped
    status_text="+1 vs закрытых",
)

# Овражный гном: hellish stench - when attacking untapped creature, they must tap or take 2 damage
ABILITY_HELLISH_STENCH = Ability(
    id="hellish_stench",
    name="Адское зловоние",
    description="При ударе по открытому: цель закрывается или получает 2 раны",
    ability_type=AbilityType.TRIGGERED,
    trigger=AbilityTrigger.ON_ATTACK,
    damage_amount=2,  # Damage if they don't tap
    status_text="зловоние",
)


# Registry of all abilities
ABILITIES = {
    "heal_self": ABILITY_HEAL_SELF,
    "heal_ally": ABILITY_HEAL_ALLY,
    "heal_1": ABILITY_HEAL_1,
    "movement_shot": ABILITY_MOVEMENT_SHOT,
    "crown_runner_shot": ABILITY_CROWN_RUNNER_SHOT,
    "lunge": ABILITY_LUNGE,
    "lunge_2": ABILITY_LUNGE_2,
    "attack_exp": ABILITY_ATTACK_EXP,
    "front_row_bonus": ABILITY_FRONT_ROW_BONUS,
    "back_row_direct": ABILITY_BACK_ROW_DIRECT,
    "regeneration": ABILITY_REGENERATION,
    "tough_hide": ABILITY_TOUGH_HIDE,
    "direct_attack": ABILITY_DIRECT_ATTACK,
    "poison_immune": ABILITY_POISON_IMMUNE,
    "diagonal_defense": ABILITY_DIAGONAL_DEFENSE,
    "restricted_strike": ABILITY_RESTRICTED_STRIKE,
    "magical_strike": ABILITY_MAGICAL_STRIKE,
    "center_column_defense": ABILITY_CENTER_COLUMN_DEFENSE,
    "edge_column_attack": ABILITY_EDGE_COLUMN_ATTACK,
    "jump": ABILITY_JUMP,
    "gain_counter": ABILITY_GAIN_COUNTER,
    "discharge": ABILITY_DISCHARGE,
    "magic_immune": ABILITY_MAGIC_IMMUNE,
    "regeneration_1": ABILITY_REGENERATION_1,
    "valhalla_ova": ABILITY_VALHALLA_OVA,
    "steppe_defense": ABILITY_STEPPE_DEFENSE,
    "counter_shot": ABILITY_COUNTER_SHOT,
    "heal_on_attack": ABILITY_HEAL_ON_ATTACK,
    "shot_immune": ABILITY_SHOT_IMMUNE,
    "defender_no_tap": ABILITY_DEFENDER_NO_TAP,
    "unlimited_defender": ABILITY_UNLIMITED_DEFENDER,
    "defense_exp": ABILITY_DEFENSE_EXP,
    "discharge_immune": ABILITY_DISCHARGE_IMMUNE,
    "defender_buff": ABILITY_DEFENDER_BUFF,
    "scavenging": ABILITY_SCAVENGING,
    "flying": ABILITY_FLYING,
    "anti_magic": ABILITY_ANTI_MAGIC,
    "flyer_taunt": ABILITY_FLYER_TAUNT,
    "web_throw": ABILITY_WEB_THROW,
    "luck": ABILITY_LUCK,
    "stroi_dmg_1": ABILITY_STROI_DMG_1,
    "stroi_ovz_1": ABILITY_STROI_OVZ_1,
    "stroi_atk_1": ABILITY_STROI_ATK_1,
    "stroi_armor_elite": ABILITY_STROI_ARMOR_ELITE,
    "stroi_ovz_common": ABILITY_STROI_OVZ_COMMON,
    "valhalla_strike": ABILITY_VALHALLA_STRIKE,
    "borg_counter": ABILITY_BORG_COUNTER,
    "borg_strike": ABILITY_BORG_STRIKE,
    "tapped_bonus": ABILITY_TAPPED_BONUS,
    "must_attack_tapped": ABILITY_MUST_ATTACK_TAPPED,
    "axe_counter": ABILITY_AXE_COUNTER,
    "axe_tap": ABILITY_AXE_TAP,
    "axe_strike": ABILITY_AXE_STRIKE,
    "anti_swamp": ABILITY_ANTI_SWAMP,
    "icicle_throw": ABILITY_ICICLE_THROW,
    "closed_attack_bonus": ABILITY_CLOSED_ATTACK_BONUS,
    "hellish_stench": ABILITY_HELLISH_STENCH,
}


def get_ability(ability_id: str) -> Optional[Ability]:
    """Get ability by ID."""
    return ABILITIES.get(ability_id)
