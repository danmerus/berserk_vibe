"""Menu screens - main menu, settings, pause menu."""
import pygame
from typing import Optional, List, Tuple, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    COLOR_BG, COLOR_TEXT,
    scaled, UI_SCALE, UILayout
)

if TYPE_CHECKING:
    pass


class MenusMixin:
    """Mixin for menu screen rendering."""

    def draw_menu(self):
        """Draw the main menu screen with native resolution text for crisp rendering."""
        self.menu_buttons = []

        # Clear screen with background image or fallback to solid color
        if hasattr(self, 'menu_background') and self.menu_background is not None:
            self.screen.blit(self.menu_background, (0, 0))
        else:
            self.screen.fill(COLOR_BG)

        # Scale and blit background to window first
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        # Now draw text and buttons directly to window at native resolution
        title_font = self.get_native_font('title')
        title = title_font.render("БЕРСЕРК-vibe", True, (247, 211, 82))
        game_area_width = int(self.BASE_WIDTH * self.scale) if self.scale > 0 else self.BASE_WIDTH
        title_win_x = self.offset_x + game_area_width // 2 - title.get_width() // 2
        _, title_win_y = self.game_to_window_coords(0, int(80 * UI_SCALE))
        self.window.blit(title, (title_win_x, title_win_y))

        # Menu buttons
        buttons = [
            ("test_game", "Тестовая игра", True),
            ("vs_ai", "Развлечения с ботами", True),
            ("local_game", "Hotseat", True),
            ("network_game", "Игра по сети", True),
            ("deck_builder", "Создание колоды", True),
            ("settings", "Настройки", True),
            ("exit", "Выход", True),
        ]

        btn_width = int(280 * UI_SCALE)
        btn_height = int(45 * UI_SCALE)
        btn_spacing = int(15 * UI_SCALE)
        start_y = int(220 * UI_SCALE)

        btn_font = self.get_native_font('medium')

        for i, (btn_id, btn_text, is_active) in enumerate(buttons):
            btn_x = (WINDOW_WIDTH - btn_width) // 2
            btn_y = start_y + i * (btn_height + btn_spacing)
            game_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)
            win_rect = self.game_to_window_rect(game_rect)

            if is_active:
                bg_color = (60, 50, 70)
                border_color = (120, 100, 140)
                text_color = COLOR_TEXT
            else:
                bg_color = (40, 40, 45)
                border_color = (70, 70, 80)
                text_color = (100, 100, 110)

            border_width = max(1, int(2 * self.scale))
            pygame.draw.rect(self.window, bg_color, win_rect)
            pygame.draw.rect(self.window, border_color, win_rect, border_width)

            text_surface = btn_font.render(btn_text, True, text_color)
            text_x = win_rect.x + (win_rect.width - text_surface.get_width()) // 2
            text_y = win_rect.y + (win_rect.height - text_surface.get_height()) // 2
            self.window.blit(text_surface, (text_x, text_y))

            if is_active:
                self.menu_buttons.append((btn_id, game_rect))

        # Version at bottom
        version_font = self.get_native_font('small')
        version_text = version_font.render("v0.1 - MVP", True, (80, 80, 90))
        version_x, version_y = self.game_to_window_coords(int(20 * UI_SCALE), WINDOW_HEIGHT - int(30 * UI_SCALE))
        self.window.blit(version_text, (version_x, version_y))

        pygame.display.flip()

    def get_clicked_menu_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a menu button was clicked. Returns button_id or None."""
        for btn_id, rect in self.menu_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def draw_settings(self, current_resolution: tuple):
        """Draw the settings screen with native resolution text."""
        from ..constants import RESOLUTIONS

        self.settings_buttons = []

        # Clear screen with background and blit to window
        self.screen.fill(COLOR_BG)
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        game_area_width = int(self.BASE_WIDTH * self.scale) if self.scale > 0 else self.BASE_WIDTH

        # Title
        title_font = self.get_native_font('title_medium')
        title = title_font.render("НАСТРОЙКИ", True, (247, 211, 82))
        title_win_x = self.offset_x + game_area_width // 2 - title.get_width() // 2
        _, title_win_y = self.game_to_window_coords(0, scaled(60))
        self.window.blit(title, (title_win_x, title_win_y))

        # Resolution section label
        section_font = self.get_native_font('medium')
        section_title = section_font.render("Разрешение экрана:", True, COLOR_TEXT)
        section_x, section_y = self.game_to_window_coords(scaled(100), scaled(140))
        self.window.blit(section_title, (section_x, section_y))

        # Resolution buttons
        btn_width = scaled(200)
        btn_height = scaled(40)
        btn_spacing = scaled(10)
        start_x = scaled(100)
        start_y = scaled(190)

        btn_font = self.get_native_font('medium')
        border_width = max(1, int(2 * self.scale))

        for i, (w, h) in enumerate(RESOLUTIONS):
            col = i % 3
            row = i // 3
            btn_x = start_x + col * (btn_width + btn_spacing)
            btn_y = start_y + row * (btn_height + btn_spacing)
            game_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)
            win_rect = self.game_to_window_rect(game_rect)

            is_current = (w, h) == current_resolution
            if is_current:
                bg_color = (80, 100, 60)
                border_color = (150, 180, 100)
            else:
                bg_color = (60, 50, 70)
                border_color = (120, 100, 140)

            pygame.draw.rect(self.window, bg_color, win_rect)
            pygame.draw.rect(self.window, border_color, win_rect, border_width)

            res_text = f"{w} x {h}"
            text_surface = btn_font.render(res_text, True, COLOR_TEXT)
            text_x = win_rect.x + (win_rect.width - text_surface.get_width()) // 2
            text_y = win_rect.y + (win_rect.height - text_surface.get_height()) // 2
            self.window.blit(text_surface, (text_x, text_y))

            self.settings_buttons.append((f"res_{w}_{h}", game_rect))

        # Fullscreen toggle info
        small_font = self.get_native_font('small')
        fullscreen_text = small_font.render("F11 - переключить полноэкранный режим", True, (150, 150, 160))
        fs_x, fs_y = self.game_to_window_coords(scaled(100), scaled(340))
        self.window.blit(fullscreen_text, (fs_x, fs_y))

        # Sound toggle section
        from ..settings import get_sound_enabled
        sound_enabled = get_sound_enabled()

        sound_label = section_font.render("Звук:", True, COLOR_TEXT)
        sound_label_x, sound_label_y = self.game_to_window_coords(scaled(100), scaled(380))
        self.window.blit(sound_label, (sound_label_x, sound_label_y))

        sound_btn_width = scaled(120)
        sound_btn_height = scaled(40)
        sound_btn_x = scaled(200)
        sound_btn_y = scaled(375)
        sound_game_rect = pygame.Rect(sound_btn_x, sound_btn_y, sound_btn_width, sound_btn_height)
        sound_win_rect = self.game_to_window_rect(sound_game_rect)

        if sound_enabled:
            bg_color = (80, 100, 60)
            border_color = (150, 180, 100)
            sound_text = "ВКЛ"
        else:
            bg_color = (100, 60, 60)
            border_color = (180, 100, 100)
            sound_text = "ВЫКЛ"

        pygame.draw.rect(self.window, bg_color, sound_win_rect)
        pygame.draw.rect(self.window, border_color, sound_win_rect, border_width)

        text_surface = btn_font.render(sound_text, True, COLOR_TEXT)
        text_x = sound_win_rect.x + (sound_win_rect.width - text_surface.get_width()) // 2
        text_y = sound_win_rect.y + (sound_win_rect.height - text_surface.get_height()) // 2
        self.window.blit(text_surface, (text_x, text_y))

        self.settings_buttons.append(("toggle_sound", sound_game_rect))

        # Nickname section
        nickname_label = section_font.render("Никнейм (для сетевой игры):", True, COLOR_TEXT)
        nick_x, nick_y = self.game_to_window_coords(scaled(100), scaled(440))
        self.window.blit(nickname_label, (nick_x, nick_y))

        # Nickname input field
        input_game_rect = pygame.Rect(scaled(100), scaled(480), scaled(300), scaled(36))
        input_win_rect = self.game_to_window_rect(input_game_rect)

        is_active = self.settings_nickname_input.active
        bg_color = (60, 60, 70) if is_active else (50, 50, 60)
        border_color = (140, 120, 160) if is_active else (100, 100, 110)

        pygame.draw.rect(self.window, bg_color, input_win_rect)
        pygame.draw.rect(self.window, border_color, input_win_rect, border_width)

        input_text = self.settings_nickname_input.value
        text_x = input_win_rect.x + int(5 * self.scale)
        text_y = input_win_rect.y + (input_win_rect.height - btn_font.get_height()) // 2

        # Draw selection highlight if active and has selection
        if is_active and self.settings_nickname_input.has_selection:
            sel_start, sel_end = self.settings_nickname_input.selection_range
            before_sel_width = btn_font.size(input_text[:sel_start])[0] if sel_start > 0 else 0
            sel_text_width = btn_font.size(input_text[sel_start:sel_end])[0]
            sel_x = text_x + before_sel_width
            sel_rect = pygame.Rect(sel_x, text_y, sel_text_width, btn_font.get_height())
            pygame.draw.rect(self.window, (70, 100, 150), sel_rect)  # Selection color

        if input_text:
            text_surface = btn_font.render(input_text, True, COLOR_TEXT)
            self.window.blit(text_surface, (text_x, text_y))

        if is_active:
            # Update cursor blink
            self.settings_nickname_input.update_cursor_blink()

            cursor_x = text_x
            if input_text:
                text_before_cursor = input_text[:self.settings_nickname_input.cursor_pos]
                cursor_x += btn_font.size(text_before_cursor)[0]
            cursor_y = text_y + 2
            cursor_h = btn_font.get_height() - 4

            if self.settings_nickname_input.cursor_visible:
                pygame.draw.line(self.window, COLOR_TEXT, (cursor_x, cursor_y), (cursor_x, cursor_y + cursor_h), max(1, int(self.scale)))

        self.settings_nickname_rect = input_game_rect

        # Back button
        back_btn_width = scaled(180)
        back_btn_height = scaled(45)
        back_btn_x = (WINDOW_WIDTH - back_btn_width) // 2
        back_btn_y = WINDOW_HEIGHT - scaled(100)
        back_game_rect = pygame.Rect(back_btn_x, back_btn_y, back_btn_width, back_btn_height)
        back_win_rect = self.game_to_window_rect(back_game_rect)

        pygame.draw.rect(self.window, (60, 50, 70), back_win_rect)
        pygame.draw.rect(self.window, (120, 100, 140), back_win_rect, border_width)

        back_text = btn_font.render("Назад", True, COLOR_TEXT)
        text_x = back_win_rect.x + (back_win_rect.width - back_text.get_width()) // 2
        text_y = back_win_rect.y + (back_win_rect.height - back_text.get_height()) // 2
        self.window.blit(back_text, (text_x, text_y))

        self.settings_buttons.append(("back", back_game_rect))

        pygame.display.flip()

    def get_clicked_settings_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a settings button was clicked. Returns button_id or None."""
        if not hasattr(self, 'settings_buttons'):
            return None
        for btn_id, rect in self.settings_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def draw_pause_menu(self, current_resolution: tuple, is_network_game: bool = False):
        """Draw in-game pause menu overlay with native resolution text."""
        self.pause_buttons = []

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill(UILayout.POPUP_PAUSE_BG)
        self.screen.blit(overlay, (0, 0))

        # Menu panel background
        panel_width = scaled(400)
        panel_height = scaled(400)
        panel_x = (WINDOW_WIDTH - panel_width) // 2
        panel_y = (WINDOW_HEIGHT - panel_height) // 2
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)

        pygame.draw.rect(self.screen, (40, 35, 50), panel_rect)
        pygame.draw.rect(self.screen, UILayout.POPUP_PAUSE_BORDER, panel_rect, 3)

    def draw_pause_menu_native(self, current_resolution: tuple, is_network_game: bool = False):
        """Draw pause menu text/buttons at native resolution. Call after finalize_frame."""
        from ..constants import RESOLUTIONS

        self.pause_buttons = []
        border_width = max(1, int(2 * self.scale))

        panel_width = scaled(400)
        panel_height = scaled(400)
        panel_x = (WINDOW_WIDTH - panel_width) // 2
        panel_y = (WINDOW_HEIGHT - panel_height) // 2
        panel_win_rect = self.game_to_window_rect(pygame.Rect(panel_x, panel_y, panel_width, panel_height))

        # Title
        title_font = self.get_native_font('title_small')
        title = title_font.render("ПАУЗА", True, (200, 180, 100))
        _, win_y = self.game_to_window_coords(panel_x, panel_y + scaled(20))
        title_win_x = panel_win_rect.x + (panel_win_rect.width - title.get_width()) // 2
        self.window.blit(title, (title_win_x, win_y))

        # Resolution section
        section_y = panel_y + scaled(65)
        small_font = self.get_native_font('small')
        section_title = small_font.render("Разрешение:", True, COLOR_TEXT)
        sec_x, sec_y = self.game_to_window_coords(panel_x + scaled(20), section_y)
        self.window.blit(section_title, (sec_x, sec_y))

        # Resolution buttons
        btn_width = scaled(110)
        btn_height = scaled(32)
        btn_spacing = scaled(8)
        start_x = panel_x + scaled(20)
        start_y = section_y + scaled(25)

        for i, (w, h) in enumerate(RESOLUTIONS):
            col = i % 3
            row = i // 3
            btn_x = start_x + col * (btn_width + btn_spacing)
            btn_y = start_y + row * (btn_height + btn_spacing)
            game_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)
            win_rect = self.game_to_window_rect(game_rect)

            is_current = (w, h) == current_resolution
            if is_current:
                bg_color = (80, 100, 60)
                border_color = (150, 180, 100)
            else:
                bg_color = (60, 50, 70)
                border_color = (100, 80, 120)

            pygame.draw.rect(self.window, bg_color, win_rect)
            pygame.draw.rect(self.window, border_color, win_rect, border_width)

            res_text = f"{w}x{h}"
            text_surface = small_font.render(res_text, True, COLOR_TEXT)
            text_x = win_rect.x + (win_rect.width - text_surface.get_width()) // 2
            text_y = win_rect.y + (win_rect.height - text_surface.get_height()) // 2
            self.window.blit(text_surface, (text_x, text_y))

            self.pause_buttons.append((f"res_{w}_{h}", game_rect))

        # Sound toggle
        from ..settings import get_sound_enabled
        sound_enabled = get_sound_enabled()

        sound_y = start_y + 2 * (btn_height + btn_spacing) + scaled(15)
        sound_label = small_font.render("Звук:", True, COLOR_TEXT)
        sound_label_x, sound_label_y = self.game_to_window_coords(panel_x + scaled(20), sound_y)
        self.window.blit(sound_label, (sound_label_x, sound_label_y))

        sound_btn_width = scaled(80)
        sound_btn_height = scaled(32)
        sound_btn_x = panel_x + scaled(90)
        sound_game_rect = pygame.Rect(sound_btn_x, sound_y - scaled(3), sound_btn_width, sound_btn_height)
        sound_win_rect = self.game_to_window_rect(sound_game_rect)

        if sound_enabled:
            bg_color = (80, 100, 60)
            border_color = (150, 180, 100)
            sound_text = "ВКЛ"
        else:
            bg_color = (100, 60, 60)
            border_color = (180, 100, 100)
            sound_text = "ВЫКЛ"

        pygame.draw.rect(self.window, bg_color, sound_win_rect)
        pygame.draw.rect(self.window, border_color, sound_win_rect, border_width)

        text_surface = small_font.render(sound_text, True, COLOR_TEXT)
        text_x = sound_win_rect.x + (sound_win_rect.width - text_surface.get_width()) // 2
        text_y = sound_win_rect.y + (sound_win_rect.height - text_surface.get_height()) // 2
        self.window.blit(text_surface, (text_x, text_y))

        self.pause_buttons.append(("toggle_sound", sound_game_rect))

        # Action buttons
        medium_font = self.get_native_font('medium')
        action_btn_width = scaled(180)
        action_btn_height = scaled(40)
        action_y = panel_y + panel_height - scaled(160)

        if is_network_game:
            # Concede button
            concede_game_rect = pygame.Rect(
                panel_x + (panel_width - action_btn_width) // 2,
                action_y, action_btn_width, action_btn_height
            )
            concede_win_rect = self.game_to_window_rect(concede_game_rect)
            pygame.draw.rect(self.window, (120, 50, 50), concede_win_rect)
            pygame.draw.rect(self.window, (180, 80, 80), concede_win_rect, border_width)

            concede_text = medium_font.render("Сдаться", True, COLOR_TEXT)
            text_x = concede_win_rect.x + (concede_win_rect.width - concede_text.get_width()) // 2
            text_y = concede_win_rect.y + (concede_win_rect.height - concede_text.get_height()) // 2
            self.window.blit(concede_text, (text_x, text_y))

            self.pause_buttons.append(("concede", concede_game_rect))
            action_y += action_btn_height + scaled(10)
        else:
            # Exit to menu button
            exit_game_rect = pygame.Rect(
                panel_x + (panel_width - action_btn_width) // 2,
                action_y, action_btn_width, action_btn_height
            )
            exit_win_rect = self.game_to_window_rect(exit_game_rect)
            pygame.draw.rect(self.window, (120, 50, 50), exit_win_rect)
            pygame.draw.rect(self.window, (180, 80, 80), exit_win_rect, border_width)

            exit_text = medium_font.render("Выход в меню", True, COLOR_TEXT)
            text_x = exit_win_rect.x + (exit_win_rect.width - exit_text.get_width()) // 2
            text_y = exit_win_rect.y + (exit_win_rect.height - exit_text.get_height()) // 2
            self.window.blit(exit_text, (text_x, text_y))

            self.pause_buttons.append(("exit", exit_game_rect))
            action_y += action_btn_height + scaled(10)

        # Resume button
        resume_game_rect = pygame.Rect(
            panel_x + (panel_width - action_btn_width) // 2,
            action_y, action_btn_width, action_btn_height
        )
        resume_win_rect = self.game_to_window_rect(resume_game_rect)
        pygame.draw.rect(self.window, (60, 80, 60), resume_win_rect)
        pygame.draw.rect(self.window, (100, 150, 100), resume_win_rect, border_width)

        resume_text = medium_font.render("Продолжить", True, COLOR_TEXT)
        text_x = resume_win_rect.x + (resume_win_rect.width - resume_text.get_width()) // 2
        text_y = resume_win_rect.y + (resume_win_rect.height - resume_text.get_height()) // 2
        self.window.blit(resume_text, (text_x, text_y))

        self.pause_buttons.append(("resume", resume_game_rect))

        # ESC hint
        hint_text = small_font.render("ESC - продолжить игру", True, (120, 120, 130))
        _, hint_y = self.game_to_window_coords(0, panel_y + panel_height - scaled(30))
        hint_win_x = panel_win_rect.x + (panel_win_rect.width - hint_text.get_width()) // 2
        self.window.blit(hint_text, (hint_win_x, hint_y))

    def get_clicked_pause_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a pause menu button was clicked. Returns button_id or None."""
        if not hasattr(self, 'pause_buttons'):
            return None
        for btn_id, rect in self.pause_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def get_deck_builder_resources(self) -> tuple:
        """Get resources needed by deck builder.

        Returns:
            (screen, card_images, card_images_full, fonts)
        """
        fonts = {
            'large': self.font_large,
            'medium': self.font_medium,
            'small': self.font_small,
            'card_name': self.font_card_name,
            'indicator': self.font_indicator,
        }
        return self.screen, self.card_images, self.card_images_full, fonts

    # =========================================================================
    # AI SETUP POPUP
    # =========================================================================

    def draw_ai_setup_popup(self, ai_setup_state: dict):
        """Draw AI game setup popup.

        ai_setup_state should contain:
            - mode: 'vs_ai' or 'ai_vs_ai'
            - ai_delay: float (0.0 - 2.0)
            - ai_type_p1: str ('random' or 'rulebased')
            - ai_type_p2: str ('random' or 'rulebased')
        """
        self.ai_setup_buttons = []

        # Draw menu background first
        if hasattr(self, 'menu_background') and self.menu_background is not None:
            self.screen.blit(self.menu_background, (0, 0))
        else:
            self.screen.fill(COLOR_BG)

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Popup panel
        panel_width = scaled(450)
        panel_height = scaled(380)
        panel_x = (WINDOW_WIDTH - panel_width) // 2
        panel_y = (WINDOW_HEIGHT - panel_height) // 2
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)

        pygame.draw.rect(self.screen, (40, 35, 50), panel_rect)
        pygame.draw.rect(self.screen, (120, 100, 140), panel_rect, 3)

        # Scale and blit to window
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        # Now draw native resolution elements
        self._draw_ai_setup_native(ai_setup_state, panel_x, panel_y, panel_width, panel_height)

        pygame.display.flip()

    def _draw_ai_setup_native(self, state: dict, panel_x: int, panel_y: int,
                               panel_width: int, panel_height: int):
        """Draw AI setup popup elements at native resolution."""
        border_width = max(1, int(2 * self.scale))

        mode = state.get('mode', 'vs_ai')
        ai_delay = state.get('ai_delay', 0.5)
        ai_type_p1 = state.get('ai_type_p1', 'rulebased')
        ai_type_p2 = state.get('ai_type_p2', 'rulebased')

        # Title
        title_font = self.get_native_font('title_small')
        title = title_font.render("ИГРА С БОТОМ", True, (247, 211, 82))
        panel_win_rect = self.game_to_window_rect(pygame.Rect(panel_x, panel_y, panel_width, panel_height))
        _, win_y = self.game_to_window_coords(0, panel_y + scaled(15))
        title_win_x = panel_win_rect.x + (panel_win_rect.width - title.get_width()) // 2
        self.window.blit(title, (title_win_x, win_y))

        medium_font = self.get_native_font('medium')
        small_font = self.get_native_font('small')

        # Mode selection buttons
        mode_y = panel_y + scaled(60)
        mode_label = small_font.render("Режим:", True, COLOR_TEXT)
        label_x, label_y = self.game_to_window_coords(panel_x + scaled(20), mode_y)
        self.window.blit(mode_label, (label_x, label_y))

        btn_width = scaled(180)
        btn_height = scaled(35)
        btn_spacing = scaled(10)

        # "Play vs AI" button
        vs_ai_rect = pygame.Rect(panel_x + scaled(20), mode_y + scaled(25), btn_width, btn_height)
        vs_ai_win = self.game_to_window_rect(vs_ai_rect)
        is_vs_ai = mode == 'vs_ai'
        bg_color = (80, 100, 60) if is_vs_ai else (60, 50, 70)
        border_color = (150, 180, 100) if is_vs_ai else (100, 80, 120)
        pygame.draw.rect(self.window, bg_color, vs_ai_win)
        pygame.draw.rect(self.window, border_color, vs_ai_win, border_width)
        text = small_font.render("Играть против ИИ", True, COLOR_TEXT)
        self.window.blit(text, (vs_ai_win.x + (vs_ai_win.width - text.get_width()) // 2,
                                vs_ai_win.y + (vs_ai_win.height - text.get_height()) // 2))
        self.ai_setup_buttons.append(("mode_vs_ai", vs_ai_rect))

        # "AI vs AI" button
        ai_ai_rect = pygame.Rect(panel_x + scaled(20) + btn_width + btn_spacing,
                                  mode_y + scaled(25), btn_width, btn_height)
        ai_ai_win = self.game_to_window_rect(ai_ai_rect)
        is_ai_ai = mode == 'ai_vs_ai'
        bg_color = (80, 100, 60) if is_ai_ai else (60, 50, 70)
        border_color = (150, 180, 100) if is_ai_ai else (100, 80, 120)
        pygame.draw.rect(self.window, bg_color, ai_ai_win)
        pygame.draw.rect(self.window, border_color, ai_ai_win, border_width)
        text = small_font.render("Смотреть ИИ vs ИИ", True, COLOR_TEXT)
        self.window.blit(text, (ai_ai_win.x + (ai_ai_win.width - text.get_width()) // 2,
                                ai_ai_win.y + (ai_ai_win.height - text.get_height()) // 2))
        self.ai_setup_buttons.append(("mode_ai_vs_ai", ai_ai_rect))

        # AI Type selection
        ai_type_y = mode_y + scaled(80)

        ai_types = [('random', 'Random'), ('rulebased', 'Rule-based'),] # ('utility', 'Utility')
        dropdown_width = scaled(170)
        dropdown_height = scaled(32)

        if mode == 'vs_ai':
            # Only show P2 AI selection
            ai_label = small_font.render("Тип ИИ противника:", True, COLOR_TEXT)
            ai_x, ai_y = self.game_to_window_coords(panel_x + scaled(20), ai_type_y)
            self.window.blit(ai_label, (ai_x, ai_y))

            self._draw_ai_dropdown(panel_x + scaled(20), ai_type_y + scaled(25),
                                   dropdown_width, dropdown_height, ai_type_p2,
                                   ai_types, "ai_p2", border_width, small_font)
        else:
            # Show both P1 and P2 AI selection
            p1_label = small_font.render("ИИ Игрока 1:", True, COLOR_TEXT)
            p1_x, p1_y = self.game_to_window_coords(panel_x + scaled(20), ai_type_y)
            self.window.blit(p1_label, (p1_x, p1_y))

            self._draw_ai_dropdown(panel_x + scaled(20), ai_type_y + scaled(25),
                                   dropdown_width, dropdown_height, ai_type_p1,
                                   ai_types, "ai_p1", border_width, small_font)

            p2_label = small_font.render("ИИ Игрока 2:", True, COLOR_TEXT)
            p2_x, p2_y = self.game_to_window_coords(panel_x + scaled(230), ai_type_y)
            self.window.blit(p2_label, (p2_x, p2_y))

            self._draw_ai_dropdown(panel_x + scaled(230), ai_type_y + scaled(25),
                                   dropdown_width, dropdown_height, ai_type_p2,
                                   ai_types, "ai_p2", border_width, small_font)

        # Delay slider
        delay_y = ai_type_y + scaled(85)
        delay_label = small_font.render(f"Задержка хода ИИ: {ai_delay:.1f} сек", True, COLOR_TEXT)
        delay_x, delay_label_y = self.game_to_window_coords(panel_x + scaled(20), delay_y)
        self.window.blit(delay_label, (delay_x, delay_label_y))

        # Slider track
        slider_y = delay_y + scaled(30)
        slider_width = scaled(380)
        slider_height = scaled(8)
        slider_x = panel_x + scaled(20)

        slider_rect = pygame.Rect(slider_x, slider_y, slider_width, slider_height)
        slider_win = self.game_to_window_rect(slider_rect)
        pygame.draw.rect(self.window, (60, 60, 70), slider_win)
        pygame.draw.rect(self.window, (100, 100, 110), slider_win, 1)

        # Slider fill (based on delay value 0-2)
        fill_width = int(slider_win.width * (ai_delay / 2.0))
        fill_rect = pygame.Rect(slider_win.x, slider_win.y, fill_width, slider_win.height)
        pygame.draw.rect(self.window, (100, 140, 100), fill_rect)

        # Slider handle
        handle_x = slider_win.x + fill_width - scaled(6)
        handle_rect = pygame.Rect(handle_x, slider_win.y - scaled(4), scaled(12), slider_win.height + scaled(8))
        pygame.draw.rect(self.window, (150, 180, 150), handle_rect)
        pygame.draw.rect(self.window, (200, 220, 200), handle_rect, 1)

        # Store slider area for click detection
        self.ai_setup_buttons.append(("delay_slider", slider_rect))

        # Delay preset buttons
        preset_y = slider_y + scaled(20)
        preset_width = scaled(60)
        preset_height = scaled(28)
        presets = [(0.0, "0"), (0.5, "0.5"), (1.0, "1.0"), (2.0, "2.0")]

        for i, (val, label) in enumerate(presets):
            preset_x = slider_x + i * (preset_width + scaled(10))
            preset_rect = pygame.Rect(preset_x, preset_y, preset_width, preset_height)
            preset_win = self.game_to_window_rect(preset_rect)

            is_current = abs(ai_delay - val) < 0.1
            bg_color = (80, 100, 60) if is_current else (50, 50, 60)
            border_color = (120, 150, 100) if is_current else (80, 80, 90)

            pygame.draw.rect(self.window, bg_color, preset_win)
            pygame.draw.rect(self.window, border_color, preset_win, 1)

            text = small_font.render(label, True, COLOR_TEXT)
            self.window.blit(text, (preset_win.x + (preset_win.width - text.get_width()) // 2,
                                    preset_win.y + (preset_win.height - text.get_height()) // 2))
            self.ai_setup_buttons.append((f"delay_{val}", preset_rect))

        # Start and Cancel buttons
        action_y = panel_y + panel_height - scaled(60)
        action_width = scaled(140)
        action_height = scaled(40)

        # Cancel button
        cancel_rect = pygame.Rect(panel_x + scaled(50), action_y, action_width, action_height)
        cancel_win = self.game_to_window_rect(cancel_rect)
        pygame.draw.rect(self.window, (80, 50, 50), cancel_win)
        pygame.draw.rect(self.window, (140, 80, 80), cancel_win, border_width)
        text = medium_font.render("Отмена", True, COLOR_TEXT)
        self.window.blit(text, (cancel_win.x + (cancel_win.width - text.get_width()) // 2,
                                cancel_win.y + (cancel_win.height - text.get_height()) // 2))
        self.ai_setup_buttons.append(("cancel", cancel_rect))

        # Start button
        start_rect = pygame.Rect(panel_x + panel_width - scaled(50) - action_width,
                                  action_y, action_width, action_height)
        start_win = self.game_to_window_rect(start_rect)
        pygame.draw.rect(self.window, (50, 80, 50), start_win)
        pygame.draw.rect(self.window, (80, 140, 80), start_win, border_width)
        text = medium_font.render("Начать", True, COLOR_TEXT)
        self.window.blit(text, (start_win.x + (start_win.width - text.get_width()) // 2,
                                start_win.y + (start_win.height - text.get_height()) // 2))
        self.ai_setup_buttons.append(("start", start_rect))

    def _draw_ai_dropdown(self, x: int, y: int, width: int, height: int,
                          current_value: str, options: list, btn_prefix: str,
                          border_width: int, font):
        """Draw AI type selection as toggle buttons."""
        btn_width = width // len(options) - scaled(2)

        for i, (value, label) in enumerate(options):
            btn_x = x + i * (btn_width + scaled(4))
            btn_rect = pygame.Rect(btn_x, y, btn_width, height)
            btn_win = self.game_to_window_rect(btn_rect)

            is_selected = current_value == value
            bg_color = (80, 100, 60) if is_selected else (50, 50, 60)
            border_color = (120, 150, 100) if is_selected else (80, 80, 90)

            pygame.draw.rect(self.window, bg_color, btn_win)
            pygame.draw.rect(self.window, border_color, btn_win, border_width)

            text = font.render(label, True, COLOR_TEXT)
            self.window.blit(text, (btn_win.x + (btn_win.width - text.get_width()) // 2,
                                    btn_win.y + (btn_win.height - text.get_height()) // 2))

            self.ai_setup_buttons.append((f"{btn_prefix}_{value}", btn_rect))

    def get_clicked_ai_setup_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if an AI setup button was clicked. Returns button_id or None."""
        if not hasattr(self, 'ai_setup_buttons'):
            return None
        for btn_id, rect in self.ai_setup_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def get_ai_delay_from_slider(self, mouse_x: int, mouse_y: int, slider_rect: pygame.Rect) -> Optional[float]:
        """Calculate delay value from mouse position on slider."""
        if not slider_rect.collidepoint(mouse_x, mouse_y):
            return None
        relative_x = mouse_x - slider_rect.x
        ratio = max(0.0, min(1.0, relative_x / slider_rect.width))
        return round(ratio * 2.0, 1)  # 0.0 to 2.0
