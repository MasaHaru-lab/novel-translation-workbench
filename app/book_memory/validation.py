"""Lightweight validation helpers for book memory records.

Each ``validate_*`` function returns a ``ValidationResult`` with any errors
found. A result with zero errors is considered valid. This keeps validation
purely functional and side-effect-free.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.book_memory.models import (
    EntityType,
    MemoryRecordStatus,
    BookEntity,
    Relationship,
    TitleRecord,
    ChapterEvent,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)


@dataclass
class ValidationError:
    """A single validation error."""

    field: str
    message: str
    value: object = None


@dataclass
class ValidationResult:
    """Result of a validation pass.

    A result with zero errors is considered valid.
    """

    errors: List[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Return a new ValidationResult with errors combined."""
        return ValidationResult(errors=self.errors + other.errors)


# ── Field-level predicates ──────────────────────────────────────────────────


_ID_REQUIRED_MSG = "id must be a non-empty string"
_ZH_REQUIRED_MSG = "name_zh must be a non-empty string"
_EN_REQUIRED_MSG = "name_en must be a non-empty string"


def _check_required_str(
    value: object, field_name: str, message: str
) -> Optional[ValidationError]:
    if not value or (isinstance(value, str) and not value.strip()):
        return ValidationError(field=field_name, message=message, value=value)
    return None


def _check_optional_str(
    value: object, field_name: str, max_len: int = 5000
) -> Optional[ValidationError]:
    if value is None:
        return None
    if not isinstance(value, str):
        return ValidationError(
            field=field_name, message=f"{field_name} must be a string", value=value
        )
    if len(value) > max_len:
        return ValidationError(
            field=field_name,
            message=f"{field_name} exceeds {max_len} characters",
            value=value,
        )
    return None


def _check_enum(value: object, field_name: str, enum_cls: type) -> Optional[ValidationError]:
    if value is None:
        return ValidationError(
            field=field_name, message=f"{field_name} must not be None", value=value
        )
    valid = {e.value for e in enum_cls}
    if isinstance(value, enum_cls):
        return None
    if isinstance(value, str) and value in valid:
        return None
    return ValidationError(
        field=field_name,
        message=f"{field_name} must be one of {sorted(valid)}, got {value!r}",
        value=value,
    )


# ── Record-level validators ─────────────────────────────────────────────────


def validate_entity(entity: BookEntity) -> ValidationResult:
    """Validate a single BookEntity record."""
    errors: List[ValidationError] = []

    err = _check_required_str(entity.id, "id", _ID_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(entity.name_zh, "name_zh", _ZH_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(entity.name_en, "name_en", _EN_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_enum(entity.entity_type, "entity_type", EntityType)
    if err:
        errors.append(err)

    err = _check_enum(entity.status, "status", MemoryRecordStatus)
    if err:
        errors.append(err)

    err = _check_optional_str(entity.description, "description")
    if err:
        errors.append(err)

    if entity.first_chapter is not None and entity.first_chapter < 1:
        errors.append(
            ValidationError(
                field="first_chapter",
                message="first_chapter must be >= 1 when set",
                value=entity.first_chapter,
            )
        )

    if entity.last_chapter is not None and entity.last_chapter < 1:
        errors.append(
            ValidationError(
                field="last_chapter",
                message="last_chapter must be >= 1 when set",
                value=entity.last_chapter,
            )
        )

    if (
        entity.first_chapter is not None
        and entity.last_chapter is not None
        and entity.last_chapter < entity.first_chapter
    ):
        errors.append(
            ValidationError(
                field="last_chapter",
                message="last_chapter must be >= first_chapter",
                value=entity.last_chapter,
            )
        )

    return ValidationResult(errors=errors)


def validate_relationship(rel: Relationship) -> ValidationResult:
    """Validate a single Relationship record."""
    errors: List[ValidationError] = []

    err = _check_required_str(rel.id, "id", _ID_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(rel.source_id, "source_id", "source_id must be a non-empty string")
    if err:
        errors.append(err)

    err = _check_required_str(rel.target_id, "target_id", "target_id must be a non-empty string")
    if err:
        errors.append(err)

    err = _check_required_str(rel.relation_type, "relation_type", "relation_type must be a non-empty string")
    if err:
        errors.append(err)

    err = _check_enum(rel.status, "status", MemoryRecordStatus)
    if err:
        errors.append(err)

    if rel.source_id == rel.target_id:
        errors.append(
            ValidationError(
                field="target_id",
                message="source_id and target_id must be different",
                value=rel.target_id,
            )
        )

    return ValidationResult(errors=errors)


def validate_title_record(rec: TitleRecord) -> ValidationResult:
    """Validate a single TitleRecord."""
    errors: List[ValidationError] = []

    err = _check_required_str(rec.id, "id", _ID_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(rec.name_zh, "name_zh", _ZH_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(rec.name_en, "name_en", _EN_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_enum(rec.status, "status", MemoryRecordStatus)
    if err:
        errors.append(err)

    valid_categories = {"title", "address", "term"}
    if rec.category not in valid_categories:
        errors.append(
            ValidationError(
                field="category",
                message=f"category must be one of {sorted(valid_categories)}, got {rec.category!r}",
                value=rec.category,
            )
        )

    return ValidationResult(errors=errors)


def validate_chapter_event(event: ChapterEvent) -> ValidationResult:
    """Validate a single ChapterEvent."""
    errors: List[ValidationError] = []

    if event.chapter < 1:
        errors.append(
            ValidationError(
                field="chapter",
                message="chapter must be >= 1",
                value=event.chapter,
            )
        )

    err = _check_enum(event.status, "status", MemoryRecordStatus)
    if err:
        errors.append(err)

    return ValidationResult(errors=errors)


def validate_translation_decision(dec: TranslationDecision) -> ValidationResult:
    """Validate a single TranslationDecision."""
    errors: List[ValidationError] = []

    err = _check_required_str(dec.id, "id", _ID_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(dec.entity_id, "entity_id", "entity_id must be a non-empty string")
    if err:
        errors.append(err)

    err = _check_required_str(
        dec.decision_type, "decision_type", "decision_type must be a non-empty string"
    )
    if err:
        errors.append(err)

    valid_types = {"rendering", "style", "consistency"}
    if dec.decision_type not in valid_types:
        errors.append(
            ValidationError(
                field="decision_type",
                message=f"decision_type must be one of {sorted(valid_types)}, got {dec.decision_type!r}",
                value=dec.decision_type,
            )
        )

    err = _check_enum(dec.status, "status", MemoryRecordStatus)
    if err:
        errors.append(err)

    if dec.chapter_decided < 0:
        errors.append(
            ValidationError(
                field="chapter_decided",
                message="chapter_decided must be >= 0",
                value=dec.chapter_decided,
            )
        )

    return ValidationResult(errors=errors)


def validate_unresolved_decision(ud: UnresolvedDecision) -> ValidationResult:
    """Validate a single UnresolvedDecision."""
    errors: List[ValidationError] = []

    err = _check_required_str(ud.id, "id", _ID_REQUIRED_MSG)
    if err:
        errors.append(err)

    err = _check_required_str(ud.question, "question", "question must be a non-empty string")
    if err:
        errors.append(err)

    if ud.created_chapter < 0:
        errors.append(
            ValidationError(
                field="created_chapter",
                message="created_chapter must be >= 0",
                value=ud.created_chapter,
            )
        )

    return ValidationResult(errors=errors)


# ── Container-level validators ──────────────────────────────────────────────


def validate_book_memory(memory: BookMemory) -> ValidationResult:
    """Validate an entire BookMemory container.

    Runs per-record validation on every record and cross-reference checks:
    - relationship source/target entities exist
    - chapter_event entities_involved refer to known entity ids
    - translation_decision entity_id refers to a known entity or title
    """
    result = ValidationResult()

    # Build known entity and title id sets
    known_entity_ids: set = set(memory.entities.keys())
    known_title_ids: set = set(memory.titles.keys())

    for eid, entity in memory.entities.items():
        r = validate_entity(entity)
        result = result.merge(r)

    for rid, rel in memory.relationships.items():
        r = validate_relationship(rel)
        result = result.merge(r)

        # Cross-reference: source entity exists
        if rel.source_id not in known_entity_ids:
            result = result.merge(
                ValidationResult(
                    errors=[
                        ValidationError(
                            field="source_id",
                            message=f"Relationship {rid!r} references unknown entity {rel.source_id!r}",
                            value=rel.source_id,
                        )
                    ]
                )
            )

        # Cross-reference: target entity exists
        if rel.target_id not in known_entity_ids:
            result = result.merge(
                ValidationResult(
                    errors=[
                        ValidationError(
                            field="target_id",
                            message=f"Relationship {rid!r} references unknown entity {rel.target_id!r}",
                            value=rel.target_id,
                        )
                    ]
                )
            )

    for tid, title in memory.titles.items():
        r = validate_title_record(title)
        result = result.merge(r)

    for cnum, event in memory.chapter_events.items():
        r = validate_chapter_event(event)
        result = result.merge(r)

        # Cross-reference: entities_involved exist
        for eid in event.entities_involved:
            if eid not in known_entity_ids:
                result = result.merge(
                    ValidationResult(
                        errors=[
                            ValidationError(
                                field="entities_involved",
                                message=f"Chapter {cnum} references unknown entity {eid!r}",
                                value=eid,
                            )
                        ]
                    )
                )

    for did, dec in memory.translation_decisions.items():
        r = validate_translation_decision(dec)
        result = result.merge(r)

        # Cross-reference: entity_id exists
        eid = dec.entity_id
        if eid not in known_entity_ids and eid not in known_title_ids:
            result = result.merge(
                ValidationResult(
                    errors=[
                        ValidationError(
                            field="entity_id",
                            message=f"Translation decision {did!r} references unknown entity/title {eid!r}",
                            value=eid,
                        )
                    ]
                )
            )

    for did, ud in memory.unresolved_decisions.items():
        r = validate_unresolved_decision(ud)
        result = result.merge(r)

    return result
