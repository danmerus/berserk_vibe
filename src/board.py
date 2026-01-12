"""Board management for the game."""
from typing import List, Optional, Set
from .card import Card
from .constants import BOARD_COLS, BOARD_ROWS


class Board:
    """
    6x5 game board with flying zones.

    Main board layout (player 1 at bottom, player 2 at top):

        Col:  0   1   2   3   4
            ┌───┬───┬───┬───┬───┐
    Row 5   │25 │26 │27 │28 │29 │  <- Player 2 back row
            ├───┼───┼───┼───┼───┤
    Row 4   │20 │21 │22 │23 │24 │
            ├───┼───┼───┼───┼───┤
    Row 3   │15 │16 │17 │18 │19 │
            ├───┼───┼───┼───┼───┤
    Row 2   │10 │11 │12 │13 │14 │
            ├───┼───┼───┼───┼───┤
    Row 1   │ 5 │ 6 │ 7 │ 8 │ 9 │
            ├───┼───┼───┼───┼───┤
    Row 0   │ 0 │ 1 │ 2 │ 3 │ 4 │  <- Player 1 back row
            └───┴───┴───┴───┴───┘

    Flying zones (3 slots per player):
        Player 1: positions 30, 31, 32
        Player 2: positions 33, 34, 35

    Position = row * 5 + col (for main board 0-29)
    """

    FLYING_P1_START = 30  # Positions 30, 31, 32
    FLYING_P2_START = 33  # Positions 33, 34, 35
    FLYING_SLOTS = 3

    def __init__(self):
        self.cells: List[Optional[Card]] = [None] * (BOARD_COLS * BOARD_ROWS)
        # Flying zones (3 slots per player)
        self.flying_p1: List[Optional[Card]] = [None] * self.FLYING_SLOTS
        self.flying_p2: List[Optional[Card]] = [None] * self.FLYING_SLOTS
        self.graveyard_p1: List[Card] = []
        self.graveyard_p2: List[Card] = []

    def pos_to_coords(self, pos: int) -> tuple[int, int]:
        """Convert position index to (col, row)."""
        return pos % BOARD_COLS, pos // BOARD_COLS

    def coords_to_pos(self, col: int, row: int) -> int:
        """Convert (col, row) to position index."""
        return row * BOARD_COLS + col

    def is_valid_pos(self, pos: int) -> bool:
        """Check if position is valid (main board only)."""
        return 0 <= pos < len(self.cells)

    def is_flying_pos(self, pos: int) -> bool:
        """Check if position is in flying zone."""
        return self.FLYING_P1_START <= pos < self.FLYING_P1_START + self.FLYING_SLOTS * 2

    def get_flying_zone(self, pos: int) -> Optional[List[Optional['Card']]]:
        """Get the flying zone list for a position, or None if not flying pos."""
        if self.FLYING_P1_START <= pos < self.FLYING_P1_START + self.FLYING_SLOTS:
            return self.flying_p1
        elif self.FLYING_P2_START <= pos < self.FLYING_P2_START + self.FLYING_SLOTS:
            return self.flying_p2
        return None

    def get_flying_index(self, pos: int) -> int:
        """Get index within flying zone for a position."""
        if self.FLYING_P1_START <= pos < self.FLYING_P1_START + self.FLYING_SLOTS:
            return pos - self.FLYING_P1_START
        elif self.FLYING_P2_START <= pos < self.FLYING_P2_START + self.FLYING_SLOTS:
            return pos - self.FLYING_P2_START
        return -1

    def get_card(self, pos: int) -> Optional[Card]:
        """Get card at position (main board or flying zone)."""
        if self.is_flying_pos(pos):
            zone = self.get_flying_zone(pos)
            idx = self.get_flying_index(pos)
            return zone[idx] if zone else None
        if not self.is_valid_pos(pos):
            return None
        return self.cells[pos]

    def get_card_by_id(self, card_id: int) -> Optional[Card]:
        """Find a card by its ID across all board locations."""
        # Check main board
        for card in self.cells:
            if card is not None and card.id == card_id:
                return card
        # Check flying zones
        for card in self.flying_p1:
            if card is not None and card.id == card_id:
                return card
        for card in self.flying_p2:
            if card is not None and card.id == card_id:
                return card
        return None

    def place_card(self, card: Card, pos: int) -> bool:
        """Place a card on the board. Returns True if successful."""
        if self.is_flying_pos(pos):
            zone = self.get_flying_zone(pos)
            idx = self.get_flying_index(pos)
            if zone is None or zone[idx] is not None:
                return False
            zone[idx] = card
            card.position = pos
            return True
        if not self.is_valid_pos(pos) or self.cells[pos] is not None:
            return False
        self.cells[pos] = card
        card.position = pos
        return True

    def remove_card(self, pos: int) -> Optional[Card]:
        """Remove and return card from position."""
        if self.is_flying_pos(pos):
            zone = self.get_flying_zone(pos)
            idx = self.get_flying_index(pos)
            if zone is None:
                return None
            card = zone[idx]
            if card:
                card.position = None
                zone[idx] = None
            return card
        if not self.is_valid_pos(pos):
            return None
        card = self.cells[pos]
        if card:
            card.position = None
            self.cells[pos] = None
        return card

    def move_card(self, from_pos: int, to_pos: int) -> bool:
        """Move a card from one position to another."""
        if not self.is_valid_pos(from_pos) or not self.is_valid_pos(to_pos):
            return False
        if self.cells[from_pos] is None or self.cells[to_pos] is not None:
            return False

        card = self.cells[from_pos]
        self.cells[from_pos] = None
        self.cells[to_pos] = card
        card.position = to_pos
        return True

    def get_adjacent_cells(self, pos: int, include_diagonals: bool = False) -> List[int]:
        """Get adjacent cell positions (orthogonal only by default)."""
        col, row = self.pos_to_coords(pos)
        adjacent = []

        # Orthogonal neighbors
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if include_diagonals:
            directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dc, dr in directions:
            nc, nr = col + dc, row + dr
            if 0 <= nc < BOARD_COLS and 0 <= nr < BOARD_ROWS:
                adjacent.append(self.coords_to_pos(nc, nr))

        return adjacent

    def get_valid_moves(self, card: Card) -> List[int]:
        """Get valid movement positions for a card (1 square at a time, or jump)."""
        if card.position is None or card.tapped or card.curr_move <= 0:
            return []

        # Check if card has jump ability
        has_jump = card.has_ability("jump")

        if has_jump:
            # Jump: can move to any empty cell within range (Manhattan distance)
            valid = []
            col, row = self.pos_to_coords(card.position)
            jump_range = card.curr_move  # Use remaining move as jump range
            for pos in range(len(self.cells)):
                if self.cells[pos] is None:  # Empty cell
                    tc, tr = self.pos_to_coords(pos)
                    dist = abs(tc - col) + abs(tr - row)  # Manhattan distance
                    if 0 < dist <= jump_range:
                        valid.append(pos)
            return valid
        else:
            # Normal: only allow moving to adjacent empty cells (1 square at a time)
            valid = []
            for adj in self.get_adjacent_cells(card.position, include_diagonals=False):
                if self.cells[adj] is None:  # Empty cell
                    valid.append(adj)
            return valid

    def get_attack_targets(self, card: Card, include_allies: bool = True) -> List[int]:
        """Get valid attack target positions for a card (includes allies for friendly fire)."""
        if card.position is None or card.tapped:
            return []

        # Flying creatures can attack anyone on battlefield or flying zone
        if self.is_flying_pos(card.position):
            return self._get_flying_attack_targets(card, include_allies)

        # Handle restricted_strike (can only attack card directly in front)
        if card.has_ability("restricted_strike"):
            return self._get_restricted_strike_targets(card)

        targets = []
        for adj in self.get_adjacent_cells(card.position, include_diagonals=True):
            target_card = self.cells[adj]
            if target_card and target_card.is_alive and target_card != card:
                if target_card.player != card.player:
                    targets.append(adj)
                elif include_allies:
                    targets.append(adj)

        return targets

    def _get_restricted_strike_targets(self, card: Card) -> List[int]:
        """Get targets for restricted_strike (only card directly in front, same column)."""
        col, row = self.pos_to_coords(card.position)

        # Determine forward direction based on player
        if card.player == 1:
            # Player 1: forward is toward higher rows
            front_row = row + 1
        else:
            # Player 2: forward is toward lower rows
            front_row = row - 1

        # Check bounds
        if front_row < 0 or front_row >= BOARD_ROWS:
            return []

        # Get position directly in front
        front_pos = self.coords_to_pos(col, front_row)
        target_card = self.cells[front_pos]

        # Can only attack if there's an enemy card there
        if target_card and target_card.is_alive and target_card.player != card.player:
            return [front_pos]

        return []

    def _get_flying_attack_targets(self, card: Card, include_allies: bool = True) -> List[int]:
        """Get attack targets for a flying creature (can attack anyone)."""
        targets = []
        enemy_player = 2 if card.player == 1 else 1

        # Check if enemy has any card with flyer_taunt
        flyer_taunt_targets = []
        for pos, target_card in enumerate(self.cells):
            if target_card and target_card.is_alive and target_card.player == enemy_player:
                if target_card.has_ability("flyer_taunt"):
                    flyer_taunt_targets.append(pos)

        # If enemy has flyer_taunt, can ONLY attack those creatures
        if flyer_taunt_targets:
            return flyer_taunt_targets

        # All ground creatures
        for pos, target_card in enumerate(self.cells):
            if target_card and target_card.is_alive and target_card != card:
                if target_card.player != card.player:
                    targets.append(pos)
                elif include_allies:
                    targets.append(pos)

        # All flying creatures (both zones)
        for i, target_card in enumerate(self.flying_p1):
            if target_card and target_card.is_alive and target_card != card:
                pos = self.FLYING_P1_START + i
                if target_card.player != card.player:
                    targets.append(pos)
                elif include_allies:
                    targets.append(pos)

        for i, target_card in enumerate(self.flying_p2):
            if target_card and target_card.is_alive and target_card != card:
                pos = self.FLYING_P2_START + i
                if target_card.player != card.player:
                    targets.append(pos)
                elif include_allies:
                    targets.append(pos)

        return targets

    def get_all_cards(self, player: Optional[int] = None, include_flying: bool = True) -> List[Card]:
        """Get all cards on board, optionally filtered by player."""
        cards = [c for c in self.cells if c is not None]
        if include_flying:
            cards += [c for c in self.flying_p1 if c is not None]
            cards += [c for c in self.flying_p2 if c is not None]
        if player is not None:
            cards = [c for c in cards if c.player == player]
        return cards

    def get_flying_cards(self, player: Optional[int] = None) -> List[Card]:
        """Get all flying cards, optionally filtered by player."""
        cards = []
        cards += [c for c in self.flying_p1 if c is not None]
        cards += [c for c in self.flying_p2 if c is not None]
        if player is not None:
            cards = [c for c in cards if c.player == player]
        return cards

    def send_to_graveyard(self, card: Card):
        """Move a dead card to its owner's graveyard."""
        if card.position is not None:
            if self.is_flying_pos(card.position):
                zone = self.get_flying_zone(card.position)
                idx = self.get_flying_index(card.position)
                if zone:
                    zone[idx] = None
            else:
                self.cells[card.position] = None
            card.position = None

        if card.player == 1:
            self.graveyard_p1.append(card)
        else:
            self.graveyard_p2.append(card)

    def get_placement_zone(self, player: int) -> List[int]:
        """Get valid initial placement positions for a player (main board only)."""
        if player == 1:
            # Player 1: rows 0-2 (bottom)
            return [i for i in range(15) if self.cells[i] is None]
        else:
            # Player 2: rows 3-5 (top)
            return [i for i in range(15, 30) if self.cells[i] is None]

    def get_flying_placement_zone(self, player: int) -> List[int]:
        """Get valid flying zone positions for a player."""
        if player == 1:
            return [self.FLYING_P1_START + i for i in range(self.FLYING_SLOTS)
                    if self.flying_p1[i] is None]
        else:
            return [self.FLYING_P2_START + i for i in range(self.FLYING_SLOTS)
                    if self.flying_p2[i] is None]

    def get_valid_defenders(self, attacker: Card, target: Card) -> List[Card]:
        """
        Get valid defenders that can intercept an attack.

        Standard rules:
        - Adjacent to BOTH attacker and target
        - Same team as target, not tapped, alive, not target itself

        Flying rules:
        - If target is flying: ONLY other flyers can defend
        - If attacker is flying: other flyers OR creatures adjacent to target can defend
        """
        if attacker.position is None or target.position is None:
            return []

        defenders = []
        attacker_is_flying = self.is_flying_pos(attacker.position)
        target_is_flying = self.is_flying_pos(target.position)

        # If target is flying, only other flyers can defend
        if target_is_flying:
            for card in self.get_flying_cards(player=target.player):
                if card == target or not card.is_alive or card.webbed:
                    continue
                if card.tapped:
                    continue
                defenders.append(card)
            return defenders

        # If attacker is flying attacking ground target
        if attacker_is_flying:
            # Flyers can defend
            for card in self.get_flying_cards(player=target.player):
                if card == target or not card.is_alive or card.webbed:
                    continue
                if card.tapped:
                    continue
                defenders.append(card)
            # Ground creatures adjacent to target can also defend
            target_adjacent = self.get_adjacent_cells(target.position, include_diagonals=True)
            for pos in target_adjacent:
                card = self.get_card(pos)
                if card is None or card.player != target.player or card == target or not card.is_alive or card.webbed:
                    continue
                if card.tapped:
                    continue
                defenders.append(card)
            return defenders

        # Standard ground combat: adjacent to both attacker and target
        attacker_adjacent = set(self.get_adjacent_cells(attacker.position, include_diagonals=True))
        target_adjacent = set(self.get_adjacent_cells(target.position, include_diagonals=True))
        common_adjacent = attacker_adjacent & target_adjacent

        for pos in common_adjacent:
            card = self.get_card(pos)
            if card is None or card.player != target.player or card == target or not card.is_alive or card.webbed:
                continue
            if card.tapped:
                continue
            defenders.append(card)

        return defenders

    def check_winner(self) -> Optional[int]:
        """Check if a player has won. Returns winner (1 or 2) or None."""
        p1_cards = self.get_all_cards(player=1)
        p2_cards = self.get_all_cards(player=2)

        alive_p1 = [c for c in p1_cards if c.is_alive]
        alive_p2 = [c for c in p2_cards if c.is_alive]

        if not alive_p1 and not alive_p2:
            return 0  # Draw
        elif not alive_p1:
            return 2
        elif not alive_p2:
            return 1
        return None

    def to_dict(self) -> dict:
        """Serialize board state to dictionary for network/storage."""
        return {
            'cells': [card.to_dict() if card else None for card in self.cells],
            'flying_p1': [card.to_dict() if card else None for card in self.flying_p1],
            'flying_p2': [card.to_dict() if card else None for card in self.flying_p2],
            'graveyard_p1': [card.to_dict() for card in self.graveyard_p1],
            'graveyard_p2': [card.to_dict() for card in self.graveyard_p2],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Board':
        """Deserialize board state from dictionary."""
        board = cls()
        board.cells = [
            Card.from_dict(card_data) if card_data else None
            for card_data in data.get('cells', [None] * 30)
        ]
        board.flying_p1 = [
            Card.from_dict(card_data) if card_data else None
            for card_data in data.get('flying_p1', [None] * cls.FLYING_SLOTS)
        ]
        board.flying_p2 = [
            Card.from_dict(card_data) if card_data else None
            for card_data in data.get('flying_p2', [None] * cls.FLYING_SLOTS)
        ]
        board.graveyard_p1 = [
            Card.from_dict(card_data) for card_data in data.get('graveyard_p1', [])
        ]
        board.graveyard_p2 = [
            Card.from_dict(card_data) for card_data in data.get('graveyard_p2', [])
        ]
        return board
