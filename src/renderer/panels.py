"""Side panels - flying zones and graveyards."""
import pygame
import math
from typing import Optional, List, TYPE_CHECKING

from ..constants import (
    COLOR_PLAYER1, COLOR_PLAYER2, COLOR_TEXT,
    scaled, UILayout
)

if TYPE_CHECKING:
    from ..game import Game
    from ..card import Card


class PanelsMixin:
    """Mixin for side panel rendering (flying zones, graveyards)."""

    def is_panel_expanded(self, panel_id: str) -> bool:
        """Check if a specific panel is expanded."""
        if panel_id == 'p1_flyers':
            return self.expanded_panel_p1 == 'flyers'
        elif panel_id == 'p1_grave':
            return self.expanded_panel_p1 == 'grave'
        elif panel_id == 'p2_flyers':
            return self.expanded_panel_p2 == 'flyers'
        elif panel_id == 'p2_grave':
            return self.expanded_panel_p2 == 'grave'
        return False

    def toggle_panel(self, panel_id: str):
        """Toggle a panel. Only one panel per player can be expanded."""
        if panel_id.startswith('p1'):
            panel_type = panel_id.replace('p1_', '')
            if self.expanded_panel_p1 == panel_type:
                self.expanded_panel_p1 = None
            else:
                self.expanded_panel_p1 = panel_type
        else:  # p2
            panel_type = panel_id.replace('p2_', '')
            if self.expanded_panel_p2 == panel_type:
                self.expanded_panel_p2 = None
            else:
                self.expanded_panel_p2 = panel_type

    def draw_side_panels(self, game: 'Game'):
        """Draw unified side panels for flyers and graveyards with card thumbnails."""
        from ..board import Board

        # Panel positions are fixed (physical screen locations)
        left_panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
        left_panel_y = scaled(UILayout.SIDE_PANEL_P2_Y)
        right_panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
        right_panel_y = scaled(UILayout.SIDE_PANEL_P1_Y)

        # Determine which content goes where based on viewing player
        if self.viewing_player == 2:
            left_flyers = game.board.flying_p1
            right_flyers = game.board.flying_p2
            left_graveyard = game.board.graveyard_p1
            right_graveyard = game.board.graveyard_p2
            left_label_flyers = "Летающие П1"
            right_label_flyers = "Летающие П2"
            left_label_grave = "Кладбище П1"
            right_label_grave = "Кладбище П2"
            left_color = COLOR_PLAYER1
            right_color = COLOR_PLAYER2
            left_flyer_panel = 'p1_flyers'
            right_flyer_panel = 'p2_flyers'
            left_grave_panel = 'p1_grave'
            right_grave_panel = 'p2_grave'
        else:
            left_flyers = game.board.flying_p2
            right_flyers = game.board.flying_p1
            left_graveyard = game.board.graveyard_p2
            right_graveyard = game.board.graveyard_p1
            left_label_flyers = "Летающие П2"
            right_label_flyers = "Летающие П1"
            left_label_grave = "Кладбище П2"
            right_label_grave = "Кладбище П1"
            left_color = COLOR_PLAYER2
            right_color = COLOR_PLAYER1
            left_flyer_panel = 'p2_flyers'
            right_flyer_panel = 'p1_flyers'
            left_grave_panel = 'p2_grave'
            right_grave_panel = 'p1_grave'

        # Auto-expand flying zones if they have flyers
        has_p1_flyers = any(c is not None for c in game.board.flying_p1)
        has_p2_flyers = any(c is not None for c in game.board.flying_p2)
        if has_p1_flyers and self.expanded_panel_p1 is None:
            self.expanded_panel_p1 = 'flyers'
        if has_p2_flyers and self.expanded_panel_p2 is None:
            self.expanded_panel_p2 = 'flyers'

        # Force-expand flying panel when there are flying targets to select
        needs_flying_selection = (
            game.awaiting_defender or
            game.awaiting_counter_shot or
            game.awaiting_movement_shot or
            game.awaiting_ability_target
        )
        if needs_flying_selection and game.interaction:
            valid_positions = game.interaction.valid_positions
            p1_flying_range = range(Board.FLYING_P1_START, Board.FLYING_P1_START + Board.FLYING_SLOTS)
            if any(pos in valid_positions for pos in p1_flying_range):
                self.expanded_panel_p1 = 'flyers'
            p2_flying_range = range(Board.FLYING_P2_START, Board.FLYING_P2_START + Board.FLYING_SLOTS)
            if any(pos in valid_positions for pos in p2_flying_range):
                self.expanded_panel_p2 = 'flyers'

        # Also expand when attack mode shows flying targets
        if self._ui.attack_mode and self._ui.valid_attacks:
            p1_flying_range = range(Board.FLYING_P1_START, Board.FLYING_P1_START + Board.FLYING_SLOTS)
            if any(pos in self._ui.valid_attacks for pos in p1_flying_range):
                self.expanded_panel_p1 = 'flyers'
            p2_flying_range = range(Board.FLYING_P2_START, Board.FLYING_P2_START + Board.FLYING_SLOTS)
            if any(pos in self._ui.valid_attacks for pos in p2_flying_range):
                self.expanded_panel_p2 = 'flyers'

        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        expanded_height = scaled(UILayout.SIDE_PANEL_EXPANDED_HEIGHT)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)

        self.side_panel_tab_rects = {}

        # ========== LEFT SIDE PANEL ==========
        left_flyers_expanded = self.is_panel_expanded(left_flyer_panel)
        left_flyers_rect = pygame.Rect(left_panel_x, left_panel_y, panel_width, tab_height)
        self.side_panel_tab_rects[left_flyer_panel] = left_flyers_rect

        left_bg = (80, 50, 50) if left_color == COLOR_PLAYER2 else (50, 60, 80)
        left_bg_dark = (50, 35, 35) if left_color == COLOR_PLAYER2 else (30, 40, 50)
        tab_color = left_bg if left_flyers_expanded else left_bg_dark
        pygame.draw.rect(self.screen, tab_color, left_flyers_rect)
        pygame.draw.rect(self.screen, left_color, left_flyers_rect, 2)

        flyer_count = sum(1 for c in left_flyers if c is not None)
        label = self.font_small.render(f"{left_label_flyers} ({flyer_count})", True, left_color)
        self.screen.blit(label, (left_panel_x + 5, left_panel_y + 5))

        # Expanded content for left flyers
        if left_flyers_expanded:
            content_y = left_panel_y + tab_height + spacing
            content_rect = pygame.Rect(left_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, left_bg_dark, content_rect)
            pygame.draw.rect(self.screen, left_color, content_rect, 1)

            # Check if there are death animations - keep cards at slot positions if so
            left_flyer_player = 1 if self.viewing_player == 2 else 2
            has_death_anim = self.has_flying_death_animation(left_flyer_player)
            if has_death_anim:
                # Preserve slot indices during death animation
                flyers = []
                slot_indices = []
                for i, c in enumerate(left_flyers):
                    if c is not None:
                        flyers.append(c)
                        slot_indices.append(i)
            else:
                flyers = [c for c in left_flyers if c is not None]
                slot_indices = None
            scroll = self.side_panel_scroll.get(left_flyer_panel, 0)
            self._draw_panel_cards(flyers, left_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, left_flyer_panel, slot_indices)

        # Left graveyard tab
        left_grave_y = left_panel_y + tab_height + spacing
        if left_flyers_expanded:
            left_grave_y += expanded_height + spacing
        left_grave_expanded = self.is_panel_expanded(left_grave_panel)
        left_grave_rect = pygame.Rect(left_panel_x, left_grave_y, panel_width, tab_height)
        self.side_panel_tab_rects[left_grave_panel] = left_grave_rect

        tab_color = left_bg if left_grave_expanded else left_bg_dark
        pygame.draw.rect(self.screen, tab_color, left_grave_rect)
        pygame.draw.rect(self.screen, left_color, left_grave_rect, 2)

        grave_count = len(left_graveyard)
        label = self.font_small.render(f"{left_label_grave} ({grave_count})", True, left_color)
        self.screen.blit(label, (left_panel_x + 5, left_grave_y + 5))

        # Expanded content for left graveyard
        if left_grave_expanded:
            content_y = left_grave_y + tab_height + spacing
            content_rect = pygame.Rect(left_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, left_bg_dark, content_rect)
            pygame.draw.rect(self.screen, left_color, content_rect, 1)

            grave_cards = list(reversed(left_graveyard))
            scroll = self.side_panel_scroll.get(left_grave_panel, 0)
            self._draw_panel_cards(grave_cards, left_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, left_grave_panel)

        # ========== RIGHT SIDE PANEL ==========
        right_flyers_expanded = self.is_panel_expanded(right_flyer_panel)
        right_flyers_rect = pygame.Rect(right_panel_x, right_panel_y, panel_width, tab_height)
        self.side_panel_tab_rects[right_flyer_panel] = right_flyers_rect

        right_bg = (80, 50, 50) if right_color == COLOR_PLAYER2 else (50, 60, 80)
        right_bg_dark = (50, 35, 35) if right_color == COLOR_PLAYER2 else (30, 40, 50)
        tab_color = right_bg if right_flyers_expanded else right_bg_dark
        pygame.draw.rect(self.screen, tab_color, right_flyers_rect)
        pygame.draw.rect(self.screen, right_color, right_flyers_rect, 2)

        flyer_count = sum(1 for c in right_flyers if c is not None)
        label = self.font_small.render(f"{right_label_flyers} ({flyer_count})", True, right_color)
        self.screen.blit(label, (right_panel_x + 5, right_panel_y + 5))

        # Expanded content for right flyers
        if right_flyers_expanded:
            content_y = right_panel_y + tab_height + spacing
            content_rect = pygame.Rect(right_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, right_bg_dark, content_rect)
            pygame.draw.rect(self.screen, right_color, content_rect, 1)

            # Check if there are death animations - keep cards at slot positions if so
            right_flyer_player = 2 if self.viewing_player == 2 else 1
            has_death_anim = self.has_flying_death_animation(right_flyer_player)
            if has_death_anim:
                # Preserve slot indices during death animation
                flyers = []
                slot_indices = []
                for i, c in enumerate(right_flyers):
                    if c is not None:
                        flyers.append(c)
                        slot_indices.append(i)
            else:
                flyers = [c for c in right_flyers if c is not None]
                slot_indices = None
            scroll = self.side_panel_scroll.get(right_flyer_panel, 0)
            self._draw_panel_cards(flyers, right_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, right_flyer_panel, slot_indices)

        # Right graveyard tab
        right_grave_y = right_panel_y + tab_height + spacing
        if right_flyers_expanded:
            right_grave_y += expanded_height + spacing
        right_grave_expanded = self.is_panel_expanded(right_grave_panel)
        right_grave_rect = pygame.Rect(right_panel_x, right_grave_y, panel_width, tab_height)
        self.side_panel_tab_rects[right_grave_panel] = right_grave_rect

        tab_color = right_bg if right_grave_expanded else right_bg_dark
        pygame.draw.rect(self.screen, tab_color, right_grave_rect)
        pygame.draw.rect(self.screen, right_color, right_grave_rect, 2)

        grave_count = len(right_graveyard)
        label = self.font_small.render(f"{right_label_grave} ({grave_count})", True, right_color)
        self.screen.blit(label, (right_panel_x + 5, right_grave_y + 5))

        # Expanded content for right graveyard
        if right_grave_expanded:
            content_y = right_grave_y + tab_height + spacing
            content_rect = pygame.Rect(right_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, right_bg_dark, content_rect)
            pygame.draw.rect(self.screen, right_color, content_rect, 1)

            grave_cards = list(reversed(right_graveyard))
            scroll = self.side_panel_scroll.get(right_grave_panel, 0)
            self._draw_panel_cards(grave_cards, right_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, right_grave_panel)

    def _draw_panel_cards(self, cards: List['Card'], panel_x: int, content_y: int,
                          panel_width: int, panel_height: int, card_size: int,
                          card_spacing: int, scroll: int, game: 'Game', panel_id: str,
                          slot_indices: List[int] = None):
        """Draw cards in a side panel with scrolling support.

        Args:
            slot_indices: If provided, use these indices for positioning instead of
                         enumeration indices. Used during death animations to keep
                         surviving cards at their original positions.
        """
        if not cards:
            empty_text = self.font_small.render("Пусто", True, (100, 100, 100))
            self.screen.blit(empty_text, (panel_x + 10, content_y + 10))
            return

        # Calculate total content height based on max slot index if using slot positions
        if slot_indices:
            max_slot = max(slot_indices) if slot_indices else 0
            total_height = (max_slot + 1) * (card_size + card_spacing) - card_spacing
        else:
            total_height = len(cards) * (card_size + card_spacing) - card_spacing
        visible_height = panel_height - 10

        # Clamp scroll
        max_scroll = max(0, total_height - visible_height)
        scroll = max(0, min(scroll, max_scroll))
        self.side_panel_scroll[panel_id] = scroll

        # Create clipping rect
        clip_rect = pygame.Rect(panel_x + 2, content_y + 2, panel_width - 4, panel_height - 4)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)

        # Draw cards
        card_x = panel_x + (panel_width - card_size) // 2
        is_graveyard = 'grave' in panel_id
        is_flyers = 'flyers' in panel_id

        # Collect highlighted positions for flying cards
        highlighted_positions = set()
        highlighted_card_ids = set()
        highlight_type = None
        if is_flyers and game:
            is_acting = (game.interaction and game.interaction.acting_player == self.viewing_player)

            if game.awaiting_defender and game.interaction and is_acting:
                highlighted_card_ids = set(game.interaction.valid_card_ids)
                highlight_type = 'defender'
            elif game.awaiting_counter_shot and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'counter_shot'
            elif game.awaiting_movement_shot and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'counter_shot'
            elif game.awaiting_ability_target and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'ability'
            elif game.awaiting_valhalla and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'valhalla'
            elif game.current_player == self.viewing_player:
                highlighted_positions = set(self._ui.valid_attacks)
                highlight_type = 'attack'

        for i, card in enumerate(cards):
            # Use slot index for positioning if provided, otherwise use enumeration index
            visual_idx = slot_indices[i] if slot_indices else i
            card_y = content_y + 5 + visual_idx * (card_size + card_spacing) - scroll
            # Only draw if visible
            if card_y + card_size > content_y and card_y < content_y + panel_height:
                self.draw_card_thumbnail(card, card_x, card_y, card_size, game, is_graveyard)

                # Draw selection border for selected flying card (gold)
                # Compare by ID since network games create new Card objects on sync
                if is_flyers and game and self._ui.selected_card and self._ui.selected_card.id == card.id:
                    select_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                    pygame.draw.rect(self.screen, (255, 215, 0), select_rect, 3)

                # Draw highlight as colored border
                is_highlighted = (
                    (is_flyers and card.position in highlighted_positions) or
                    (is_flyers and card.id in highlighted_card_ids)
                )
                if is_highlighted:
                    border_width = 4
                    if highlight_type == 'defender':
                        glow_intensity = 0.5 + 0.5 * math.sin(self.priority_glow_timer)
                        border_color = (255, int(100 * glow_intensity), int(100 * glow_intensity))
                    elif highlight_type == 'attack':
                        border_color = (255, 100, 100)
                    elif highlight_type == 'ability':
                        border_color = (180, 100, 220)
                    elif highlight_type == 'valhalla':
                        border_color = (255, 200, 100)
                    elif highlight_type == 'counter_shot':
                        border_color = (255, 150, 50)
                    else:
                        border_color = (200, 200, 200)
                    highlight_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                    pygame.draw.rect(self.screen, border_color, highlight_rect, border_width)

                # Valhalla indicator for graveyard cards
                if is_graveyard:
                    has_valhalla = any(aid.startswith("valhalla") for aid in card.stats.ability_ids)
                    if has_valhalla and card.killed_by_enemy:
                        valhalla_text = self.font_small.render("[V]", True, (255, 200, 100))
                        self.screen.blit(valhalla_text, (card_x + 4, card_y + card_size - 30))

        # Restore clip
        self.screen.set_clip(old_clip)

        # Draw scroll indicators if needed
        if max_scroll > 0:
            if scroll > 0:
                pygame.draw.polygon(self.screen, (180, 180, 180),
                                    [(panel_x + panel_width - 15, content_y + 8),
                                     (panel_x + panel_width - 10, content_y + 3),
                                     (panel_x + panel_width - 5, content_y + 8)])
            if scroll < max_scroll:
                pygame.draw.polygon(self.screen, (180, 180, 180),
                                    [(panel_x + panel_width - 15, content_y + panel_height - 8),
                                     (panel_x + panel_width - 10, content_y + panel_height - 3),
                                     (panel_x + panel_width - 5, content_y + panel_height - 8)])

    def scroll_side_panel(self, direction: int, panel_id: str = None):
        """Scroll a side panel. If panel_id not specified, scrolls the expanded panel for each player."""
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        scroll_amount = card_size // 2

        if panel_id:
            self.side_panel_scroll[panel_id] = max(
                0, self.side_panel_scroll.get(panel_id, 0) + direction * scroll_amount
            )
        else:
            if self.expanded_panel_p1:
                p1_panel = f'p1_{self.expanded_panel_p1}'
                self.side_panel_scroll[p1_panel] = max(
                    0, self.side_panel_scroll.get(p1_panel, 0) + direction * scroll_amount
                )
            if self.expanded_panel_p2:
                p2_panel = f'p2_{self.expanded_panel_p2}'
                self.side_panel_scroll[p2_panel] = max(
                    0, self.side_panel_scroll.get(p2_panel, 0) + direction * scroll_amount
                )

    def handle_side_panel_click(self, mouse_x: int, mouse_y: int) -> bool:
        """Handle click on side panel tabs. Returns True if handled."""
        for panel_id, rect in self.side_panel_tab_rects.items():
            if rect.collidepoint(mouse_x, mouse_y):
                self.toggle_panel(panel_id)
                return True
        return False

    def get_flying_slot_at_pos(self, mouse_x: int, mouse_y: int, game: 'Game') -> Optional[int]:
        """Check if mouse is over a flying slot and return the position (30-39).

        This mirrors the exact logic used in draw_side_panels to ensure pixel-perfect
        matching between rendered cards and click detection.
        """
        from ..board import Board

        # Use the exact same panel layout logic as draw_side_panels
        left_panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
        left_panel_y = scaled(UILayout.SIDE_PANEL_P2_Y)
        right_panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
        right_panel_y = scaled(UILayout.SIDE_PANEL_P1_Y)

        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        expanded_height = scaled(UILayout.SIDE_PANEL_EXPANDED_HEIGHT)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)

        # Determine which content goes where based on viewing player
        # (same logic as draw_side_panels)
        if self.viewing_player == 2:
            left_flyers = game.board.flying_p1
            right_flyers = game.board.flying_p2
            left_flyer_panel = 'p1_flyers'
            right_flyer_panel = 'p2_flyers'
            left_base_pos = Board.FLYING_P1_START
            right_base_pos = Board.FLYING_P2_START
        else:
            left_flyers = game.board.flying_p2
            right_flyers = game.board.flying_p1
            left_flyer_panel = 'p2_flyers'
            right_flyer_panel = 'p1_flyers'
            left_base_pos = Board.FLYING_P2_START
            right_base_pos = Board.FLYING_P1_START

        # Check LEFT panel flyers
        if self.is_panel_expanded(left_flyer_panel):
            content_y = left_panel_y + tab_height + spacing
            scroll = self.side_panel_scroll.get(left_flyer_panel, 0)
            card_x = left_panel_x + (panel_width - card_size) // 2

            # Clip rect matching the drawing code (ensures clicks on scrolled-out portions don't register)
            clip_rect = pygame.Rect(left_panel_x + 2, content_y + 2, panel_width - 4, expanded_height - 4)

            # First check if mouse is even within the panel area
            if clip_rect.collidepoint(mouse_x, mouse_y):
                # Check if there are death animations - use slot positions if so
                left_flyer_player = 1 if self.viewing_player == 2 else 2
                use_slot_positions = self.has_flying_death_animation(left_flyer_player)

                # Get cards with their original slot indices
                cards_with_slots = [(i, c) for i, c in enumerate(left_flyers) if c is not None]
                for draw_idx, (slot_idx, card) in enumerate(cards_with_slots):
                    # Use slot index for positioning during death animations
                    visual_idx = slot_idx if use_slot_positions else draw_idx
                    card_y = content_y + 5 + visual_idx * (card_size + card_spacing) - scroll
                    # Exact same visibility check as _draw_panel_cards
                    if card_y + card_size > content_y and card_y < content_y + expanded_height:
                        slot_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                        # Clip the slot rect to the visible area
                        visible_rect = slot_rect.clip(clip_rect)
                        if visible_rect.collidepoint(mouse_x, mouse_y):
                            return left_base_pos + slot_idx

        # Check RIGHT panel flyers
        if self.is_panel_expanded(right_flyer_panel):
            content_y = right_panel_y + tab_height + spacing
            scroll = self.side_panel_scroll.get(right_flyer_panel, 0)
            card_x = right_panel_x + (panel_width - card_size) // 2

            # Clip rect matching the drawing code
            clip_rect = pygame.Rect(right_panel_x + 2, content_y + 2, panel_width - 4, expanded_height - 4)

            # First check if mouse is even within the panel area
            if clip_rect.collidepoint(mouse_x, mouse_y):
                # Check if there are death animations - use slot positions if so
                right_flyer_player = 2 if self.viewing_player == 2 else 1
                use_slot_positions = self.has_flying_death_animation(right_flyer_player)

                # Get cards with their original slot indices
                cards_with_slots = [(i, c) for i, c in enumerate(right_flyers) if c is not None]
                for draw_idx, (slot_idx, card) in enumerate(cards_with_slots):
                    # Use slot index for positioning during death animations
                    visual_idx = slot_idx if use_slot_positions else draw_idx
                    card_y = content_y + 5 + visual_idx * (card_size + card_spacing) - scroll
                    # Exact same visibility check as _draw_panel_cards
                    if card_y + card_size > content_y and card_y < content_y + expanded_height:
                        slot_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                        # Clip the slot rect to the visible area
                        visible_rect = slot_rect.clip(clip_rect)
                        if visible_rect.collidepoint(mouse_x, mouse_y):
                            return right_base_pos + slot_idx

        return None

    def get_graveyard_card_at_pos(self, game: 'Game', mouse_x: int, mouse_y: int) -> Optional['Card']:
        """Check if mouse is over a graveyard card and return the card.

        Only returns cards that are visible within the panel bounds.
        """
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        expanded_height = scaled(UILayout.SIDE_PANEL_EXPANDED_HEIGHT)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)
        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)

        # Check P1 graveyard
        if self.is_panel_expanded('p1_grave'):
            if self.viewing_player == 2:
                panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                base_y = scaled(UILayout.SIDE_PANEL_P2_Y)
                graveyard = game.board.graveyard_p1
            else:
                panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                base_y = scaled(UILayout.SIDE_PANEL_P1_Y)
                graveyard = game.board.graveyard_p1

            # Calculate graveyard content position (after flyers tab and possibly expanded flyers)
            grave_y = base_y + tab_height + spacing
            if self.is_panel_expanded('p1_flyers'):
                grave_y += expanded_height + spacing
            content_y = grave_y + tab_height + spacing
            panel_bottom = content_y + expanded_height

            scroll = self.side_panel_scroll.get('p1_grave', 0)
            card_x = panel_x + (panel_width - card_size) // 2
            grave_cards = list(reversed(graveyard))

            for i, card in enumerate(grave_cards):
                card_y = content_y + 5 + i * (card_size + card_spacing) - scroll
                # Only check if card is visible within panel bounds
                if card_y + card_size > content_y and card_y < panel_bottom:
                    card_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                    if card_rect.collidepoint(mouse_x, mouse_y):
                        return card

        # Check P2 graveyard
        if self.is_panel_expanded('p2_grave'):
            if self.viewing_player == 2:
                panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                base_y = scaled(UILayout.SIDE_PANEL_P1_Y)
                graveyard = game.board.graveyard_p2
            else:
                panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                base_y = scaled(UILayout.SIDE_PANEL_P2_Y)
                graveyard = game.board.graveyard_p2

            # Calculate graveyard content position
            grave_y = base_y + tab_height + spacing
            if self.is_panel_expanded('p2_flyers'):
                grave_y += expanded_height + spacing
            content_y = grave_y + tab_height + spacing
            panel_bottom = content_y + expanded_height

            scroll = self.side_panel_scroll.get('p2_grave', 0)
            card_x = panel_x + (panel_width - card_size) // 2
            grave_cards = list(reversed(graveyard))

            for i, card in enumerate(grave_cards):
                card_y = content_y + 5 + i * (card_size + card_spacing) - scroll
                # Only check if card is visible within panel bounds
                if card_y + card_size > content_y and card_y < panel_bottom:
                    card_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                    if card_rect.collidepoint(mouse_x, mouse_y):
                        return card

        return None
