"""Squad placement state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler
from .helpers import get_phase_state

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class SquadPlaceHandler(StateHandler):
    """Handler for squad placement state.

    Handles:
    - Dragging cards onto the board
    - Card placement validation
    - Confirming placement to start game
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)

    def _get_placement(self):
        """Get the active placement state and renderer."""
        ps = get_phase_state(
            self.ctx.network_prep_state,
            self.ctx.local_game_state,
            'placement_state'
        )
        pr = get_phase_state(
            self.ctx.network_prep_state,
            self.ctx.local_game_state,
            'placement_renderer'
        )
        return ps, pr

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle placement events."""
        ps, pr = self._get_placement()
        if not ps or not pr:
            return None

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event, pr)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my, ps, pr)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_right_click(mx, my, ps, pr)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_mouse_up(mx, my, ps, pr)

        elif event.type == pygame.MOUSEMOTION:
            # Dragging is handled by render() which passes mouse_pos to pr.draw()
            return None

        return None

    def _handle_keydown(self, event: pygame.event.Event, pr) -> Optional['AppState']:
        """Handle key press in placement."""
        if event.key == pygame.K_ESCAPE:
            if self.ctx.renderer.popup_card:
                self.ctx.renderer.hide_popup()
        return None

    def _handle_click(self, mx: int, my: int, ps, pr) -> Optional['AppState']:
        """Handle left click in placement."""
        from ..constants import AppState
        from ..match import MatchServer, LocalMatchClient
        from ..placement import PlacementState
        from ..placement_renderer import PlacementRenderer

        # Check if already waiting for opponent (network)
        if self.ctx.network_prep_state and self.ctx.network_prep_state.get('waiting_for_opponent'):
            return None

        # Check confirm button
        if pr.is_confirm_clicked(mx, my) and ps.is_complete():
            placed_cards = ps.finalize()

            # Network game
            if self.ctx.network_prep_state is not None:
                self.ctx.network_prep_state['placed_cards'] = placed_cards
                if self.ctx.network_ui and self.ctx.network_ui.client:
                    placed_cards_data = [card.to_dict() for card in placed_cards]
                    self.ctx.network_ui.client.send_placement_done(placed_cards_data)
                    self.ctx.network_prep_state['waiting_for_opponent'] = True
                return None

            # Local game flow
            player = self.ctx.local_game_state['current_player']
            if player == 1:
                self.ctx.local_game_state['placed_cards_p1'] = placed_cards
                self.ctx.local_game_state['current_player'] = 2
                ps = PlacementState(player=2, squad_cards=self.ctx.local_game_state['squad_p2'])
                s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
                pr = PlacementRenderer(s, ci, f)
                self.ctx.local_game_state['placement_state'] = ps
                self.ctx.local_game_state['placement_renderer'] = pr
                return None  # Stay in SQUAD_PLACE
            else:
                self.ctx.local_game_state['placed_cards_p2'] = placed_cards
                # Start the game!
                server = MatchServer()
                server.setup_with_placement(
                    self.ctx.local_game_state['placed_cards_p1'],
                    self.ctx.local_game_state['placed_cards_p2']
                )
                client_p1 = LocalMatchClient(server, player=1)
                client_p2 = LocalMatchClient(server, player=2)

                self.ctx.server = server
                self.ctx.client_p1 = client_p1
                self.ctx.client_p2 = client_p2
                self.ctx.game = server.game
                self.ctx.match_client = client_p1  # P1 starts
                self.ctx.client = client_p1.game_client
                return AppState.GAME

        # Start card drag
        card = pr.get_unplaced_card_at(mx, my)
        if card:
            ox, oy = pr.get_card_center_offset()
            ps.start_drag(card, ox, oy)
            return None

        # Pick up placed card
        pos = pr.get_placed_position_at(mx, my)
        if pos is not None:
            card = ps.unplace_card(pos)
            if card:
                ox, oy = pr.get_card_center_offset()
                ps.start_drag(card, ox, oy)
                return None

        return None

    def _handle_right_click(self, mx: int, my: int, ps, pr) -> Optional['AppState']:
        """Handle right click (show card popup)."""
        renderer = self.ctx.renderer

        if renderer.popup_card:
            renderer.hide_popup()
        else:
            card = pr.get_card_at(mx, my, ps)
            if card:
                renderer.show_popup(card)

        return None

    def _handle_mouse_up(self, mx: int, my: int, ps, pr) -> Optional['AppState']:
        """Handle mouse button release (drop card)."""
        if ps.dragging_card:
            drop_pos = pr.get_drop_position(mx, my, ps)
            if drop_pos is not None:
                ps.place_card(ps.dragging_card, drop_pos)
            ps.stop_drag()
        return None

    def update(self, dt: float) -> Optional['AppState']:
        """Update placement state."""
        from ..constants import AppState

        # Poll network if waiting for opponent
        if self.ctx.network_prep_state and self.ctx.network_prep_state.get('waiting_for_opponent'):
            if self.ctx.network_ui and self.ctx.network_ui.client:
                self.ctx.network_ui.client.poll()

            # Check if game started (on_game_start callback sets network_game)
            if self.ctx.network_game is not None:
                return AppState.NETWORK_GAME

        return None

    def render(self) -> None:
        """Render the placement screen."""
        from ..constants import WINDOW_WIDTH, WINDOW_HEIGHT, scaled

        ps, pr = self._get_placement()
        if ps and pr:
            # Check if waiting for opponent
            waiting = (self.ctx.network_prep_state and
                       self.ctx.network_prep_state.get('waiting_for_opponent'))

            mouse_pos = self.ctx.renderer.screen_to_game_coords(*pygame.mouse.get_pos())
            pr.draw(ps, mouse_pos)

            if waiting:
                # Draw waiting overlay banner
                renderer = self.ctx.renderer
                banner_width = scaled(400)
                banner_height = scaled(60)
                banner_x = (WINDOW_WIDTH - banner_width) // 2
                banner_y = WINDOW_HEIGHT - banner_height - scaled(20)
                banner = pygame.Surface((banner_width, banner_height), pygame.SRCALPHA)
                banner.fill((0, 0, 0, 200))
                renderer.screen.blit(banner, (banner_x, banner_y))
                text = renderer.font_medium.render("Ожидание противника...", True, (255, 255, 255))
                text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, banner_y + banner_height // 2))
                renderer.screen.blit(text, text_rect)

            # Draw card popup if open
            self.ctx.renderer.draw_popup()

            self.ctx.renderer.finalize_frame()
