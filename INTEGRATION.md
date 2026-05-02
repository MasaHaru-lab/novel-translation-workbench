# Real Model Backend Integration

## Summary

The draft translation endpoint now integrates with a local model backend via HTTP. The mock translation is replaced with real inference for draft translation; polished translation remains mock.

## Changed Files

- `app/config.py` – added `MODEL_BACKEND_URL` and `MODEL_TIMEOUT_SECONDS`
- `app/translate/backend_adapter.py` – new adapter module with prompt builder and HTTP client
- `app/service/draft_service.py` – updated to call backend adapter, added error handling
- `app/tests/test_backend_adapter.py` – unit tests for the adapter
- `app/tests/test_draft_service.py` – updated tests to mock backend adapter
- `README.md` – updated with configuration and service instructions

## Environment Variables

See `.env.example` for the canonical, up-to-date reference. This table summarizes the backend-relevant subset:

| Variable | Description | Default | Used by |
|----------|-------------|---------|---------|
| `MODEL_BACKEND_URL` | HTTP endpoint of the translation model backend (e.g., Ollama `/api/generate`) | (required) | `app/config.py`, `backend_adapter.py` |
| `MODEL_TIMEOUT_SECONDS` | Timeout for backend requests (seconds) | `30` | `app/config.py`, `backend_adapter.py` |
| `DEEPSEEK_BASE_URL` | DeepSeek API base URL | `https://api.deepseek.com/v1` | `model_profiles.py` (deepseek profiles) |
| `DEEPSEEK_API_KEY` | DeepSeek API key (secret — see below) | (required for deepseek) | `model_profiles.py`, `deepseek_adapter.py` |
| `FISHHEAD_BASE_URL` | Local Fishhead/Ollama backend URL | (optional) | `model_profiles.py` (local-qwen profile) |
| `TRANSLATION_SERVICE_URL` | Base URL for the translation service (used by HTTP client) | `http://localhost:8000` | `app/config.py` |

### Secrets

`DEEPSEEK_API_KEY` is the only credential in this project.

- **Never commit** `.env` or `.env.local` — both are gitignored.
- **Never log, print, or display** the key value in output, logs, or error messages.
- The codebase references secrets **by env var name only** — `resolve_api_key()` reads from `os.environ` and never stores the value in logs, manifests, or error details.
- Set your key in `.env.local` (autoloaded by the CLI/service, gitignored) rather than via `export` to avoid leaving it in shell history.

### Fishhead host resolution

Do not hard-code Fishhead IP addresses in env files or documentation. Resolve the active host with:

```bash
ssh -G Fishhead-Core | grep -E '^hostname '
```

This avoids stale IP assumptions when the Fishhead address changes.

## Starting the Translation Service

1. Activate the project venv (`source venv/bin/activate`), then install optional dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set the model backend URL (or use `.env.local` — see `.env.example`):
   ```bash
   export MODEL_BACKEND_URL=http://localhost:11434/api/generate
   ```

3. Start the service:
   ```bash
   python run_translation_service.py
   ```
   The service will run at `http://localhost:8000`. Health check: `GET /health`.

## Using the CLI with Real Backend

```bash
python -m app.cli run --service-url http://localhost:8000
```

If the backend fails and you want to allow falling back to local mock translation, add `--allow-mock-fallback`.

## Backend Contract

The service sends a POST request to the backend URL with a JSON payload:
```json
{"prompt": "..."}
```

The prompt is constructed to request faithful draft translation, includes glossary terms, and provides previous/next segment as context only.

The backend must return a JSON response containing the generated text in one of these fields: `"text"`, `"response"`, `"generated_text"`, `"content"`. If the response is a plain string, it will be used as-is.

## Error Handling

- If `MODEL_BACKEND_URL` is not set, the service returns HTTP 503 with a clear message.
- If the backend request fails (connection, timeout, HTTP error), the service returns HTTP 503 with details.
- The CLI respects the `--allow-mock-fallback` flag; without it, a service failure will stop the pipeline.

## Testing

Run the test suite (with venv activated):
```bash
python -m pytest app/tests/
```

New adapter tests mock the backend HTTP call; service tests mock the adapter.

## Notes

- The glossary replacement is applied both in the prompt and as a safety pass on the returned text.
- The polished translation endpoint remains mock; only draft translation uses the real backend.
- The translation contract (`TranslationInput`/`TranslationOutput`) is unchanged.