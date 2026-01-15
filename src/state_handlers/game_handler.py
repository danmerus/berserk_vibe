"""Local game state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler
from .helpers import handle_game_scroll, handle_game_esc, handle_pause_menu_click, process_game_events

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class GameHandler(StateHandler):
    """Handler for local game state.

    Handles:
    - Game interactions (move, attack, abilities)
    - Pause menu
    - Game over
    - Turn switching for hotseat mode
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle game events."""
        from ..constants import AppState, GamePhase
        from ..commands import cmd_confirm

        # Sync active player BEFORE processing events (hotseat mode only)
        # In AI mode, human always views from their perspective
        if self.ctx.ai_player is None and not self.ctx.is_ai_vs_ai:
            self._update_active_player()

        game = self.ctx.game
        client = self.ctx.client
        match_client = self.ctx.match_client

        if not game or not client or not match_client:
            return None

        if event.type == pygame.KEYDOWN:
            # In AI vs AI mode, only allow ESC for pause menu
            if self.ctx.is_ai_vs_ai:
                if event.key == pygame.K_ESCAPE:
                    return self._handle_keydown(event)
                return None
            return self._handle_keydown(event)

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = self.ctx.renderer.screen_to_game_coords(*pygame.mouse.get_pos())
            handle_game_scroll(game, client, self.ctx.renderer, mx, my, event.y)
            return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            # In AI vs AI mode, only allow pause menu and game over popup clicks
            if self.ctx.is_ai_vs_ai:
                return self._handle_click_spectator(mx, my)
            return self._handle_click(mx, my)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_right_click(mx, my)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.ctx.renderer.stop_popup_drag()
            self.ctx.renderer.stop_log_scrollbar_drag()
            return None

        elif event.type == pygame.MOUSEMOTION:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            if self.ctx.renderer.dragging_popup:
                self.ctx.renderer.drag_popup(mx, my)
            self.ctx.renderer.drag_log_scrollbar(my)
            return None

        return None

    def _handle_keydown(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle key press in game."""
        from ..constants import AppState, GamePhase
        from ..commands import cmd_confirm, cmd_cancel

        game = self.ctx.game
        client = self.ctx.client
        match_client = self.ctx.match_client
        renderer = self.ctx.renderer

        if event.key == pygame.K_ESCAPE:
            def cancel_fn():
                from ..commands import cmd_cancel
                self._send_command(cmd_cancel(game.current_player))

            handled, new_pause_state = handle_game_esc(
                game, client, renderer, cancel_fn, self.ctx.show_pause_menu
            )
            self.ctx.show_pause_menu = new_pause_state
            return None

        elif event.key == pygame.K_RETURN and game.phase == GamePhase.SETUP:
            game.finish_placement()
            return None

        elif event.key == pygame.K_y and game.awaiting_heal_confirm:
            player = game.interaction.acting_player if game.interaction else game.current_player
            self._send_command(cmd_confirm(player, True))
            return None

        elif event.key == pygame.K_n and game.awaiting_heal_confirm:
            player = game.interaction.acting_player if game.interaction else game.current_player
            self._send_command(cmd_confirm(player, False))
            return None

        elif event.key == pygame.K_y and game.awaiting_untap_confirm:
            player = game.interaction.acting_player if game.interaction else game.current_player
            self._send_command(cmd_confirm(player, True))
            return None

        elif event.key == pygame.K_n and game.awaiting_untap_confirm:
            player = game.interaction.acting_player if game.interaction else game.current_player
            self._send_command(cmd_confirm(player, False))
            return None

        return None

    def _handle_click_spectator(self, mx: int, my: int) -> Optional['AppState']:
        """Handle left click in AI vs AI spectator mode (limited actions)."""
        from ..constants import AppState, GamePhase

        game = self.ctx.game
        renderer = self.ctx.renderer

        # Pause menu
        if self.ctx.show_pause_menu:
            return self._handle_pause_menu_click(mx, my)

        # Game over popup - click to dismiss and return to menu
        if game.phase == GamePhase.GAME_OVER and renderer.game_over_popup:
            renderer.hide_game_over_popup()
            self.ctx.reset_local_game()
            return AppState.MENU

        # Card popup - allow dismissing
        if renderer.popup_card:
            renderer.hide_popup()
            return None

        # No other actions allowed in spectator mode
        return None

    def _handle_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle left click in game."""
        from ..constants import AppState, GamePhase
        from ..click_handler import GameClickHandler

        game = self.ctx.game
        client = self.ctx.client
        match_client = self.ctx.match_client
        renderer = self.ctx.renderer

        # Pause menu
        if self.ctx.show_pause_menu:
            return self._handle_pause_menu_click(mx, my)

        # Game over popup - click to dismiss and return to menu
        if game.phase == GamePhase.GAME_OVER and renderer.game_over_popup:
            renderer.hide_game_over_popup()
            self.ctx.reset_local_game()
            return AppState.MENU

        # Card popup
        if renderer.popup_card:
            renderer.hide_popup()
            return None

        # Use unified click handler
        def send_fn(cmd):
            return self._send_command(cmd)

        handler = GameClickHandler(game, client, renderer, send_fn, player=None)
        handler.handle_left_click(mx, my)

        return None

    def _handle_right_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle right click (show card popup or deselect)."""
        game = self.ctx.game
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
        self.ctx.client.deselect()
        return None

    def _handle_pause_menu_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle click in pause menu."""
        from ..constants import AppState, GamePhase
        from ..settings import set_resolution, get_sound_enabled, set_sound_enabled

        game = self.ctx.game
        renderer = self.ctx.renderer

        btn = renderer.get_clicked_pause_button(mx, my)
        if btn == "resume":
            self.ctx.show_pause_menu = False
        elif btn == "concede":
            game.winner = 2 if game.current_player == 1 else 1
            game.phase = GamePhase.GAME_OVER
            self.ctx.show_pause_menu = False
        elif btn == "exit":
            self.ctx.show_pause_menu = False
            self.ctx.reset_local_game()
            return AppState.MENU
        elif btn == "toggle_sound":
            set_sound_enabled(not get_sound_enabled())
        elif btn and btn.startswith("res_"):
            # Resolution change
            parts = btn.split("_")
            if len(parts) == 3:
                new_w, new_h = int(parts[1]), int(parts[2])
                self.ctx.current_resolution = (new_w, new_h)
                import pygame
                self.ctx.screen = pygame.display.set_mode(self.ctx.current_resolution, pygame.RESIZABLE)
                self.ctx.renderer.handle_resize(self.ctx.screen)
                set_resolution(new_w, new_h)

        return None

    def _send_command(self, cmd) -> bool:
        """Send a command to the match client and process events."""
        match_client = self.ctx.match_client
        if not match_client:
            return False

        result = match_client.send_command(cmd)
        if result.events:
            process_game_events(self.ctx.game, self.ctx.renderer, result.events)
        return result.accepted

    def update(self, dt: float) -> Optional['AppState']:
        """Update game state."""
        from ..constants import GamePhase

        game = self.ctx.game
        client = self.ctx.client
        renderer = self.ctx.renderer

        if not game or not client:
            return None

        # Update client animations
        client.update(dt)

        # Switch active player for hotseat mode (when no AI)
        if self.ctx.ai_player is None and not self.ctx.is_ai_vs_ai:
            self._update_active_player()

        # Let AI take action if it's AI's turn (includes AI vs AI mode)
        if (self.ctx.ai_player or self.ctx.is_ai_vs_ai) and game.phase == GamePhase.MAIN:
            # Decrement AI action timer
            if hasattr(self, '_ai_action_timer') and self._ai_action_timer > 0:
                self._ai_action_timer -= dt
            self._update_ai()

        # Show game over popup when game ends
        if game.phase == GamePhase.GAME_OVER and not renderer.game_over_popup:
            winner = game.board.check_winner()
            renderer.show_game_over_popup(winner if winner is not None else 0)

        return None

    def _update_ai(self):
        """Let AI take action if it's AI's turn."""
        # Determine which AI should act
        ai = None
        if self.ctx.is_ai_vs_ai:
            # AI vs AI mode - check both AIs
            if self.ctx.ai_player and self.ctx.ai_player.is_my_turn():
                ai = self.ctx.ai_player
            elif self.ctx.ai_player_2 and self.ctx.ai_player_2.is_my_turn():
                ai = self.ctx.ai_player_2
        else:
            # Human vs AI mode
            if self.ctx.ai_player and self.ctx.ai_player.is_my_turn():
                ai = self.ctx.ai_player

        if not ai:
            return

        # Delay between AI actions (configurable)
        if not hasattr(self, '_ai_action_timer'):
            self._ai_action_timer = 0.0

        if self._ai_action_timer > 0:
            return  # Still waiting

        action = ai.choose_action()
        if action:
            result = self.ctx.server.apply(action.command)
            if result.events:
                process_game_events(self.ctx.game, self.ctx.renderer, result.events)
            # Reset timer for next action using configured delay
            self._ai_action_timer = self.ctx.ai_delay

    def _update_active_player(self):
        """Update active player for hotseat mode."""
        game = self.ctx.game
        if not game:
            return

        # Determine who should be acting (same logic for both test and hotseat)
        # Auto-switch to whoever needs to act based on priority/interaction/turn
        if game.awaiting_priority:
            acting = game.priority_player
        elif game.interaction and game.interaction.acting_player:
            acting = game.interaction.acting_player
        else:
            acting = game.current_player

        # Switch to the acting player's client
        if acting == 1:
            self.ctx.match_client = self.ctx.client_p1
        else:
            self.ctx.match_client = self.ctx.client_p2

        if self.ctx.match_client:
            self.ctx.client = self.ctx.match_client.game_client
            self.ctx.renderer.viewing_player = acting

    def render(self) -> None:
        """Render the game."""
        game = self.ctx.game
        client = self.ctx.client
        renderer = self.ctx.renderer

        if not game or not client:
            return

        # Draw game (includes game over popup if set)
        skip_flip = self.ctx.show_pause_menu
        test_player = self.ctx.test_game_controlled_player if self.ctx.is_test_game else "not_test_game"
        renderer.draw(game, 0.016, client.ui, skip_flip=skip_flip, test_controlled_player=test_player)

        # Draw pause menu overlay
        if self.ctx.show_pause_menu:
            renderer.draw_pause_menu(self.ctx.current_resolution, is_network_game=False)
            renderer.finalize_frame(skip_flip=True)
            renderer.draw_pause_menu_native(self.ctx.current_resolution, is_network_game=False)
            pygame.display.flip()

    def on_enter(self) -> None:
        """Called when entering game state."""
        self.ctx.show_pause_menu = False
        # Clear stale visual effects from previous games
        self.ctx.renderer.clear_all_effects()
        # Reset AI action timer
        self._ai_action_timer = 0.0

        # Set up viewing mode based on game type
        if self.ctx.is_ai_vs_ai:
            # AI vs AI mode: always view from P1 perspective
            self.ctx.match_client = self.ctx.client_p1
            self.ctx.client = self.ctx.match_client.game_client
            self.ctx.renderer.viewing_player = 1
        elif self.ctx.ai_player:
            # Human vs AI mode: human always views from their perspective
            human = self.ctx.human_player
            self.ctx.match_client = self.ctx.client_p1 if human == 1 else self.ctx.client_p2
            self.ctx.client = self.ctx.match_client.game_client
            self.ctx.renderer.viewing_player = human
        else:
            # Hotseat: Initialize active player and viewing_player immediately
            self._update_active_player()

    def on_exit(self) -> None:
        """Called when leaving game state."""
        self.ctx.show_pause_menu = False
