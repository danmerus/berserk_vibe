"""
Reusable UI components for consistent styling.
"""
import pygame
from typing import Optional, Tuple, Callable
from dataclasses import dataclass, field


@dataclass
class ButtonStyle:
    """Style configuration for buttons."""
    bg: Tuple[int, int, int] = (60, 60, 70)
    bg_hover: Tuple[int, int, int] = (80, 80, 90)
    bg_pressed: Tuple[int, int, int] = (50, 50, 60)
    bg_disabled: Tuple[int, int, int] = (40, 40, 45)
    border: Tuple[int, int, int] = (100, 100, 110)
    border_hover: Tuple[int, int, int] = (120, 120, 130)
    border_disabled: Tuple[int, int, int] = (70, 70, 80)
    text: Tuple[int, int, int] = (240, 240, 240)
    text_disabled: Tuple[int, int, int] = (100, 100, 110)
    border_width: int = 2
    border_radius: int = 4


@dataclass
class PanelStyle:
    """Style configuration for panels."""
    bg: Tuple[int, int, int, int] = (40, 40, 50, 230)  # RGBA
    border: Tuple[int, int, int] = (80, 80, 100)
    border_width: int = 2
    border_radius: int = 0
    padding: int = 10


# Predefined button styles
BUTTON_STYLES = {
    'default': ButtonStyle(),
    'menu': ButtonStyle(
        bg=(60, 50, 70),
        bg_hover=(80, 70, 90),
        border=(120, 100, 140),
        border_hover=(140, 120, 160),
    ),
    'danger': ButtonStyle(
        bg=(100, 50, 50),
        bg_hover=(120, 60, 60),
        border=(150, 80, 80),
    ),
    'success': ButtonStyle(
        bg=(50, 100, 50),
        bg_hover=(60, 120, 60),
        border=(80, 150, 80),
    ),
    'draw_normal': ButtonStyle(
        bg=(60, 60, 70),
        bg_hover=(70, 70, 80),
        border=(100, 100, 110),
        text=(200, 200, 200),
    ),
    'draw_accept': ButtonStyle(
        bg=(70, 130, 70),
        bg_hover=(80, 140, 80),
        border=(100, 180, 100),
        text=(240, 240, 240),
    ),
    'draw_waiting': ButtonStyle(
        bg=(80, 80, 60),
        bg_hover=(80, 80, 60),  # No hover change when waiting
        border=(120, 120, 80),
        text=(180, 180, 150),
    ),
    'skip': ButtonStyle(
        bg=(80, 60, 60),
        bg_hover=(100, 80, 80),
        border=(140, 120, 120),
    ),
    'pass': ButtonStyle(
        bg=(60, 50, 80),
        bg_hover=(80, 70, 100),
        border=(100, 80, 140),
    ),
}

# Predefined panel styles
PANEL_STYLES = {
    'default': PanelStyle(),
    'popup': PanelStyle(
        bg=(40, 50, 60, 230),
        border=(80, 100, 120),
        border_width=2,
    ),
    'card_info': PanelStyle(
        bg=(35, 35, 45, 230),
        border=(70, 70, 90),
        padding=10,
    ),
    'graveyard': PanelStyle(
        bg=(30, 30, 40, 200),
        border=(60, 60, 80),
        padding=5,
    ),
}


class Button:
    """
    Reusable button component with hover and click states.

    Usage:
        btn = Button(pygame.Rect(100, 100, 200, 40), "Click Me")
        btn.update(mouse_pos)  # Call each frame
        btn.draw(surface, font)
        if btn.clicked(mouse_pos, mouse_pressed):
            do_something()
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        style: str = 'default',
        enabled: bool = True,
        custom_style: Optional[ButtonStyle] = None
    ):
        """
        Initialize button.

        Args:
            rect: Button rectangle (position and size)
            text: Button label
            style: Style name from BUTTON_STYLES
            enabled: Whether button is clickable
            custom_style: Override style with custom ButtonStyle
        """
        self.rect = rect
        self.text = text
        self.style = custom_style or BUTTON_STYLES.get(style, BUTTON_STYLES['default'])
        self.enabled = enabled
        self.hovered = False
        self.pressed = False
        self._was_pressed = False

    def update(self, mouse_pos: Tuple[int, int], mouse_pressed: bool = False):
        """
        Update button state based on mouse position.

        Args:
            mouse_pos: Current mouse position
            mouse_pressed: Whether left mouse button is down
        """
        self.hovered = self.rect.collidepoint(mouse_pos) if self.enabled else False
        self._was_pressed = self.pressed
        self.pressed = self.hovered and mouse_pressed

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        """
        Draw the button.

        Args:
            surface: Surface to draw on
            font: Font for button text
        """
        style = self.style

        # Determine colors based on state
        if not self.enabled:
            bg = style.bg_disabled
            border = style.border_disabled
            text_color = style.text_disabled
        elif self.pressed:
            bg = style.bg_pressed
            border = style.border_hover
            text_color = style.text
        elif self.hovered:
            bg = style.bg_hover
            border = style.border_hover
            text_color = style.text
        else:
            bg = style.bg
            border = style.border
            text_color = style.text

        # Draw background
        pygame.draw.rect(surface, bg, self.rect, border_radius=style.border_radius)

        # Draw border
        if style.border_width > 0:
            pygame.draw.rect(surface, border, self.rect, style.border_width,
                           border_radius=style.border_radius)

        # Draw text centered
        text_surface = font.render(self.text, True, text_color)
        text_x = self.rect.x + (self.rect.width - text_surface.get_width()) // 2
        text_y = self.rect.y + (self.rect.height - text_surface.get_height()) // 2
        surface.blit(text_surface, (text_x, text_y))

    def clicked(self, mouse_pos: Tuple[int, int], mouse_just_pressed: bool) -> bool:
        """
        Check if button was clicked this frame.

        Args:
            mouse_pos: Current mouse position
            mouse_just_pressed: Whether mouse was just pressed (not held)

        Returns:
            True if button was clicked
        """
        return self.enabled and self.rect.collidepoint(mouse_pos) and mouse_just_pressed

    def set_style(self, style_name: str):
        """Change button style by name."""
        self.style = BUTTON_STYLES.get(style_name, BUTTON_STYLES['default'])

    def set_text(self, text: str):
        """Update button text."""
        self.text = text


class Panel:
    """
    Reusable panel component for UI containers.

    Usage:
        panel = Panel(pygame.Rect(50, 50, 300, 200))
        panel.draw(surface)
    """

    def __init__(
        self,
        rect: pygame.Rect,
        style: str = 'default',
        custom_style: Optional[PanelStyle] = None
    ):
        """
        Initialize panel.

        Args:
            rect: Panel rectangle
            style: Style name from PANEL_STYLES
            custom_style: Override style with custom PanelStyle
        """
        self.rect = rect
        self.style = custom_style or PANEL_STYLES.get(style, PANEL_STYLES['default'])

    def draw(self, surface: pygame.Surface):
        """
        Draw the panel background and border.

        Args:
            surface: Surface to draw on
        """
        style = self.style

        # Create surface with alpha for semi-transparent bg
        if len(style.bg) == 4:
            panel_surface = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
            panel_surface.fill(style.bg)
            surface.blit(panel_surface, (self.rect.x, self.rect.y))
        else:
            pygame.draw.rect(surface, style.bg, self.rect, border_radius=style.border_radius)

        # Draw border
        if style.border_width > 0:
            pygame.draw.rect(surface, style.border, self.rect, style.border_width,
                           border_radius=style.border_radius)

    def get_content_rect(self) -> pygame.Rect:
        """Get the inner content area (accounting for padding)."""
        p = self.style.padding
        return pygame.Rect(
            self.rect.x + p,
            self.rect.y + p,
            self.rect.width - 2 * p,
            self.rect.height - 2 * p
        )


def draw_button_simple(
    surface: pygame.Surface,
    rect: pygame.Rect,
    text: str,
    font: pygame.font.Font,
    style: str = 'default',
    hovered: bool = False
) -> pygame.Rect:
    """
    Draw a button without tracking state (stateless utility).
    Good for simple one-off buttons where hover state is externally tracked.

    Args:
        surface: Surface to draw on
        rect: Button rectangle
        text: Button label
        font: Font for text
        style: Style name from BUTTON_STYLES
        hovered: Whether to draw in hovered state

    Returns:
        The button rect (for click detection)
    """
    btn_style = BUTTON_STYLES.get(style, BUTTON_STYLES['default'])

    # Choose colors based on hover
    if hovered:
        bg = btn_style.bg_hover
        border = btn_style.border_hover
    else:
        bg = btn_style.bg
        border = btn_style.border

    # Draw background
    pygame.draw.rect(surface, bg, rect, border_radius=btn_style.border_radius)

    # Draw border
    if btn_style.border_width > 0:
        pygame.draw.rect(surface, border, rect, btn_style.border_width,
                       border_radius=btn_style.border_radius)

    # Draw text centered
    text_surface = font.render(text, True, btn_style.text)
    text_x = rect.x + (rect.width - text_surface.get_width()) // 2
    text_y = rect.y + (rect.height - text_surface.get_height()) // 2
    surface.blit(text_surface, (text_x, text_y))

    return rect


class ButtonGroup:
    """
    Manages a group of buttons for menus.

    Usage:
        group = ButtonGroup()
        group.add('play', Button(...))
        group.add('quit', Button(...))
        group.update(mouse_pos, mouse_pressed)
        group.draw(surface, font)
        clicked_id = group.get_clicked(mouse_pos, mouse_just_pressed)
    """

    def __init__(self):
        self.buttons: dict[str, Button] = {}
        self._order: list[str] = []

    def add(self, button_id: str, button: Button):
        """Add a button to the group."""
        self.buttons[button_id] = button
        if button_id not in self._order:
            self._order.append(button_id)

    def remove(self, button_id: str):
        """Remove a button from the group."""
        if button_id in self.buttons:
            del self.buttons[button_id]
            self._order.remove(button_id)

    def clear(self):
        """Remove all buttons."""
        self.buttons.clear()
        self._order.clear()

    def update(self, mouse_pos: Tuple[int, int], mouse_pressed: bool = False):
        """Update all buttons."""
        for button in self.buttons.values():
            button.update(mouse_pos, mouse_pressed)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        """Draw all buttons in order."""
        for button_id in self._order:
            self.buttons[button_id].draw(surface, font)

    def get_clicked(self, mouse_pos: Tuple[int, int], mouse_just_pressed: bool) -> Optional[str]:
        """
        Get the ID of clicked button, if any.

        Returns:
            Button ID or None
        """
        for button_id, button in self.buttons.items():
            if button.clicked(mouse_pos, mouse_just_pressed):
                return button_id
        return None

    def get(self, button_id: str) -> Optional[Button]:
        """Get button by ID."""
        return self.buttons.get(button_id)
