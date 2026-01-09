# Berserk Digital Card Game Project

## Project Overview

Digital implementation of the Russian card game "Берсерк" (Berserk) - a strategic collectible card game where players command fantasy creature squads. Built with Pygame for hot-seat (local multiplayer) mode.

**Rules Source:** https://berserk.ru/pravila-igri
**Card Database:** https://proberserk.ru/edition/aa7e3

---

## Current Architecture

### Technology Stack
- **GUI Framework:** Pygame (with resizable window support)
- **Resolution:** 1280x720 base, scales to any window size
- **Rendering:** Render surface approach (fixed resolution scaled to window)

### Project Structure
```
berserk_vibe/
├── main.py                 # Entry point, event loop, input handling
├── claude.md               # This file - project documentation
├── build.py                # PyInstaller build script
├── download_cards.py       # Card image downloader
│
├── src/                    # Game engine
│   ├── __init__.py
│   ├── constants.py        # Enums, colors, dimensions
│   ├── card.py             # Card and CardStats classes
│   ├── board.py            # Board management, positions, flying zones
│   ├── game.py             # Game state, combat, abilities, turns
│   ├── abilities.py        # Ability definitions and registry
│   ├── card_database.py    # Card definitions and starter deck
│   └── renderer.py         # All Pygame rendering, UI, visual effects
│
└── data/
    └── cards/              # Card images (*.jpg)
```

---

## Core Systems

### Board Layout
```
Flying P2    |  Board (5x6)           | Flying P1
(left)       |                        | (right)
             |  Player 2 (rows 3-5)   |
Pos 33-35    | 25 26 27 28 29         | Pos 30-32
             | 20 21 22 23 24         |
             | 15 16 17 18 19         |
             ├────────────────────────┤
             | 10 11 12 13 14         |
             |  5  6  7  8  9         |
             |  0  1  2  3  4         |
             |  Player 1 (rows 0-2)   |
```

- **Main board:** 30 cells (positions 0-29)
- **Flying zones:** 3 slots per player (P1: 30-32, P2: 33-35)
- **Player 1:** Bottom 3 rows (positions 0-14)
- **Player 2:** Top 3 rows (positions 15-29)

### Combat System

**Dice Roll Resolution (d6 vs d6):**

| Roll Difference | Attacker Damage | Defender Counter |
|-----------------|-----------------|------------------|
| +5 or more      | Strong (index 2)| None             |
| +3 to +4        | Strong          | None             |
| +1 to +2        | Medium (index 1)| None             |
| 0 (roll 1-4)    | Weak (index 0)  | None             |
| 0 (roll 5-6)    | None            | Weak             |
| -1 to -2        | None            | None             |
| -3 to -4        | None            | Weak             |
| -5 or less      | None            | Medium           |

**Against tapped cards:** Only attacker rolls, no counter-attack possible.

**Damage tiers:** Each card has attack tuple (weak, medium, strong), e.g., `(2, 3, 5)`

### Defender System
- Untapped adjacent allies can intercept attacks
- Defender choice popup appears when valid defenders exist
- Some cards have "direct attack" (направленный) - cannot be intercepted
- Defenders can have special abilities (no tap, unlimited defense, etc.)

### Flying Creatures
- Placed in separate flying zones (not main board)
- Can attack any card on the board
- Can be targeted by ranged attacks regardless of range
- Have their own movement rules (move=0 typically)
- Example: Корпит (flying, direct attack, scavenging)

---

## Ability System

### Ability Types
- **ACTIVE:** Requires activation, taps the card
- **PASSIVE:** Always active, no action needed
- **TRIGGERED:** Activates on specific events

### Triggers
- `ON_TURN_START` - Start of owner's turn (regeneration, buffs)
- `ON_ATTACK` - When attacking (counter shot, heal on attack)
- `ON_DEFEND` - When becoming a defender (defender buff)
- `ON_KILL` - When killing an enemy (scavenging)
- `VALHALLA` - From graveyard when killed by enemy

### Implemented Abilities

| ID | Name | Description |
|----|------|-------------|
| `heal_ally` | Дыхание леса | Heal any creature +2 HP |
| `crown_runner_shot` | Выстрел | Ranged 1-2-2 damage (min range 2) |
| `lunge` / `lunge_2` | Удар через ряд | Attack through one cell (fixed damage) |
| `attack_exp` | Опыт в атаке | +1 to attack dice roll |
| `defense_exp` | Опыт в защите | +1 to defense dice roll |
| `regeneration` | Регенерация | +3 HP at turn start |
| `regeneration_1` | Регенерация | +1 HP at turn start |
| `tough_hide` | Толстая шкура | -2 damage from creatures costing ≤3 |
| `direct_attack` | Направленный | Attack cannot be intercepted |
| `poison_immune` | Защита от яда | Cannot be poisoned |
| `magic_immune` | Защита от магии | Immune to magic/spells |
| `shot_immune` | Защита от выстрелов | Immune to ranged attacks |
| `diagonal_defense` | Защита от диагонали | -2 damage from diagonal attacks |
| `restricted_strike` | Только напротив | Can only attack card directly opposite |
| `magical_strike` | Магический удар | Deal 2 magic damage (ignores reductions) |
| `defender_no_tap` | Стойкий защитник | Doesn't tap when defending |
| `unlimited_defender` | Многократная защита | Can defend any number of times |
| `defender_buff` | Ярость защитника | +2 attack and +1 dice when defending |
| `counter_shot` | Ответный выстрел | When attacking, also deal 2 ranged damage |
| `heal_on_attack` | Исцеление при ударе | Heal for target's medium damage when attacking |
| `scavenging` | Трупоедство | Full heal when killing enemy |
| `valhalla_ova` | Вальхалла | Give ally +1 attack dice (from graveyard) |
| `flying` | Летающий | Flying creature marker |

---

## Visual System

### Interaction Arrows
- **Red arrows:** All attack types (melee, ranged, magic, lunge)
- **Green arrows:** Healing abilities
- Arrows appear when action is declared
- Persist for minimum 1 second after damage is dealt
- Clear immediately when selecting new target or deselecting

### Floating Text
- **Red numbers:** Damage dealt (-X)
- **Green numbers:** Healing received (+X)
- Float upward and fade over 1 second

### Popups (Draggable)
- **Defender selection:** Choose which card intercepts
- **Valhalla target:** Select ally to receive buff
- **Counter shot target:** Select target for bonus ranged attack
- **Heal confirmation:** Accept/decline heal-on-attack
- All popups can be dragged to not obscure the board

### Card Display
- Card art cropped from full card images
- HP bar shows current/max health
- Move counter shows remaining movement
- Tapped cards shown in grayscale and rotated
- Selected card highlighted in gold
- Valid moves shown in green, attacks in red

---

## Card Database

### Current Cards (31 unique)

**Mountains (Горы):**
- Циклоп, Гном-басаарг, Хобгоблин, Хранитель гор
- Повелитель молний, Гобрах, Ледовый охотник
- Горный великан, Мастер топора, Костедробитель
- Смотритель горнила, Овражный гном

**Forest (Лес):**
- Лёккен, Эльфийский воин, Бегущая по кронам
- Кобольд, Клаэр, Борг, Ловец удачи
- Матросы Аделаиды, Мразень, Друид
- Корпит (flying), Оури, Паук-пересмешник, Дракс

### Card Stats Structure
```python
CardStats(
    name="Циклоп",
    cost=8,                          # Crystal cost
    element=Element.FOREST,          # Card element
    card_type=CardType.CREATURE,     # CREATURE or FLYER
    life=14,                         # Max HP
    attack=(4, 5, 6),                # (weak, medium, strong)
    move=1,                          # Movement points
    is_flying=False,                 # Flying creature flag
    description="...",               # Card text
    ability_ids=["ability1", ...]    # List of ability IDs
)
```

---

## Controls

| Input | Action |
|-------|--------|
| **Left Click** card | Select card |
| **Left Click** green cell | Move selected card |
| **Left Click** red cell | Attack target |
| **Right Click** card | Show card popup (full art + stats) |
| **Right Click** empty | Deselect card |
| **Space** | Skip defender choice / End turn |
| **Enter** | Finish placement phase |
| **Y / N** | Confirm/decline heal-on-attack |
| **R** | Restart game |
| **F11** | Toggle fullscreen |
| **ESC** | Quit game |
| **Scroll** | Scroll message log |

---

## Game Flow

### Phases
1. **SETUP:** Cards placed face-down (currently auto-placed for testing)
2. **REVEAL:** Cards revealed simultaneously
3. **MAIN:** Players take turns moving and attacking
4. **GAME_OVER:** One player has no creatures left

### Turn Structure
1. Cards untap and reset movement
2. Regeneration and turn-start triggers fire
3. Valhalla abilities from graveyard queue up
4. Player can: move, attack, use abilities
5. End turn passes to opponent

### Victory Condition
Destroy all opponent's creatures (main board + flying zone).

---

## Window System

### Resizable Window
- Base resolution: 1280x720
- Window can be resized by dragging edges
- F11 toggles fullscreen
- Aspect ratio maintained with letterboxing
- All mouse coordinates properly scaled

### Coordinate Systems
- **Screen coords:** Raw mouse position from Pygame
- **Game coords:** Converted via `screen_to_game_coords()`
- **Board position:** Cell index 0-29 (or 30-35 for flying)

---

## Future Plans / TODOs

### Gameplay
- [ ] Stack system for ability resolution order
- [ ] More card abilities (spells, artifacts)
- [ ] Deck building screen
- [ ] Squad formation with crystal costs
- [ ] Save/load game state

### Cards
- [ ] Add more card sets
- [ ] Implement remaining ability types
- [ ] Card rarity system
- [ ] Unique card rules

### UI
- [ ] Main menu
- [ ] Settings screen
- [ ] Card collection viewer
- [ ] Deck editor

### Network
- [ ] Online multiplayer
- [ ] Server/client architecture
- [ ] Lobby system

---

## Quick Reference

```bash
# Install dependencies
pip install pygame

# Run game
python main.py

# Build executable
python build.py
```

## Dependencies
```
pygame>=2.5.0
```

---

## Session Notes

### Recent Changes (2026-01-08)
- Added resizable window with F11 fullscreen toggle
- Implemented render surface scaling (maintains aspect ratio)
- Added interaction arrows for attacks/heals
- Arrows persist for 1 second minimum, clear on new action
- Simplified arrow colors (red=damage, green=heal)
- Made confirmation popups draggable
- Generalized popup system with PopupConfig
- Fixed flying zone card positioning
- Removed P1/P2 row labels from board
- Added flying creature targeting for ranged attacks
- Added direct_attack to Корпит
- Fixed coordinate scaling for all mouse inputs

### Previous Session (2026-01-07)
- Implemented flying creatures system
- Added flying zones (3 slots per player)
- Flying cards can attack any board position
- Implemented Корпит with flying, scavenging abilities
- Added visual effects (floating damage/heal numbers)
- Implemented defender system with popup selection
- Added Valhalla trigger system
- Added counter_shot and heal_on_attack abilities
