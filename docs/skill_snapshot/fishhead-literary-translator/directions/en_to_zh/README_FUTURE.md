# en_to_zh — Future Direction Profile (Not Implemented)

This directory is reserved as a placeholder for a future English-to-Chinese
literary translation direction profile under the
`fishhead-literary-translator` framework.

It is intentionally **not implemented** at this time.

## Status

- not implemented
- not in scope of any current batch
- not a default candidate for the next batch

## When this gets implemented

A future direction profile here would mirror the `zh_to_en/` shape:

```
directions/en_to_zh/
├── STYLE_RULES.md        # direction-specific style and fidelity rules
└── roles/
    ├── translator.md     # role A — literary translator
    └── reviewer.md       # role B — quality gate / reviewer
```

It must reuse the framework-level `SKILL.md`, the shared workflow in
`shared/WORKFLOW.md`, and the workbench protocol in
`WORKBENCH_PROTOCOL.md`. It must not duplicate the framework, the shared
workflow, or the workbench repository.

Until the user explicitly opens an `en_to_zh` initiative, treat any work
under this directory as out of scope.
