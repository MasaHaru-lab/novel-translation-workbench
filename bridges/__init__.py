"""Provider-specific backend bridges.

Each module in this package adapts a third-party model API to the workbench
backend contract:

    request:  POST { "prompt": str, "max_tokens": int? }
    response: { "text": str }

The first implemented bridge is ``ollama_bridge``. Additional providers
(e.g. OpenAI, Claude) follow the same shape: a small HTTP shim that
translates the workbench contract to and from the provider's native API.
"""
