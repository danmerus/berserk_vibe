"""Tunnel management for NAT traversal using bore.

Bore is an open-source tool that creates TCP tunnels without requiring signup.
https://github.com/ekzhang/bore

This module handles:
- Auto-downloading bore binary if not present
- Starting/stopping tunnels
- Parsing tunnel URL from output
"""

import os
import sys
import subprocess
import threading
import time
import zipfile
import io
import logging
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Bore release info
BORE_VERSION = "0.5.2"
BORE_REPO = "ekzhang/bore"
BORE_SERVER = "bore.pub"

# Platform-specific binary names
if sys.platform == "win32":
    BORE_BINARY = "bore.exe"
    BORE_ASSET = f"bore-v{BORE_VERSION}-x86_64-pc-windows-msvc.zip"
else:
    BORE_BINARY = "bore"
    if sys.platform == "darwin":
        BORE_ASSET = f"bore-v{BORE_VERSION}-x86_64-apple-darwin.zip"
    else:
        BORE_ASSET = f"bore-v{BORE_VERSION}-x86_64-unknown-linux-musl.zip"

# Download URL
BORE_DOWNLOAD_URL = f"https://github.com/{BORE_REPO}/releases/download/v{BORE_VERSION}/{BORE_ASSET}"


def get_bore_path() -> Path:
    """Get path to bore binary.

    In frozen exe: uses user home directory (~/.berserk_vibe/tools/)
    In development: uses project tools/ directory
    """
    is_frozen = getattr(sys, 'frozen', False)

    if is_frozen:
        # Frozen exe: use user-writable directory
        tools_dir = Path.home() / ".berserk_vibe" / "tools"
    else:
        # Development: use project tools/ directory
        project_root = Path(__file__).parent.parent
        tools_dir = project_root / "tools"

    return tools_dir / BORE_BINARY


def is_bore_installed() -> bool:
    """Check if bore binary exists."""
    return get_bore_path().exists()


def download_bore(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    Download bore binary from GitHub releases.

    Args:
        progress_callback: Optional callback for progress updates

    Returns:
        True if successful, False otherwise
    """
    import urllib.request

    bore_path = get_bore_path()
    tools_dir = bore_path.parent

    try:
        # Create tools directory
        tools_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback("Загрузка bore...")

        logger.info(f"Downloading bore from {BORE_DOWNLOAD_URL}")

        # Download the zip file
        with urllib.request.urlopen(BORE_DOWNLOAD_URL, timeout=30) as response:
            zip_data = response.read()

        if progress_callback:
            progress_callback("Распаковка...")

        # Extract bore binary from zip
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # Find the bore binary in the archive
            for name in zf.namelist():
                if name.endswith(BORE_BINARY) or name == BORE_BINARY:
                    # Extract to tools directory
                    with zf.open(name) as src:
                        with open(bore_path, 'wb') as dst:
                            dst.write(src.read())
                    break
            else:
                # Binary might be at root level
                if BORE_BINARY in zf.namelist():
                    zf.extract(BORE_BINARY, tools_dir)
                else:
                    logger.error(f"Could not find {BORE_BINARY} in archive")
                    return False

        # Make executable on Unix
        if sys.platform != "win32":
            os.chmod(bore_path, 0o755)

        logger.info(f"Bore installed to {bore_path}")

        if progress_callback:
            progress_callback("Готово!")

        return True

    except Exception as e:
        logger.error(f"Failed to download bore: {e}")
        if progress_callback:
            progress_callback(f"Ошибка: {e}")
        return False


@dataclass
class BoreTunnel:
    """Manages a bore tunnel subprocess."""

    port: int
    server: str = BORE_SERVER

    # State
    process: Optional[subprocess.Popen] = None
    public_url: str = ""
    is_running: bool = False
    error: str = ""

    # For reading output in background
    _output_thread: Optional[threading.Thread] = None
    _stop_event: threading.Event = field(default_factory=threading.Event)

    # Callback when URL is ready
    on_url_ready: Optional[Callable[[str], None]] = None
    on_error: Optional[Callable[[str], None]] = None

    def start(self) -> bool:
        """
        Start the bore tunnel.

        Returns:
            True if process started (URL will come via callback), False on immediate failure
        """
        if self.is_running:
            return True

        bore_path = get_bore_path()

        if not bore_path.exists():
            self.error = "bore не найден. Требуется загрузка."
            if self.on_error:
                self.on_error(self.error)
            return False

        try:
            # Start bore process
            # Command: bore local <port> --to <server>
            cmd = [str(bore_path), "local", str(self.port), "--to", self.server]

            # Hide console window on Windows
            creation_flags = 0
            startupinfo = None
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
                startupinfo=startupinfo,
                text=True,
                bufsize=1,
            )

            self.is_running = True
            self._stop_event.clear()

            # Start thread to read output and find URL
            self._output_thread = threading.Thread(target=self._read_output, daemon=True)
            self._output_thread.start()

            return True

        except Exception as e:
            self.error = f"Ошибка запуска: {e}"
            if self.on_error:
                self.on_error(self.error)
            return False

    def _read_output(self):
        """Background thread to read bore output and extract URL."""
        try:
            for line in self.process.stdout:
                if self._stop_event.is_set():
                    break

                line = line.strip()
                logger.debug(f"bore: {line}")

                # Look for the "listening at" line
                # Example: "listening at bore.pub:12345"
                if "listening at" in line.lower():
                    # Extract URL from line
                    parts = line.split("listening at")
                    if len(parts) > 1:
                        url = parts[1].strip()
                        # Clean up any trailing punctuation or log formatting
                        url = url.split()[0] if url else ""
                        if url:
                            self.public_url = url
                            logger.info(f"Tunnel ready: {url}")
                            if self.on_url_ready:
                                self.on_url_ready(url)

                # Check for errors
                elif "error" in line.lower():
                    self.error = line
                    if self.on_error:
                        self.on_error(line)

        except Exception as e:
            if not self._stop_event.is_set():
                self.error = str(e)
                if self.on_error:
                    self.on_error(str(e))

        # Process ended
        self.is_running = False

    def stop(self):
        """Stop the bore tunnel."""
        self._stop_event.set()

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        self.is_running = False
        self.public_url = ""
        self.error = ""

    def __del__(self):
        """Cleanup on destruction."""
        self.stop()


def ensure_bore_installed(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    Ensure bore is installed, downloading if necessary.

    Args:
        progress_callback: Optional callback for progress updates

    Returns:
        True if bore is available, False otherwise
    """
    if is_bore_installed():
        return True

    return download_bore(progress_callback)
