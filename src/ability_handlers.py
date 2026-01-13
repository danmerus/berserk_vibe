"""Ability handler registry - Command pattern for ability execution.

Each handler is a function that executes a specific ability.
Handlers are registered via the @handler decorator.

Targeting functions define valid targets for abilities.
Targeters are registered via the @targeter decorator.

Trigger handlers execute triggered abilities (ON_KILL, ON_ATTACK, etc.).
Trigger handlers are registered via the @trigger decorator.
"""
from typing import Callable, Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .game import Game
    from .card import Card
    from .abilities import Ability, AbilityTrigger

# Handler signature: (game, card, target, ability) -> bool
AbilityHandler = Callable[["Game", "Card", Optional["Card"], "Ability"], bool]

# Targeter signature: (game, card, ability, base_targets) -> List[int]
# base_targets are positions pre-filtered by range and target_type
AbilityTargeter = Callable[["Game", "Card", "Ability", List[int]], List[int]]

# Trigger handler signature: (game, card, ability, context) -> bool
# Context dict contains trigger-specific data:
#   ON_KILL: {'victim': Card}
#   ON_TURN_START: {} (no extra context)
#   ON_DEFEND: {'attacker': Card}
#   ON_ATTACK: {'target': Card, 'was_tapped': bool, 'attack_hit': bool, 'damage_dealt': int}
TriggerContext = Dict[str, Any]
TriggerHandler = Callable[["Game", "Card", "Ability", TriggerContext], bool]

# Registry of ability handlers
_HANDLERS: dict[str, AbilityHandler] = {}

# Registry of custom targeting functions
_TARGETERS: dict[str, AbilityTargeter] = {}

# Registry of trigger handlers
_TRIGGER_HANDLERS: dict[str, TriggerHandler] = {}


def handler(ability_id: str):
    """Decorator to register an ability handler."""
    def decorator(fn: AbilityHandler) -> AbilityHandler:
        _HANDLERS[ability_id] = fn
        return fn
    return decorator


def get_handler(ability_id: str) -> Optional[AbilityHandler]:
    """Get handler for an ability, or None if not registered."""
    return _HANDLERS.get(ability_id)


def has_handler(ability_id: str) -> bool:
    """Check if an ability has a registered handler."""
    return ability_id in _HANDLERS


def targeter(ability_id: str):
    """Decorator to register a custom targeting function for an ability."""
    def decorator(fn: AbilityTargeter) -> AbilityTargeter:
        _TARGETERS[ability_id] = fn
        return fn
    return decorator


def get_targeter(ability_id: str) -> Optional[AbilityTargeter]:
    """Get custom targeter for an ability, or None if not registered."""
    return _TARGETERS.get(ability_id)


def trigger(ability_id: str):
    """Decorator to register a trigger handler for a triggered ability."""
    def decorator(fn: TriggerHandler) -> TriggerHandler:
        _TRIGGER_HANDLERS[ability_id] = fn
        return fn
    return decorator


def get_trigger_handler(ability_id: str) -> Optional[TriggerHandler]:
    """Get trigger handler for an ability, or None if not registered."""
    return _TRIGGER_HANDLERS.get(ability_id)


def has_trigger_handler(ability_id: str) -> bool:
    """Check if an ability has a registered trigger handler."""
    return ability_id in _TRIGGER_HANDLERS


# =============================================================================
# PRECONDITION CHECKING
# =============================================================================

def check_preconditions(
    game: "Game",
    card: "Card",
    ability: "Ability",
    target: Optional["Card"] = None
) -> tuple[bool, str]:
    """
    Check if all preconditions for an ability are met.

    Returns (success, error_message). If success is True, error_message is empty.
    """
    # Counter preconditions
    if ability.requires_counters > 0:
        if card.counters < ability.requires_counters:
            return False, f"нужно {ability.requires_counters} фишек (есть {card.counters})"

    # Position preconditions
    if ability.requires_own_row is not None:
        if not game._is_in_own_row(card, ability.requires_own_row):
            row_names = {0: "третьем", 1: "втором", 2: "первом"}  # 0=back(3rd), 1=mid(2nd), 2=front(1st)
            return False, f"нужно быть в {row_names.get(ability.requires_own_row, '?')} ряду"

    if ability.requires_edge_column:
        col = game._get_card_column(card)
        if col not in (0, 4):
            return False, "нужно быть на фланге (колонка 0 или 4)"

    if ability.requires_center_column:
        col = game._get_card_column(card)
        if col != 2:
            return False, "нужно быть в центре (колонка 2)"

    # Card state preconditions
    if ability.requires_damaged:
        if card.curr_life >= card.life:
            return False, "нет повреждений для исцеления"

    if ability.requires_formation:
        if not card.in_formation:
            return False, "нужно быть в строю"

    # Target preconditions (only check if target is provided)
    if target is not None:
        if ability.target_must_be_tapped:
            if not target.tapped:
                return False, "цель должна быть закрыта"

        if ability.target_not_flying:
            if target.position is not None and game.board.is_flying_pos(target.position):
                return False, "нельзя использовать на летающих"

    return True, ""


def check_trigger_preconditions(
    game: "Game",
    card: "Card",
    ability: "Ability",
    ctx: TriggerContext
) -> bool:
    """
    Check preconditions for triggered abilities.
    Returns True if all preconditions are met.
    """
    # Formation requirement for triggers
    if ability.requires_formation:
        if not card.in_formation:
            return False

    # Row requirement
    if ability.requires_own_row is not None:
        if not game._is_in_own_row(card, ability.requires_own_row):
            return False

    # Damaged requirement (for healing triggers like regeneration)
    if ability.requires_damaged:
        if card.curr_life >= card.life:
            return False

    return True


# =============================================================================
# DATA-DRIVEN ABILITY EXECUTION
# =============================================================================

def execute_effect(
    game: "Game",
    card: "Card",
    ability: "Ability",
    target: Optional["Card"] = None
) -> bool:
    """
    Execute a data-driven ability effect based on ability.effect_type.

    Returns True if effect was executed, False if effect_type is NONE or unhandled.
    """
    from .abilities import EffectType

    effect = ability.effect_type

    if effect == EffectType.NONE:
        return False

    elif effect == EffectType.HEAL_TARGET:
        if not target:
            return False
        healed = target.heal(ability.heal_amount)
        if healed > 0:
            game.log(f"{card.name} исцеляет {target.name} (+{healed} HP)")
            game.emit_heal(target.position, healed)
        card.tap()
        if ability.cooldown > 0:
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
        return True

    elif effect == EffectType.HEAL_SELF:
        healed = card.heal(ability.heal_amount)
        if healed > 0:
            game.log(f"{card.name}: {ability.name} (+{healed} HP)")
            game.emit_heal(card.position, healed)
        card.tap()
        if ability.cooldown > 0:
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
        return True

    elif effect == EffectType.FULL_HEAL_SELF:
        if card.curr_life < card.life:
            heal_amount = card.life - card.curr_life
            card.curr_life = card.life
            game.emit_heal(card.position, heal_amount)
            game.log(f"{card.name}: полное исцеление (+{heal_amount} HP)")
        return True

    elif effect == EffectType.BUFF_ATTACK:
        if not target:
            return False
        target.temp_attack_bonus += ability.damage_bonus
        game.log(f"{card.name} усиливает {target.name} (+{ability.damage_bonus} к атаке)")
        card.tap()
        if ability.cooldown > 0:
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
        return True

    elif effect == EffectType.BUFF_RANGED:
        card.temp_ranged_bonus += ability.damage_bonus
        game.log(f"{card.name}: +{ability.damage_bonus} к выстрелам")
        return True

    elif effect == EffectType.BUFF_DICE:
        if not target:
            return False
        target.temp_dice_bonus += ability.dice_bonus_attack
        game.log(f"{card.name} усиливает {target.name} (ОвА+{ability.dice_bonus_attack})")
        card.tap()
        if ability.cooldown > 0:
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
        return True

    elif effect == EffectType.GRANT_DIRECT:
        card.has_direct = True
        game.log(f"{card.name}: направленный удар")
        return True

    elif effect == EffectType.GAIN_COUNTER:
        if card.max_counters > 0 and card.counters >= card.max_counters:
            game.log(f"{card.name}: максимум фишек ({card.max_counters})")
            return False
        card.counters += 1
        game.log(f"{card.name}: +1 фишка ({card.counters})")
        card.tap()
        if ability.cooldown > 0:
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
        return True

    elif effect == EffectType.APPLY_WEBBED:
        if not target:
            return False
        game.emit_arrow(card.position, target.position, 'attack')
        target.webbed = True
        game.log(f"{card.name} опутывает {target.name} паутиной!")
        game.emit_clear_arrows()
        card.tap()
        if ability.cooldown > 0:
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
        return True

    return False


def execute_ability(
    game: "Game",
    card: "Card",
    ability: "Ability",
    target: Optional["Card"] = None
) -> bool:
    """
    Execute an ability using data-driven execution if possible.

    First checks preconditions, then executes the effect.
    Returns True if ability was executed successfully.
    """
    # Check preconditions
    ok, error = check_preconditions(game, card, ability, target)
    if not ok:
        game.log(f"{card.name}: {error}")
        return False

    # Try data-driven execution
    return execute_effect(game, card, ability, target)


def execute_trigger_effect(
    game: "Game",
    card: "Card",
    ability: "Ability",
    ctx: TriggerContext
) -> bool:
    """
    Execute a data-driven trigger effect based on ability.effect_type.

    Returns True if effect was executed, False if effect_type is NONE or unhandled.
    """
    from .abilities import EffectType

    effect = ability.effect_type

    if effect == EffectType.NONE:
        return False

    elif effect == EffectType.HEAL_SELF:
        if ability.heal_amount > 0:
            healed = card.heal(ability.heal_amount)
            if healed > 0:
                game.log(f"{card.name}: {ability.name} (+{healed} HP)")
                game.emit_heal(card.position, healed)
                return True
        return False

    elif effect == EffectType.FULL_HEAL_SELF:
        if card.curr_life < card.life:
            heal_amount = card.life - card.curr_life
            card.curr_life = card.life
            game.emit_heal(card.position, heal_amount)
            game.log(f"  -> {card.name}: полное исцеление!")
            return True
        return False

    elif effect == EffectType.BUFF_RANGED:
        card.temp_ranged_bonus += ability.damage_bonus
        game.log(f"{card.name}: +{ability.damage_bonus} к выстрелам")
        return True

    elif effect == EffectType.GRANT_DIRECT:
        card.has_direct = True
        game.log(f"{card.name}: направленный удар")
        return True

    elif effect == EffectType.GAIN_COUNTER:
        if card.max_counters == 0 or card.counters < card.max_counters:
            card.counters += 1
            game.log(f"{card.name}: +1 фишка ({card.counters})")
            return True
        return False

    return False


# =============================================================================
# CUSTOM TARGETING FUNCTIONS
# =============================================================================

@targeter("lunge")
@targeter("lunge_2")
def target_lunge(game: "Game", card: "Card", ability: "Ability", base_targets: List[int]) -> List[int]:
    """Lunge targeting: only orthogonal targets with valid path (no enemies in between)."""
    valid = []
    for pos in base_targets:
        if _is_valid_lunge_path(game, card.position, pos, card.player):
            valid.append(pos)
    return valid


def _is_valid_lunge_path(game: "Game", from_pos: int, to_pos: int, player: int) -> bool:
    """Check if lunge path is valid (orthogonal, no enemies in between)."""
    from_col, from_row = from_pos % 5, from_pos // 5
    to_col, to_row = to_pos % 5, to_pos // 5

    # Must be orthogonal (same row or same column)
    if from_col != to_col and from_row != to_row:
        return False

    # Check the cell in between
    mid_col = (from_col + to_col) // 2
    mid_row = (from_row + to_row) // 2
    mid_pos = mid_row * 5 + mid_col

    mid_card = game.board.get_card(mid_pos)
    # Can go through empty or friendly, not through enemy
    if mid_card is not None and mid_card.player != player:
        return False

    return True


@targeter("web_throw")
def target_web_throw(game: "Game", card: "Card", ability: "Ability", base_targets: List[int]) -> List[int]:
    """Web throw targeting: cannot target flying creatures."""
    # Filter out flying positions (30-35)
    return [pos for pos in base_targets if pos < 30]


# =============================================================================
# ACTIVE ABILITY HANDLERS
# =============================================================================

@handler("web_throw")
def handle_web_throw(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Apply web status to target."""
    return execute_ability(game, card, ability, target)


@handler("gain_counter")
def handle_gain_counter(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Gain a counter (for discharge ability)."""
    return execute_ability(game, card, ability, target)


@handler("borg_counter")
def handle_borg_counter(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Борг: tap to gain counter (max 1)."""
    return execute_ability(game, card, ability, target)


@handler("borg_strike")
def handle_borg_strike(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Борг: spend counter for 3 damage + stun if target is tapped."""
    # Check preconditions (counter requirement)
    ok, error = check_preconditions(game, card, ability, target)
    if not ok:
        game.log(f"{card.name}: {error}")
        return False
    if not target:
        game.log(f"{card.name}: нет цели")
        return False

    # Spend counter (handled by precondition system)
    if ability.spends_counters:
        card.counters -= ability.requires_counters
    damage = ability.damage_amount  # Fixed 3 damage
    game.emit_arrow(card.position, target.position, 'attack')

    # Apply hit damage reduction (diagonal_defense, etc.)
    hit_reduction = game._get_hit_damage_reduction(target, card)
    initial_damage = damage
    if hit_reduction > 0 and damage > 0:
        damage = max(0, damage - hit_reduction)

    # If target is tapped, stun it (won't untap next turn)
    if target.tapped:
        target.stunned = True
        game.log(f"{card.name} бьёт рогами {target.name}: {initial_damage} урона + оглушение!")
    else:
        game.log(f"{card.name} бьёт рогами {target.name}: {initial_damage} урона")

    if hit_reduction > 0 and damage < initial_damage:
        game.log(f"  [{target.name}: {initial_damage}-{hit_reduction}={damage}]")

    game._deal_damage(target, damage)
    game.emit_clear_arrows()
    game._handle_death(target, card)
    card.tap()
    game._check_winner()
    return True


@handler("axe_tap")
def handle_axe_tap(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Axe master: tap to gain a counter."""
    return execute_ability(game, card, ability, target)


@handler("axe_strike")
def handle_axe_strike(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Axe strike: magical strike with counter-based damage."""
    # Get counters_spent from interaction context
    counters_spent = game.interaction.context.get('counters_spent', 0) if game.interaction else 0
    if counters_spent < 0 or counters_spent > card.counters:
        game.log(f"{card.name}: недостаточно фишек")
        return False

    if not target:
        return False

    return game._magic_attack(card, target, ability.id, counters_spent)


@handler("discharge")
def handle_discharge(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Discharge: deal damage based on counters (base + 3 per counter)."""
    if not target:
        return False

    base_damage = ability.damage_amount
    bonus_damage = card.counters * 3  # +3 per counter
    total_damage = base_damage + bonus_damage
    game.emit_arrow(card.position, target.position, 'attack')

    # Always lose a counter when discharging
    if card.counters > 0:
        card.counters -= 1

    # Check for discharge immunity
    if target.has_ability("magic_immune") or target.has_ability("discharge_immune"):
        game.log(f"{card.name} разряд на {target.name}: защита от разрядов!")
        game.log(f"  [Осталось фишек: {card.counters}]")
        game.emit_clear_arrows()
        card.tap()
        return True

    dealt, webbed = game._deal_damage(target, total_damage, is_magical=True)
    if not webbed:
        game.log(f"{card.name} разряд на {target.name}: {total_damage} урона ({base_damage}+{bonus_damage})")
        game.log(f"  [Осталось фишек: {card.counters}]")
    game.emit_clear_arrows()
    game._handle_death(target, card)
    card.tap()
    game._check_winner()
    return True


@handler("magical_strike")
def handle_magical_strike(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Magical strike: dice-based damage that ignores reductions."""
    if not target:
        return False
    return game._magic_attack(card, target, ability.id)


def _handle_lunge(game: "Game", card: "Card", target: Optional["Card"], ability: "Ability") -> bool:
    """Lunge attack: fixed damage through one cell, no counter."""
    if not target:
        return False
    return game._lunge_attack(card, target, ability)

# Register same handler for both lunge variants (damage differs in ability definition)
_HANDLERS["lunge"] = _handle_lunge
_HANDLERS["lunge_2"] = _handle_lunge


# =============================================================================
# TRIGGERED ABILITY HANDLERS
# =============================================================================

# --- ON_KILL triggers ---

@trigger("scavenging")
def trigger_scavenging(game: "Game", card: "Card", ability: "Ability", ctx: TriggerContext) -> bool:
    """Scavenging: full heal when killing an enemy."""
    return execute_trigger_effect(game, card, ability, ctx)


# --- ON_TURN_START triggers ---

@trigger("regeneration")
@trigger("regeneration_1")
def trigger_regeneration(game: "Game", card: "Card", ability: "Ability", ctx: TriggerContext) -> bool:
    """Regeneration: heal at turn start (amount from ability.heal_amount)."""
    if not check_trigger_preconditions(game, card, ability, ctx):
        return False
    return execute_trigger_effect(game, card, ability, ctx)


@trigger("front_row_bonus")
def trigger_front_row_bonus(game: "Game", card: "Card", ability: "Ability", ctx: TriggerContext) -> bool:
    """Front row bonus: +1 to ranged attacks when in first row."""
    if not check_trigger_preconditions(game, card, ability, ctx):
        return False
    return execute_trigger_effect(game, card, ability, ctx)


@trigger("back_row_direct")
def trigger_back_row_direct(game: "Game", card: "Card", ability: "Ability", ctx: TriggerContext) -> bool:
    """Back row direct: ranged attacks become direct when in third row."""
    if not check_trigger_preconditions(game, card, ability, ctx):
        return False
    return execute_trigger_effect(game, card, ability, ctx)


@trigger("axe_counter")
def trigger_axe_counter(game: "Game", card: "Card", ability: "Ability", ctx: TriggerContext) -> bool:
    """Axe counter: gain counter at turn start when in formation."""
    if not check_trigger_preconditions(game, card, ability, ctx):
        return False
    return execute_trigger_effect(game, card, ability, ctx)


# --- ON_DEFEND triggers ---

@trigger("defender_buff")
def trigger_defender_buff(game: "Game", card: "Card", ability: "Ability", ctx: TriggerContext) -> bool:
    """Defender buff: +2 attack and +1 dice when defending."""
    card.defender_buff_attack = ability.damage_bonus  # +2
    card.defender_buff_dice = ability.dice_bonus_attack  # ОвА+1
    card.defender_buff_turns = 1  # Lasts through 1 owner turn-end
    game.log(f"  -> {card.name}: +{ability.damage_bonus} к удару, ОвА+{ability.dice_bonus_attack} (до конца след. хода)")
    return True


# --- ON_ATTACK triggers ---
# Note: Some ON_ATTACK triggers (counter_shot, heal_on_attack, hellish_stench) require
# special handling with target selection or UI prompts, so they remain in game.py for now.
# Simple ON_ATTACK triggers can be added here.
