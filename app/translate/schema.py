from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class GlossaryTerm:
    """A glossary term mapping source language to target language."""
    zh: str
    en: str


@dataclass
class TranslationInput:
    """Structured input for translation processing."""
    segment_id: str  # string for flexibility
    source_text: str
    prev_context: Optional[str] = None
    next_context: Optional[str] = None
    glossary_terms: List[GlossaryTerm] = None
    context_pack_text: str = ""  # Pre-rendered ContextPack for Prompt A/B injection (R3)

    def __post_init__(self):
        if self.glossary_terms is None:
            self.glossary_terms = []


@dataclass
class TranslationOutput:
    """Structured output from translation processing."""
    segment_id: str
    draft_translation: str
    polished_translation: str
    notes: List[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []