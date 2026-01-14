"""Network lobby UI for multiplayer games.

Handles:
- Server connection
- Match creation/joining
- Waiting for opponent
- Error display
"""

import pygame
import time
import subprocess
import sys
import socket
import atexit
import threading
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Dict
from enum import Enum, auto

# Global reference for cleanup on exit
_active_server_process = None
_active_server_thread = None
_active_server_instance = None
_server_loop = None
_server_ready = None  # threading.Event to signal server is ready
_server_error = None  # Store any startup error
_active_bore_tunnel = None  # Track bore tunnel for cleanup

def _cleanup_server_on_exit():
    """Kill server process/thread and tunnel when Python exits."""
    global _active_server_process, _active_server_instance, _server_loop, _active_bore_tunnel

    # Stop bore tunnel first
    if _active_bore_tunnel:
        try:
            _active_bore_tunnel.stop()
        except:
            pass

    # Stop subprocess if running
    if _active_server_process and _active_server_process.poll() is None:
        try:
            _active_server_process.terminate()
            _active_server_process.wait(timeout=2)
        except:
            try:
                _active_server_process.kill()
            except:
                pass

    # Stop threaded server if running
    if _active_server_instance and _server_loop:
        try:
            _server_loop.call_soon_threadsafe(_server_loop.stop)
        except:
            pass

atexit.register(_cleanup_server_on_exit)


def _run_server_in_thread(port: int, ready_event: threading.Event):
    """Run the game server in a background thread (for frozen exe)."""
    global _active_server_instance, _server_loop, _server_error
    import traceback

    _server_error = None

    try:
        from .network.server import GameServer
    except Exception as e:
        _server_error = f"Import error: {e}\n{traceback.format_exc()}"
        ready_event.set()
        return

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _server_loop = loop

        server = GameServer(host='0.0.0.0', port=port)
        _active_server_instance = server

        # Create a wrapper that signals when server is bound
        async def start_and_signal():
            # Start the server (binds to port)
            ssl_ctx = server._create_ssl_context()
            server._server = await asyncio.start_server(
                server._handle_connection,
                server.host,
                server.port,
                ssl=ssl_ctx,
                reuse_address=True,
            )
            server._running = True

            # Signal that server is ready
            ready_event.set()

            # Start background tasks
            asyncio.create_task(server._heartbeat_loop())
            asyncio.create_task(server._cleanup_loop())

            # Serve forever
            async with server._server:
                await server._server.serve_forever()

        loop.run_until_complete(start_and_signal())
    except Exception as e:
        _server_error = f"{e}\n{traceback.format_exc()}"
        ready_event.set()  # Signal even on error so main thread doesn't wait forever
    finally:
        if _server_loop and not _server_loop.is_closed():
            _server_loop.close()


def _kill_process_on_port(port: int) -> bool:
    """Kill any process using the specified port. Returns True if killed something."""
    if sys.platform != 'win32':
        return False

    try:
        # Find PID using the port
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True, timeout=5
        )

        for line in result.stdout.split('\n'):
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        # Kill the process
                        subprocess.run(
                            ['taskkill', '/F', '/PID', pid],
                            capture_output=True, timeout=5
                        )
                        time.sleep(0.3)  # Wait for port to be released
                        return True
    except:
        pass

    return False


def _is_port_available(port: int) -> bool:
    """Check if a port is available on all interfaces."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('0.0.0.0', port))
            return True
    except OSError:
        return False


from .constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, scaled,
    COLOR_BG, COLOR_TEXT, UILayout,
)
from .network.client import NetworkClient, ClientState
from .text_input import TextInput, draw_text_input_field
from .tunnel import BoreTunnel, ensure_bore_installed, is_bore_installed
from .chat import ChatUI


class LobbyState(Enum):
    """Lobby UI states."""
    CONNECT = auto()       # Enter server address
    CONNECTING = auto()    # Connecting to server
    LOBBY = auto()         # Connected, choose create/join
    CREATING = auto()      # Creating match
    BROWSE = auto()        # Browsing open matches
    WAITING = auto()       # Waiting for opponent
    READY = auto()         # Both players connected, ready confirmation
    ERROR = auto()         # Error state


@dataclass
class NetworkUI:
    """Network lobby UI manager."""

    screen: pygame.Surface
    font_large: pygame.font.Font
    font_medium: pygame.font.Font
    font_small: pygame.font.Font

    # State
    state: LobbyState = LobbyState.CONNECT
    client: Optional[NetworkClient] = None

    # Input fields (now using TextInput)
    inputs: Dict[str, TextInput] = field(default_factory=dict)
    active_input: str = ""  # Which input field is active

    # Match state
    created_match_code: str = ""
    available_matches: List[dict] = field(default_factory=list)  # List of open matches
    matches_loading: bool = False

    # Ready state
    my_ready: bool = False
    opponent_ready: bool = False
    opponent_name: str = ""
    my_player_number: int = 0

    # Error/status
    status_message: str = ""
    error_message: str = ""
    copy_notification: str = ""  # "Скопировано!" notification
    copy_notification_time: float = 0.0  # When notification was shown

    # Buttons for click detection
    buttons: List[tuple] = field(default_factory=list)

    # Squad for network game (set before creating/joining)
    squad: List[str] = field(default_factory=list)
    placed_cards: List[dict] = field(default_factory=list)  # Cards with positions

    # Callbacks
    on_game_start: Optional[Callable[[int, dict], None]] = None
    on_both_ready: Optional[Callable[[], None]] = None  # Called when both players ready
    on_connected: Optional[Callable[[], None]] = None  # Called when connected to server

    # Server process (if started locally)
    server_process: Optional[subprocess.Popen] = None
    cached_local_ip: str = ""

    # Bore tunnel (open-source, no signup required)
    bore_tunnel: Optional[BoreTunnel] = None
    tunnel_url: str = ""
    tunnel_status: str = ""  # Status message during tunnel setup

    # Chat UI
    chat: Optional[ChatUI] = None
    lobby_user_count: int = 0

    def __post_init__(self):
        self.buttons = []
        # Initialize text inputs - load saved nickname
        from .settings import get_nickname
        saved_nickname = get_nickname() or "Player"
        self.inputs = {
            'server': TextInput(value="13.48.80.75:7777", max_length=50),
            'name': TextInput(value=saved_nickname, max_length=20),
            'code': TextInput(value="", max_length=6, uppercase=True, allowed_chars="ABCDEF0123456789"),
        }
        # Initialize chat UI on left side (using constants)
        self.chat = ChatUI(
            x=scaled(UILayout.LOBBY_CHAT_X),
            y=scaled(UILayout.LOBBY_CHAT_Y),
            width=scaled(UILayout.LOBBY_CHAT_WIDTH),
            height=scaled(UILayout.LOBBY_CHAT_HEIGHT),
            title_height=scaled(UILayout.CHAT_TITLE_HEIGHT),
            input_height=scaled(UILayout.CHAT_INPUT_HEIGHT),
        )
        # Create title font (slightly bigger)
        font_title = pygame.font.SysFont('arial', scaled(UILayout.CHAT_TITLE_FONT_SIZE))
        self.chat.set_fonts(self.font_small, self.font_small, font_title)
        self.chat.on_send = self._on_chat_send
        self._setup_client()

    # Property accessors for input values
    @property
    def server_address(self) -> str:
        return self.inputs['server'].value

    @property
    def player_name(self) -> str:
        return self.inputs['name'].value

    @property
    def match_code(self) -> str:
        return self.inputs['code'].value

    def _setup_client(self):
        """Initialize network client with callbacks."""
        self.client = NetworkClient()
        self.client.on_connected = self._on_connected
        self.client.on_disconnected = self._on_disconnected
        self.client.on_error = self._on_error
        self.client.on_match_created = self._on_match_created
        self.client.on_match_joined = self._on_match_joined
        self.client.on_player_joined = self._on_player_joined
        self.client.on_ready_status = self._on_ready_status
        self.client.on_game_start = self._on_game_start
        self.client.on_match_list = self._on_match_list
        self.client.on_chat = self._on_chat_received
        self.client.on_lobby_status = self._on_lobby_status

    def _on_connected(self):
        """Called when connected to server."""
        self.state = LobbyState.LOBBY
        self.status_message = "Connected!"
        self.error_message = ""
        # Set player name on chat for color matching
        if self.chat:
            self.chat.my_player_name = self.player_name
        # Call external callback
        if self.on_connected:
            self.on_connected()

    def _on_disconnected(self, reason: str):
        """Called when disconnected."""
        self.state = LobbyState.CONNECT
        self.error_message = f"Disconnected: {reason}"

    def _on_error(self, error: str):
        """Called on error."""
        self.error_message = error
        if self.state == LobbyState.CONNECTING:
            self.state = LobbyState.CONNECT

    def _on_match_created(self, match_id: str):
        """Called when match is created."""
        self.created_match_code = match_id
        self.state = LobbyState.WAITING
        self.status_message = f"Match created! Code: {match_id}"

    def _on_match_joined(self, player: int, snapshot: dict):
        """Called when joined a match - go to ready screen."""
        self.my_player_number = player
        self.my_ready = False
        self.opponent_ready = False
        self.state = LobbyState.READY
        self.status_message = f"Вы - Игрок {player}"

    def _on_player_joined(self, player: int, player_name: str):
        """Called when opponent joins or info received."""
        self.opponent_name = player_name
        self.status_message = f"Противник: {player_name}"

    def _on_ready_status(self, player: int, is_ready: bool, player_name: str):
        """Called when a player's ready status changes."""
        if player == self.my_player_number:
            self.my_ready = is_ready
        else:
            self.opponent_ready = is_ready
            if player_name:
                self.opponent_name = player_name

        if is_ready:
            if player == self.my_player_number:
                self.status_message = "Вы готовы! Ожидание противника..."
            else:
                self.status_message = f"{self.opponent_name} готов!"

        # Check if both ready - trigger deck selection
        if self.my_ready and self.opponent_ready:
            if self.on_both_ready:
                self.on_both_ready()

    def _on_game_start(self, snapshot: dict):
        """Called when game starts."""
        if self.on_game_start:
            self.on_game_start(self.client.player_number, snapshot)

    def _on_match_list(self, matches: List[dict]):
        """Called when match list is received."""
        self.available_matches = matches
        self.matches_loading = False
        if not matches:
            self.status_message = "Нет открытых игр"
        else:
            self.status_message = f"Найдено игр: {len(matches)}"

    def _on_chat_received(self, player_name: str, text: str, player_number: int):
        """Called when a chat message is received."""
        if self.chat:
            self.chat.add_message(player_name, text, player_number)

    def _on_lobby_status(self, user_count: int):
        """Called when lobby status is updated."""
        self.lobby_user_count = user_count

    def _on_chat_send(self, text: str):
        """Called when user sends a chat message."""
        if self.client:
            self.client.send_chat(text)

    def update(self):
        """Poll for network updates. Call every frame."""
        if self.client:
            self.client.poll()

    def connect(self):
        """Connect to server."""
        if not self.server_address or not self.player_name:
            self.error_message = "Enter server address and player name"
            return

        # Parse address
        parts = self.server_address.split(':')
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 7777

        self.state = LobbyState.CONNECTING
        self.status_message = f"Connecting to {host}:{port}..."
        self.error_message = ""

        self.client.connect(host, port, self.player_name, use_tls=False)

    def create_match(self):
        """Create a new match."""
        self.state = LobbyState.CREATING
        self.status_message = "Creating match..."
        # Squad/placement sent later via PLACEMENT_DONE after deck/squad/placement phase
        self.client.create_match([], [])

    def join_match_by_id(self, match_id: str):
        """Join a match by its ID."""
        self.status_message = f"Подключение к игре..."
        # Squad/placement sent later via PLACEMENT_DONE after deck/squad/placement phase
        self.client.join_match(match_id, [], [])

    def disconnect(self):
        """Disconnect from server."""
        if self.client:
            self.client.disconnect()
        self.state = LobbyState.CONNECT
        self.status_message = ""
        self.error_message = ""
        self.created_match_code = ""
        self.inputs['code'].clear()

    def _set_active_input(self, field: str):
        """Set which input field is active."""
        # If clicking on same field that's already active, do nothing
        # (let handle_mouse_event handle cursor positioning)
        if field == self.active_input and field in self.inputs and self.inputs[field].active:
            return

        # Deactivate old input
        if self.active_input and self.active_input in self.inputs:
            self.inputs[self.active_input].deactivate()

        self.active_input = field

        # Activate new input
        if field and field in self.inputs:
            self.inputs[field].activate(self.inputs[field].value)

    def handle_text_input(self, event: pygame.event.Event) -> bool:
        """Handle text input events using TextInput class. Returns True if consumed."""
        # First, let chat handle the event if it's active
        if self.chat and self.state not in (LobbyState.CONNECT, LobbyState.CONNECTING):
            if self.chat.handle_event(event):
                return True

        if not self.active_input or self.active_input not in self.inputs:
            return False

        text_input = self.inputs[self.active_input]
        result = text_input.handle_event(event)

        if result == 'submit':
            if self.state == LobbyState.CONNECT:
                self.connect()
            elif self.state == LobbyState.JOINING:
                self.join_match()
            return True
        elif result is not None:
            return True

        return False

    def handle_click(self, mx: int, my: int) -> Optional[str]:
        """Handle mouse click. Returns action if button clicked."""
        for btn_id, btn_rect in self.buttons:
            if btn_rect.collidepoint(mx, my):
                return btn_id
        return None

    def handle_mouse_event(self, event: pygame.event.Event):
        """Handle mouse events for text input selection and chat."""
        # Let chat handle mouse events first
        if self.chat and self.state not in (LobbyState.CONNECT, LobbyState.CONNECTING):
            if self.chat.handle_event(event):
                return

        if not self.active_input or self.active_input not in self.inputs:
            return

        # Find the rect for the active input from stored buttons
        for btn_id, btn_rect in self.buttons:
            if btn_id == f"input_{self.active_input}":
                self.inputs[self.active_input].handle_mouse_event(
                    event, btn_rect, self.font_small
                )
                break

    def draw(self):
        """Draw the network lobby UI."""
        self.buttons = []

        # Background
        self.screen.fill(COLOR_BG)

        # Title
        title = self.font_large.render("Игра по сети", True, COLOR_TEXT)
        title_x = (WINDOW_WIDTH - title.get_width()) // 2
        self.screen.blit(title, (title_x, scaled(50)))

        # Draw user count when connected (top left)
        if self.state not in (LobbyState.CONNECT, LobbyState.CONNECTING):
            user_text = self.font_large.render(f"Онлайн: {self.lobby_user_count}", True, (100, 200, 100))
            self.screen.blit(user_text, (scaled(50), scaled(20)))

        # Draw chat on left side when connected
        if self.state not in (LobbyState.CONNECT, LobbyState.CONNECTING) and self.chat:
            self.chat.draw(self.screen)

        # Draw based on state
        if self.state == LobbyState.CONNECT:
            self._draw_connect_screen()
        elif self.state == LobbyState.CONNECTING:
            self._draw_connecting_screen()
        elif self.state == LobbyState.LOBBY:
            self._draw_lobby_screen()
        elif self.state in (LobbyState.CREATING, LobbyState.WAITING):
            self._draw_waiting_screen()
        elif self.state == LobbyState.BROWSE:
            self._draw_browse_screen()
        elif self.state == LobbyState.READY:
            self._draw_ready_screen()

        # Status/error/copy messages
        if self.copy_notification and time.time() - self.copy_notification_time < 2.0:
            notif = self.font_medium.render(self.copy_notification, True, (100, 255, 100))
            self.screen.blit(notif, (WINDOW_WIDTH // 2 - notif.get_width() // 2, WINDOW_HEIGHT - scaled(110)))
        elif self.status_message:
            status = self.font_small.render(self.status_message, True, (100, 200, 100))
            self.screen.blit(status, (scaled(50), WINDOW_HEIGHT - scaled(80)))

        if self.error_message:
            error = self.font_small.render(self.error_message, True, (200, 100, 100))
            self.screen.blit(error, (scaled(50), WINDOW_HEIGHT - scaled(50)))

        # Back button (always visible)
        self._draw_button("back", "Назад", scaled(50), WINDOW_HEIGHT - scaled(120), scaled(120), scaled(35))

    def _draw_connect_screen(self):
        """Draw server connection screen."""
        center_x = WINDOW_WIDTH // 2
        y = scaled(120)

        # Server address input
        label = self.font_medium.render("Адрес сервера:", True, COLOR_TEXT)
        self.screen.blit(label, (center_x - scaled(150), y))
        y += scaled(40)

        self._draw_input_field("server", center_x - scaled(150), y, scaled(300))
        y += scaled(60)

        # Player name
        label = self.font_medium.render("Имя игрока:", True, COLOR_TEXT)
        self.screen.blit(label, (center_x - scaled(150), y))
        y += scaled(40)

        self._draw_input_field("name", center_x - scaled(150), y, scaled(300))
        y += scaled(70)

        # Buttons row
        btn_y = y
        # Connect button
        self._draw_button("connect", "Подключиться", center_x - scaled(220), btn_y, scaled(200), scaled(45))

        # Start server button
        if not self.server_process or self.server_process.poll() is not None:
            self._draw_button("start_server", "Создать сервер", center_x + scaled(20), btn_y, scaled(200), scaled(45))
        else:
            self._draw_button("stop_server", "Остановить сервер", center_x + scaled(20), btn_y, scaled(200), scaled(45))

    def _draw_connecting_screen(self):
        """Draw connecting status."""
        text = self.font_medium.render("Подключение...", True, COLOR_TEXT)
        text_x = (WINDOW_WIDTH - text.get_width()) // 2
        self.screen.blit(text, (text_x, WINDOW_HEIGHT // 2))

    def _draw_server_info(self, center_x: int, y: int) -> int:
        """Draw server connection info with clickable copy. Returns new y position."""
        # Check if server is running (subprocess or thread)
        subprocess_running = self.server_process and self.server_process.poll() is None
        thread_running = _active_server_thread and _active_server_thread.is_alive()
        if not subprocess_running and not thread_running:
            return y

        # Show tunnel status/URL first (primary way to connect)
        if self.tunnel_status:
            # Show loading status
            status_text = self.font_small.render(self.tunnel_status, True, (200, 200, 100))
            self.screen.blit(status_text, (center_x - status_text.get_width() // 2, y))
            y += scaled(30)
        elif self.tunnel_url:
            # Show tunnel URL (most prominent - this is what friends use)
            tunnel_label = self.font_small.render("Адрес для друга:", True, (150, 150, 150))
            tunnel_text = self.font_medium.render(self.tunnel_url, True, (255, 220, 100))

            self.screen.blit(tunnel_label, (center_x - tunnel_label.get_width() // 2, y))
            y += scaled(22)

            # Clickable tunnel box
            t_rect = pygame.Rect(
                center_x - tunnel_text.get_width() // 2 - scaled(10),
                y,
                tunnel_text.get_width() + scaled(20),
                tunnel_text.get_height() + scaled(8)
            )
            pygame.draw.rect(self.screen, (60, 50, 30), t_rect)
            pygame.draw.rect(self.screen, (255, 220, 100), t_rect, 2)
            self.screen.blit(tunnel_text, (center_x - tunnel_text.get_width() // 2, y + scaled(4)))
            self.buttons.append(("copy_tunnel", t_rect))

            # Hint
            hint = self.font_small.render("(нажмите чтобы скопировать)", True, (120, 120, 120))
            self.screen.blit(hint, (center_x - hint.get_width() // 2, y + t_rect.height + scaled(3)))
            y += t_rect.height + scaled(25)

        # Show LAN IP as secondary option
        if self.cached_local_ip:
            # Get actual port from server address
            parts = self.server_address.split(':')
            port = parts[1] if len(parts) > 1 else '7777'
            ip_addr = f"{self.cached_local_ip}:{port}"
            lan_label = self.font_small.render("LAN:", True, (100, 100, 100))
            lan_text = self.font_small.render(ip_addr, True, (150, 150, 150))

            total_width = lan_label.get_width() + scaled(8) + lan_text.get_width()
            start_x = center_x - total_width // 2

            self.screen.blit(lan_label, (start_x, y))

            # Clickable IP box
            ip_x = start_x + lan_label.get_width() + scaled(8)
            ip_rect = pygame.Rect(ip_x - scaled(3), y - scaled(2), lan_text.get_width() + scaled(6), lan_text.get_height() + scaled(4))
            pygame.draw.rect(self.screen, (35, 35, 40), ip_rect)
            pygame.draw.rect(self.screen, (80, 80, 90), ip_rect, 1)
            self.screen.blit(lan_text, (ip_x, y))
            self.buttons.append(("copy_local_ip", ip_rect))
            y += scaled(28)

        return y

    def _draw_lobby_screen(self):
        """Draw main lobby - create or browse games."""
        center_x = WINDOW_WIDTH // 2
        y = scaled(130)

        # Server info (if hosting)
        y = self._draw_server_info(center_x, y)
        y = max(y, scaled(180))  # Minimum y position

        # Connected status
        status = self.font_small.render(f"Подключено как: {self.player_name}", True, (100, 200, 100))
        self.screen.blit(status, (center_x - status.get_width() // 2, y))
        y += scaled(50)

        # Create match button
        self._draw_button("create", "Создать игру", center_x - scaled(120), y, scaled(240), scaled(50))
        y += scaled(70)

        # Browse games button
        self._draw_button("browse", "Открытые игры", center_x - scaled(120), y, scaled(240), scaled(50))
        y += scaled(70)

        # Disconnect button
        self._draw_button("disconnect", "Отключиться", center_x - scaled(100), y, scaled(200), scaled(40))

    def _draw_waiting_screen(self):
        """Draw waiting for opponent screen."""
        center_x = WINDOW_WIDTH // 2
        y = scaled(120)

        # Server info (if hosting) - show tunnel URL for friend to connect
        y = self._draw_server_info(center_x, y)
        y = max(y, scaled(200))

        # Waiting message
        waiting = self.font_medium.render("Ожидание противника...", True, COLOR_TEXT)
        self.screen.blit(waiting, (center_x - waiting.get_width() // 2, y))
        y += scaled(40)

        # Instructions
        hint = self.font_small.render("Друг должен подключиться и нажать 'Открытые игры'", True, (150, 150, 150))
        self.screen.blit(hint, (center_x - hint.get_width() // 2, y))
        y += scaled(60)

        # Cancel button
        self._draw_button("cancel", "Отмена", center_x - scaled(80), y, scaled(160), scaled(40))

    def _draw_browse_screen(self):
        """Draw browse open matches screen."""
        center_x = WINDOW_WIDTH // 2
        y = scaled(120)

        label = self.font_medium.render("Открытые игры", True, COLOR_TEXT)
        self.screen.blit(label, (center_x - label.get_width() // 2, y))
        y += scaled(50)

        # Refresh button
        self._draw_button("refresh", "Обновить", center_x + scaled(100), y - scaled(40), scaled(100), scaled(30))

        if self.matches_loading:
            loading = self.font_small.render("Загрузка...", True, (150, 150, 150))
            self.screen.blit(loading, (center_x - loading.get_width() // 2, y))
            y += scaled(40)
        elif not self.available_matches:
            no_matches = self.font_small.render("Нет открытых игр", True, (150, 150, 150))
            self.screen.blit(no_matches, (center_x - no_matches.get_width() // 2, y))
            y += scaled(40)
        else:
            # Draw list of matches
            for i, match in enumerate(self.available_matches[:5]):  # Show max 5
                match_id = match.get('match_id', '???')
                host_name = match.get('host_name', 'Unknown')

                # Draw match row as clickable button
                row_text = f"{host_name}"
                btn_width = scaled(300)
                btn_height = scaled(40)
                btn_x = center_x - btn_width // 2
                btn_y = y

                # Draw button background
                rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)
                pygame.draw.rect(self.screen, (50, 60, 70), rect)
                pygame.draw.rect(self.screen, (100, 120, 140), rect, 2)

                # Draw host name
                name_text = self.font_medium.render(row_text, True, COLOR_TEXT)
                self.screen.blit(name_text, (btn_x + scaled(15), btn_y + (btn_height - name_text.get_height()) // 2))

                # Draw "Join" indicator on right
                join_text = self.font_small.render("Войти →", True, (100, 200, 100))
                self.screen.blit(join_text, (btn_x + btn_width - join_text.get_width() - scaled(15),
                                             btn_y + (btn_height - join_text.get_height()) // 2))

                self.buttons.append((f"join_match_{match_id}", rect))
                y += scaled(50)

        y = max(y, scaled(350))

        # Back to lobby
        self._draw_button("lobby", "Назад", center_x - scaled(80), y, scaled(160), scaled(35))

    def _draw_ready_screen(self):
        """Draw ready confirmation screen."""
        center_x = WINDOW_WIDTH // 2
        y = scaled(120)

        # Title
        title = self.font_medium.render("Подготовка к игре", True, COLOR_TEXT)
        self.screen.blit(title, (center_x - title.get_width() // 2, y))
        y += scaled(60)

        # Player info boxes
        box_width = scaled(200)
        box_height = scaled(120)
        gap = scaled(80)

        # My info (left)
        my_x = center_x - gap // 2 - box_width
        my_color = (70, 130, 180) if self.my_player_number == 1 else (180, 70, 70)
        self._draw_player_box(my_x, y, box_width, box_height,
                              f"Игрок {self.my_player_number}",
                              self.player_name, self.my_ready, my_color)

        # Opponent info (right)
        opp_x = center_x + gap // 2
        opp_color = (180, 70, 70) if self.my_player_number == 1 else (70, 130, 180)
        opp_num = 3 - self.my_player_number
        self._draw_player_box(opp_x, y, box_width, box_height,
                              f"Игрок {opp_num}",
                              self.opponent_name or "Ожидание...", self.opponent_ready, opp_color)

        y += box_height + scaled(50)

        # Ready button or waiting message
        if not self.my_ready:
            self._draw_button("send_ready", "Готов!", center_x - scaled(100), y, scaled(200), scaled(50))
        else:
            if self.opponent_ready:
                waiting = self.font_medium.render("Запуск игры...", True, (100, 200, 100))
            else:
                waiting = self.font_medium.render("Ожидание противника...", True, (150, 150, 150))
            self.screen.blit(waiting, (center_x - waiting.get_width() // 2, y + scaled(10)))

        y += scaled(80)

        # Cancel button
        self._draw_button("cancel_ready", "Отмена", center_x - scaled(80), y, scaled(160), scaled(35))

    def _draw_player_box(self, x: int, y: int, width: int, height: int,
                         title: str, name: str, is_ready: bool, color: tuple):
        """Draw a player info box."""
        # Background
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (40, 40, 50), rect)
        pygame.draw.rect(self.screen, color, rect, 3)

        # Title (Player 1 / Player 2)
        title_surf = self.font_small.render(title, True, color)
        self.screen.blit(title_surf, (x + (width - title_surf.get_width()) // 2, y + scaled(10)))

        # Name
        name_surf = self.font_medium.render(name, True, COLOR_TEXT)
        self.screen.blit(name_surf, (x + (width - name_surf.get_width()) // 2, y + scaled(40)))

        # Ready status
        if is_ready:
            status_text = "ГОТОВ"
            status_color = (100, 200, 100)
        else:
            status_text = "не готов"
            status_color = (150, 150, 150)

        status_surf = self.font_small.render(status_text, True, status_color)
        self.screen.blit(status_surf, (x + (width - status_surf.get_width()) // 2, y + scaled(80)))

    def _draw_input_field(self, field_id: str, x: int, y: int, width: int):
        """Draw an input field using TextInput."""
        if field_id not in self.inputs:
            return

        text_input = self.inputs[field_id]
        height = scaled(35)

        rect = draw_text_input_field(
            self.screen,
            self.font_small,
            text_input,
            x, y, width, height,
            bg_color=(40, 40, 50),
            bg_active_color=(50, 50, 60),
            border_color=(80, 80, 90),
            border_active_color=(120, 100, 140),
            text_color=COLOR_TEXT,
        )

        # Store as button for click detection (to activate input)
        self.buttons.append((f"input_{field_id}", rect))

    def _draw_button(self, btn_id: str, text: str, x: int, y: int, width: int, height: int):
        """Draw a button."""
        rect = pygame.Rect(x, y, width, height)

        bg_color = (60, 50, 70)
        border_color = (120, 100, 140)

        pygame.draw.rect(self.screen, bg_color, rect)
        pygame.draw.rect(self.screen, border_color, rect, 2)

        text_surface = self.font_medium.render(text, True, COLOR_TEXT)
        text_x = x + (width - text_surface.get_width()) // 2
        text_y = y + (height - text_surface.get_height()) // 2
        self.screen.blit(text_surface, (text_x, text_y))

        self.buttons.append((btn_id, rect))

    def process_action(self, action: str) -> Optional[str]:
        """Process a button action. Returns 'back' to exit lobby, 'start' when game starts."""
        if action == 'back':
            self.disconnect()
            self._stop_local_server()
            return 'back'

        elif action == 'connect':
            self.connect()

        elif action == 'disconnect':
            self.disconnect()

        elif action == 'create':
            self.create_match()

        elif action == 'browse':
            self.state = LobbyState.BROWSE
            self.available_matches = []
            self.matches_loading = True
            self.client.list_matches()

        elif action == 'refresh':
            self.matches_loading = True
            self.available_matches = []
            self.client.list_matches()

        elif action.startswith('join_match_'):
            match_id = action[11:]  # Remove 'join_match_' prefix
            self.join_match_by_id(match_id)

        elif action == 'lobby':
            self.state = LobbyState.LOBBY
            self._set_active_input("")
            self.available_matches = []

        elif action == 'cancel':
            self.state = LobbyState.LOBBY
            self.created_match_code = ""

        elif action == 'send_ready':
            self.client.send_ready()

        elif action == 'cancel_ready':
            # Leave the match and go back to lobby
            self.client.leave_match()
            self.state = LobbyState.LOBBY
            self.my_ready = False
            self.opponent_ready = False
            self.opponent_name = ""

        elif action == 'copy_local_ip':
            parts = self.server_address.split(':')
            port = parts[1] if len(parts) > 1 else '7777'
            self._copy_to_clipboard(f"{self.cached_local_ip}:{port}")

        elif action == 'start_server':
            self._start_local_server()

        elif action == 'stop_server':
            self._stop_local_server()

        elif action == 'copy_tunnel':
            if self.tunnel_url:
                self._copy_to_clipboard(self.tunnel_url)

        elif action.startswith('input_'):
            field = action[6:]  # Remove 'input_' prefix
            self._set_active_input(field)
            # Auto-paste when clicking code input
            if field == 'code' and not self.match_code:
                self.inputs['code'].paste_from_clipboard()

        return None

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard and show notification."""
        try:
            # Try pygame.scrap first (cross-platform)
            pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode('utf-8'))
            self.copy_notification = "Скопировано!"
        except Exception:
            try:
                # Fallback to pyperclip if available
                import pyperclip
                pyperclip.copy(text)
                self.copy_notification = "Скопировано!"
            except ImportError:
                # Last resort - Windows specific
                try:
                    import subprocess
                    subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
                    self.copy_notification = "Скопировано!"
                except Exception:
                    self.copy_notification = "Не удалось скопировать"

        self.copy_notification_time = time.time()

    def _start_local_server(self):
        """Start a local game server."""
        global _active_server_process, _active_server_thread

        # Check instance server first
        if self.server_process and self.server_process.poll() is None:
            self.status_message = "Сервер уже запущен"
            return

        # Check global server (might be from previous NetworkUI instance)
        if _active_server_process and _active_server_process.poll() is None:
            # Restore reference and reuse existing server
            self.server_process = _active_server_process
            self.status_message = "Сервер уже запущен"
            return

        # Check threaded server (from frozen exe)
        if _active_server_thread and _active_server_thread.is_alive() and _active_server_instance:
            self.status_message = "Сервер уже запущен"
            return

        # Clean up dead thread references
        if _active_server_thread and not _active_server_thread.is_alive():
            _active_server_thread = None
            _active_server_instance = None

        try:
            # Try multiple ports
            ports_to_try = [7777, 7778, 7779, 7780]
            port = None

            for try_port in ports_to_try:
                if _is_port_available(try_port):
                    port = try_port
                    break
                else:
                    # Try to kill process on port
                    self.status_message = f"Освобождение порта {try_port}..."
                    _kill_process_on_port(try_port)
                    time.sleep(0.3)
                    if _is_port_available(try_port):
                        port = try_port
                        break

            if port is None:
                self.error_message = "Все порты (7777-7780) заняты"
                return

            # Check if running from frozen exe (PyInstaller)
            is_frozen = getattr(sys, 'frozen', False)

            if is_frozen:
                global _server_ready, _server_error
                # Create event to wait for server to be ready
                _server_ready = threading.Event()
                _server_error = None

                # Run server in a background thread (subprocess won't work in frozen exe)
                _active_server_thread = threading.Thread(
                    target=_run_server_in_thread,
                    args=(port, _server_ready),
                    daemon=True
                )
                _active_server_thread.start()

                # Wait for server to signal it's ready (with timeout)
                if not _server_ready.wait(timeout=3.0):
                    self.error_message = "Таймаут запуска сервера"
                    return

                # Check if server had an error during startup
                if _server_error:
                    # Log full error to file for debugging
                    try:
                        log_path = Path.home() / ".berserk_vibe" / "server_error.log"
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(log_path, 'w', encoding='utf-8') as f:
                            f.write(_server_error)
                    except:
                        pass
                    # Show first line of error in UI
                    first_line = _server_error.split('\n')[0]
                    self.error_message = f"Ошибка сервера: {first_line[:80]}"
                    return

                # Double-check the port is actually in use
                if _is_port_available(port):
                    self.error_message = "Не удалось запустить сервер"
                    return
            else:
                # Development mode: start server as subprocess
                creation_flags = 0
                startupinfo = None
                if sys.platform == 'win32':
                    creation_flags = subprocess.CREATE_NO_WINDOW
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                self.server_process = subprocess.Popen(
                    [sys.executable, '-m', 'src.network.server', '--port', str(port)],
                    creationflags=creation_flags,
                    startupinfo=startupinfo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                # Wait a moment for server to start
                time.sleep(0.5)

                # Check if server crashed immediately
                if self.server_process.poll() is not None:
                    # Try to get error output
                    _, stderr = self.server_process.communicate(timeout=1)
                    error_text = stderr.decode('utf-8', errors='ignore').strip() if stderr else ""
                    if error_text:
                        self.error_message = f"Ошибка сервера: {error_text[:100]}"
                    else:
                        self.error_message = f"Сервер завершился с кодом {self.server_process.returncode}"
                    self.server_process = None
                    return

                # Store global reference for cleanup on exit
                _active_server_process = self.server_process

            # Set address to localhost for auto-connect
            self.inputs['server'].set_value(f"localhost:{port}")

            # Cache LAN IP for display
            self.cached_local_ip = self._get_local_ip()

            self.status_message = f"Сервер запущен"
            self.error_message = ""

            # Auto-connect after starting server
            time.sleep(0.3)
            self.connect()

            # Auto-start tunnel for internet play
            self._start_tunnel()

        except Exception as e:
            self.error_message = f"Ошибка запуска сервера: {e}"

    def _stop_local_server(self):
        """Stop the local game server."""
        global _active_server_process, _active_server_instance, _server_loop, _active_server_thread

        # Stop tunnel first
        self._stop_tunnel()

        # Stop subprocess server
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
            _active_server_process = None
            self.cached_local_ip = ""
            self.status_message = "Сервер остановлен"

        # Stop threaded server (for frozen exe)
        if _active_server_instance and _server_loop:
            try:
                _server_loop.call_soon_threadsafe(_server_loop.stop)
            except:
                pass
            _active_server_instance = None
            _server_loop = None
            _active_server_thread = None
            self.cached_local_ip = ""
            self.status_message = "Сервер остановлен"

    def _start_tunnel(self):
        """Start bore tunnel for internet access (no signup required)."""
        if self.bore_tunnel and self.bore_tunnel.is_running:
            self.status_message = "Туннель уже запущен"
            return

        # Check if server is running (either subprocess or threaded)
        server_running = (
            (self.server_process and self.server_process.poll() is None) or
            (_active_server_instance is not None)
        )
        if not server_running:
            self.error_message = "Сначала запустите сервер"
            return

        # Get port from server address
        parts = self.server_address.split(':')
        port = int(parts[1]) if len(parts) > 1 else 7777

        # Ensure bore is installed (download if needed)
        self.tunnel_status = "Проверка bore..."
        if not is_bore_installed():
            self.tunnel_status = "Загрузка bore..."
            if not ensure_bore_installed(lambda msg: setattr(self, 'tunnel_status', msg)):
                self.error_message = "Не удалось загрузить bore"
                self.tunnel_status = ""
                return

        # Create and start tunnel
        global _active_bore_tunnel
        self.tunnel_status = "Создание туннеля..."
        self.bore_tunnel = BoreTunnel(
            port=port,
            on_url_ready=self._on_tunnel_ready,
            on_error=self._on_tunnel_error,
        )
        _active_bore_tunnel = self.bore_tunnel  # Track for cleanup on exit

        if not self.bore_tunnel.start():
            self.error_message = self.bore_tunnel.error or "Не удалось запустить туннель"
            self.tunnel_status = ""
            self.bore_tunnel = None
            _active_bore_tunnel = None

    def _on_tunnel_ready(self, url: str):
        """Called when bore tunnel URL is ready."""
        self.tunnel_url = url
        self.tunnel_status = ""
        self.status_message = "Туннель создан!"
        self.error_message = ""

    def _on_tunnel_error(self, error: str):
        """Called when bore tunnel encounters an error."""
        self.error_message = f"Ошибка туннеля: {error}"
        self.tunnel_status = ""

    def _stop_tunnel(self):
        """Stop the bore tunnel."""
        global _active_bore_tunnel
        if self.bore_tunnel:
            self.bore_tunnel.stop()
            self.bore_tunnel = None
            _active_bore_tunnel = None
        self.tunnel_url = ""
        self.tunnel_status = ""

    def _get_local_ip(self) -> str:
        """Get local IP address for LAN play."""
        try:
            # Create a socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return ""
