"""AI logic for squad selection and card placement."""
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass

from ..card_database import CARD_DATABASE
from ..card import Card, create_card
from ..constants import Element
from ..squad_builder import SquadBuilder, HAND_SIZE


@dataclass
class CardScore:
    """Score for a card in squad selection."""
    name: str
    cost: int
    element: Element
    is_elite: bool
    is_flying: bool
    score: float  # Higher is better


def score_card(name: str) -> float:
    """Score a card for squad selection.

    Higher score = more desirable card.
    Factors:
    - Base cost (higher cost = generally stronger)
    - Useful abilities
    - Good attack/HP ratio
    """
    stats = CARD_DATABASE.get(name)
    if not stats:
        return 0.0

    score = 0.0

    # Base score from cost (cost roughly = power level)
    score += stats.cost * 10

    # HP bonus (survivability)
    score += stats.life * 2

    # Attack bonus (average damage)
    avg_atk = sum(stats.attack) / 3
    score += avg_atk * 3

    # Movement bonus
    score += stats.move * 5

    # Flying is valuable
    if stats.is_flying:
        score += 15

    # Elite cards are generally stronger
    if stats.is_elite:
        score += 10

    # Ability bonuses
    ability_scores = {
        'regeneration': 20,
        'regeneration_1': 10,
        'heal_ally': 25,
        'heal_self': 15,
        'direct_attack': 20,
        'defender_no_tap': 15,
        'unlimited_defender': 20,
        'shot': 15,  # ranged
        'lunge': 20,
        'lunge_2': 25,
        'tough_hide': 10,
        'magic_immune': 10,
        'attack_exp': 15,
        'defense_exp': 15,
        'scavenging': 15,
        'valhalla': 20,
    }

    for ability_id in stats.ability_ids:
        for key, bonus in ability_scores.items():
            if key in ability_id:
                score += bonus
                break

    return score


def select_squad_greedy(builder: SquadBuilder) -> List[str]:
    """Select squad using greedy algorithm.

    Strategy:
    1. Score all cards in hand
    2. Group by element to minimize penalties
    3. Greedily select best cards that fit budget

    Returns list of selected card names.
    """
    hand = builder.hand.copy()

    # Score all cards
    scored_cards = []
    for name in hand:
        stats = CARD_DATABASE.get(name)
        if stats:
            scored_cards.append(CardScore(
                name=name,
                cost=stats.cost,
                element=stats.element,
                is_elite=stats.is_elite,
                is_flying=stats.is_flying,
                score=score_card(name)
            ))

    # Sort by score descending
    scored_cards.sort(key=lambda c: -c.score)

    # Group by element (excluding neutral)
    element_groups: Dict[Element, List[CardScore]] = {}
    neutral_cards: List[CardScore] = []

    for card in scored_cards:
        if card.element == Element.NEUTRAL:
            neutral_cards.append(card)
        else:
            if card.element not in element_groups:
                element_groups[card.element] = []
            element_groups[card.element].append(card)

    # Find best element(s) to focus on
    # Score each element by total value of its cards
    element_scores = {}
    for elem, cards in element_groups.items():
        total_score = sum(c.score for c in cards)
        element_scores[elem] = total_score

    # Sort elements by total score
    sorted_elements = sorted(element_scores.keys(),
                            key=lambda e: -element_scores[e])

    # Build selection order: best element first, then others, then neutral
    selection_order = []

    # Add cards from best element
    if sorted_elements:
        best_element = sorted_elements[0]
        selection_order.extend(element_groups[best_element])

    # Add neutral cards (no penalty)
    selection_order.extend(neutral_cards)

    # Add cards from other elements (will incur penalty)
    for elem in sorted_elements[1:]:
        selection_order.extend(element_groups[elem])

    # Re-sort by score within this order isn't needed - just try in order
    # But let's re-sort to prioritize high-value cards
    selection_order.sort(key=lambda c: -c.score)

    # Greedily add cards
    selected = []
    for card in selection_order:
        can_add, _ = builder.can_add_card(card.name)
        if can_add:
            if builder.add_card(card.name, prefer_silver=True):
                selected.append(card.name)

    return selected


def select_squad_optimized(builder: SquadBuilder) -> List[str]:
    """Select squad with optimization for element penalties.

    Try different element combinations and pick the best result.
    """
    hand = builder.hand.copy()

    # Get all elements in hand
    elements_in_hand: Set[Element] = set()
    for name in hand:
        stats = CARD_DATABASE.get(name)
        if stats and stats.element != Element.NEUTRAL:
            elements_in_hand.add(stats.element)

    # If only one element, just use greedy
    if len(elements_in_hand) <= 1:
        return select_squad_greedy(builder)

    # Try single-element strategies and pick best
    best_squad = []
    best_value = 0

    # Try each element as primary
    for primary_element in elements_in_hand:
        # Reset builder (create new one with same hand)
        test_builder = SquadBuilder(
            player=builder.player,
            deck_cards=builder.deck_cards
        )
        test_builder.hand = hand.copy()
        test_builder.remaining_deck = builder.remaining_deck.copy()
        test_builder.mulligan_count = builder.mulligan_count
        test_builder.gold = builder.gold
        test_builder.silver = builder.silver

        # Select cards prioritizing this element
        squad = _select_with_primary_element(test_builder, primary_element)

        # Score the squad
        value = sum(score_card(name) for name in squad)

        if value > best_value:
            best_value = value
            best_squad = squad

    # Apply the best selection to actual builder
    builder.squad.clear()
    builder.squad_costs.clear()

    # Reset crystals
    if builder.player == 1:
        from ..squad_builder import PLAYER1_GOLD, PLAYER1_SILVER
        builder.gold = PLAYER1_GOLD - builder.mulligan_count
        builder.silver = PLAYER1_SILVER
    else:
        from ..squad_builder import PLAYER2_GOLD, PLAYER2_SILVER
        builder.gold = PLAYER2_GOLD - builder.mulligan_count
        builder.silver = PLAYER2_SILVER

    builder.hand = hand.copy()

    for name in best_squad:
        if name in builder.hand:
            builder.add_card(name, prefer_silver=True)

    return builder.squad.copy()


def _select_with_primary_element(builder: SquadBuilder,
                                  primary: Element) -> List[str]:
    """Select cards prioritizing a primary element."""
    hand = builder.hand.copy()

    # Score and categorize
    primary_cards = []
    neutral_cards = []
    other_cards = []

    for name in hand:
        stats = CARD_DATABASE.get(name)
        if not stats:
            continue

        score = score_card(name)

        if stats.element == primary:
            primary_cards.append((name, score))
        elif stats.element == Element.NEUTRAL:
            neutral_cards.append((name, score))
        else:
            other_cards.append((name, score))

    # Sort each group by score
    primary_cards.sort(key=lambda x: -x[1])
    neutral_cards.sort(key=lambda x: -x[1])
    other_cards.sort(key=lambda x: -x[1])

    # Build selection order: primary > neutral > other
    selection_order = (
        [c[0] for c in primary_cards] +
        [c[0] for c in neutral_cards] +
        [c[0] for c in other_cards]
    )

    # Add cards
    selected = []
    for name in selection_order:
        can_add, _ = builder.can_add_card(name)
        if can_add:
            if builder.add_card(name, prefer_silver=True):
                selected.append(name)

    return selected


def _has_formation_ability(card: Card) -> bool:
    """Check if card has a formation ability."""
    from ..abilities import get_ability
    for aid in card.stats.ability_ids:
        ability = get_ability(aid)
        if ability and ability.is_formation:
            return True
    return False


def _get_adjacent_positions(pos: int) -> List[int]:
    """Get orthogonally adjacent positions on the main board."""
    if pos >= 30:  # Flying zone
        return []
    row, col = pos // 5, pos % 5
    adjacent = []
    if row > 0:
        adjacent.append(pos - 5)  # Up
    if row < 5:
        adjacent.append(pos + 5)  # Down
    if col > 0:
        adjacent.append(pos - 1)  # Left
    if col < 4:
        adjacent.append(pos + 1)  # Right
    return [p for p in adjacent if 0 <= p < 30]


def place_cards_heuristic(cards: List[Card], player: int) -> Dict[int, Card]:
    """Place cards using heuristics.

    Strategy:
    - High HP cards in front row (tanks)
    - Ranged/support cards in back row
    - Flying cards in flying zones
    - Formation cards placed adjacent to each other

    Args:
        cards: List of Card objects to place
        player: Player number (1 or 2)

    Returns:
        Dict mapping position -> Card
    """
    placement: Dict[int, Card] = {}

    # Separate flying and ground cards
    flying_cards = [c for c in cards if c.stats.is_flying]
    ground_cards = [c for c in cards if not c.stats.is_flying]

    # Separate formation cards from other ground cards
    formation_cards = [c for c in ground_cards if _has_formation_ability(c)]
    non_formation_cards = [c for c in ground_cards if not _has_formation_ability(c)]

    # Score ground cards for front/back placement
    # Higher score = more suitable for front row
    def front_row_score(card: Card) -> float:
        score = 0.0
        # High HP = tank
        score += card.life * 3
        # High attack = frontline fighter
        score += sum(card.stats.attack) / 3 * 2
        # Defender abilities = front row
        for aid in card.stats.ability_ids:
            if 'defender' in aid:
                score += 20
            if 'tough' in aid or 'armor' in aid:
                score += 15
            # Ranged = back row (negative)
            if 'shot' in aid or 'lunge' in aid:
                score -= 20
            # Healing = back row
            if 'heal' in aid:
                score -= 15
        return score

    # Sort ground cards by front row score (highest = front)
    ground_cards.sort(key=lambda c: -front_row_score(c))

    # Define positions
    if player == 1:
        # P1: rows 0-2 (positions 0-14)
        front_row = [10, 11, 12, 13, 14]  # Row 2 (closest to enemy)
        middle_row = [5, 6, 7, 8, 9]      # Row 1
        back_row = [0, 1, 2, 3, 4]        # Row 0 (furthest from enemy)
        flying_positions = [30, 31, 32, 33, 34]  # P1 flying zone
    else:
        # P2: rows 3-5 (positions 15-29)
        front_row = [15, 16, 17, 18, 19]  # Row 3 (closest to enemy)
        middle_row = [20, 21, 22, 23, 24] # Row 4
        back_row = [25, 26, 27, 28, 29]   # Row 5 (furthest from enemy)
        flying_positions = [35, 36, 37, 38, 39]  # P2 flying zone

    # Place flying cards in flying zone (5 slots available)
    for i, card in enumerate(flying_cards):
        if i < len(flying_positions):
            pos = flying_positions[i]
            placement[pos] = card
            card.position = pos

    # Place ground cards: front row first, then middle, then back
    all_positions = front_row + middle_row + back_row

    # Prefer center positions within each row
    def position_priority(pos: int) -> int:
        # Center column (2) is best, then 1 and 3, then 0 and 4
        col = pos % 5
        priority_map = {2: 0, 1: 1, 3: 1, 0: 2, 4: 2}
        return priority_map.get(col, 3)

    # Sort positions within each row by center priority
    front_row.sort(key=position_priority)
    middle_row.sort(key=position_priority)
    back_row.sort(key=position_priority)

    # Collect all available positions by row priority
    all_positions = front_row + middle_row + back_row
    used_positions: Set[int] = set()

    # Place formation cards first - try to place them adjacent to each other
    if len(formation_cards) >= 2:
        # Sort formation cards by front row score
        formation_cards.sort(key=lambda c: -front_row_score(c))

        # Find good adjacent position pairs in middle/front rows (for formation)
        # Prefer horizontal pairs (same row) as they're easier to maintain
        formation_pairs = []
        for row_positions in [front_row, middle_row]:
            for i in range(len(row_positions) - 1):
                p1, p2 = row_positions[i], row_positions[i + 1]
                # Check if horizontally adjacent
                if abs(p1 - p2) == 1:
                    formation_pairs.append((p1, p2))

        # Place first two formation cards as a pair
        if formation_pairs and len(formation_cards) >= 2:
            p1, p2 = formation_pairs[0]
            placement[p1] = formation_cards[0]
            formation_cards[0].position = p1
            used_positions.add(p1)

            placement[p2] = formation_cards[1]
            formation_cards[1].position = p2
            used_positions.add(p2)

            # Place remaining formation cards adjacent to existing ones if possible
            for card in formation_cards[2:]:
                placed = False
                for placed_pos in [p1, p2]:
                    for adj in _get_adjacent_positions(placed_pos):
                        if adj not in used_positions and adj in all_positions:
                            placement[adj] = card
                            card.position = adj
                            used_positions.add(adj)
                            placed = True
                            break
                    if placed:
                        break
                if not placed:
                    # Couldn't place adjacent, add to non-formation cards
                    non_formation_cards.append(card)

            # Remove placed formation cards
            formation_cards = []

    # Any remaining formation cards go with non-formation
    non_formation_cards.extend(formation_cards)

    # Sort remaining cards by front row score
    non_formation_cards.sort(key=lambda c: -front_row_score(c))

    # Place remaining ground cards in available positions
    available_positions = [p for p in (front_row + middle_row + back_row)
                          if p not in used_positions]

    for card in non_formation_cards:
        if available_positions:
            pos = available_positions.pop(0)
            placement[pos] = card
            card.position = pos
            used_positions.add(pos)

    return placement


def build_ai_squad(player: int, deck_cards: List[str]) -> Tuple[List[str], Dict[int, Card]]:
    """Build a complete squad for AI player.

    Args:
        player: Player number (1 or 2)
        deck_cards: Full deck of card names

    Returns:
        Tuple of (squad_names, placement_dict)
    """
    # Create squad builder
    builder = SquadBuilder(player=player, deck_cards=deck_cards)

    # Select squad
    squad_names = select_squad_optimized(builder)

    # Create card objects
    base_id = (player - 1) * 100 + 1
    cards = []
    for i, name in enumerate(squad_names):
        card = create_card(name, player=player, card_id=base_id + i)
        cards.append(card)

    # Place cards
    placement = place_cards_heuristic(cards, player)

    return squad_names, placement
