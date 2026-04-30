"""Book memory — structured narrative graph memory for long-book translation consistency.

Provides the data model, validation, JSON persistence, and project-asset bootstrap
for a ``BookMemory`` that can grow alongside translation of a 1000+ chapter novel.
"""

from app.book_memory.models import (
    EntityType,
    MemoryRecordStatus,
    EvidenceRef,
    BookEntity,
    Relationship,
    TitleRecord,
    ChapterEvent,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)
from app.book_memory.validation import (
    validate_book_memory,
    validate_entity,
    validate_relationship,
    validate_title_record,
    validate_chapter_event,
    validate_translation_decision,
    validate_unresolved_decision,
    ValidationError,
    ValidationResult,
)
from app.book_memory.store import (
    BookMemoryStore,
    InMemoryBookMemoryStore,
    FileBookMemoryStore,
)
from app.book_memory.bootstrap import bootstrap_from_project_assets
from app.book_memory.serialization import (
    book_memory_to_dict,
    book_memory_from_dict,
)
from app.book_memory.retrieval import (
    EntityMatch,
    TitleMatch,
    ContextPack,
    build_context_pack,
    DEFAULT_MAX_CHARS,
)

__all__ = [
    "EntityType",
    "MemoryRecordStatus",
    "EvidenceRef",
    "BookEntity",
    "Relationship",
    "TitleRecord",
    "ChapterEvent",
    "TranslationDecision",
    "UnresolvedDecision",
    "BookMemory",
    "validate_book_memory",
    "validate_entity",
    "validate_relationship",
    "validate_title_record",
    "validate_chapter_event",
    "validate_translation_decision",
    "validate_unresolved_decision",
    "ValidationError",
    "ValidationResult",
    "BookMemoryStore",
    "InMemoryBookMemoryStore",
    "FileBookMemoryStore",
    "bootstrap_from_project_assets",
    "book_memory_to_dict",
    "book_memory_from_dict",
    "EntityMatch",
    "TitleMatch",
    "ContextPack",
    "build_context_pack",
    "DEFAULT_MAX_CHARS",
]
