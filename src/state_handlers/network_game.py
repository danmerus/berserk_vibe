"""Network game state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler
from .helpers import handle_game_scroll, handle_game_esc, process_game_events

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class NetworkGameHandler(StateHandler):
    """Handler for network game state.

    Handles:
    - Game interactions (move, attack, abilities)
    - Network polling and syncing
    - Chat
    - Draw offers
    - Pause menu
    - Game over
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)
        self.draw_button_rect: Optional[pygame.Rect] = None

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle network game events."""
        from ..constants import AppState

        # Sync viewing player BEFORE processing events
        self.ctx.renderer.viewing_player = self.ctx.network_player

        game = self.ctx.network_game
        client = self.ctx.network_game_client
        chat = self.ctx.network_chat

        if not game or not client:
            return None

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event)

        elif event.type == pygame.TEXTINPUT:
            if chat and chat.is_input_focused():
                chat.handle_event(event)
            return None

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = self.ctx.renderer.screen_to_game_coords(*pygame.mouse.get_pos())
            # Let chat handle scroll first
            if chat and chat.handle_event(event):
                return None
            handle_game_scroll(game, client, self.ctx.renderer, mx, my, event.y)
            return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my, event)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_right_click(mx, my)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            self.ctx.renderer.stop_popup_drag()
            self.ctx.renderer.stop_log_scrollbar_drag()
            if chat:
                chat_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
                chat.handle_event(chat_event)
            return None

        elif event.type == pygame.MOUSEMOTION:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            if self.ctx.renderer.dragging_popup:
                self.ctx.renderer.drag_popup(mx, my)
            self.ctx.renderer.drag_log_scrollbar(my)
            if chat:
                chat_event = pygame.event.Event(event.type, pos=(mx, my), rel=event.rel, buttons=event.buttons)
                chat.handle_event(chat_event)
            return None

        return None

    def _handle_keydown(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle key press in network game."""
        from ..constants import AppState
        from ..commands import cmd_confirm, cmd_cancel

        game = self.ctx.network_game
        client = self.ctx.network_game_client
        chat = self.ctx.network_chat
        renderer = self.ctx.renderer
        network_client = self.ctx.network_client
        player = self.ctx.network_player

        # Let chat handle event first if focused
        if chat and chat.is_input_focused():
            if chat.handle_event(event):
                return None

        if event.key == pygame.K_ESCAPE:
            if self.ctx.show_pause_menu:
                self.ctx.show_pause_menu = False
            elif chat and chat.is_input_focused():
                chat.text_input.deactivate()
            elif renderer.popup_card:
                renderer.hide_popup()
            elif renderer.dice_popup_open:
                renderer.close_dice_popup()
            elif game.awaiting_ability_target:
                self._send_command(cmd_cancel(player))
                client.deselect()
            elif client.selected_card:
                client.deselect()
            else:
                self.ctx.show_pause_menu = True
            return None

        elif event.key == pygame.K_y and game.awaiting_heal_confirm:
            acting = game.interaction.acting_player if game.interaction else game.current_player
            if acting == player:
                self._send_command(cmd_confirm(player, True))
            return None

        elif event.key == pygame.K_n and game.awaiting_heal_confirm:
            acting = game.interaction.acting_player if game.interaction else game.current_player
            if acting == player:
                self._send_command(cmd_confirm(player, False))
            return None

        elif event.key == pygame.K_F5:
            if network_client:
                if chat:
                    chat.add_system_message("Запрос синхронизации...")
                network_client.request_resync()
                client.deselect()
            return None

        return None

    def _handle_click(self, mx: int, my: int, event: pygame.event.Event) -> Optional['AppState']:
        """Handle left click in network game."""
        from ..constants import AppState, GamePhase
        from ..click_handler import GameClickHandler

        game = self.ctx.network_game
        client = self.ctx.network_game_client
        renderer = self.ctx.renderer
        chat = self.ctx.network_chat
        player = self.ctx.network_player

        # Chat click
        if chat:
            chat_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
            if chat.handle_event(chat_event):
                return None

        # Draw button
        result = self._handle_draw_button_click(mx, my)
        if result is not None:
            return result

        # Pause menu
        if self.ctx.show_pause_menu:
            return self._handle_pause_menu_click(mx, my)

        # Game over popup - click to dismiss and return to menu
        if game.phase == GamePhase.GAME_OVER and renderer.game_over_popup:
            renderer.hide_game_over_popup()
            self.ctx.reset_network_game()
            return AppState.MENU

        # Card popup
        if renderer.popup_card:
            renderer.hide_popup()
            return None

        # Use unified click handler
        def send_fn(cmd):
            return self._send_command(cmd)

        handler = GameClickHandler(game, client, renderer, send_fn, player=player)
        handler.handle_left_click(mx, my)

        return None

    def _handle_right_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle right click (show card popup or deselect)."""
        game = self.ctx.network_game
        renderer = self.ctx.renderer

        # Check for card at position
        pos = renderer.screen_to_pos(mx, my)
        if pos is not None:
            card = game.board.get_card(pos)
            if card:
                renderer.show_popup(card)
                return None

        # Check flying zones
        flying_pos = renderer.get_flying_slot_at_pos(mx, my, game)
        if flying_pos is not None:
            card = game.board.get_card(flying_pos)
            if card:
                renderer.show_popup(card)
                return None

        # Check graveyard
        card = renderer.get_graveyard_card_at_pos(game, mx, my)
        if card:
            renderer.show_popup(card)
            return None

        # Deselect
        self.ctx.network_game_client.deselect()
        return None

    def _handle_draw_button_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle click on draw offer button."""
        network_client = self.ctx.network_client

        # Check if clicking draw button
        if self.draw_button_rect and self.draw_button_rect.collidepoint(mx, my):
            if self.ctx.draw_offered_by_opponent:
                # Accept the draw
                if network_client:
                    network_client.send_draw_accept()
            elif not self.ctx.draw_offered_by_us:
                # Offer a draw
                if network_client:
                    network_client.send_draw_offer()
                    self.ctx.draw_offered_by_us = True
            return None  # Handled, but no state change

        return None  # Not handled

    def _handle_pause_menu_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle click in pause menu."""
        from ..constants import AppState
        from ..settings import set_resolution, get_sound_enabled, set_sound_enabled

        renderer = self.ctx.renderer

        btn = renderer.get_clicked_pause_button(mx, my)
        if btn == "resume":
            self.ctx.show_pause_menu = False
        elif btn == "concede":
            # For network, just leave the match
            if self.ctx.network_client:
                self.ctx.network_client.leave_match()
            self.ctx.show_pause_menu = False
            self.ctx.reset_network_game()
            return AppState.MENU
        elif btn == "exit":
            self.ctx.show_pause_menu = False
            if self.ctx.network_client:
                self.ctx.network_client.leave_match()
            self.ctx.reset_network_game()
            return AppState.MENU
        elif btn == "toggle_sound":
            set_sound_enabled(not get_sound_enabled())
        elif btn and btn.startswith("res_"):
            # Resolution change
            parts = btn.split("_")
            if len(parts) == 3:
                new_w, new_h = int(parts[1]), int(parts[2])
                self.ctx.current_resolution = (new_w, new_h)
                self.ctx.screen = pygame.display.set_mode(self.ctx.current_resolution, pygame.RESIZABLE)
                self.ctx.renderer.handle_resize(self.ctx.screen)
                set_resolution(new_w, new_h)

        return None

    def _send_command(self, cmd) -> bool:
        """Send a command to the network client."""
        if self.ctx.network_client:
            self.ctx.network_client.send_command(cmd)
            return True
        return False

    def update(self, dt: float) -> Optional['AppState']:
        """Update network game state."""
        from ..constants import GamePhase

        game = self.ctx.network_game
        client = self.ctx.network_game_client
        renderer = self.ctx.renderer
        network_client = self.ctx.network_client

        if not game or not client:
            return None

        # Poll network
        if network_client:
            network_client.poll()
            # Update game from network client's game state
            if network_client.game:
                self.ctx.network_game = network_client.game
                game = self.ctx.network_game
                client.game = game

        # Update client animations
        client.update(dt)

        # Update draw button flash timer
        if self.ctx.draw_button_flash_timer > 0:
            self.ctx.draw_button_flash_timer -= 1

        # Update viewing player to match our player
        renderer.viewing_player = self.ctx.network_player

        # Show game over popup when game ends
        if game.phase == GamePhase.GAME_OVER and not renderer.game_over_popup:
            winner = game.winner if game.winner is not None else game.board.check_winner()
            p1_name, p2_name = None, None
            if self.ctx.network_ui:
                if self.ctx.network_player == 1:
                    p1_name = self.ctx.network_ui.player_name
                    p2_name = self.ctx.network_ui.opponent_name
                else:
                    p1_name = self.ctx.network_ui.opponent_name
                    p2_name = self.ctx.network_ui.player_name
            renderer.show_game_over_popup(winner if winner is not None else 0, p1_name, p2_name)

        return None

    def render(self) -> None:
        """Render the network game."""
        from ..constants import UILayout

        game = self.ctx.network_game
        client = self.ctx.network_game_client
        renderer = self.ctx.renderer
        chat = self.ctx.network_chat

        if not game or not client:
            return

        # Draw game, skip flip if we need to draw chat/pause menu
        has_chat = chat is not None
        skip_flip = self.ctx.show_pause_menu or has_chat
        renderer.draw(game, 0.016, client.ui, skip_flip=skip_flip)

        # Draw chat and draw button
        if chat:
            chat.x = UILayout.CHAT_X
            chat.y = UILayout.CHAT_Y
            chat.width = UILayout.CHAT_WIDTH
            chat.height = UILayout.CHAT_HEIGHT
            chat.input_height = UILayout.CHAT_INPUT_HEIGHT
            chat.draw(renderer.screen)

            # Draw the draw offer button below chat
            self._draw_draw_button(renderer)

            if not self.ctx.show_pause_menu:
                def draw_native_ui(w, c):
                    renderer.draw_ui_native(game)
                    if renderer.game_over_popup:
                        renderer.draw_game_over_popup_native()
                renderer.finalize_frame(native_ui_callback=draw_native_ui)

        # Draw pause menu overlay
        if self.ctx.show_pause_menu:
            renderer.draw_pause_menu(self.ctx.current_resolution, is_network_game=True)
            renderer.finalize_frame(skip_flip=True)
            renderer.draw_pause_menu_native(self.ctx.current_resolution, is_network_game=True)
            pygame.display.flip()

    def _draw_draw_button(self, renderer):
        """Draw the draw offer button."""
        from ..constants import UILayout

        btn_x = UILayout.CHAT_X
        btn_y = UILayout.CHAT_Y + UILayout.CHAT_HEIGHT + UILayout.DRAW_BUTTON_OFFSET_Y
        btn_w = UILayout.CHAT_WIDTH
        btn_h = UILayout.DRAW_BUTTON_HEIGHT
        self.draw_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        # Determine button state and colors
        if self.ctx.draw_offered_by_opponent:
            if self.ctx.draw_button_flash_timer > 0:
                if (self.ctx.draw_button_flash_timer // 10) % 2 == 0:
                    btn_color = UILayout.DRAW_BUTTON_ACCEPT_BG_FLASH
                else:
                    btn_color = UILayout.DRAW_BUTTON_ACCEPT_BG_DARK
            else:
                btn_color = UILayout.DRAW_BUTTON_ACCEPT_BG
            btn_text = "Принять ничью"
            text_color = UILayout.DRAW_BUTTON_ACCEPT_TEXT
        elif self.ctx.draw_offered_by_us:
            btn_color = UILayout.DRAW_BUTTON_WAITING_BG
            btn_text = "Ожидание..."
            text_color = UILayout.DRAW_BUTTON_WAITING_TEXT
        else:
            btn_color = UILayout.DRAW_BUTTON_BG
            btn_text = "Предложить ничью"
            text_color = UILayout.DRAW_BUTTON_TEXT

        pygame.draw.rect(renderer.screen, btn_color, self.draw_button_rect)
        pygame.draw.rect(renderer.screen, UILayout.DRAW_BUTTON_BORDER, self.draw_button_rect, 1)

        # Render button text
        text_surface = renderer.font_small.render(btn_text, True, text_color)
        text_x = btn_x + (btn_w - text_surface.get_width()) // 2
        text_y = btn_y + (btn_h - text_surface.get_height()) // 2
        renderer.screen.blit(text_surface, (text_x, text_y))

    def on_enter(self) -> None:
        """Called when entering network game state."""
        self.ctx.show_pause_menu = False
        # Clear stale visual effects from previous games
        self.ctx.renderer.clear_all_effects()
        # Initialize viewing player immediately
        self.ctx.renderer.viewing_player = self.ctx.network_player

    def on_exit(self) -> None:
        """Called when leaving network game state."""
        self.ctx.show_pause_menu = False
