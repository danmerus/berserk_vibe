"""Settings management - saves and loads user preferences."""
import json
import os
from pathlib import Path
from typing import Tuple, Optional

# Settings file location (in user's home directory)
SETTINGS_DIR = Path.home() / ".berserk_vibe"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

# Default settings
DEFAULT_SETTINGS = {
    "resolution": [1920, 1080],
    "fullscreen": False,
}


def ensure_settings_dir():
    """Create settings directory if it doesn't exist."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    """Load settings from file, or return defaults if file doesn't exist."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                # Merge with defaults (in case new settings were added)
                settings = DEFAULT_SETTINGS.copy()
                settings.update(saved)
                print(f"Settings loaded from {SETTINGS_FILE}: {settings}")
                return settings
        else:
            print(f"Settings file not found at {SETTINGS_FILE}, using defaults")
    except (json.JSONDecodeError, IOError) as e:
        print(f"Failed to load settings: {e}")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    """Save settings to file."""
    try:
        ensure_settings_dir()
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        print(f"Settings saved to {SETTINGS_FILE}")
    except Exception as e:
        print(f"Failed to save settings: {e}")


def get_resolution() -> Tuple[int, int]:
    """Get saved resolution as tuple."""
    settings = load_settings()
    res = settings.get("resolution", DEFAULT_SETTINGS["resolution"])
    return (res[0], res[1])


def set_resolution(width: int, height: int):
    """Save resolution setting."""
    settings = load_settings()
    settings["resolution"] = [width, height]
    save_settings(settings)


def get_fullscreen() -> bool:
    """Get saved fullscreen setting."""
    settings = load_settings()
    return settings.get("fullscreen", False)


def set_fullscreen(fullscreen: bool):
    """Save fullscreen setting."""
    settings = load_settings()
    settings["fullscreen"] = fullscreen
    save_settings(settings)
