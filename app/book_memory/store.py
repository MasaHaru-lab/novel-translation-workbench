"""Storage layer for BookMemory — JSON persistence and in-memory store.

Provides two implementations:

- ``InMemoryBookMemoryStore``: holds a BookMemory in memory (useful for tests).
- ``FileBookMemoryStore``: persists to a JSON file on disk.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.book_memory.models import BookMemory
from app.book_memory.serialization import (
    book_memory_to_dict,
    book_memory_from_dict,
)
from app.book_memory.validation import validate_book_memory, ValidationResult

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "book_memory"
DEFAULT_FILENAME = "book_memory.json"


class BookMemoryStore(ABC):
    """Abstract base for a BookMemory store."""

    @abstractmethod
    def load(self) -> Optional[BookMemory]:
        """Load the current BookMemory, or None if none exists."""
        ...

    @abstractmethod
    def save(self, memory: BookMemory) -> None:
        """Persist the given BookMemory."""
        ...

    @abstractmethod
    def exists(self) -> bool:
        """True if persisted data exists and can be loaded."""
        ...


class InMemoryBookMemoryStore(BookMemoryStore):
    """In-memory BookMemory store (useful for tests and transient use)."""

    def __init__(self, memory: Optional[BookMemory] = None):
        self._memory = memory or BookMemory()

    def load(self) -> Optional[BookMemory]:
        return self._memory

    def save(self, memory: BookMemory) -> None:
        self._memory = memory

    def exists(self) -> bool:
        return self._memory is not None


class FileBookMemoryStore(BookMemoryStore):
    """File-backed BookMemory store using JSON serialisation.

    Args:
        filepath: Path to the JSON file. Defaults to
            ``data/book_memory/book_memory.json``.
    """

    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath or (DEFAULT_DIR / DEFAULT_FILENAME)

    def load(self) -> Optional[BookMemory]:
        """Load BookMemory from the JSON file.

        Returns None if the file does not exist. Raises on parse errors.
        """
        if not self.filepath.is_file():
            return None

        try:
            raw = self.filepath.read_text(encoding="utf-8")
            data = json.loads(raw)
            return book_memory_from_dict(data)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse book memory JSON at {self.filepath}: {e}"
            ) from e

    def save(self, memory: BookMemory) -> None:
        """Persist BookMemory to the JSON file.

        Runs validation before saving. Logs a warning but still saves if
        validation finds errors (the data is not rejected at the store level).
        """
        # Validate before saving (warn-only, don't block)
        vresult: ValidationResult = validate_book_memory(memory)
        if not vresult.is_valid:
            logger.warning(
                "BookMemory validation found %d error(s) before save: %s",
                vresult.error_count,
                [str(e) for e in vresult.errors],
            )

        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        data = book_memory_to_dict(memory)
        self.filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def exists(self) -> bool:
        return self.filepath.is_file()
