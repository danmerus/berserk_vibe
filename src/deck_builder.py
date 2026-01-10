"""Deck builder for creating and managing card decks."""
import json
import os
import base64
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .card_database import CARD_DATABASE


# Maximum copies of a single card in deck
MAX_COPIES_PER_CARD = 3
# Library has 3 copies of each card
LIBRARY_COPIES = 3
# Deck size limits
MIN_DECK_SIZE = 30
MAX_DECK_SIZE = 50


@dataclass
class DeckBuilder:
    """Manages deck building state."""

    name: str = "Новая колода"
    cards: Dict[str, int] = field(default_factory=dict)  # card_name -> count in deck
    file_path: Optional[str] = None  # Path if loaded from file
    _protected: bool = field(default=False, repr=False)  # Track protected status

    def __post_init__(self):
        """Initialize library with all available cards."""
        self._library = self._create_library()

    def _create_library(self) -> Dict[str, int]:
        """Create library with LIBRARY_COPIES of each card."""
        library = {}
        for card_name in CARD_DATABASE.keys():
            # Remaining = library copies minus what's in deck
            in_deck = self.cards.get(card_name, 0)
            library[card_name] = LIBRARY_COPIES - in_deck
        return library

    def get_library_cards(self) -> List[Tuple[str, int]]:
        """Get all library cards with remaining counts.

        Returns list of (card_name, remaining_count) sorted by element then name.
        """
        result = []
        for card_name, remaining in self._library.items():
            result.append((card_name, remaining))

        # Sort by element, then by cost, then by name
        def sort_key(item):
            card_name = item[0]
            stats = CARD_DATABASE[card_name]
            return (stats.element.value, stats.cost, card_name)

        return sorted(result, key=sort_key)

    def get_deck_cards(self) -> List[Tuple[str, int]]:
        """Get all cards in deck with counts.

        Returns list of (card_name, count) sorted by element then name.
        """
        result = [(name, count) for name, count in self.cards.items() if count > 0]

        # Sort by element, then by cost, then by name
        def sort_key(item):
            card_name = item[0]
            stats = CARD_DATABASE[card_name]
            return (stats.element.value, stats.cost, card_name)

        return sorted(result, key=sort_key)

    def add_card(self, card_name: str) -> bool:
        """Add a card from library to deck.

        Returns True if successful, False if cannot add.
        """
        if card_name not in CARD_DATABASE:
            return False

        # Check deck size limit
        if self.get_total_count() >= MAX_DECK_SIZE:
            return False

        # Check if library has copies available
        if self._library.get(card_name, 0) <= 0:
            return False

        # Check max copies per card
        if self.cards.get(card_name, 0) >= MAX_COPIES_PER_CARD:
            return False

        # Add to deck, remove from library
        self.cards[card_name] = self.cards.get(card_name, 0) + 1
        self._library[card_name] -= 1
        return True

    def remove_card(self, card_name: str) -> bool:
        """Remove a card from deck back to library.

        Returns True if successful, False if card not in deck.
        """
        if card_name not in self.cards or self.cards[card_name] <= 0:
            return False

        # Remove from deck, add back to library
        self.cards[card_name] -= 1
        if self.cards[card_name] == 0:
            del self.cards[card_name]
        self._library[card_name] = self._library.get(card_name, 0) + 1
        return True

    def get_total_count(self) -> int:
        """Get total number of cards in deck."""
        return sum(self.cards.values())

    def get_deck_card_list(self) -> List[str]:
        """Get flat list of all cards in deck (with duplicates).

        Returns list of card names, e.g. ["Циклоп", "Циклоп", "Гном-басаарг", ...]
        """
        result = []
        for card_name, count in self.cards.items():
            result.extend([card_name] * count)
        return result

    def is_valid(self) -> bool:
        """Check if deck meets size requirements (30-50 cards)."""
        total = self.get_total_count()
        return MIN_DECK_SIZE <= total <= MAX_DECK_SIZE

    def clear(self):
        """Clear deck and reset library."""
        self.cards.clear()
        self._library = self._create_library()
        self.file_path = None
        self._protected = False

    def new_deck(self, name: str = "Новая колода"):
        """Start a new empty deck."""
        self.name = name
        self.clear()

    def save(self, directory: str = "data/decks", new_name: str = None) -> bool:
        """Save deck to JSON file.

        Args:
            directory: Directory to save to
            new_name: Optional new name for the deck

        Returns True if successful, False if protected or error.
        """
        # Protected decks cannot be modified - must save as new deck
        if self._protected and not new_name:
            return False

        try:
            os.makedirs(directory, exist_ok=True)

            # Update name if provided
            if new_name:
                self.name = new_name

            # Create safe filename from deck name
            safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in self.name)
            safe_name = safe_name.strip() or "deck"
            new_filepath = os.path.join(directory, f"{safe_name}.json")

            # Check if we're renaming (old file exists and path is different)
            old_filepath = self.file_path

            # Protected decks: only allow saving to a NEW file (copy as unprotected)
            if self._protected:
                if new_filepath == old_filepath:
                    return False  # Can't overwrite protected file
                # Save as new unprotected deck
                data = {
                    "name": self.name,
                    "cards": [{"name": name, "count": count}
                             for name, count in self.cards.items() if count > 0]
                }
                # New copy is NOT protected
            else:
                # Normal save
                data = {
                    "name": self.name,
                    "cards": [{"name": name, "count": count}
                             for name, count in self.cards.items() if count > 0]
                }

            # Save to file
            with open(new_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Delete old file if renaming (and it's a different file, and not protected)
            if old_filepath and old_filepath != new_filepath and os.path.exists(old_filepath):
                if not self._protected:
                    try:
                        os.remove(old_filepath)
                    except Exception:
                        pass

            self.file_path = new_filepath
            self._protected = False  # New/renamed file is not protected
            return True
        except Exception as e:
            print(f"Error saving deck: {e}")
            return False

    def load(self, filepath: str) -> bool:
        """Load deck from JSON file.

        Returns True if successful.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.name = data.get("name", "Загруженная колода")
            self.cards.clear()
            self._protected = data.get("protected", False)

            for card_data in data.get("cards", []):
                card_name = card_data.get("name")
                count = card_data.get("count", 1)
                if card_name in CARD_DATABASE:
                    self.cards[card_name] = min(count, MAX_COPIES_PER_CARD)

            self._library = self._create_library()
            self.file_path = filepath
            return True
        except Exception as e:
            print(f"Error loading deck: {e}")
            return False

    def is_protected(self) -> bool:
        """Check if the current deck is protected from deletion."""
        return self._protected

    def delete(self) -> bool:
        """Delete the current deck file.

        Returns True if successful, False if protected or error.
        """
        if not self.file_path or not os.path.exists(self.file_path):
            return False

        # Don't delete protected decks - check both in-memory and file
        if self._protected:
            return False

        # Extra safety: always check the file directly before deleting
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get("protected", False):
                return False
        except Exception:
            pass  # If we can't read, proceed with caution based on _protected flag

        try:
            os.remove(self.file_path)
            self.clear()
            self.name = "Новая колода"
            return True
        except Exception as e:
            print(f"Error deleting deck: {e}")
            return False

    def export_code(self) -> str:
        """Export deck as a shareable code string.

        Format: base64 encoded JSON of card names and counts.
        """
        if not self.cards:
            return ""

        # Create compact representation
        data = {
            "n": self.name,
            "c": [[name, count] for name, count in self.cards.items() if count > 0]
        }

        json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        encoded = base64.b64encode(json_str.encode('utf-8')).decode('ascii')
        return encoded

    def import_code(self, code: str) -> bool:
        """Import deck from a code string.

        Returns True if successful.
        """
        try:
            code = code.strip()
            if not code:
                return False

            json_str = base64.b64decode(code.encode('ascii')).decode('utf-8')
            data = json.loads(json_str)

            self.name = data.get("n", "Импортированная колода")
            self.cards.clear()

            for card_data in data.get("c", []):
                if isinstance(card_data, list) and len(card_data) >= 2:
                    card_name, count = card_data[0], card_data[1]
                    if card_name in CARD_DATABASE:
                        self.cards[card_name] = min(count, MAX_COPIES_PER_CARD)

            self._library = self._create_library()
            self.file_path = None
            self._protected = False  # Imported deck is not protected
            return True
        except Exception as e:
            print(f"Error importing deck: {e}")
            return False

    @staticmethod
    def list_saved_decks(directory: str = "data/decks") -> List[str]:
        """Get list of saved deck file paths."""
        if not os.path.exists(directory):
            return []

        decks = []
        for filename in os.listdir(directory):
            if filename.endswith('.json'):
                decks.append(os.path.join(directory, filename))
        return sorted(decks)

    @staticmethod
    def get_deck_name_from_file(filepath: str) -> str:
        """Read deck name from file without loading full deck."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("name", os.path.basename(filepath))
        except:
            return os.path.basename(filepath)
