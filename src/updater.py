"""Auto-updater using GitHub Releases.

Checks for new versions and downloads updates.
"""

import os
import sys
import subprocess
import tempfile
import threading
from typing import Optional, Callable
from dataclasses import dataclass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .version import __version__, UPDATE_CHECK_URL, GITHUB_OWNER, GITHUB_REPO


@dataclass
class UpdateInfo:
    """Information about an available update."""
    version: str
    download_url: str
    release_notes: str
    file_size: int  # bytes


def parse_version(v: str) -> tuple:
    """Parse version string to tuple for comparison."""
    # Remove 'v' prefix if present
    v = v.lstrip('v')
    try:
        return tuple(int(x) for x in v.split('.'))
    except ValueError:
        return (0, 0, 0)


def is_newer_version(current: str, latest: str) -> bool:
    """Check if latest version is newer than current."""
    return parse_version(latest) > parse_version(current)


def check_for_update() -> Optional[UpdateInfo]:
    """Check GitHub for a newer release.

    Returns UpdateInfo if update available, None otherwise.
    """
    if not HAS_REQUESTS:
        print("requests library not installed, skipping update check")
        return None

    try:
        resp = requests.get(UPDATE_CHECK_URL, timeout=5)
        if not resp.ok:
            return None

        data = resp.json()
        latest_version = data.get('tag_name', '').lstrip('v')

        if not latest_version:
            return None

        if not is_newer_version(__version__, latest_version):
            return None

        # Find .exe asset
        download_url = None
        file_size = 0
        for asset in data.get('assets', []):
            if asset['name'].endswith('.exe'):
                download_url = asset['browser_download_url']
                file_size = asset.get('size', 0)
                break

        if not download_url:
            # No exe found, link to release page
            download_url = data.get('html_url',
                f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest")

        return UpdateInfo(
            version=latest_version,
            download_url=download_url,
            release_notes=data.get('body', ''),
            file_size=file_size
        )

    except Exception as e:
        print(f"Update check failed: {e}")
        return None


def check_for_update_async(callback: Callable[[Optional[UpdateInfo]], None]) -> None:
    """Check for updates in background thread.

    Args:
        callback: Function to call with result (UpdateInfo or None)
    """
    def _check():
        result = check_for_update()
        callback(result)

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()


def download_update(update: UpdateInfo,
                    progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
    """Download update to temp file.

    Args:
        update: UpdateInfo with download URL
        progress_callback: Optional callback(downloaded_bytes, total_bytes)

    Returns:
        Path to downloaded file, or None on failure
    """
    if not HAS_REQUESTS:
        return None

    if not update.download_url.endswith('.exe'):
        # Not a direct exe download
        return None

    try:
        resp = requests.get(update.download_url, stream=True, timeout=30)
        if not resp.ok:
            return None

        total_size = int(resp.headers.get('content-length', 0))

        # Create temp file
        fd, temp_path = tempfile.mkstemp(suffix='.exe')

        downloaded = 0
        with os.fdopen(fd, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)

        return temp_path

    except Exception as e:
        print(f"Download failed: {e}")
        return None


def apply_update(downloaded_exe: str) -> bool:
    """Apply downloaded update by replacing current exe.

    Creates a batch script that:
    1. Waits for current process to exit
    2. Replaces the exe
    3. Restarts the app

    Returns True if update process started successfully.
    """
    if not os.path.exists(downloaded_exe):
        return False

    # Get current exe path
    if getattr(sys, 'frozen', False):
        current_exe = sys.executable
    else:
        # Running from Python - can't auto-update
        print("Auto-update only works in frozen .exe mode")
        return False

    # Create updater batch script
    batch_content = f'''@echo off
echo Updating Berserk...
timeout /t 2 /nobreak >nul
move /y "{downloaded_exe}" "{current_exe}"
if errorlevel 1 (
    echo Update failed!
    pause
    exit /b 1
)
echo Update complete!
start "" "{current_exe}"
del "%~f0"
'''

    batch_path = os.path.join(tempfile.gettempdir(), 'berserk_updater.bat')
    with open(batch_path, 'w') as f:
        f.write(batch_content)

    # Launch batch script and exit
    subprocess.Popen(
        ['cmd', '/c', batch_path],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    )

    return True


def get_release_page_url() -> str:
    """Get URL to GitHub releases page."""
    return f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


def open_release_page() -> None:
    """Open GitHub releases page in browser."""
    import webbrowser
    webbrowser.open(get_release_page_url())
