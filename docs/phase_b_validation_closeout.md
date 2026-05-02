# Phase B Real-Model Validation Closeout

**Date:** 2026-05-02
**Branch:** `main`
**HEAD:** `9f87a6f` — "fix: filter common lowercase notes variants"

## Purpose

Validate that Round 2 (notes-variant filtering) and Round 3/Phase B Round 2
(cross-entity consistency prevention) eliminated mechanical consistency pollution
when running the approved sample through the real-model chapter pipeline with
book memory and a DeepSeek model profile.

## Command

```bash
venv/bin/python -m app.cli chapter run \
  --source data/source/one_chapter_quality_source.txt \
  --book-memory data/book_memory/book_memory.json \
  --model-profile deepseek-v4-flash
```

## Results

| Field | Value |
|---|---|
| Status | **completed** |
| Segments | 3/3, 0 retries |
| Quality gate | **passed** — 0 errors, 0 warnings |
| Strategy | Complexity high, granularity finer, consistency enhanced, mode conservative |
| Elapsed | 210.3s |
| Output | `data/exports/one_chapter_quality_source_en.md` |
| Manifest | `data/exports/one_chapter_quality_source_en.manifest.json` |
| Working tree | clean (before and after) |

## Key Inspection Findings

### Mechanical replacement pollution — all clear

| Signal | Verdict | Detail |
|---|---|---|
| "mother" → "legal mother" | **Fixed** | `legal mother` renders 嫡母 correctly once. No over-expansion. |
| "venerable" → "Chi Yuan Daoist" | **Fixed** | `Chi Yuan Daoist` used for both 赤元老道 references. No generic bleed. |
| "old" / "girl" consistency | **Fixed** | `Old Lady Qin` (title) vs `old lady` (descriptive) correctly distinguished. `girl` only in natural prose. |
| Qin Liuxi / Xi'er corruption | **Fixed** | `Qin Liuxi` for narrative/POV; `Xi'er` for familiar dialogue address. Canonical mapping per book memory. |
| Cross-entity replacement | **Fixed** | All 7 entities (Old Lady Qin, Qin Liuxi, Lady Wang, Lady Xie, Ding Momo, Chi Yuan Daoist, Qin Yuanshan) correct and distinct. |

### Context-sensitive term accuracy

All 24 tracked terms resolved correctly against `data/book_memory/book_memory.json`,
including 秦老太太→Old Lady Qin, 丁嬷嬷→Ding Momo, 嫡母→legal mother, 嫡长女→legal eldest daughter,
福礼→formal feminine salute, 光禄寺卿→Chief Minister of the Court of Imperial Entertainments,
命格→fate pattern, 冲煞→clashing baleful influence, 大灃→Great Feng, 吉祥物→auspicious symbol,
and 伴君如伴虎→like lying beside a tiger (consistent across two occurrences).

### Model translation quality

No meaning errors, hallucinated additions, register errors, missing content,
or inline Chinese observed.

## Issue Classification

All 6 inspection priorities: **Fixed / no issue.**

Zero instances of:
- Mechanical notes-variant pollution ✓
- Cross-entity consistency pollution ✓
- Semantic/context-aware classification failure ✓
- Model translation quality issue ✓

## Conclusion

**No Round 4 fix batch needed.** Round 2 and Round 3 fixes are holding against
real-model output with DeepSeek profile and full book memory context.

Phase B quality-loop validation is complete for the approved sample.
