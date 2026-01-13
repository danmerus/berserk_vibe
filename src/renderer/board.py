"""Board rendering - grid, cards, highlights."""
import pygame
from typing import Optional, List, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    BOARD_COLS, BOARD_ROWS, CELL_SIZE, BOARD_OFFSET_X, BOARD_OFFSET_Y,
    CARD_WIDTH, CARD_HEIGHT,
    COLOR_BG, COLOR_BOARD_LIGHT, COLOR_BOARD_DARK, COLOR_GRID_LINE,
    COLOR_PLAYER1, COLOR_PLAYER2, COLOR_SELECTED,
    COLOR_MOVE_HIGHLIGHT, COLOR_ATTACK_HIGHLIGHT,
    COLOR_TEXT, scaled, UI_SCALE, UILayout
)
from ..card_database import get_card_image

if TYPE_CHECKING:
    from ..game import Game
    from ..card import Card


class BoardMixin:
    """Mixin for board and card rendering."""

    def draw_board(self, game: 'Game'):
        """Draw the game board grid."""
        for row in range(BOARD_ROWS):
            for col in range(BOARD_COLS):
                x = BOARD_OFFSET_X + col * CELL_SIZE
                y = BOARD_OFFSET_Y + row * CELL_SIZE

                # Checkerboard pattern
                if (row + col) % 2 == 0:
                    color = COLOR_BOARD_LIGHT
                else:
                    color = COLOR_BOARD_DARK

                pygame.draw.rect(self.screen, color, (x, y, CELL_SIZE, CELL_SIZE))
                pygame.draw.rect(self.screen, COLOR_GRID_LINE, (x, y, CELL_SIZE, CELL_SIZE), 1)

    def draw_highlights(self, game: 'Game'):
        """Draw highlights for valid moves, attacks, and interaction targets on main board."""
        # Valid moves (green) - only on main board
        for pos in self._ui.valid_moves:
            if not self._is_flying_pos(pos):
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.move_highlight, (x, y))

        # Valid attacks (red) - only on main board
        for pos in self._ui.valid_attacks:
            if not self._is_flying_pos(pos):
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.attack_highlight, (x, y))

        # Interaction target highlights
        is_acting = (game.interaction and game.interaction.acting_player == self.viewing_player)

        if game.awaiting_defender and game.interaction and is_acting:
            # Defender highlights - highlight cards that can defend
            for card_id in game.interaction.valid_card_ids:
                card = game.board.get_card_by_id(card_id)
                if card and card.position is not None and not self._is_flying_pos(card.position):
                    x, y = self.pos_to_screen(card.position)
                    self.screen.blit(self.defender_highlight, (x, y))

        elif game.awaiting_ability_target and game.interaction and is_acting:
            # Ability target highlights (purple)
            for pos in game.interaction.valid_positions:
                if not self._is_flying_pos(pos):
                    x, y = self.pos_to_screen(pos)
                    self.screen.blit(self.ability_highlight, (x, y))

        elif game.awaiting_counter_shot and game.interaction and is_acting:
            # Counter shot target highlights (orange)
            for pos in game.interaction.valid_positions:
                if not self._is_flying_pos(pos):
                    x, y = self.pos_to_screen(pos)
                    self.screen.blit(self.counter_shot_highlight, (x, y))

        elif game.awaiting_movement_shot and game.interaction and is_acting:
            # Movement shot target highlights (orange)
            for pos in game.interaction.valid_positions:
                if not self._is_flying_pos(pos):
                    x, y = self.pos_to_screen(pos)
                    self.screen.blit(self.counter_shot_highlight, (x, y))

        elif game.awaiting_valhalla and game.interaction and is_acting:
            # Valhalla target highlights (gold)
            for pos in game.interaction.valid_positions:
                if not self._is_flying_pos(pos):
                    x, y = self.pos_to_screen(pos)
                    self.screen.blit(self.valhalla_highlight, (x, y))

    def draw_card(self, card: 'Card', x: int, y: int, selected: bool = False,
                  glow_intensity: float = 0.0, game: 'Game' = None, glow_color: tuple = None):
        """Draw a single card with image.

        Args:
            card: Card to draw
            x, y: Position
            selected: Whether card is selected
            glow_intensity: 0-1 for pulsing glow effect (instant abilities, defenders)
            glow_color: RGB tuple for glow color, defaults to golden (255, 220, 100)
        """
        # Check if card is face-down and belongs to opponent
        is_hidden = card.face_down and card.player != self.viewing_player

        # Card rectangle (slightly smaller than cell)
        card_rect = pygame.Rect(
            x + (CELL_SIZE - CARD_WIDTH) // 2,
            y + (CELL_SIZE - CARD_HEIGHT) // 2,
            CARD_WIDTH,
            CARD_HEIGHT
        )

        # Draw face-down card (cardback) for hidden enemy cards
        if is_hidden:
            self._draw_face_down_card(card_rect)
            return

        # Draw pulsing glow effect if intensity > 0
        if glow_intensity > 0:
            if glow_color is None:
                glow_color = (255, 220, 100)  # Golden glow (default)
            glow_alpha = int(180 * glow_intensity)
            glow_size = int(10 + 8 * glow_intensity)

            for i in range(glow_size, 0, -2):
                glow_rect = card_rect.inflate(i * 2, i * 2)
                glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
                layer_alpha = int(glow_alpha * (glow_size - i + 1) / glow_size)
                pygame.draw.rect(glow_surface, (*glow_color, layer_alpha), glow_surface.get_rect(), border_radius=3)
                self.screen.blit(glow_surface, glow_rect.topleft)

        # Player border color - based on viewing player perspective
        if card.player == self.viewing_player:
            border_color = (180, 150, 50)  # Gold for own cards
        else:
            border_color = (70, 100, 160)  # Blue for enemy cards

        pygame.draw.rect(self.screen, border_color, card_rect)

        # Name bar dimensions
        name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
        name_bar_y = card_rect.y + CARD_HEIGHT - name_bar_height

        # Determine name bar colors
        if card.player == self.viewing_player:
            name_bar_color = (180, 160, 60)
            name_text_color = (40, 30, 0)
        else:
            name_bar_color = (60, 80, 140)
            name_text_color = (220, 230, 255)

        # Card name text
        max_name_len = UILayout.CARD_NAME_MAX_LEN
        display_name = card.name[:max_name_len] + '..' if len(card.name) > max_name_len else card.name
        name_surface = self.font_card_name.render(display_name, True, name_text_color)

        # Try to draw card image with name bar
        img_filename = get_card_image(card.name)
        if img_filename and img_filename in self.card_images:
            img_raw = self.card_images[img_filename]
            target_h = CARD_HEIGHT - name_bar_height
            img = pygame.transform.smoothscale(img_raw, (CARD_WIDTH, target_h))

            if card.tapped:
                self._draw_tapped_card(card, card_rect, img, name_bar_height,
                                       name_bar_color, name_surface)
            else:
                self._draw_normal_card(card, card_rect, img, img_filename,
                                       name_bar_height, name_bar_y, name_bar_color, name_surface)

        # Selection border
        if selected:
            pygame.draw.rect(self.screen, COLOR_SELECTED, card_rect, 3)
        else:
            pygame.draw.rect(self.screen, COLOR_TEXT, card_rect, 1)

        # Stats for non-tapped cards
        if not card.tapped:
            self._draw_card_stats(card, card_rect, name_bar_height, name_bar_y)

        # Webbed indicator
        if card.webbed:
            self._draw_webbed_indicator(card, card_rect)

        # Counter indicator
        if not card.tapped and card.counters > 0:
            self._draw_counter_indicator(card, card_rect)

        # Formation indicator
        if not card.tapped and card.in_formation:
            self._draw_formation_indicator(card, card_rect)

        # Armor indicator
        if not card.tapped:
            self._draw_armor_indicator(card, card_rect, name_bar_height)

    def _draw_tapped_card(self, card: 'Card', card_rect: pygame.Rect, img: pygame.Surface,
                          name_bar_height: int, name_bar_color: tuple, name_surface: pygame.Surface):
        """Draw a tapped card (rotated with grayscale art)."""
        composite_width = CARD_WIDTH
        composite_height = img.get_height() + name_bar_height
        composite = pygame.Surface((composite_width, composite_height))

        # Convert image to grayscale
        grey_img = img.copy()
        arr = pygame.surfarray.pixels3d(grey_img)
        gray = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype('uint8')
        arr[:, :, 0] = gray
        arr[:, :, 1] = gray
        arr[:, :, 2] = gray
        del arr

        img_x_offset = (composite_width - grey_img.get_width()) // 2
        composite.blit(grey_img, (img_x_offset, 0))

        # Draw name bar at bottom
        pygame.draw.rect(composite, name_bar_color,
                         (0, img.get_height(), composite_width, name_bar_height))
        name_x_offset = (composite_width - name_surface.get_width()) // 2
        name_y_offset = img.get_height() + (name_bar_height - name_surface.get_height()) // 2
        composite.blit(name_surface, (name_x_offset, name_y_offset))

        # Add indicators
        stat_width = scaled(UILayout.INDICATOR_HP_WIDTH)
        stat_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
        stat_y = img.get_height() - stat_height - scaled(UILayout.INDICATOR_GAP)
        move_x = composite_width - stat_width - scaled(UILayout.INDICATOR_MARGIN)
        ind_margin = scaled(UILayout.INDICATOR_MARGIN)

        # HP indicator
        pygame.draw.rect(composite, (25, 85, 25), (ind_margin, stat_y, stat_width, stat_height))
        pygame.draw.rect(composite, (50, 130, 50), (ind_margin, stat_y, stat_width, stat_height), 1)
        hp_text = f"{card.curr_life}/{card.life}"
        hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
        composite.blit(hp_surface, (ind_margin + (stat_width - hp_surface.get_width()) // 2,
                                   stat_y + (stat_height - hp_surface.get_height()) // 2))

        # Move indicator
        pygame.draw.rect(composite, (120, 40, 40), (move_x, stat_y, stat_width, stat_height))
        pygame.draw.rect(composite, (180, 80, 80), (move_x, stat_y, stat_width, stat_height), 1)
        move_text = f"{card.curr_move}/{card.move}"
        move_surface = self.font_indicator.render(move_text, True, COLOR_TEXT)
        composite.blit(move_surface, (move_x + (stat_width - move_surface.get_width()) // 2,
                                     stat_y + (stat_height - move_surface.get_height()) // 2))

        # Counter indicator
        if card.counters > 0:
            counter_size = scaled(UILayout.COUNTER_SIZE)
            counter_x = composite_width - counter_size - scaled(UILayout.INDICATOR_GAP)
            counter_y = scaled(UILayout.INDICATOR_GAP)
            pygame.draw.circle(composite, (50, 100, 200),
                               (counter_x + counter_size // 2, counter_y + counter_size // 2),
                               counter_size // 2)
            pygame.draw.circle(composite, (100, 150, 255),
                               (counter_x + counter_size // 2, counter_y + counter_size // 2),
                               counter_size // 2, 2)
            counter_text = self.font_small.render(str(card.counters), True, (255, 255, 255))
            composite.blit(counter_text, (counter_x + (counter_size - counter_text.get_width()) // 2,
                                          counter_y + (counter_size - counter_text.get_height()) // 2))

        # Formation indicator
        if card.in_formation:
            badge_size = scaled(UILayout.FORMATION_SIZE)
            badge_x = scaled(UILayout.INDICATOR_GAP)
            badge_y = scaled(UILayout.INDICATOR_GAP)
            pygame.draw.rect(composite, (180, 150, 50), (badge_x, badge_y, badge_size, badge_size))
            pygame.draw.rect(composite, (255, 220, 100), (badge_x, badge_y, badge_size, badge_size), 1)
            formation_text = self.font_small.render("С", True, (255, 255, 255))
            composite.blit(formation_text, (badge_x + (badge_size - formation_text.get_width()) // 2,
                                            badge_y + (badge_size - formation_text.get_height()) // 2))

        # Armor indicator
        total_armor = card.armor_remaining + card.formation_armor_remaining
        if card.armor > 0 or card.formation_armor_remaining > 0:
            armor_size = scaled(UILayout.ARMOR_SIZE)
            armor_x = scaled(UILayout.INDICATOR_GAP)
            armor_y = stat_y - armor_size - scaled(UILayout.INDICATOR_GAP)
            armor_color = (100, 100, 120) if total_armor > 0 else (60, 60, 70)
            pygame.draw.rect(composite, armor_color, (armor_x, armor_y, armor_size, armor_size))
            pygame.draw.rect(composite, (180, 180, 200), (armor_x, armor_y, armor_size, armor_size), 1)
            armor_text = self.font_small.render(str(total_armor), True, (255, 255, 255))
            composite.blit(armor_text, (armor_x + (armor_size - armor_text.get_width()) // 2,
                                        armor_y + (armor_size - armor_text.get_height()) // 2))

        # Rotate 90 degrees clockwise
        rotated = pygame.transform.rotate(composite, -90)

        rot_x = card_rect.x + (card_rect.width - rotated.get_width()) // 2
        rot_y = card_rect.y + (card_rect.height - rotated.get_height()) // 2
        self.screen.blit(rotated, (rot_x, rot_y))

    def _draw_normal_card(self, card: 'Card', card_rect: pygame.Rect, img: pygame.Surface,
                          img_filename: str, name_bar_height: int, name_bar_y: int,
                          name_bar_color: tuple, name_surface: pygame.Surface):
        """Draw a non-tapped card normally."""
        img_clip = pygame.Rect(card_rect.x, card_rect.y, card_rect.width,
                               card_rect.height - name_bar_height)
        self.screen.set_clip(img_clip)

        img_x = card_rect.x + (card_rect.width - img.get_width()) // 2
        img_y = card_rect.y
        self.screen.blit(img, (img_x, img_y))

        self.screen.set_clip(None)

        # Draw name bar
        name_bar_rect = pygame.Rect(card_rect.x, name_bar_y, CARD_WIDTH, name_bar_height)
        pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)

        name_x = card_rect.x + (CARD_WIDTH - name_surface.get_width()) // 2
        name_y = name_bar_y + (name_bar_height - name_surface.get_height()) // 2
        self.screen.blit(name_surface, (name_x, name_y))

    def _draw_card_stats(self, card: 'Card', card_rect: pygame.Rect,
                         name_bar_height: int, name_bar_y: int):
        """Draw HP and Move indicators for non-tapped cards."""
        stat_width = scaled(UILayout.INDICATOR_HP_WIDTH)
        stat_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
        ind_margin = scaled(UILayout.INDICATOR_MARGIN)
        ind_gap = scaled(UILayout.INDICATOR_GAP)
        stat_y = name_bar_y - stat_height - ind_gap

        # HP on green background
        hp_bg_rect = pygame.Rect(card_rect.x + ind_margin, stat_y, stat_width, stat_height)
        pygame.draw.rect(self.screen, (25, 85, 25), hp_bg_rect)
        pygame.draw.rect(self.screen, (50, 130, 50), hp_bg_rect, 1)
        hp_text = f"{card.curr_life}/{card.life}"
        hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
        hp_text_x = hp_bg_rect.x + (stat_width - hp_surface.get_width()) // 2
        hp_text_y = hp_bg_rect.y + (stat_height - hp_surface.get_height()) // 2
        self.screen.blit(hp_surface, (hp_text_x, hp_text_y))

        # Move on red background
        move_bg_rect = pygame.Rect(card_rect.x + CARD_WIDTH - stat_width - ind_margin,
                                   stat_y, stat_width, stat_height)
        pygame.draw.rect(self.screen, (120, 40, 40), move_bg_rect)
        pygame.draw.rect(self.screen, (180, 80, 80), move_bg_rect, 1)
        move_text = f"{card.curr_move}/{card.move}"
        move_surface = self.font_indicator.render(move_text, True, COLOR_TEXT)
        move_text_x = move_bg_rect.x + (stat_width - move_surface.get_width()) // 2
        move_text_y = move_bg_rect.y + (stat_height - move_surface.get_height()) // 2
        self.screen.blit(move_surface, (move_text_x, move_text_y))

    def _draw_webbed_indicator(self, card: 'Card', card_rect: pygame.Rect):
        """Draw webbed status overlay."""
        web_surface = pygame.Surface((card_rect.width, card_rect.height), pygame.SRCALPHA)
        web_surface.fill((255, 255, 255, 80))

        for i in range(-card_rect.height, card_rect.width, 12):
            pygame.draw.line(web_surface, (200, 200, 200, 150),
                             (i, 0), (i + card_rect.height, card_rect.height), 2)
            pygame.draw.line(web_surface, (200, 200, 200, 150),
                             (i + card_rect.height, 0), (i, card_rect.height), 2)

        self.screen.blit(web_surface, card_rect.topleft)

        web_text = self.font_small.render("ПАУТИНА", True, (255, 255, 255))
        web_bg = pygame.Rect(card_rect.centerx - web_text.get_width() // 2 - 2,
                             card_rect.y + 5, web_text.get_width() + 4, 14)
        pygame.draw.rect(self.screen, (100, 100, 100, 200), web_bg)
        self.screen.blit(web_text, (web_bg.x + 2, web_bg.y))

    def _draw_counter_indicator(self, card: 'Card', card_rect: pygame.Rect):
        """Draw counter/token indicator."""
        counter_size = scaled(UILayout.COUNTER_SIZE)
        ind_gap = scaled(UILayout.INDICATOR_GAP)
        counter_x = card_rect.x + CARD_WIDTH - counter_size - ind_gap
        counter_y = card_rect.y + ind_gap

        pygame.draw.circle(self.screen, (50, 100, 200),
                           (counter_x + counter_size // 2, counter_y + counter_size // 2),
                           counter_size // 2)
        pygame.draw.circle(self.screen, (100, 150, 255),
                           (counter_x + counter_size // 2, counter_y + counter_size // 2),
                           counter_size // 2, 2)
        counter_text = self.font_small.render(str(card.counters), True, (255, 255, 255))
        text_x = counter_x + (counter_size - counter_text.get_width()) // 2
        text_y = counter_y + (counter_size - counter_text.get_height()) // 2
        self.screen.blit(counter_text, (text_x, text_y))

    def _draw_formation_indicator(self, card: 'Card', card_rect: pygame.Rect):
        """Draw formation status indicator."""
        badge_size = scaled(UILayout.FORMATION_SIZE)
        ind_gap = scaled(UILayout.INDICATOR_GAP)
        badge_x = card_rect.x + ind_gap
        badge_y = card_rect.y + ind_gap

        pygame.draw.rect(self.screen, (180, 150, 50),
                         (badge_x, badge_y, badge_size, badge_size))
        pygame.draw.rect(self.screen, (255, 220, 100),
                         (badge_x, badge_y, badge_size, badge_size), 1)
        formation_text = self.font_small.render("С", True, (255, 255, 255))
        text_x = badge_x + (badge_size - formation_text.get_width()) // 2
        text_y = badge_y + (badge_size - formation_text.get_height()) // 2
        self.screen.blit(formation_text, (text_x, text_y))

    def _draw_armor_indicator(self, card: 'Card', card_rect: pygame.Rect, name_bar_height: int):
        """Draw armor indicator."""
        total_armor = card.armor_remaining + card.formation_armor_remaining
        if card.armor > 0 or card.formation_armor_remaining > 0:
            armor_size = scaled(UILayout.ARMOR_SIZE)
            ind_gap = scaled(UILayout.INDICATOR_GAP)
            stat_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
            armor_x = card_rect.x + ind_gap
            armor_y = card_rect.y + CARD_HEIGHT - name_bar_height - stat_height - armor_size - ind_gap * 2

            armor_color = (100, 100, 120) if total_armor > 0 else (60, 60, 70)
            pygame.draw.rect(self.screen, armor_color,
                             (armor_x, armor_y, armor_size, armor_size))
            pygame.draw.rect(self.screen, (180, 180, 200),
                             (armor_x, armor_y, armor_size, armor_size), 1)
            armor_text = self.font_small.render(str(total_armor), True, (255, 255, 255))
            text_x = armor_x + (armor_size - armor_text.get_width()) // 2
            text_y = armor_y + (armor_size - armor_text.get_height()) // 2
            self.screen.blit(armor_text, (text_x, text_y))

    def draw_cards(self, game: 'Game'):
        """Draw all cards on the board (including flying zones)."""
        import math
        from ..board import Board

        glow_intensity = 0.0
        glowing_card_ids = set()
        defender_card_ids = set()

        if game.awaiting_priority and game.priority_player == self.viewing_player:
            glow_intensity = 0.6 + 0.4 * abs(math.sin(self.priority_glow_timer))
            for card, ability in game.get_legal_instants(game.priority_player):
                glowing_card_ids.add(card.id)

        if game.has_forced_attack and game.current_player == self.viewing_player:
            glow_intensity = 0.6 + 0.4 * abs(math.sin(self.priority_glow_timer))
            for card in game.board.get_all_cards(self.viewing_player):
                if game.get_forced_attacker_card(card) is not None:
                    glowing_card_ids.add(card.id)

        if game.awaiting_defender and game.interaction:
            if game.interaction.acting_player == self.viewing_player:
                glow_intensity = 0.6 + 0.4 * abs(math.sin(self.priority_glow_timer))
                for card_id in game.interaction.valid_card_ids:
                    defender_card_ids.add(card_id)

        # Draw main board cards
        for pos in range(BOARD_ROWS * BOARD_COLS):
            card = game.board.get_card(pos)
            if card:
                x, y = self.pos_to_screen(pos)
                x_draw, y_draw = self.get_card_draw_position(card.id, x, y)
                selected = (self._ui.selected_card and self._ui.selected_card.id == card.id)

                card_glow = 0.0
                card_glow_color = None
                if card.id in glowing_card_ids:
                    card_glow = glow_intensity
                elif card.id in defender_card_ids:
                    card_glow = glow_intensity
                    card_glow_color = (255, 80, 80)

                self.draw_card(card, x_draw, y_draw, selected, card_glow, game, card_glow_color)

        # Flying cards are drawn in draw_side_panels()

    def draw_card_thumbnail(self, card: 'Card', x: int, y: int, size: int,
                            game: 'Game' = None, is_graveyard: bool = False):
        """Draw a small card thumbnail for side panels."""
        card_rect = pygame.Rect(x, y, size, size)

        # Check if card should be shown as hidden (face-down enemy card)
        is_hidden = card.face_down and card.player != self.viewing_player
        if is_hidden:
            self._draw_face_down_thumbnail(card_rect, size)
            return

        if card.player == self.viewing_player:
            border_color = (180, 150, 50)
        else:
            border_color = (70, 100, 160)

        pygame.draw.rect(self.screen, border_color, card_rect)

        name_bar_height = max(12, size // 7)

        if card.player == self.viewing_player:
            name_bar_color = (180, 160, 60)
            name_text_color = (40, 30, 0)
        else:
            name_bar_color = (60, 80, 140)
            name_text_color = (220, 230, 255)

        img_filename = get_card_image(card.name)
        if img_filename and img_filename in self.card_images:
            img = self.card_images[img_filename]

            img_area_height = size - name_bar_height - 4
            img_area_width = size - 4

            img_scaled = pygame.transform.smoothscale(img, (img_area_width, img_area_height))

            if card.tapped:
                # Grayscale for tapped
                arr = pygame.surfarray.pixels3d(img_scaled)
                gray = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype('uint8')
                arr[:, :, 0] = gray
                arr[:, :, 1] = gray
                arr[:, :, 2] = gray
                del arr

                composite = pygame.Surface((img_area_width, img_area_height + name_bar_height), pygame.SRCALPHA)
                composite.blit(img_scaled, (0, 0))

                if not is_graveyard:
                    ind_width = scaled(UILayout.INDICATOR_HP_WIDTH)
                    ind_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
                    ind_margin = scaled(UILayout.INDICATOR_MARGIN)
                    ind_gap = scaled(UILayout.INDICATOR_GAP)
                    hp_y = img_area_height - ind_height - ind_gap
                    hp_bg_rect = pygame.Rect(ind_margin, hp_y, ind_width, ind_height)
                    pygame.draw.rect(composite, (25, 85, 25), hp_bg_rect)
                    pygame.draw.rect(composite, (50, 130, 50), hp_bg_rect, 1)
                    hp_text = f"{card.curr_life}/{card.life}"
                    hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
                    hp_text_x = hp_bg_rect.x + (ind_width - hp_surface.get_width()) // 2
                    hp_text_y = hp_bg_rect.y + (ind_height - hp_surface.get_height()) // 2
                    composite.blit(hp_surface, (hp_text_x, hp_text_y))

                name_bar_rect_local = pygame.Rect(0, img_area_height, img_area_width, name_bar_height)
                pygame.draw.rect(composite, name_bar_color, name_bar_rect_local)
                max_len = size // 10
                display_name = card.name[:max_len] + '..' if len(card.name) > max_len else card.name
                name_surface = self.font_small.render(display_name, True, name_text_color)
                name_x = (img_area_width - name_surface.get_width()) // 2
                name_y = img_area_height + (name_bar_height - name_surface.get_height()) // 2
                composite.blit(name_surface, (name_x, name_y))

                rotated = pygame.transform.rotate(composite, -90)
                rot_x = x + 2 + (img_area_width - rotated.get_width()) // 2
                rot_y = y + 2 + (img_area_height + name_bar_height - rotated.get_height()) // 2
                self.screen.blit(rotated, (rot_x, rot_y))
            else:
                self.screen.blit(img_scaled, (x + 2, y + 2))

                name_bar_rect = pygame.Rect(x + 2, y + size - name_bar_height - 2, img_area_width, name_bar_height)
                pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)

                max_len = size // 10
                display_name = card.name[:max_len] + '..' if len(card.name) > max_len else card.name
                name_surface = self.font_small.render(display_name, True, name_text_color)
                name_x = name_bar_rect.x + (name_bar_rect.width - name_surface.get_width()) // 2
                name_y = name_bar_rect.y + (name_bar_rect.height - name_surface.get_height()) // 2
                self.screen.blit(name_surface, (name_x, name_y))
        else:
            pygame.draw.rect(self.screen, (40, 40, 50), card_rect.inflate(-4, -4))
            name_bar_rect = pygame.Rect(x + 2, y + size - name_bar_height - 2, size - 4, name_bar_height)
            pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)
            max_len = UILayout.CARD_NAME_MAX_LEN
            display_name = card.name[:max_len] + '..' if len(card.name) > max_len else card.name
            name_surface = self.font_small.render(display_name, True, name_text_color)
            self.screen.blit(name_surface, (x + 4, y + size - name_bar_height))

        if not is_graveyard and not card.tapped:
            ind_width = scaled(UILayout.INDICATOR_HP_WIDTH)
            ind_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
            ind_margin = scaled(UILayout.INDICATOR_MARGIN)
            ind_gap = scaled(UILayout.INDICATOR_GAP)
            stat_y = y + size - name_bar_height - ind_height - ind_gap - 2

            hp_bg_rect = pygame.Rect(x + ind_margin, stat_y, ind_width, ind_height)
            pygame.draw.rect(self.screen, (25, 85, 25), hp_bg_rect)
            pygame.draw.rect(self.screen, (50, 130, 50), hp_bg_rect, 1)
            hp_text = f"{card.curr_life}/{card.life}"
            hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
            hp_text_x = hp_bg_rect.x + (ind_width - hp_surface.get_width()) // 2
            hp_text_y = hp_bg_rect.y + (ind_height - hp_surface.get_height()) // 2
            self.screen.blit(hp_surface, (hp_text_x, hp_text_y))

    def get_card_at_screen_pos(self, game: 'Game', mouse_x: int, mouse_y: int) -> Optional['Card']:
        """Get the card at a screen position (main board or flying zones)."""
        # Check main board first
        pos = self.screen_to_pos(mouse_x, mouse_y)
        if pos is not None:
            return game.board.get_card(pos)

        # Check flying zones
        flying_pos = self.get_flying_slot_at_pos(mouse_x, mouse_y, game)
        if flying_pos is not None:
            return game.board.get_card(flying_pos)

        return None

    def _draw_face_down_card(self, card_rect: pygame.Rect):
        """Draw a face-down card (cardback) for hidden enemy cards."""
        # Draw border
        pygame.draw.rect(self.screen, (70, 100, 160), card_rect)  # Blue for enemy

        # Draw cardback image if available
        if self.cardback_image:
            name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
            target_h = CARD_HEIGHT - name_bar_height
            img = pygame.transform.smoothscale(self.cardback_image, (CARD_WIDTH, target_h))
            img_x = card_rect.x + (card_rect.width - img.get_width()) // 2
            img_y = card_rect.y
            self.screen.blit(img, (img_x, img_y))

            # Draw "???" name bar
            name_bar_y = card_rect.y + CARD_HEIGHT - name_bar_height
            name_bar_rect = pygame.Rect(card_rect.x, name_bar_y, CARD_WIDTH, name_bar_height)
            pygame.draw.rect(self.screen, (60, 80, 140), name_bar_rect)

            name_surface = self.font_card_name.render("???", True, (220, 230, 255))
            name_x = card_rect.x + (CARD_WIDTH - name_surface.get_width()) // 2
            name_y = name_bar_y + (name_bar_height - name_surface.get_height()) // 2
            self.screen.blit(name_surface, (name_x, name_y))
        else:
            # Fallback if no cardback image - draw simple pattern
            pygame.draw.rect(self.screen, (40, 50, 80), card_rect.inflate(-4, -4))

            # Draw "?" text
            question = self.font_large.render("?", True, (100, 120, 180))
            q_x = card_rect.centerx - question.get_width() // 2
            q_y = card_rect.centery - question.get_height() // 2
            self.screen.blit(question, (q_x, q_y))

        # Border
        pygame.draw.rect(self.screen, COLOR_TEXT, card_rect, 1)

    def _draw_face_down_thumbnail(self, card_rect: pygame.Rect, size: int):
        """Draw a face-down card thumbnail for hidden enemy cards in side panels."""
        # Draw border
        pygame.draw.rect(self.screen, (70, 100, 160), card_rect)

        name_bar_height = max(12, size // 7)

        # Draw cardback image if available
        if self.cardback_image:
            img_area_height = size - name_bar_height - 4
            img_area_width = size - 4

            img = pygame.transform.smoothscale(self.cardback_image, (img_area_width, img_area_height))
            self.screen.blit(img, (card_rect.x + 2, card_rect.y + 2))

            # Draw "???" name bar
            name_bar_rect = pygame.Rect(card_rect.x + 2, card_rect.y + size - name_bar_height - 2,
                                        img_area_width, name_bar_height)
            pygame.draw.rect(self.screen, (60, 80, 140), name_bar_rect)

            name_surface = self.font_small.render("???", True, (220, 230, 255))
            name_x = name_bar_rect.x + (name_bar_rect.width - name_surface.get_width()) // 2
            name_y = name_bar_rect.y + (name_bar_rect.height - name_surface.get_height()) // 2
            self.screen.blit(name_surface, (name_x, name_y))
        else:
            # Fallback if no cardback image
            pygame.draw.rect(self.screen, (40, 50, 80), card_rect.inflate(-4, -4))

            # Draw "?" text
            question = self.font_small.render("?", True, (100, 120, 180))
            q_x = card_rect.centerx - question.get_width() // 2
            q_y = card_rect.centery - question.get_height() // 2
            self.screen.blit(question, (q_x, q_y))

        # Border
        pygame.draw.rect(self.screen, COLOR_TEXT, card_rect, 1)
