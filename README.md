# Novel Translation Workbench (MVP)

A local MVP for translating Chinese novel chapters into English with two-stage translation: faithful draft and polished version.

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

**Current state (Batch 4B completed):**
- Chapter plan generation with pre-execution strategy assessment
- Segment-level execution via the existing translation engine
- Aggregation of segment results into full chapter output
- Basic manifest/resume support for interrupted runs
- Limited consistency audit/correction pass
- Strategy enactment minimal closed loop (budget, consistency intensity, enactment record)

**Next batch:** chapter-level CLI/HTTP integration (expose orchestrator as user entry point).

**Orchestrator relationship to WORKFLOW.md:**
The orchestrator invokes the segment-level workflow defined in `WORKFLOW.md` for each segment. `WORKFLOW.md` remains the segment-level execution protocol.

For orchestrator design and current capabilities, see `ORCHESTRATION.md`.

## Goal

Take one Chinese chapter (plain text), split it into segments (~800-1200 Chinese characters), and produce two English versions:
1. Faithful draft translation
2. Polished readable version

**Important**: This is not a generic translator but a novel translation workflow focused on preserving tone, character, and narrative flow.

## Scope

- Input: `data/source/chapter1.txt` (plain text, UTF‑8)
- Segmentation: split into chunks ~800‑1200 characters, keeping paragraph boundaries
- Translation:
  - `draft_translate`: uses a local model backend via HTTP service (configurable) or mock translation.
  - `polish_translate`: runs the default workflow (Prompt A → Prompt B internal review → one revision pass if needed) using the same model backend, producing polished prose.
- Output: `data/exports/chapter1_en.md` (Markdown with segments, draft, polished)

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

## Installation & Running

1. Clone or create the project directory.
2. Ensure Python 3.7+ is installed.
3. Place your Chinese chapter as `data/source/chapter1.txt`.
4. Run the pipeline:

```bash
python -m app.cli run
```

You can specify custom input/output paths:

```bash
python -m app.cli run --source path/to/source.txt --output path/to/output.md
```

5. The output will be written to `data/exports/chapter1_en.md` (by default).

## Translation Service (Optional)

The project includes an HTTP translation service that can be used instead of the local mock translation.

### Using the Service

1. Install optional dependencies:

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

The service reads the following environment variables:

- `MODEL_BACKEND_URL` – HTTP endpoint of the translation model backend (required for real translation)
- `MODEL_TIMEOUT_SECONDS` – timeout for backend requests (default: 30)
- `TRANSLATION_SERVICE_URL` – base URL for the translation service (used by the client)

If `MODEL_BACKEND_URL` is not set, the service will return a 503 error when draft translation is requested.

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

Run the segmentation tests:

```bash
python -m pytest app/tests/
```

or directly:

```bash
python app/tests/test_segmenter.py
```

## Next Steps

**Immediate (Batch 5):** chapter-level CLI/HTTP integration — expose the orchestrator as the main user entry point.

**Beyond current batch:**
- Replace mock translation with actual translation models (e.g., locally hosted LLM).
- Add configuration for segment size, model parameters.
- Support multiple chapters and batch processing.
- Add post‑editing UI for human refinement.
- Integrate terminology/glossary management.

## License

Internal tool — no license specified.