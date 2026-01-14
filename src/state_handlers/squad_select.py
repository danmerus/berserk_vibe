"""Squad selection state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler
from .helpers import get_phase_state, handle_prep_pause_menu_event, render_prep_pause_menu

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class SquadSelectHandler(StateHandler):
    """Handler for squad selection state.

    Handles:
    - Selecting cards from hand to add to squad
    - Removing cards from squad
    - Mulligan (reshuffle hand for gold)
    - Squad validation and confirmation
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)

    def _get_builders(self):
        """Get the active squad builder and renderer."""
        sb = get_phase_state(
            self.ctx.network_prep_state,
            self.ctx.local_game_state,
            'squad_builder'
        )
        sr = get_phase_state(
            self.ctx.network_prep_state,
            self.ctx.local_game_state,
            'squad_renderer'
        )
        return sb, sr

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle squad selection events."""
        from ..constants import AppState, UILayout

        sb, sr = self._get_builders()
        if not sb or not sr:
            return None

        # Handle pause menu first
        result = handle_prep_pause_menu_event(self.ctx, event)
        if result is not False:  # False means not in pause menu
            return result

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event, sr)

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = self.ctx.renderer.screen_to_game_coords(*pygame.mouse.get_pos())
            if my < UILayout.DECK_BUILDER_DECK_Y:
                sr.scroll_hand(event.y)
            else:
                sr.scroll_squad(event.y)
            return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my, sb, sr)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_right_click(mx, my, sr)

        return None

    def _handle_keydown(self, event: pygame.event.Event, sr) -> Optional['AppState']:
        """Handle key press in squad selection."""
        if event.key == pygame.K_ESCAPE:
            if sr.popup_card_name:
                sr.hide_card_popup()
            else:
                self.ctx.show_pause_menu = True
        return None

    def _handle_click(self, mx: int, my: int, sb, sr) -> Optional['AppState']:
        """Handle left click in squad selection."""
        from ..constants import AppState
        from ..placement import PlacementState
        from ..placement_renderer import PlacementRenderer
        from ..squad_builder import SquadBuilder
        from ..squad_builder_renderer import SquadBuilderRenderer

        # Handle popup first
        if sr.popup_card_name:
            sr.hide_card_popup()
            return None

        # Check button clicks
        btn = sr.get_clicked_button(mx, my)
        if btn == 'mulligan':
            if sb.mulligan():
                sr.show_notification("Карты пересданы")
            else:
                sr.show_notification("Недостаточно золота")
            return None

        elif btn == 'confirm':
            if not sb.is_valid():
                return None

            squad = sb.finalize()

            # Network game
            if self.ctx.network_prep_state is not None:
                self.ctx.network_prep_state['squad'] = squad
                my_player = self.ctx.network_ui.my_player_number if self.ctx.network_ui else 1
                ps = PlacementState(player=my_player, squad_cards=squad)
                s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
                pr = PlacementRenderer(s, ci, f)
                pr.custom_header = "Расстановка - Сетевая игра"
                self.ctx.network_prep_state['placement_state'] = ps
                self.ctx.network_prep_state['placement_renderer'] = pr
                return AppState.SQUAD_PLACE

            # Local game flow
            player = self.ctx.local_game_state['current_player']
            if player == 1:
                self.ctx.local_game_state['squad_p1'] = squad
                self.ctx.local_game_state['current_player'] = 2
                sb = SquadBuilder(player=2, deck_cards=self.ctx.local_game_state['deck_p2'])
                s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
                sr = SquadBuilderRenderer(s, ci, f)
                self.ctx.local_game_state['squad_builder'] = sb
                self.ctx.local_game_state['squad_renderer'] = sr
                return None  # Stay in SQUAD_SELECT
            else:
                self.ctx.local_game_state['squad_p2'] = squad
                self.ctx.local_game_state['current_player'] = 1
                ps = PlacementState(player=1, squad_cards=self.ctx.local_game_state['squad_p1'])
                s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
                pr = PlacementRenderer(s, ci, f)
                self.ctx.local_game_state['placement_state'] = ps
                self.ctx.local_game_state['placement_renderer'] = pr
                return AppState.SQUAD_PLACE

        # Card clicks
        if not btn:
            card = sr.get_clicked_hand_card(mx, my)
            if card:
                if not sb.add_card(card):
                    _, reason = sb.can_add_card(card)
                    sr.show_notification(reason)
                return None

            card = sr.get_clicked_squad_card(mx, my)
            if card:
                sb.remove_card(card)
                return None

        return None

    def _handle_right_click(self, mx: int, my: int, sr) -> Optional['AppState']:
        """Handle right click (show card popup)."""
        card = sr.get_clicked_hand_card(mx, my)
        if card:
            sr.show_card_popup(card)
            return None

        card = sr.get_clicked_squad_card(mx, my)
        if card:
            sr.show_card_popup(card)
            return None

        return None

    def update(self, dt: float) -> Optional['AppState']:
        """Update squad selection state."""
        _, sr = self._get_builders()
        if sr:
            sr.update_notification()
        return None

    def render(self) -> None:
        """Render the squad selection."""
        sb, sr = self._get_builders()
        if sb and sr:
            _, _, card_images_full, _ = self.ctx.renderer.get_deck_builder_resources()
            sr.draw(sb, card_images_full)

            if render_prep_pause_menu(self.ctx):
                return
            self.ctx.renderer.finalize_frame()

    def on_enter(self) -> None:
        """Called when entering squad selection state."""
        self.ctx.show_pause_menu = False
