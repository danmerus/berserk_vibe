"""Visual effects - floating text, arrows, card animations."""
import pygame
import math
from typing import Tuple, List, Dict, TYPE_CHECKING

from ..constants import CELL_SIZE, scaled, UILayout

if TYPE_CHECKING:
    from ..game import Game


class EffectsMixin:
    """Mixin for visual effects and animations."""

    def add_floating_text(self, board_pos: int, text: str, color: Tuple[int, int, int]):
        """Add a floating text effect at a board position."""
        from ..board import Board

        # For flying positions, store board_pos and recalculate screen position each frame
        # This ensures the text follows the card if positions shift (e.g., when another flyer dies)
        is_flying = board_pos >= Board.FLYING_P1_START

        if is_flying:
            # Store board position for dynamic recalculation
            self.floating_texts.append({
                'board_pos': board_pos,
                'y_offset': 0,  # Accumulated float offset
                'text': text,
                'color': color,
                'life': 1.0,
                'max_life': 1.0
            })
        else:
            # For ground cards, calculate position once (they don't shift)
            x, y = self.pos_to_screen(board_pos)
            x += CELL_SIZE // 2
            y += CELL_SIZE // 2
            self.floating_texts.append({
                'x': x,
                'y': y,
                'text': text,
                'color': color,
                'life': 1.0,
                'max_life': 1.0
            })

    def update_floating_texts(self, dt: float):
        """Update floating text positions and lifetimes."""
        for ft in self.floating_texts:
            ft['life'] -= dt
            # Update position - flying texts use y_offset, ground texts use y
            if 'y_offset' in ft:
                ft['y_offset'] -= 40 * dt  # Float upward
            else:
                ft['y'] -= 40 * dt  # Float upward
        # Remove dead texts
        self.floating_texts = [ft for ft in self.floating_texts if ft['life'] > 0]

    def draw_floating_texts(self, game: 'Game' = None):
        """Draw all floating text effects."""
        for ft in self.floating_texts:
            alpha = int(255 * (ft['life'] / ft['max_life']))
            # Create text surface
            text_surface = self.font_large.render(ft['text'], True, ft['color'])
            # Apply alpha by creating a copy with per-pixel alpha
            text_surface.set_alpha(alpha)

            # Get screen position - flying texts recalculate each frame
            if 'board_pos' in ft:
                # Flying text - recalculate position to follow card using unified method
                # Pass game so pos_to_screen can calculate correct visual index for shifted flyers
                x, y = self.pos_to_screen(ft['board_pos'], game)
                card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
                x += card_size // 2
                y += card_size // 2 + ft['y_offset']
            else:
                # Ground text - use stored position
                x = ft['x']
                y = ft['y']

            # Center text
            text_x = x - text_surface.get_width() // 2
            text_y = int(y) - text_surface.get_height() // 2
            self.screen.blit(text_surface, (text_x, text_y))

    def add_arrow(self, from_pos: int, to_pos: int, color: Tuple[int, int, int]):
        """Add an interaction arrow between two board positions."""
        self.arrows.append({
            'from_pos': from_pos,
            'to_pos': to_pos,
            'color': color,
            'min_display': 1.0,  # Minimum display time in seconds
        })

    def clear_arrows(self):
        """Mark all arrows to clear after minimum display time."""
        for arrow in self.arrows:
            # Mark for clearing - will be removed after min_display reaches 0
            arrow['clearing'] = True

    def clear_arrows_immediate(self):
        """Clear all arrows immediately (for cancellation)."""
        self.arrows.clear()

    def update_arrows(self, dt: float):
        """Update arrow timers."""
        for arrow in self.arrows:
            arrow['min_display'] -= dt
        # Remove arrows that are marked for clearing AND have shown for minimum time
        self.arrows = [a for a in self.arrows
                       if not (a.get('clearing') and a['min_display'] <= 0)]

    def draw_arrows(self, game: 'Game' = None):
        """Draw all interaction arrows."""
        for arrow in self.arrows:
            alpha = 255  # Full opacity until cleared

            # Get screen positions (center of cells)
            # Pass game for accurate flying zone positioning
            from_x, from_y = self.pos_to_screen(arrow['from_pos'], game)
            to_x, to_y = self.pos_to_screen(arrow['to_pos'], game)
            from_x += CELL_SIZE // 2
            from_y += CELL_SIZE // 2
            to_x += CELL_SIZE // 2
            to_y += CELL_SIZE // 2

            # Calculate arrow direction
            dx = to_x - from_x
            dy = to_y - from_y
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1:
                continue

            # Normalize direction
            dx /= length
            dy /= length

            # Shorten arrow to not overlap cards
            margin = 45
            start_x = from_x + dx * margin
            start_y = from_y + dy * margin
            end_x = to_x - dx * margin
            end_y = to_y - dy * margin

            # Create surface for arrow with alpha
            arrow_surface = pygame.Surface((self.BASE_WIDTH, self.BASE_HEIGHT), pygame.SRCALPHA)

            # Draw arrow line (thick)
            color_with_alpha = (*arrow['color'], alpha)
            pygame.draw.line(arrow_surface, color_with_alpha,
                           (int(start_x), int(start_y)),
                           (int(end_x), int(end_y)), 4)

            # Draw arrowhead
            head_length = 15
            head_angle = math.pi / 6  # 30 degrees

            # Calculate arrowhead points
            angle = math.atan2(dy, dx)
            head_x1 = end_x - head_length * math.cos(angle - head_angle)
            head_y1 = end_y - head_length * math.sin(angle - head_angle)
            head_x2 = end_x - head_length * math.cos(angle + head_angle)
            head_y2 = end_y - head_length * math.sin(angle + head_angle)

            pygame.draw.polygon(arrow_surface, color_with_alpha, [
                (int(end_x), int(end_y)),
                (int(head_x1), int(head_y1)),
                (int(head_x2), int(head_y2))
            ])

            self.screen.blit(arrow_surface, (0, 0))

    def update_card_animations(self, game: 'Game', dt: float):
        """Update card movement animations and detect new movements."""
        # Update existing animations
        finished = []
        for card_id, anim in self.card_animations.items():
            anim['progress'] += dt / self.CARD_MOVE_DURATION
            if anim['progress'] >= 1.0:
                finished.append(card_id)
        for card_id in finished:
            del self.card_animations[card_id]

        # Detect new card movements by comparing positions
        current_positions = {}
        for pos in range(36):  # All board positions including flying
            card = game.board.get_card(pos)
            if card:
                current_positions[card.id] = pos

        # Check for position changes
        for card_id, new_pos in current_positions.items():
            old_pos = self.card_last_positions.get(card_id)
            if old_pos is not None and old_pos != new_pos:
                # Card moved - start animation
                from_x, from_y = self.pos_to_screen(old_pos)
                to_x, to_y = self.pos_to_screen(new_pos)
                self.card_animations[card_id] = {
                    'from_x': from_x,
                    'from_y': from_y,
                    'to_x': to_x,
                    'to_y': to_y,
                    'progress': 0.0
                }

        # Update last known positions
        self.card_last_positions = current_positions

    def get_card_draw_position(self, card_id: int, base_x: int, base_y: int) -> Tuple[int, int]:
        """Get the position to draw a card, accounting for movement animation."""
        if card_id in self.card_animations:
            anim = self.card_animations[card_id]
            # Smooth easing function (ease-out)
            t = anim['progress']
            t = 1 - (1 - t) ** 2  # Quadratic ease-out
            x = int(anim['from_x'] + (anim['to_x'] - anim['from_x']) * t)
            y = int(anim['from_y'] + (anim['to_y'] - anim['from_y']) * t)
            return x, y
        return base_x, base_y

    def clear_all_effects(self):
        """Clear all visual effects. Call when starting a new game."""
        self.card_animations.clear()
        self.card_last_positions.clear()
        self.arrows.clear()
        self.floating_texts.clear()
        self.death_animations.clear()

    def start_death_animation(self, card: 'Card', pos: int, visual_index: int = -1):
        """Start a death animation for a card.

        Args:
            card: The card that died
            pos: The board position where the card was
            visual_index: For flying cards, the visual index at time of death (before removal)
        """
        from ..constants import CARD_WIDTH, CARD_HEIGHT
        from ..board import Board

        # Get screen position using unified method
        if pos >= Board.FLYING_P1_START:
            x, y = self.get_flying_screen_pos(pos, visual_index=visual_index)
        else:
            x, y = self.pos_to_screen(pos)

        # Capture the card surface for the animation
        card_surface = self._render_card_for_death(card, pos)

        self.death_animations[card.id] = {
            'timer': 0.0,
            'x': x,
            'y': y,
            'pos': pos,  # Store position for checking flying zone
            'surface': card_surface,
            'width': CARD_WIDTH,
            'height': CARD_HEIGHT,
        }

    def _render_card_for_death(self, card: 'Card', pos: int) -> pygame.Surface:
        """Render a card surface for death animation."""
        from ..constants import CARD_WIDTH, CARD_HEIGHT, COLOR_PLAYER1, COLOR_PLAYER2
        from ..card_database import get_card_image

        # Create surface for the card
        surface = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)

        # Get card image using the image mapping
        img_filename = get_card_image(card.name)
        if img_filename and img_filename in self.card_images:
            img = self.card_images[img_filename]
            # Scale to card size (image is 2x)
            scaled_img = pygame.transform.smoothscale(img, (CARD_WIDTH, CARD_HEIGHT))
            surface.blit(scaled_img, (0, 0))
        else:
            # Fallback: solid color
            color = COLOR_PLAYER1 if card.player == 1 else COLOR_PLAYER2
            surface.fill(color)

        # Draw border
        border_color = COLOR_PLAYER1 if card.player == 1 else COLOR_PLAYER2
        pygame.draw.rect(surface, border_color, surface.get_rect(), 2)

        return surface

    def update_death_animations(self, dt: float):
        """Update death animation timers."""
        finished = []
        for card_id, anim in self.death_animations.items():
            anim['timer'] += dt
            if anim['timer'] >= self.DEATH_ANIM_DURATION:
                finished.append(card_id)
        for card_id in finished:
            del self.death_animations[card_id]

    def draw_death_animations(self):
        """Draw all active death animations."""
        from ..constants import CARD_WIDTH, CARD_HEIGHT

        for card_id, anim in self.death_animations.items():
            t = anim['timer'] / self.DEATH_ANIM_DURATION
            pop_t = self.DEATH_POP_DURATION / self.DEATH_ANIM_DURATION

            # Calculate scale: pop up then shrink
            if t < pop_t:
                # Pop phase: scale from 1.0 to 1.15
                pop_progress = t / pop_t
                scale = 1.0 + 0.15 * pop_progress
                alpha = 255
            else:
                # Shrink phase: scale from 1.15 to 0
                shrink_progress = (t - pop_t) / (1.0 - pop_t)
                # Ease out for smooth shrink
                shrink_progress = shrink_progress ** 0.5
                scale = 1.15 * (1.0 - shrink_progress)
                # Fade out during shrink
                alpha = int(255 * (1.0 - shrink_progress))

            if scale <= 0.01:
                continue

            # Calculate scaled size
            new_width = int(CARD_WIDTH * scale)
            new_height = int(CARD_HEIGHT * scale)

            if new_width < 1 or new_height < 1:
                continue

            # Scale the surface
            scaled_surface = pygame.transform.smoothscale(anim['surface'], (new_width, new_height))
            scaled_surface.set_alpha(alpha)

            # Center on original position
            center_x = anim['x'] + CARD_WIDTH // 2
            center_y = anim['y'] + CARD_HEIGHT // 2
            draw_x = center_x - new_width // 2
            draw_y = center_y - new_height // 2

            self.screen.blit(scaled_surface, (draw_x, draw_y))

    def is_card_dying(self, card_id: int) -> bool:
        """Check if a card has an active death animation."""
        return card_id in self.death_animations

    def has_flying_death_animation(self, player: int) -> bool:
        """Check if there are active death animations for flying cards of a player.

        Used to delay the visual shift of surviving flyers until death animations complete.
        """
        from ..board import Board

        for card_id, anim in self.death_animations.items():
            pos = anim.get('pos', -1)
            if pos >= Board.FLYING_P1_START:
                if player == 1 and pos < Board.FLYING_P2_START:
                    return True
                if player == 2 and pos >= Board.FLYING_P2_START:
                    return True
        return False
