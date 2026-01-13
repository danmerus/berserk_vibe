"""
Font management with caching.
Fonts are created once at startup and reused throughout the application.
"""
import os
import pygame
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FontSpec:
    """Specification for a font."""
    name: str  # Font name (for SysFont) or path (for custom font)
    base_size: int  # Size at 1.0 scale
    is_custom: bool = False  # True if using custom font file


class FontManager:
    """
    Manages font creation and caching.

    Usage:
        FontManager.init(scale=1.5)  # Call once at startup
        font = FontManager.get('medium')  # Get cached font
        font = FontManager.get('title', 48)  # Get font at specific size
    """

    _fonts: Dict[Tuple[str, int], pygame.font.Font] = {}
    _scale: float = 1.0
    _initialized: bool = False
    _custom_font_path: Optional[str] = None

    # Default font specifications
    FONT_SPECS = {
        'large': FontSpec('arial', 24),
        'medium': FontSpec('arial', 20),
        'small': FontSpec('arial', 14),
        'card_name': FontSpec('arial', 11),
        'popup': FontSpec('arial', 14),
        'indicator': FontSpec('tahoma', 10),
        'title': FontSpec('arial', 48),
        'title_medium': FontSpec('arial', 36),
        'title_small': FontSpec('arial', 28),
    }

    @classmethod
    def init(cls, scale: float = 1.0, custom_font_dir: Optional[str] = None):
        """
        Initialize the font manager.

        Args:
            scale: UI scale factor (e.g., 1.5 for 1920x1080 from 1280x720 base)
            custom_font_dir: Optional path to directory containing custom fonts
        """
        cls._scale = scale
        cls._custom_font_path = custom_font_dir
        cls._fonts.clear()

        # Look for custom fonts in standard locations
        font_dirs = []
        if custom_font_dir:
            font_dirs.append(custom_font_dir)
        # Add common relative paths
        font_dirs.extend([
            'data/fonts',
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'fonts'),
        ])

        # Check for custom fonts
        for font_dir in font_dirs:
            if not os.path.isdir(font_dir):
                continue

            # Look for RuslanDisplay font (for menus)
            ruslan_font = os.path.join(font_dir, 'RuslanDisplay-Regular.ttf')
            if os.path.exists(ruslan_font):
                # Use RuslanDisplay for all menu fonts
                for name in ['title', 'title_medium', 'title_small',]:
                    cls.FONT_SPECS[name] = FontSpec(ruslan_font, cls.FONT_SPECS[name].base_size, is_custom=True)
                break

            # Fallback: look for main.ttf
            main_font = os.path.join(font_dir, 'main.ttf')
            indicator_font = os.path.join(font_dir, 'indicator.ttf')

            if os.path.exists(main_font):
                for name in ['large', 'medium', 'small', 'card_name', 'popup',
                           'title', 'title_medium', 'title_small']:
                    cls.FONT_SPECS[name] = FontSpec(main_font, cls.FONT_SPECS[name].base_size, is_custom=True)

            if os.path.exists(indicator_font):
                cls.FONT_SPECS['indicator'] = FontSpec(indicator_font, 10, is_custom=True)

            if os.path.exists(main_font) or os.path.exists(ruslan_font):
                break

        # Pre-cache common fonts
        for name in cls.FONT_SPECS:
            cls.get(name)

        cls._initialized = True

    @classmethod
    def get(cls, name: str, size: Optional[int] = None) -> pygame.font.Font:
        """
        Get a font by name, optionally with a custom size.

        Args:
            name: Font name from FONT_SPECS or 'arial'/'tahoma' for system fonts
            size: Optional size override (will be scaled)

        Returns:
            Cached pygame.font.Font instance
        """
        if name in cls.FONT_SPECS:
            spec = cls.FONT_SPECS[name]
            base_size = size if size is not None else spec.base_size
            scaled_size = int(base_size * cls._scale)
            cache_key = (name, scaled_size)

            if cache_key not in cls._fonts:
                if spec.is_custom:
                    cls._fonts[cache_key] = pygame.font.Font(spec.name, scaled_size)
                else:
                    cls._fonts[cache_key] = pygame.font.SysFont(spec.name, scaled_size)

            return cls._fonts[cache_key]
        else:
            # Fallback for arbitrary font names
            scaled_size = int((size or 14) * cls._scale)
            cache_key = (name, scaled_size)

            if cache_key not in cls._fonts:
                cls._fonts[cache_key] = pygame.font.SysFont(name, scaled_size)

            return cls._fonts[cache_key]

    @classmethod
    def get_scaled(cls, name: str, base_size: int) -> pygame.font.Font:
        """
        Get a font with explicit base size (will be scaled).

        Args:
            name: System font name (e.g., 'arial')
            base_size: Size before scaling

        Returns:
            Cached pygame.font.Font instance
        """
        scaled_size = int(base_size * cls._scale)
        cache_key = (name, scaled_size)

        if cache_key not in cls._fonts:
            cls._fonts[cache_key] = pygame.font.SysFont(name, scaled_size)

        return cls._fonts[cache_key]

    @classmethod
    def update_scale(cls, new_scale: float):
        """
        Update the scale factor and clear cache.
        Call this when window is resized.
        """
        if new_scale != cls._scale:
            cls._scale = new_scale
            cls._fonts.clear()
            # Re-cache common fonts
            for name in cls.FONT_SPECS:
                cls.get(name)

    @classmethod
    def clear_cache(cls):
        """Clear the font cache."""
        cls._fonts.clear()

    @classmethod
    @property
    def scale(cls) -> float:
        """Get current scale factor."""
        return cls._scale
