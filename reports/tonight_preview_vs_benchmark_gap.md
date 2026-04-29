# Tonight Preview vs Benchmark Gap

Comparing Translation A (current pipeline, `qwen2.5:14b`) with Translation B (prior benchmark, likely stronger model).

## 1. Biggest differences between A and B

**A translates words; B translates scenes.** A preserves Chinese sentence structure and diction — the English follows the Chinese grammar so closely that you can almost reconstruct the original word order. B breaks free: it takes the *meaning* of each line and re-expresses it in natural English paragraph rhythm.

**Prose register.** A uses flat, dictionary-equivalent language ("baleful influence of the Qin family", "registered you under your principal mother's name", "the debt of raising you"). B uses idiomatic, novel-ready English ("walking on thin ice", "double-edged sword", "her curiosity was piqued", "like hitting a wall of cotton").

**Dialogue naturalness.** A's dialogue sounds like someone reading a translation aloud: stilted attribution ("Old Lady Qin said calmly", "Qin Liuxi said with a self-mocking smile"). B's dialogue embeds naturally into the narrative flow with varied, punchy beats.

**Naming and address.** A renders "西丫头" as lowercase `"girl,"` — the reader cannot tell if this is a term of address, a description, or a stage direction. The benchmark versions render it as `"Little Xi"` or `"Xi girl"` — clearly an affectionate family address, which preserves the relationship cue.

**Consistency within output.** A has internal register conflicts: `"girl"` (lowercase, generic) next to `"Old Lady Qin"` (formal title) next to `"The Daoist Red Yuan"` (transliterated title). It feels like three different translators handled adjacent sentences.

## 2. Why A feels like raw machine output

A is doing a textbook ML translation: maximize token-level fidelity to the source at the cost of readability. Every clause in the Chinese gets an English clause in the same order. Every noun phrase gets a literal expansion. The result is *correct* in the sense that no information is lost, but *wrong* in the sense that no native reader would write it this way.

Specific signals:

- **Agentless passives and awkward nominalization** — "you were often ill because of the baleful influence of the Qin family" vs. B's implied active voice.
- **Over-explanation** — "the previous statement had already set the context" is a translation of a bridging phrase that a human writer would omit or fold into narrative.
- **Uniform sentence cadence** — nearly every sentence in A follows the same S-V-O length, producing a monotonous rhythm. B varies sentence length and uses fragmentary beats for effect.

## 3. Why B feels closer to readable novel prose

B treats the source as a *scene to be rendered*, not a *string to be converted*. The translator (human or model) asked: "What would an English novelist write here?" rather than "What English words correspond to these Chinese words?"

Concrete techniques visible in B:

- **Idiom substitution** — 伴君如伴虎 becomes "serving the emperor is like walking on thin ice", not a word-for-word gloss.
- **Compression** — B folds multi-clause Chinese constructions into tighter English sentences.
- **Register consistency** — all characters speak and are described at the same literary level; no sudden drops into clinical or bureaucratic English.
- **Narrative distance** — B uses past perfect and other tense/aspect markers to create narrative distance and flow. A tends toward simple past throughout, creating a flat timeline.

## 4. What to improve first

Ordered by expected impact:

1. **Backend model (highest leverage, but unvalidated).** `qwen2.5:14b` is the current verified pipeline backend — the one we proved works end-to-end in Sprint 1B. Its poor literary output proves it is insufficient for final quality, but this report's comparison is between a 14B model and an unknown (likely 70B+) benchmark. We cannot attribute the gap entirely to model size without a controlled comparison. A faster, smaller model was chosen for path verification; the best available backend may differ. See the backend benchmark track below for the recommended evaluation before any default-backend change.

2. **Prompt A (draft instruction).** The draft prompt likely instructs "faithful translation" or prioritizes completeness over readability. This produces mechanically correct but stylistically flat prose. The prompt should instruct *literary re-expression*: "Translate this scene as an English novelist would write it. Preserve meaning, characters, and pacing, but use natural English sentence structure and idiom."

3. **Prompt B (review pass).** The review pass runs after the draft but the final output still has obvious machine-translation artifacts. This means Prompt B is not catching the pattern it should — it finds structural issues (title casing, name variants) but not register problems. Prompt B could be strengthened to evaluate naturalness, not just correctness.

4. **Glossary / project assets.** "西丫头" should be in the glossary as `"Little Xi"` or `"Xi'er"` to prevent the pipeline from defaulting to `"girl"`. Similarly, 命格, 冲煞, 记在名下, and other recurring historical-fiction terms need defined translations so the model gets consistent guidance across segments.

5. **Quality gate (lowest immediate leverage).** The quality gate passed — meaning it did not catch any of these issues. Adding a naturalness / register check would help, but this is downstream of fixing the draft output first.

## 5. Next most useful batch

**Sprint 2A: Quality-memory extraction → prompt upgrade → re-run.**

Three phases, executed in order within Sprint 2A:

**Phase 1 — Extract quality memory from tonight's evidence (no prompt changes yet).**

The gap report above is Sprint 2A's evidence layer. Before touching any prompt, extract its findings into three persistent quality-memory files under `quality_memory/`:

- `mistranslation_terms.md` — 错译词库. Term-level failures and preferred renderings. Covers address terms, kinship/status terms, official ranks, ritual/court terms, historical-household vocabulary, and literalized idioms. Initial candidates: 丫头, 嫡母, 命格, 冲煞, 光禄寺卿, 三牲, 小人作祟.

- `failure_patterns.md` — Whole-output / scene-level / style-level failure modes. Catches patterns like "A translates words; B translates scenes", prose register gaps, dialogue attribution stiltedness, internal register conflicts, and the 14B-capacity ceiling.

- `benchmark_excerpts.md` (or `phrasing_bank.md`) — Positive examples from Translation B. Reusable examples of scene-level re-expression, dialogue rhythm, register consistency, natural attribution, and idiomatic fiction prose.

These files transform a one-time comparison into reusable guidance that future pipeline runs and prompt revisions can reference directly.

**Phase 2 — Upgrade prompts using the extracted lessons.**

With the quality-memory layer in place:

- Revise Prompt A from "faithful translation" instruction to "literary re-expression" instruction, informed by the failure patterns and phrasing bank.
- Revise Prompt B to judge naturalness and register consistency, not just structural correctness and name matching.
- Add glossary entries to project assets for the most frequently mishandled terms identified in `mistranslation_terms.md`.

**Phase 3 — Run and compare.**

Run `data/source/one_chapter_quality_source.txt` through the updated pipeline and compare the new output against this report's Translation B benchmark. The comparison reuses the same evaluation framework (prose scene quality, dialogue register, term stability, fidelity) established in this gap report.

The backend model upgrade track (below) is independent of this sequence. Each track can proceed without blocking the other.

---

### Backend benchmark track (parallel to Sprint 2A)

Before changing the default backend, run a controlled comparison to establish which model actually produces better literary output given the same prompts and assets.

Protocol:

1. **Keep qwen2.5:14b as the baseline.** It is the verified pipeline backend — known to work, known to be fast, known ceiling on literary quality.

2. **Identify stronger available candidates.** Check what other backends are reachable:
   - Fishhead Ollama: any larger pulled models, or available to pull (e.g. qwen2.5:72b, llama3.3:70b)
   - Fishhead wrapper: if the wrapper is revived, what model does it serve?
   - Local: Ollama on this machine with a pulled model
   - Alternative remote endpoints

3. **Run the same source passage** (`data/source/one_chapter_quality_source.txt`) through each candidate using identical Prompt A, Prompt B, project assets, and pipeline flags. Do not vary anything except the backend.

4. **Save outputs side by side** under `data/exports/backend_compare_<model>.md` for direct comparison.

5. **Evaluate each output on:**
   - Prose scene quality (does it read like a novel?)
   - Dialogue register (do characters sound like people?)
   - Term stability (are names/titles consistent?)
   - Fidelity (is the source meaning preserved?)
   - Speed and operational cost (latency, GPU hours, reliability)

6. **Only then decide** whether to change the default backend. The decision should be backed by side-by-side evidence, not by assumption that bigger = better for literary translation.
