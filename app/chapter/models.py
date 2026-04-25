from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.chapter.manifest import ChapterStatus, RunManifest, SegmentStatus
from app.segment.segmenter import Segment
from app.translate.schema import TranslationOutput


@dataclass
class ChapterPlan:
    """A plan for translating a full chapter.

    Produced by the planning phase. Contains the chapter title,
    full source text, and a list of segments to translate in order.

    Extended in Batch 4A with strategy assessment fields:
    - ``complexity_level``: assessed chapter complexity ("low", "medium", "high")
    - ``complexity_signals``: raw complexity signal values
    - ``segment_risks``: per-segment risk assessment dicts
    - ``strategy_plan``: full strategy plan with decisions and rationale

    All strategy fields are Optional and default to None so existing code
    that creates plans without strategy assessment continues to work.
    """

    chapter_title: str
    source_text: str
    segments: List[Segment] = field(default_factory=list)

    # Batch 4A: strategy assessment fields
    complexity_level: Optional[str] = None
    """Assessed chapter complexity level: "low", "medium", or "high"."""

    complexity_signals: Optional[dict] = None
    """Raw complexity signal values (total_chars, dialogue_density, etc.)."""

    segment_risks: Optional[Dict[str, dict]] = None
    """Per-segment risk assessments, keyed by segment_id string."""

    strategy_plan: Optional[dict] = None
    """Full strategy plan including overall strategy, per-segment strategies,
    and human-readable rationale."""

    @property
    def segment_count(self) -> int:
        return len(self.segments)


@dataclass
class ChapterResult:
    """Aggregated result of a completed chapter translation.

    Contains the original source, per-segment translation outputs,
    and the full aggregated English chapter text.

    Extended in Batch 2 with runtime status tracking:
    - ``chapter_status``: overall chapter run status
    - ``segment_statuses``: per-segment status map (by segment_id)
    - ``manifest``: optional reference to the run manifest (set when
      the orchestrator runs with manifest-based execution)
    - ``failed_segment_ids``: which segments failed (empty if none)
    - ``resumable``: whether the run can be resumed

    Extended in Batch 3 with consistency pass results:
    - ``consistency_audit``: chapter-level consistency audit findings
    - ``correction_summary``: summary of automatic corrections applied
    - ``corrected_translation``: the post-consistency-pass text (if
      corrections were applied); otherwise None (use aggregated_translation)
    """

    chapter_title: str
    source_text: str
    segment_results: List[TranslationOutput] = field(default_factory=list)
    aggregated_translation: str = ""

    # Batch 2: runtime status fields
    chapter_status: ChapterStatus = ChapterStatus.PENDING
    segment_statuses: Dict[str, SegmentStatus] = field(default_factory=dict)
    manifest: Optional[RunManifest] = None
    failed_segment_ids: List[str] = field(default_factory=list)
    resumable: bool = False

    # Batch 3: consistency pass fields
    consistency_audit: Optional[dict] = None
    """Structured summary dict from the consistency audit (or None if not run)."""

    correction_summary: Optional[dict] = None
    """Structured summary dict from the correction pass (or None if not run)."""

    corrected_translation: Optional[str] = None
    """Post-consistency-pass corrected text. None when no corrections were
    needed or when the consistency pass was not run."""

    # Batch 4A: strategy assessment visibility
    strategy_plan_summary: Optional[dict] = None
    """Strategy plan summary from the pre-execution strategy assessment.
    Contains complexity level, risk assessments, and strategy decisions.
    None when strategy assessment was not performed or failed."""

    # Quality gate report (deterministic post-hoc validation).
    # Populated by the orchestrator after aggregation. ``None`` means the
    # gate was not run; an empty report means the chapter passed.
    # ``Any`` typing avoids a forward-import cycle with quality.py.
    quality_report: Optional[object] = None

    # Batch 4B: enactment record
    enactment: Optional[dict] = None
    """Enactment record showing how strategy decisions were applied at runtime.

    Structure::

        {
            "planned": {
                "segmentation_granularity": "standard" | "finer",
                "budget_profile": "light" | "standard" | "conservative",
                "consistency_intensity": "standard" | "enhanced"
            },
            "enacted": {
                "segmentation": {
                    "granularity": str,
                    "max_chars": int,
                    "min_chars": int,
                    "segment_count": int
                },
                "budget": {
                    "profile": str,
                    "draft_max_tokens": int,
                    "review_max_tokens": int,
                    "polish_max_tokens": int
                },
                "consistency": {
                    "intensity": str,
                    "audit_issues_found": int,
                    "auto_fixable": int,
                    "auto_fixed": int,
                    "corrections_applied": bool
                }
            },
            "consistent": bool
        }

    ``consistent`` is True when all three planned strategy dimensions match
    what was actually enacted (no override needed). None when strategy
    assessment was not performed.
    """

    @property
    def segment_count(self) -> int:
        return len(self.segment_results)

    @property
    def is_complete(self) -> bool:
        """True when all segments translated successfully."""
        return self.chapter_status == ChapterStatus.COMPLETED

    @property
    def is_partial(self) -> bool:
        """True when some segments succeeded, some failed."""
        return self.chapter_status == ChapterStatus.PARTIAL

    @property
    def success_count(self) -> int:
        """Number of successfully translated segments."""
        return sum(
            1 for s in self.segment_statuses.values()
            if s == SegmentStatus.COMPLETED
        )

    @property
    def final_translation(self) -> str:
        """Return the best available translation text.

        Prefers the consistency-corrected version when available, falls
        back to the basic aggregated translation otherwise.
        """
        if self.corrected_translation is not None:
            return self.corrected_translation
        return self.aggregated_translation
