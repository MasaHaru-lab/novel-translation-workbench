"""Book-level import kernel.

Provides the smallest filesystem-based primitives for importing a full
novel: chapter splitting, on-disk workspace layout, and initial Book +
BookJob state. Translation execution lives in ``app.chapter`` and is
not invoked from this module.
"""
