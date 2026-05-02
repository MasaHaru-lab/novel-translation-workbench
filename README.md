# Novel Translation Workbench (MVP)

A local MVP for translating Chinese novel chapters into English with two-stage translation: faithful draft and polished version.

> **Framework**: this repo is the current implementation of the `fishhead-literary-translator` framework, `zh_to_en` direction profile (A = literary translator, B = quality gate / reviewer). The canonical skill lives at `~/.claude/skills/fishhead-literary-translator/`; a versioned snapshot is kept at `docs/skill_snapshot/fishhead-literary-translator/`. See `docs/SKILL_INTEGRATION.md` for the mapping.

## Document hierarchy

This project uses a layered document structure:

- `SKILL.md` defines the highest-level translation standard, style constraints, consistency rules, and project-memory expectations.
- `WORKFLOW.md` defines the default execution workflow for translation.
- `CLAUDE.md` acts as the project entry document for agent behavior and document priority.
- `prompts/prompt_a.md` and `prompts/prompt_b.md` are the executable prompt-layer files for translation and review.
- `ORCHESTRATION.md` describes the chapter-level orchestrator kernel and its current capabilities.

If there is ever a conflict, follow:

`SKILL.md` > `WORKFLOW.md` > prompt files > local implementation

## Default translation behavior

For an ongoing work, the default translation flow is:

read relevant project assets → Prompt A translation → Prompt B internal review → one revision pass if needed → final reviewed prose

Relevant project assets include:

- `project_assets/characters.md`
- `project_assets/titles_and_terms.md`
- `project_assets/glossary.md`
- `project_assets/style_notes.md`
- `project_assets/unresolved_decisions.md`

## Chapter-level orchestration

The project includes a chapter-level orchestrator kernel (`app/chapter/orchestrator.py`) that reuses the existing segment-level translation functions.

**Phase A sealed (2026-04-26):**
- Chapter plan generation, segment-level execution, aggregation
- Manifest/resume support for interrupted runs
- Consistency audit/correction pass
- Chapter-level CLI (`chapter run`, `chapter stream`, `--dry-run`, `--resume`)
- Chapter-level HTTP API (`POST /translate/chapter` with manifest/resume semantics)
- Strategy enactment closed loop

**Phase B (next):** quality loop — run/inspect real translated output, feed recurring issues back into zh_to_en style rules, roles, or book assets. No architecture redesign.

**Orchestrator relationship to WORKFLOW.md:**
The orchestrator invokes the segment-level workflow defined in `WORKFLOW.md` for each segment. `WORKFLOW.md` remains the segment-level execution protocol.

For orchestrator design and current capabilities, see `ORCHESTRATION.md`.

## Goal

Take one Chinese chapter (plain text), split it into segments (~800-1200 Chinese characters), and produce two English versions:
1. Faithful draft translation
2. Polished readable version

**Important**: This is not a generic translator but a novel translation workflow focused on preserving tone, character, and narrative flow.

## Scope

- Input: `data/source/one_chapter_quality_source.txt` (plain text, UTF‑8)
- Segmentation: split into chunks ~800‑1200 characters, keeping paragraph boundaries
- Translation:
  - `draft_translate`: uses a local model backend via HTTP service (configurable) or mock translation.
  - `polish_translate`: runs the default workflow (Prompt A → Prompt B internal review → one revision pass if needed) using the same model backend, producing polished prose.
- Output: `data/exports/one_chapter_quality_source_en.md` (Markdown with segments, draft, polished)

## Project Structure

```
novel-translation-workbench/
├── data/
│   ├── source/           # source Chinese text files
│   └── exports/          # generated translations
├── app/
│   ├── segment/          # text segmentation logic
│   │   ├── __init__.py
│   │   └── segmenter.py  # Segment dataclass & create_segments()
│   ├── translate/        # translation functions and backend adapter
│   │   ├── __init__.py
│   │   ├── schema.py     # TranslationInput, TranslationOutput, GlossaryTerm
│   │   ├── translator.py # draft_translate(), polish_translate() (mock)
│   │   └── backend_adapter.py # real model backend integration
│   ├── service/          # HTTP translation service
│   │   ├── __init__.py
│   │   ├── draft_service.py # FastAPI endpoint POST /translate/draft
│   │   └── client.py     # HTTP client for the service
│   ├── config.py         # configuration (URLs, timeouts)
│   ├── cli.py            # command‑line interface
│   └── tests/
│       ├── test_segmenter.py
│       ├── test_translator.py
│       ├── test_draft_service.py
│       ├── test_client.py
│       └── test_backend_adapter.py
├── run_translation_service.py # convenience script to start service
├── requirements.txt       # optional dependencies
├── README.md
└── STATUS.md
```

## Quick start

Always use the project venv (`venv/bin/python`) — not system `python3`.

```bash
# 1. Create and activate the venv (first time only)
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run tests
python -m pytest app/tests/

# 4. Run the translation pipeline (requires data/source/one_chapter_quality_source.txt)
python -m app.cli run
```

To skip activation, use `venv/bin/python` directly instead of bare `python`.

You can specify custom input/output paths:

```bash
python -m app.cli run --source path/to/source.txt --output path/to/output.md
```

When `--output` is omitted, it is derived from `--source` (e.g. `data/source/chapter3.txt` → `data/exports/chapter3_en.md`).

### Chapter-level translation

The preferred path for full-chapter translation. Auto-segments, translates each segment, aggregates into full chapter text, then runs a consistency pass (name/title/term variant correction).

#### Output artifacts

- **`chapter run --output`** writes the **final translation** to a file. When the consistency pass detects and corrects issues, the file contains the post-consistency corrected text. In partial runs (some segments failed), the file still contains what was completed — labeled accordingly in the run summary.
- **`chapter stream`** writes the same final translation to **stdout**. The output is the same artifact as `chapter run --output`.
- **Aggregated** translation is the raw concatenation of all segment translations (pre-consistency).
- **Corrected** (post-consistency) is the aggregated text with consistency fixes applied. This is the best usable output when available.
- When some segments fail, output is **partial** — only successfully translated segments are included. The run summary shows the count (e.g., `partial — 2/5 segments`).

```bash
# Run chapter translation (auto-segment → auto-translate → aggregate → consistency)
python -m app.cli chapter run --source data/source/one_chapter_quality_source.txt --output data/exports/one_chapter_quality_source_en.md
```

#### Run lifecycle

Each `chapter run` creates two files alongside the output path:

- **`<output>`** — the final translation text. After a partial run (some segments failed), this file still contains what was completed. Use this as your best available result.
- **`<output>.manifest.json`** — the run progress record. This file tracks which segments completed, failed, or are still pending. It is created automatically and updated after each segment.

**If a run is interrupted or finishes partially:**
- The output file contains the text from all successfully translated segments.
- The manifest file records what was done and what remains.
- Pass `--resume` to continue from where it left off. Completed segments are reused; pending and failed segments are processed again (subject to retry limits).

```bash
# Resume an interrupted or partial chapter run
python -m app.cli chapter run --resume --source data/source/one_chapter_quality_source.txt --output data/exports/one_chapter_quality_source_en.md
```

**If a run completes successfully:**
- The output file contains the full translated chapter.
- The manifest file is a record of the run. You do not need it unless you re-run with the same output path.

```bash
# Stream mode: read from file, output final translation to stdout
python -m app.cli chapter stream --source data/source/one_chapter_quality_source.txt > one_chapter_quality_source_en.md
```

Stream mode also reads from stdin when `--source` is omitted:

```bash
cat data/source/one_chapter_quality_source.txt | python -m app.cli chapter stream > one_chapter_quality_source_en.md
```

### Batch chapter translation

Translate multiple source files in a single command. Each source gets a safe default output derived from its filename. One failed chapter does not block subsequent chapters.

```bash
# Run batch translation for two chapters (requires two source files)
python -m app.cli chapter batch --source data/source/one_chapter_quality_source.txt --source data/source/test.txt
```

Per-source output derivation: `data/source/one_chapter_quality_source.txt` → `data/exports/one_chapter_quality_source_en.md`, etc.

The batch command accepts the same shared flags as `chapter run` (`--service-url`, `--allow-mock-fallback`, `--assets-mode`, `--resume`, `--no-clobber`). KeyboardInterrupt (Ctrl+C) propagates cleanly.

Produces a per-chapter compact summary after all sources are processed:

```
Batch translation: 2 source(s)

[1/2] one_chapter_quality_source.txt
  Source:  data/source/one_chapter_quality_source.txt
  Output:  data/exports/one_chapter_quality_source_en.md
  ...
[2/2] test.txt
  Source:  data/source/test.txt
  Output:  data/exports/test_en.md
  ...
--- Batch Summary ---
  one_chapter_quality_source.txt   COMPLETED
  test.txt                         COMPLETED
  (2 source(s) · 2 completed · 0 failed)
```

### Canonical commands

| Action | Command |
|--------|---------|
| Run tests | `python -m pytest app/tests/` |
| Run segment-level pipeline (legacy) | `python -m app.cli run` |
| Run chapter-level pipeline | `python -m app.cli chapter run` |
| Run batch chapter translation | `python -m app.cli chapter batch --source ...` |
| Stream chapter translation to stdout | `python -m app.cli chapter stream` |
| Start translation service | `python run_translation_service.py` |
| Intake a new chapter sample | `./样本 <name>` |

### Chapter Sample Intake

Save a real chapter sample into `data/source/` for validation:

```bash
# Paste interactive (type, paste text, Ctrl+D)
./样本 ch_asclepius_01

# From clipboard / file pipe
pbpaste | ./样本 ch_asc_02
cat my_chapter.txt | ./样本 ch_asc_03

# Auto-named (timestamp-based)
./样本
```

After saving, the tool prints the next **dry-run validation command** — a no-model, mock-safe check that previews how the source would segment and be processed. Empty input, invalid names, and duplicate files are rejected with a clear error.

> Commands above assume an activated venv. Without activation, prefix each with `venv/bin/` (e.g., `venv/bin/python -m pytest app/tests/`).

## Translation Service (Optional)

The project includes an HTTP translation service that can be used instead of the local mock translation.

### Using the Service

1. Ensure the venv is activated (see [Quick start](#quick-start)), then install optional dependencies:

```bash
pip install -r requirements.txt
```

2. Set the model backend URL (e.g., a local Ollama or llama.cpp HTTP endpoint):

```bash
export MODEL_BACKEND_URL=http://localhost:11434/api/generate
```

3. Start the translation service:

```bash
python run_translation_service.py
```

The service will run at `http://localhost:8000`. Health check: `GET /health`.

4. Run the CLI with the service URL:

```bash
python -m app.cli run --service-url http://localhost:8000
```

If the service is unavailable, the CLI will fall back to local mock translation only if `--allow-mock-fallback` is set.

### Configuration

See `.env.example` for the complete, canonical reference. Key environment variables:

- `MODEL_BACKEND_URL` – HTTP endpoint of the translation model backend (required for real translation when no `--model-profile` is set)
- `DEEPSEEK_API_KEY` – DeepSeek API key (**secret** — never log or commit; set in `.env.local`)
- `MODEL_TIMEOUT_SECONDS` – timeout for backend requests (default: 30)
- `TRANSLATION_SERVICE_URL` – base URL for the translation service (used by the client)

If no backend URL is configured, the service returns a 503 error when draft translation is requested.

**Secret handling:** The only credential in this project is `DEEPSEEK_API_KEY`. It is referenced by env var name only in code — never logged, stored, or committed. Set it in `.env.local` (autoloaded, gitignored) rather than via `export` to keep it out of shell history.

**Fishhead backend:** If using Fishhead as a local translation backend, resolve the active host with `ssh -G Fishhead-Core | grep hostname` rather than hard-coding an IP address.

### Backend Contract

The service expects the model backend to accept a JSON POST request with a `"prompt"` field and return a JSON response containing the generated text in one of these fields: `"text"`, `"response"`, `"generated_text"`, `"content"`. If the response is a plain string, it will be used as-is.

The prompt is constructed to request faithful draft translation, includes glossary terms, and provides previous/next segment as context only.

## Example Output

```markdown
# Chapter 1

---

## Segment 1

### Draft
[DRAFT ENGLISH] 第一章...

### Polished
[POLISHED ENGLISH] 第一章...

---
```

## Testing

Run all tests:

```bash
python -m pytest app/tests/
```

Run a specific test file:

```bash
python -m pytest app/tests/test_segmenter.py
```

## Next Steps

**Phase B (next):** quality loop — run/inspect real translated output and feed recurring issues back into zh_to_en style rules, roles, or book assets.

**Beyond Phase B:**
- Sentence‑level splitting for long paragraphs (currently splits by character boundary)
- Configuration file for segment size, model parameters
- HTTP polish endpoint (`POST /translate/polish`)
- Add post‑editing UI for human refinement

## License

Internal tool — no license specified.