"""Card class and CardStats dataclass."""
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict

from .constants import CardType, Element


@dataclass
class CardStats:
    """Base card statistics."""
    name: str
    cost: int  # Total crystal cost
    element: Element
    card_type: CardType
    life: int
    attack: Tuple[int, int, int]  # (weak, medium, strong) damage
    move: int = 1
    is_unique: bool = False
    is_flying: bool = False  # Flying creatures go in flying zone
    is_elite: bool = False  # True = gold cost (элитная), False = common (рядовая)
    card_class: str = ""  # Card class (e.g., "Дитя Кронга", "Страж леса")
    description: str = ""
    ability_ids: List[str] = field(default_factory=list)  # List of ability IDs
    max_counters: int = 0  # Max counters (0 = no counters)
    armor: int = 0  # Armor X: blocks first X non-magical damage per turn


@dataclass
class Card:
    """A card instance on the battlefield."""
    stats: CardStats
    player: int  # 1 or 2

    # Current state
    curr_life: int = field(init=False)
    curr_move: int = field(init=False)
    tapped: bool = False
    position: Optional[int] = None  # Board position 0-29, None if not on board

    # Unique ID for this game instance
    id: int = field(default=0)

    # Ability cooldowns: {ability_id: turns_remaining}
    ability_cooldowns: Dict[str, int] = field(default_factory=dict)

    # Temporary buffs (cleared at end of turn)
    temp_attack_bonus: int = field(default=0)
    temp_ranged_bonus: int = field(default=0)  # Bonus to ranged damage
    temp_dice_bonus: int = field(default=0)    # Bonus to attack dice roll (ОвА)
    has_direct: bool = field(default=False)    # Ranged ignores defenders

    # Defender buff tracking (lasts until end of owner's next turn)
    defender_buff_attack: int = field(default=0)  # Attack bonus from defender_buff
    defender_buff_dice: int = field(default=0)    # Dice bonus from defender_buff
    defender_buff_turns: int = field(default=0)   # Turn-ends remaining

    # Death tracking for Valhalla
    killed_by_enemy: bool = field(default=False)  # True if died from enemy attack
    valhalla_triggered: bool = field(default=False)  # True if Valhalla already used

    # Web status - can't act, blocks attack when attacked
    webbed: bool = field(default=False)

    # Generic counters (e.g., for Повелитель молний discharge ability)
    counters: int = field(default=0)
    max_counters: int = field(default=0)  # 0 means no limit

    # Formation (Строй) state - set by Game.recalculate_formations()
    in_formation: bool = field(default=False)

    # Stun state - stunned cards don't untap at turn start
    stunned: bool = field(default=False)

    # Armor tracking - remaining armor points this turn (resets each turn)
    armor_remaining: int = field(default=0)
    formation_armor_remaining: int = field(default=0)  # Formation armor remaining
    formation_armor_max: int = field(default=0)  # Max formation armor (for tracking changes)

    def __post_init__(self):
        self.curr_life = self.stats.life
        self.curr_move = self.stats.move
        self.ability_cooldowns = {}
        self.temp_attack_bonus = 0
        self.temp_ranged_bonus = 0
        self.temp_dice_bonus = 0
        self.has_direct = False
        self.defender_buff_attack = 0
        self.defender_buff_dice = 0
        self.defender_buff_turns = 0
        self.counters = 0
        self.max_counters = self.stats.max_counters
        self.armor_remaining = self.stats.armor  # Initialize armor

    @property
    def name(self) -> str:
        return self.stats.name

    @property
    def life(self) -> int:
        return self.stats.life

    @property
    def attack(self) -> Tuple[int, int, int]:
        return self.stats.attack

    @property
    def move(self) -> int:
        return self.stats.move

    @property
    def is_alive(self) -> bool:
        return self.curr_life > 0

    @property
    def can_act(self) -> bool:
        return not self.tapped and self.is_alive and not self.webbed

    @property
    def armor(self) -> int:
        """Base armor value from stats."""
        return self.stats.armor

    def take_damage(self, amount: int) -> int:
        """Apply damage, return actual damage dealt."""
        actual = min(amount, self.curr_life)
        self.curr_life -= actual
        return actual

    def take_damage_with_armor(self, amount: int, is_magical: bool = False) -> Tuple[int, int]:
        """Apply damage considering armor. Returns (actual_damage, armor_absorbed).

        Armor only blocks non-magical damage.
        """
        armor_absorbed = 0
        if not is_magical and self.armor_remaining > 0:
            armor_absorbed = min(amount, self.armor_remaining)
            self.armor_remaining -= armor_absorbed
            amount -= armor_absorbed

        actual = self.take_damage(amount)
        return actual, armor_absorbed

    def reset_armor(self):
        """Reset armor to full at start of any turn."""
        self.armor_remaining = self.stats.armor

    def heal(self, amount: int) -> int:
        """Heal, return actual healing done."""
        actual = min(amount, self.life - self.curr_life)
        self.curr_life += actual
        return actual

    def reset_for_turn(self):
        """Reset card state at start of owner's turn."""
        # Handle stun - stunned cards don't untap, but stun clears
        if self.stunned:
            self.stunned = False
            # Don't untap - stays tapped
        else:
            self.tapped = False

        self.curr_move = self.move
        self.temp_attack_bonus = 0
        self.temp_ranged_bonus = 0
        self.temp_dice_bonus = 0
        self.has_direct = False

        # Reduce cooldowns
        for ability_id in list(self.ability_cooldowns.keys()):
            self.ability_cooldowns[ability_id] -= 1
            if self.ability_cooldowns[ability_id] <= 0:
                del self.ability_cooldowns[ability_id]

    def tap(self):
        """Tap the card after using an action."""
        self.tapped = True
        self.curr_move = 0

    def can_use_ability(self, ability_id: str) -> bool:
        """Check if ability can be used (not on cooldown, not tapped)."""
        if self.tapped or not self.is_alive:
            return False
        return ability_id not in self.ability_cooldowns

    def put_ability_on_cooldown(self, ability_id: str, cooldown: int):
        """Put an ability on cooldown."""
        if cooldown > 0:
            self.ability_cooldowns[ability_id] = cooldown

    def get_effective_attack(self) -> Tuple[int, int, int]:
        """Get attack values including temporary bonuses."""
        base = self.stats.attack
        bonus = self.temp_attack_bonus + self.defender_buff_attack
        return (base[0] + bonus, base[1] + bonus, base[2] + bonus)

    def clear_defender_buff(self):
        """Clear defender buff when duration expires."""
        self.defender_buff_attack = 0
        self.defender_buff_dice = 0
        self.defender_buff_turns = 0

    def tick_defender_buff(self):
        """Called at end of owner's turn. Decrements and clears if expired."""
        if self.defender_buff_turns > 0:
            self.defender_buff_turns -= 1
            if self.defender_buff_turns <= 0:
                self.clear_defender_buff()

    def has_ability(self, ability_id: str) -> bool:
        """Check if card has a specific ability."""
        return ability_id in self.stats.ability_ids

    def __repr__(self):
        return f"Card({self.name}, P{self.player}, HP:{self.curr_life}/{self.life})"


def create_card(name: str, player: int, card_id: int) -> Card:
    """Create a card instance from the database."""
    # Import here to avoid circular imports
    from .card_database import CARD_DATABASE
    if name not in CARD_DATABASE:
        raise ValueError(f"Unknown card: {name}")
    return Card(stats=CARD_DATABASE[name], player=player, id=card_id)
