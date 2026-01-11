"""Unified text input handling for UI components."""

import pygame
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Tuple


@dataclass
class TextInput:
    """Reusable text input component with cursor, selection, and clipboard support."""

    value: str = ""
    cursor_pos: int = 0
    selection_start: int = -1  # -1 means no selection
    max_length: int = 100
    allowed_chars: Optional[str] = None  # None = all chars, or string of allowed chars
    uppercase: bool = False  # Force uppercase

    # Visual state
    active: bool = False
    cursor_visible: bool = True
    cursor_blink_time: float = field(default_factory=time.time)

    # Mouse drag selection
    _drag_selecting: bool = False

    # Callbacks
    on_change: Optional[Callable[[str], None]] = None
    on_submit: Optional[Callable[[str], None]] = None
    on_cancel: Optional[Callable[[], None]] = None

    @property
    def has_selection(self) -> bool:
        """Check if there's an active selection."""
        return self.selection_start >= 0 and self.selection_start != self.cursor_pos

    @property
    def selection_range(self) -> Tuple[int, int]:
        """Get selection range as (start, end) tuple."""
        if not self.has_selection:
            return (self.cursor_pos, self.cursor_pos)
        return (min(self.selection_start, self.cursor_pos),
                max(self.selection_start, self.cursor_pos))

    @property
    def selected_text(self) -> str:
        """Get the currently selected text."""
        if not self.has_selection:
            return ""
        start, end = self.selection_range
        return self.value[start:end]

    def clear_selection(self):
        """Clear the current selection."""
        self.selection_start = -1

    def select_all(self):
        """Select all text."""
        self.selection_start = 0
        self.cursor_pos = len(self.value)
        self.cursor_visible = True
        self.cursor_blink_time = time.time()

    def activate(self, initial_value: str = ""):
        """Activate text input."""
        self.value = initial_value
        self.cursor_pos = len(initial_value)
        self.selection_start = -1
        self.active = True
        self.cursor_visible = True
        self.cursor_blink_time = time.time()
        self._drag_selecting = False
        try:
            pygame.key.start_text_input()
        except Exception:
            pass

    def deactivate(self):
        """Deactivate text input."""
        self.active = False
        self.selection_start = -1
        self._drag_selecting = False
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass

    def clear(self):
        """Clear the input value."""
        self.value = ""
        self.cursor_pos = 0
        self.selection_start = -1
        if self.on_change:
            self.on_change(self.value)

    def set_value(self, value: str):
        """Set the input value."""
        if self.uppercase:
            value = value.upper()
        if self.allowed_chars:
            value = ''.join(c for c in value if c in self.allowed_chars)
        self.value = value[:self.max_length]
        self.cursor_pos = min(self.cursor_pos, len(self.value))
        self.selection_start = -1
        if self.on_change:
            self.on_change(self.value)

    def delete_selection(self) -> bool:
        """Delete selected text. Returns True if something was deleted."""
        if not self.has_selection:
            return False
        start, end = self.selection_range
        self.value = self.value[:start] + self.value[end:]
        self.cursor_pos = start
        self.selection_start = -1
        if self.on_change:
            self.on_change(self.value)
        return True

    def insert_text(self, text: str):
        """Insert text at cursor position (replaces selection if any)."""
        # Delete selection first if any
        self.delete_selection()

        if self.uppercase:
            text = text.upper()
        if self.allowed_chars:
            text = ''.join(c for c in text if c in self.allowed_chars)

        # Check max length
        available = self.max_length - len(self.value)
        text = text[:available]

        if text:
            self.value = self.value[:self.cursor_pos] + text + self.value[self.cursor_pos:]
            self.cursor_pos += len(text)
            if self.on_change:
                self.on_change(self.value)

    def delete_char(self, forward: bool = False):
        """Delete character at cursor (backspace or delete)."""
        # If there's a selection, delete it instead
        if self.delete_selection():
            return

        if forward:
            if self.cursor_pos < len(self.value):
                self.value = self.value[:self.cursor_pos] + self.value[self.cursor_pos + 1:]
                if self.on_change:
                    self.on_change(self.value)
        else:
            if self.cursor_pos > 0:
                self.value = self.value[:self.cursor_pos - 1] + self.value[self.cursor_pos:]
                self.cursor_pos -= 1
                if self.on_change:
                    self.on_change(self.value)

    def move_cursor(self, delta: int, extend_selection: bool = False):
        """Move cursor by delta positions. Optionally extend selection."""
        if extend_selection:
            # Start selection if not already selecting
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
        else:
            # Clear selection when moving without shift
            self.selection_start = -1

        self.cursor_pos = max(0, min(len(self.value), self.cursor_pos + delta))
        self.cursor_visible = True
        self.cursor_blink_time = time.time()

    def cursor_to_start(self, extend_selection: bool = False):
        """Move cursor to start."""
        if extend_selection:
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
        else:
            self.selection_start = -1

        self.cursor_pos = 0
        self.cursor_visible = True
        self.cursor_blink_time = time.time()

    def cursor_to_end(self, extend_selection: bool = False):
        """Move cursor to end."""
        if extend_selection:
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
        else:
            self.selection_start = -1

        self.cursor_pos = len(self.value)
        self.cursor_visible = True
        self.cursor_blink_time = time.time()

    def paste_from_clipboard(self) -> bool:
        """Paste text from clipboard. Returns True if successful."""
        try:
            pygame.scrap.init()
            data = pygame.scrap.get(pygame.SCRAP_TEXT)
            if data:
                text = data.decode('utf-8').rstrip('\x00').strip()
                if text:
                    self.insert_text(text)
                    return True
        except Exception:
            pass

        # Fallback methods
        try:
            import pyperclip
            text = pyperclip.paste()
            if text:
                self.insert_text(text)
                return True
        except ImportError:
            pass

        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-command', 'Get-Clipboard'],
                capture_output=True, text=True
            )
            text = result.stdout.strip()
            if text:
                self.insert_text(text)
                return True
        except Exception:
            pass

        return False

    def update_cursor_blink(self):
        """Update cursor blink state. Call every frame."""
        if time.time() - self.cursor_blink_time > 0.5:
            self.cursor_visible = not self.cursor_visible
            self.cursor_blink_time = time.time()

    def copy_to_clipboard(self) -> bool:
        """Copy selected text to clipboard. Returns True if successful."""
        if not self.has_selection:
            return False

        text = self.selected_text
        try:
            pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode('utf-8'))
            return True
        except Exception:
            pass

        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except ImportError:
            pass

        try:
            import subprocess
            subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
            return True
        except Exception:
            pass

        return False

    def cut_to_clipboard(self) -> bool:
        """Cut selected text to clipboard. Returns True if successful."""
        if self.copy_to_clipboard():
            self.delete_selection()
            return True
        return False

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """
        Handle pygame event.
        Returns:
            'submit' - Enter pressed
            'cancel' - Escape pressed
            None - Event handled or not relevant
        """
        if not self.active:
            return None

        # Handle TEXTINPUT events (actual character input)
        if event.type == pygame.TEXTINPUT:
            self.insert_text(event.text)
            return None

        # Handle KEYDOWN for control keys
        if event.type == pygame.KEYDOWN:
            shift_held = event.mod & pygame.KMOD_SHIFT
            ctrl_held = event.mod & pygame.KMOD_CTRL

            if event.key == pygame.K_RETURN:
                if self.on_submit:
                    self.on_submit(self.value)
                return 'submit'

            elif event.key == pygame.K_ESCAPE:
                if self.on_cancel:
                    self.on_cancel()
                return 'cancel'

            elif event.key == pygame.K_BACKSPACE:
                self.delete_char(forward=False)

            elif event.key == pygame.K_DELETE:
                self.delete_char(forward=True)

            elif event.key == pygame.K_LEFT:
                self.move_cursor(-1, extend_selection=shift_held)

            elif event.key == pygame.K_RIGHT:
                self.move_cursor(1, extend_selection=shift_held)

            elif event.key == pygame.K_HOME:
                self.cursor_to_start(extend_selection=shift_held)

            elif event.key == pygame.K_END:
                self.cursor_to_end(extend_selection=shift_held)

            elif event.key == pygame.K_a and ctrl_held:
                self.select_all()

            elif event.key == pygame.K_c and ctrl_held:
                self.copy_to_clipboard()

            elif event.key == pygame.K_x and ctrl_held:
                self.cut_to_clipboard()

            elif event.key == pygame.K_v and ctrl_held:
                self.paste_from_clipboard()

        return None

    def handle_mouse_event(
        self,
        event: pygame.event.Event,
        field_rect: pygame.Rect,
        font: pygame.font.Font,
    ) -> bool:
        """
        Handle mouse events for click-to-position and drag selection.
        Returns True if event was handled.
        """
        if not self.active:
            return False

        text_x = field_rect.x + 10

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if field_rect.collidepoint(event.pos):
                # Calculate character index at click position
                char_idx = self._get_char_index_at_pos(font, text_x, event.pos[0])

                # Check for shift-click to extend selection
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    if self.selection_start < 0:
                        self.selection_start = self.cursor_pos
                    self.cursor_pos = char_idx
                else:
                    # Start new selection
                    self.cursor_pos = char_idx
                    self.selection_start = char_idx
                    self._drag_selecting = True

                self.cursor_visible = True
                self.cursor_blink_time = time.time()
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._drag_selecting:
                self._drag_selecting = False
                # If no actual selection (start == end), clear it
                if self.selection_start == self.cursor_pos:
                    self.selection_start = -1
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self._drag_selecting:
                # Extend selection while dragging
                char_idx = self._get_char_index_at_pos(font, text_x, event.pos[0])
                self.cursor_pos = char_idx
                self.cursor_visible = True
                self.cursor_blink_time = time.time()
                return True

        return False

    def _get_char_index_at_pos(self, font: pygame.font.Font, text_x: int, click_x: int) -> int:
        """Get character index at a given x position."""
        if click_x <= text_x:
            return 0

        value = self.value
        for i in range(len(value) + 1):
            char_width = font.render(value[:i], True, (0, 0, 0)).get_width()
            if text_x + char_width >= click_x:
                # Check if click is closer to this char or the previous one
                if i > 0:
                    prev_width = font.render(value[:i-1], True, (0, 0, 0)).get_width()
                    if click_x - (text_x + prev_width) < (text_x + char_width) - click_x:
                        return i - 1
                return i

        return len(value)


def draw_text_input_field(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text_input: TextInput,
    x: int, y: int, width: int, height: int,
    bg_color: tuple = (40, 40, 50),
    bg_active_color: tuple = (50, 50, 60),
    border_color: tuple = (80, 80, 90),
    border_active_color: tuple = (120, 100, 140),
    text_color: tuple = (240, 240, 240),
    selection_color: tuple = (70, 100, 150),
) -> pygame.Rect:
    """
    Draw a text input field with selection support.
    Returns the rect for click detection.
    """
    rect = pygame.Rect(x, y, width, height)

    # Background
    bg = bg_active_color if text_input.active else bg_color
    border = border_active_color if text_input.active else border_color
    pygame.draw.rect(screen, bg, rect)
    pygame.draw.rect(screen, border, rect, 2)

    # Update cursor blink
    if text_input.active:
        text_input.update_cursor_blink()

    # Calculate text position
    text_x = x + 10
    text_y = y + (height - font.get_height()) // 2

    value = text_input.value

    # Draw selection highlight if active
    if text_input.active and text_input.has_selection:
        sel_start, sel_end = text_input.selection_range

        # Calculate pixel positions for selection
        before_sel = font.render(value[:sel_start], True, text_color)
        selected = font.render(value[sel_start:sel_end], True, text_color)

        sel_x = text_x + before_sel.get_width()
        sel_width = selected.get_width()

        # Draw selection rectangle
        sel_rect = pygame.Rect(sel_x, text_y, sel_width, font.get_height())
        pygame.draw.rect(screen, selection_color, sel_rect)

    # Render the text
    text_surface = font.render(value, True, text_color)
    screen.blit(text_surface, (text_x, text_y))

    # Draw cursor if active and visible
    if text_input.active and text_input.cursor_visible:
        # Calculate cursor x position
        before_cursor = font.render(value[:text_input.cursor_pos], True, text_color)
        cursor_x = text_x + before_cursor.get_width()

        # Draw cursor line
        pygame.draw.line(screen, text_color,
                        (cursor_x, text_y + 2),
                        (cursor_x, text_y + font.get_height() - 2), 2)

    return rect


def get_char_index_at_pos(font: pygame.font.Font, text: str, text_x: int, click_x: int) -> int:
    """Get character index at a given x position."""
    if click_x <= text_x:
        return 0

    # Binary search would be more efficient, but for short strings this is fine
    for i in range(len(text) + 1):
        char_width = font.render(text[:i], True, (0, 0, 0)).get_width()
        if text_x + char_width >= click_x:
            # Check if click is closer to this char or the previous one
            if i > 0:
                prev_width = font.render(text[:i-1], True, (0, 0, 0)).get_width()
                if click_x - (text_x + prev_width) < (text_x + char_width) - click_x:
                    return i - 1
            return i

    return len(text)
