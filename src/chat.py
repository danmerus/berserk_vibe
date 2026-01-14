"""Chat UI component for network games."""

import pygame
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from .text_input import TextInput, draw_text_input_field
from .constants import COLOR_TEXT, COLOR_BG, COLOR_SELF, COLOR_OPPONENT, UILayout


@dataclass
class ChatMessage:
    """A single chat message."""
    player_name: str
    text: str
    player_number: int = 0  # 1 or 2, 0 for system messages
    timestamp: float = field(default_factory=time.time)
    is_system: bool = False  # True for system messages (join/leave/etc)


@dataclass
class ChatUI:
    """Chat window UI component."""

    # Position and size (will be set by parent)
    x: int = 0
    y: int = 0
    width: int = 250
    height: int = 400

    # State
    messages: List[ChatMessage] = field(default_factory=list)
    scroll_offset: int = 0
    max_messages: int = 100

    # Text input
    text_input: TextInput = field(default_factory=lambda: TextInput(max_length=200))

    # Visual settings
    bg_color: tuple = (30, 30, 35)
    border_color: tuple = (60, 60, 70)
    input_height: int = 32
    title_height: int = 28
    message_padding: int = 4

    # Fonts (set externally)
    font: Optional[pygame.font.Font] = None
    font_small: Optional[pygame.font.Font] = None
    font_title: Optional[pygame.font.Font] = None

    # Callbacks
    on_send: Optional[Callable[[str], None]] = None

    # Our player number/name (to highlight our messages)
    my_player_number: int = 0  # 1 or 2
    my_player_name: str = ""   # For lobby chat where player_number is 0

    # Stored rects for click detection
    _input_rect: Optional[pygame.Rect] = None
    _messages_rect: Optional[pygame.Rect] = None

    def __post_init__(self):
        self.messages = []
        self.text_input = TextInput(max_length=200)

    def set_fonts(self, font: pygame.font.Font, font_small: pygame.font.Font, font_title: Optional[pygame.font.Font] = None):
        """Set fonts for rendering."""
        self.font = font
        self.font_small = font_small
        self.font_title = font_title if font_title else font

    def add_message(self, player_name: str, text: str, player_number: int = 0, is_system: bool = False):
        """Add a new chat message."""
        msg = ChatMessage(player_name=player_name, text=text, player_number=player_number, is_system=is_system)
        self.messages.append(msg)

        # Remove old messages if over limit
        while len(self.messages) > self.max_messages:
            self.messages.pop(0)

        # Auto-scroll to bottom
        self.scroll_to_bottom()

    def add_system_message(self, text: str):
        """Add a system message (no player name)."""
        self.add_message("", text, is_system=True)

    def scroll_to_bottom(self):
        """Scroll to show the latest messages."""
        self.scroll_offset = 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle pygame event. Returns True if event was consumed."""
        # Handle text input events
        if self.text_input.active:
            result = self.text_input.handle_event(event)
            if result == 'submit':
                self._send_message()
                return True
            elif result == 'cancel':
                self.text_input.deactivate()
                return True
            elif result is None and event.type in (pygame.KEYDOWN, pygame.TEXTINPUT):
                return True

        # Handle mouse events for text input
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._input_rect and self._input_rect.collidepoint(event.pos):
                if not self.text_input.active:
                    self.text_input.activate()
                # Handle click in text input
                if self.font_small:
                    self.text_input.handle_mouse_event(event, self._input_rect, self.font_small)
                return True
            elif self._messages_rect and self._messages_rect.collidepoint(event.pos):
                # Click in messages area - deactivate input
                if self.text_input.active:
                    self.text_input.deactivate()
                return True

        # Handle mouse motion for drag selection
        if event.type == pygame.MOUSEMOTION and self.text_input.active:
            if self._input_rect and self.font_small:
                self.text_input.handle_mouse_event(event, self._input_rect, self.font_small)
                return True

        # Handle mouse up
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.text_input.active and self._input_rect and self.font_small:
                self.text_input.handle_mouse_event(event, self._input_rect, self.font_small)
                return True

        # Handle scroll in messages area
        if event.type == pygame.MOUSEWHEEL:
            if self._messages_rect:
                mouse_pos = pygame.mouse.get_pos()
                if self._messages_rect.collidepoint(mouse_pos):
                    self.scroll_offset += event.y * 20
                    self.scroll_offset = max(0, self.scroll_offset)
                    return True

        return False

    def _send_message(self):
        """Send the current input as a chat message."""
        text = self.text_input.value.strip()
        if text and self.on_send:
            self.on_send(text)
        self.text_input.clear()

    def draw(self, screen: pygame.Surface):
        """Draw the chat UI."""
        if not self.font or not self.font_small:
            return

        # Background
        bg_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(screen, self.bg_color, bg_rect)
        pygame.draw.rect(screen, self.border_color, bg_rect, 1)

        # Title bar
        title_rect = pygame.Rect(self.x, self.y, self.width, self.title_height)
        pygame.draw.rect(screen, (40, 40, 50), title_rect)
        pygame.draw.line(screen, self.border_color,
                        (self.x, self.y + self.title_height),
                        (self.x + self.width, self.y + self.title_height))

        title_font = self.font_title if self.font_title else self.font_small
        title_text = title_font.render("Чат", True, COLOR_TEXT)
        title_x = self.x + (self.width - title_text.get_width()) // 2
        title_y = self.y + (self.title_height - title_text.get_height()) // 2
        screen.blit(title_text, (title_x, title_y))

        # Messages area
        messages_y = self.y + self.title_height + 2
        messages_height = self.height - self.title_height - self.input_height - 8
        self._messages_rect = pygame.Rect(self.x + 2, messages_y, self.width - 4, messages_height)

        # Create clip rect for messages
        screen.set_clip(self._messages_rect)

        # Draw messages from bottom up
        y = messages_y + messages_height - self.message_padding + self.scroll_offset

        for msg in reversed(self.messages):
            # Render message
            if msg.is_system:
                # System message (centered, gray)
                text_surface = self.font_small.render(msg.text, True, (150, 150, 150))
                text_x = self.x + (self.width - text_surface.get_width()) // 2
                y -= text_surface.get_height() + 2
                if y + text_surface.get_height() > messages_y:
                    screen.blit(text_surface, (text_x, y))
            else:
                # Regular message
                # Name color based on player number or name (blue for you, red for others)
                is_my_message = False
                if msg.player_number != 0 and msg.player_number == self.my_player_number:
                    is_my_message = True
                elif msg.player_number == 0 and msg.player_name == self.my_player_name:
                    # Lobby chat - compare names instead
                    is_my_message = True
                name_color = COLOR_SELF if is_my_message else COLOR_OPPONENT

                # Render name and text
                name_surface = self.font_small.render(f"{msg.player_name}: ", True, name_color)

                # Word wrap the text (handles long strings without spaces)
                max_text_width = self.width - 12 - name_surface.get_width()
                lines = self._wrap_text(msg.text, max_text_width)

                # Draw lines (bottom to top)
                for i, line in enumerate(reversed(lines)):
                    text_surface = self.font_small.render(line, True, COLOR_TEXT)
                    line_height = text_surface.get_height() + 2
                    y -= line_height

                    if y + line_height > messages_y:
                        if i == len(lines) - 1:  # First line (last in reversed)
                            screen.blit(name_surface, (self.x + 6, y))
                            screen.blit(text_surface, (self.x + 6 + name_surface.get_width(), y))
                        else:
                            # Continuation lines indented
                            screen.blit(text_surface, (self.x + 6 + name_surface.get_width(), y))

                y -= 2  # Extra spacing between messages

            # Stop if we've drawn past the visible area
            if y < messages_y - 100:
                break

        # Remove clip
        screen.set_clip(None)

        # Input area
        input_y = self.y + self.height - self.input_height - 4
        self._input_rect = draw_text_input_field(
            screen, self.font_small, self.text_input,
            self.x + 4, input_y, self.width - 8, self.input_height,
            bg_color=(35, 35, 45),
            bg_active_color=(45, 45, 55),
            border_color=(70, 70, 80),
            border_active_color=(100, 80, 120),
        )

        # Hint text if input is empty and not active (centered)
        if not self.text_input.active and not self.text_input.value:
            hint = self.font_small.render("Нажмите чтобы написать...", True, (100, 100, 110))
            hint_x = self._input_rect.x + (self._input_rect.width - hint.get_width()) // 2
            hint_y = input_y + (self.input_height - hint.get_height()) // 2
            screen.blit(hint, (hint_x, hint_y))

    def is_input_focused(self) -> bool:
        """Check if the text input is currently focused."""
        return self.text_input.active

    def _wrap_text(self, text: str, max_width: int) -> List[str]:
        """Wrap text to fit within max_width, breaking long words if needed."""
        if not self.font_small:
            return [text]

        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            # Check if word itself is too long
            word_surface = self.font_small.render(word, True, COLOR_TEXT)
            if word_surface.get_width() > max_width:
                # Word is too long, need to break it character by character
                if current_line:
                    lines.append(current_line)
                    current_line = ""

                # Break long word
                current_word = ""
                for char in word:
                    test_word = current_word + char
                    test_surface = self.font_small.render(test_word, True, COLOR_TEXT)
                    if test_surface.get_width() > max_width and current_word:
                        lines.append(current_word)
                        current_word = char
                    else:
                        current_word = test_word
                if current_word:
                    current_line = current_word
            else:
                # Normal word, try to add to current line
                test_line = current_line + (" " if current_line else "") + word
                test_surface = self.font_small.render(test_line, True, COLOR_TEXT)
                if test_surface.get_width() <= max_width or not current_line:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word

        if current_line:
            lines.append(current_line)

        return lines if lines else [""]
