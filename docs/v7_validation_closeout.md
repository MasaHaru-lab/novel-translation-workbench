# v7 Validation Closeout

**Batch:** v7 real-sample validation — deepseek-v4-flash
**Date:** 2026-05-03
**Branch:** `main @ 2623d4935211173bf1e8aaa3125f3d43652b2783`
**Type:** Validation / inspection only — no edits to prompts/, app/, project_assets/, orchestrator, CLI, HTTP, or samples.

## Command

```
venv/bin/python -m app.cli chapter run \
  --source data/source/one_chapter_quality_source.txt \
  --book-memory data/book_memory/book_memory.json \
  --model-profile deepseek-v4-flash \
  --output data/exports/one_chapter_quality_sample_v7.md
```

**Model profile:** `deepseek-v4-flash`
**Provider:** OpenAI-compat via `DEEPSEEK_BASE_URL`
**Backend:** `api.deepseek.com` (live cloud API)

## Output

- **Path:** `data/exports/one_chapter_quality_sample_v7.md`
- **Manifest:** `data/exports/one_chapter_quality_sample_v7.manifest.json`
- **Run ID:** `4e48800c8cd3`
- **Segments:** 3/3 completed
- **Retries:** 1 (segment 2 — HTTPS read timeout from DeepSeek API, auto-retried successfully on attempt 2/3)
- **Quality gate:** PASSED
- **Consistency audit:** 2 issues (name_variant: 2) — 0 auto-fixable, 0 auto-fixed

## Segment overlap note

Segment 3 repeats the same dialogue scene that closes segment 2 (Old Lady Qin's "bring them back" speech, Liuxi Qin's response, Lady Xie's question), with slight rewording. This is a known orchestration artifact from segment-boundary overlap, not a translation quality issue. The 2 name_variant consistency issues are caused by the book_memory canonical form ("Qin Liuxi", Chinese order) not being updated to match the current project convention ("Liuxi Qin", Western order per ch 1-3 naming system) — the enhanced name variant check flags "Liuxi" without full canonical "Qin Liuxi" in each segment, and the output uses "Liuxi Qin" instead.

## Inspection: 6 Priorities

### 1. legal mother (嫡母)
- **Status:** CLEAN
- **Finding:** Line 9 renders 嫡母 as "legal mother." Correct, contextually appropriate. No over-expansion or drift.
- No other instances of "mother" where 嫡母 is the source.

### 2. Chi Yuan Daoist (赤元老道)
- **Status:** CLEAN
- **Finding:** Appears 3 times (lines 9, 65, 77), consistently as "Chi Yuan Daoist." No drift into "the old Daoist," appositive variants, or compound-name contamination with Old Lady Qin. Follows title-epithet format rule from style_notes.md line 30.

### 3. Old Lady Qin vs old lady (秦老太太)
- **Status:** CLEAN
- **Finding:** "Old Lady Qin" used consistently throughout all 3 segments as the narrative and dialogue default. No regression to generic lowercase "old lady" as a name substitute. No "Chi Yuan Daoist Lady Qin" contamination (previously observed in Phase C Stage 2).

### 4. Qin Liuxi / Xi'er (秦流西)
- **Status:** CLEAN
- **Finding:** Uses the Western-order canonical "Liuxi Qin" (per ch 1–3 naming system) for all narrative references. "Xi'er" reserved for familiar direct address (Old Lady Qin speaking: line 3; Lady Xie speaking: line 87). No over-use of "Xi'er" in narrative or from characters who would not use familiar address.
- **Note:** The book_memory canonical ("Qin Liuxi") is out of sync with the current project convention ("Liuxi Qin"). This mismatch generates the 2 name_variant consistency audit flags. A future batch should update book_memory to match the canonization.

### 5. Cross-entity prevention
- **Status:** CLEAN
- **Finding:** All 7 entities remain distinct and consistently rendered:
  - Liuxi Qin (narrative default)
  - Old Lady Qin (stable throughout)
  - Lady Wang (stable)
  - Lady Xie (stable)
  - Ding Momo (stable)
  - Chi Yuan Daoist (3 references, all clean)
  - Yuanshan Qin (1 reference, line 41, Western-order consistent)
- No entity contamination, no character-bleed across segments.

### 6. Context-sensitive terms
- **Status:** CLEAN
- **Finding:** Key terms rendered context-appropriately:
  - 嫡女 (line 19) → "legitimate daughter" (correct, not over-literal)
  - 大小姐 (line 19) → "Young Lady" (correct register)
  - 大房 (line 19) → "main branch" (contextual rendering, not literal "great house")
  - 光禄寺卿 (line 29) → "Chief Minister of the Court of Imperial Entertainments" (standard historical title)
  - 老宅 (lines 9, 57) → "old estate" / "old homestead" / "old family estate" (varied naturally, context-appropriate)
  - 不瞑目 (line 67) → "die with my eyes open in death" (preserves the figurative force, not flattened)
  - 一拳打在棉花上 (line 91) → "punched a ball of cotton" (preserves the vivid Chinese metaphor)

## Style Notes: Internal Voice & Dialogue Bluntness

### Internal voice (style_notes.md lines 42–48)
- **Status:** OBSERVABLY FOLLOWED — no flattening of internal reactions into neutral reports.
- Liuxi Qin's internal reasoning (line 15: "Unfeeling, yet kind — the debt of bearing and raising...") preserves her detached, objective inner register.
- Lady Wang's POV (lines 57–65) is rendered as free indirect thought with active wondering ("who had been teaching her? That Chi Yuan Daoist?") rather than flat narration.
- Liuxi Qin's inner thought (line 71: "After all, she did not have long to live") is blunt, efficient, and character-specific.
- Lady Xie's internal reaction (line 91: "felt as if she had punched a ball of cotton") preserves the vivid Chinese metaphor rather than converting to generic narration.
- **No diagnostic occasion for the specific 啧啧暗叹 pattern** — the source does not contain onomatopoeic internal reactions of that type. The internal voice guidance that IS exercised in the sample is followed.

### Dialogue bluntness (style_notes.md lines 39–40)
- **Status:** OBSERVABLY FOLLOWED
- Liuxi Qin's blunt speech to Old Lady Qin (line 53: "If the sovereign wants his minister dead, the minister has no choice but to die") is preserved without softening.
- Old Lady Qin's forceful register (line 67: "I will die with my eyes open in death") retains emotional force.
- Liuxi Qin's curt responses (line 69: "Then you really must take care of yourself") keep the source's dry bluntness without adding softening hedges or explanations.
- No instances of blunt register being sanded away.

## Summary

| Check | Result |
|---|---|
| 3/3 segments | ✓ |
| 0 retries (production) | 1 timeout-retry on segment 2 (cloud API transient, not model error) |
| Quality gate | PASSED |
| Priority 1 (legal mother) | CLEAN |
| Priority 2 (Chi Yuan Daoist) | CLEAN |
| Priority 3 (Old Lady Qin) | CLEAN |
| Priority 4 (Liuxi Qin / Xi'er) | CLEAN |
| Priority 5 (cross-entity) | CLEAN |
| Priority 6 (context-sensitive terms) | CLEAN |
| Internal voice style notes | OBSERVABLY FOLLOWED |
| Dialogue bluntness style notes | OBSERVABLY FOLLOWED |

## Status

**READY** — no blockage. No Type A/B/C resolution needed from this run.

## Known issues (observations, not blockers)

1. **Segment 2–3 overlap:** The same dialogue scene is rendered in both segment 2 and segment 3 with slight rewording. This is a known orchestration boundary artifact, not a translation defect. The 3-segment strategy (finer granularity) plus context repetition at segment boundaries produces this effect. If it becomes a usability concern, review segment boundary strategy or post-aggregation deduplication in a future batch.

2. **Book memory canonical mismatch:** `data/book_memory/book_memory.json` stores "Qin Liuxi" (Chinese order) but the project convention (canonized in `2. characters.md`) uses "Liuxi Qin" (Western order). This mismatch generates 2 name_variant consistency audit flags that are purely mechanical — the output is correct according to project convention. Recommend a future batch to align book_memory with the canonized naming system.

## Recommended follow-up batch (optional, not started)

If segment overlap needs attention: a dedicated batch scoped to segment deduplication in the post-aggregation step. This would touch `app/chapter/` only if a new deduplication filter is needed, or the orchestrator's aggregation logic if the fix is simpler. No prompt, asset, or sample changes needed.
