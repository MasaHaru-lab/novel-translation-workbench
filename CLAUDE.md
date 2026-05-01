# novel-translation-workbench

This project provides a translation workflow for Chinese novel chapters into English.

## Skill Routing (READ FIRST)

This user has many skills installed. They often do NOT remember the skill names. When the user's request matches a row in this table, **invoke the skill via the Skill tool immediately** — do not ask "should I use X?", do not silently re-implement the skill's logic, do not ignore it. If multiple match, pick the most specific.

| User says (zh / en) | Auto-invoke |
|---|---|
| "minimal fix" / "narrow change" / "scoped" / "conservative" / "只改 X" / "最小改动" / "窄范围" / "先不要改" / "先看一下" / "inspect first" — and they're about to start an edit task | `scope` (BEFORE any Edit/Write) |
| "translate" / "翻译" / "翻一下" / "把这段译成英文" — for any zh→en literary prose | `fishhead-literary-translator` |
| "humanize" / "去 AI 味" / "改得不像 AI" / "更自然" — for editing existing text | `humanizer-zh` |
| "commit this step" / "提交这一步" / "中途 commit" / "verify and commit" — mid-batch sub-step landing | `commit-batch` |
| "close out the batch" / "收尾" / "wrap up this batch" / "finish batch" — final close-out | `batch-close` |
| "save progress" / "save state" / "save my work" / "保存进度" — capture full session state | `context-save` |
| "resume" / "where was I" / "pick up where I left off" / "继续上次的" — restore prior state | `context-restore` |
| "write handoff" / "save resume note" / "留个续接点" / context feels like it's filling up on a long batch | `handoff` (proactive) |
| "debug this" / "why is this broken" / "fix this bug" / "为什么坏了" / "排查" — error or unexpected behavior | `investigate` |
| "review my plan" / "engineering review" / "lock in the plan" / "评审计划" | `plan-eng-review` |
| "second opinion" / "ask codex" / "challenge this" / "找 codex 看看" | `codex` |
| "ship" / "deploy" / "create a PR" / "push to main" — code is ready to land | `ship` |
| "search the web" / "搜一下" / "查一下最新的" — needs real-time info | `skywork-search` |
| ".pdf" / ".xlsx" / ".docx" / ".pptx" filename mentioned, or "make a PDF / spreadsheet / doc / deck" | matching `pdf` / `xlsx` / `docx` / `pptx` |
| "make this a PDF" / "export to PDF" — markdown → publication PDF | `make-pdf` |
| "open browser" / "take a screenshot" / "test the site" / "打开浏览器" / "截图" | `browse` |

Rules:
- The trigger keywords above are EXAMPLES of intent, not exact strings — match on meaning, including Chinese variants the user actually uses.
- Do NOT enumerate alternatives back to the user ("I can use scope, batch-close, …"). Just invoke the right one.
- Skills the user explicitly types as `/<name>` always win over auto-routing.
- If unsure between two skills, pick the narrower / more specific one and invoke it. The skill itself will guide the next step.
- This routing table is project-specific — it lists skills relevant to this translation workbench. Other skills exist but should fire on their own description triggers.

## Local development

Working directory must be `~/novel-translation-workbench` before any file operation. Do NOT operate from `/Users/ambrosiazheng` or any parent directory. If `pwd` is wrong, stop and ask — do not create files (including `CLAUDE.md`) at the wrong level.

Always use the project venv (`venv/bin/python`), not system `python3`.

| Action | Command |
|--------|---------|
| Run tests | `venv/bin/python -m pytest app/tests/` |
| Run pipeline | `venv/bin/python -m app.cli run` |
| Start service | `venv/bin/python run_translation_service.py` |

Default to direct `venv/bin/python` calls for routine commands. Do NOT use `source venv/bin/activate && python ...` — the activation adds no value and creates unnecessary shell-approval friction. `activate` is reserved for interactive sessions only.

### Proven patterns (reusable)

- **Test commands**: Default to `venv/bin/python -m pytest app/tests/...`. Do not `source activate` first.
- **Exit code 1 from pytest**: If pytest starts, collects, and shows PASSED/FAILED, Python is working. Exit 1 means test failure — identify the exact failed test name and reason. Do not report it as "Python unavailable" or an environment issue.
- **CLI commands**: Default to `venv/bin/python -m app.<module>` without activation.
- **Real model validator runs**: Use `venv/bin/python -m app.chapter.cli run ...` when available.

## Governing documents

This project is governed by the following document priority:

1. `SKILL.md` — highest-level translation standard, scope, style rules, consistency rules, and project-memory behavior
2. `WORKFLOW.md` — default execution workflow for this project (Steps 0–4, prompt roles, loop limits)
3. local prompt wording (`prompts/prompt_a.md`, `prompts/prompt_b.md`), adapter logic, and implementation details
4. ad hoc instructions — passage-specific adjustments; lowest priority

If these sources ever conflict, follow:

`SKILL.md` > `WORKFLOW.md` > local implementation

For the full routing decision flow (how skill-level, workflow-level, CLAUDE.md-level, and ad hoc guidance relate), see `WORKFLOW.md` → "Routing Architecture".

## Default Translation Protocol

For normal translation requests, follow the default protocol defined in `WORKFLOW.md`, but always enforce the translation standards and constraints defined in `SKILL.md`.

**Default meaning of "translate":**
- Use Prompt A to generate initial English prose
- Run one internal Prompt B review pass
- Revise once if needed
- Return final reviewed prose

Prompt files:

- Prompt A: `prompts/prompt_a.md`
- Prompt B: `prompts/prompt_b.md`

These prompt files implement the default translation and review behavior described in `WORKFLOW.md`, and must remain aligned with `SKILL.md`.

Project assets:

- `project_assets/characters.md`
- `project_assets/titles_and_terms.md`
- `project_assets/glossary.md`
- `project_assets/style_notes.md`
- `project_assets/unresolved_decisions.md`

Before translating a passage from an ongoing work, check these project assets when relevant.

Use them to maintain name consistency, term stability, style control, and awareness of still-unresolved decisions.

## Required behavior

Unless the user explicitly requests otherwise:

- do not expose full internal review notes
- do not treat translation as a rough first pass
- do not override established glossary, naming, title, or style decisions casually
- do not add unsupported specificity for ownership, gender, emotion, or causality
- do not over-modernize dialogue or flatten historical / literary atmosphere
- do not prioritize fluency over scene logic and source meaning

## Project memory expectation

When translating a book or continuing an existing work, check and maintain project-level assets when available, including:

- glossary
- character / place / title reference list
- style notes
- unresolved decision list

Each chapter should strengthen later consistency rather than restarting from zero.

## Mode overrides

- If the user explicitly asks for `translate-only`, skip internal review
- If the user explicitly asks for `review mode`, `audit`, or `style check`, use explicit review behavior
- Otherwise, `translate` means the default full internal workflow

For workflow details, see `WORKFLOW.md`.
For translation quality bar and style constraints, see `SKILL.md`.

## Chapter-level orchestration

The project includes a chapter-level orchestrator kernel (`app/chapter/orchestrator.py`) that reuses the existing segment-level translation functions.

**Phase A sealed (2026-04-26):** All Phase A surfaces are now frozen.
- Chapter plan generation with pre-execution strategy assessment
- Segment-level execution via the existing translation engine
- Aggregation of segment results into full chapter output
- Basic manifest/resume support for interrupted runs
- Limited consistency audit/correction pass
- Strategy enactment minimal closed loop (budget, consistency intensity, enactment record)
- Chapter-level CLI (`chapter run`, `chapter stream`, `--dry-run`, `--resume`)
- Chapter-level HTTP API (`POST /translate/chapter` with manifest/resume semantics)
- Output format contract (Markdown chapter output, run manifest, readable summary)
- 321 tests passing (26 service + 46 CLI + 37 chapter + others)

**Frozen:** No further work on CLI, HTTP, output-format, or quality-gate surfaces. These are sealed for the duration of Phase A.

**Phase B (next):** Quality loop — run/inspect real translated output, feed recurring issues back into zh_to_en style rules, roles, or book assets. No architecture redesign.

**Orchestrator relationship to WORKFLOW.md:**
The orchestrator invokes the segment-level workflow defined in `WORKFLOW.md` for each segment. `WORKFLOW.md` remains the segment-level execution protocol.

For orchestrator design and current capabilities, see `ORCHESTRATION.md`.

## Scope Discipline

当用户使用 "minimal / narrow / scoped / conservative / 只改 X / 先不改 / 先检查" 这类措辞时，严格照字面执行：

- 不派生语义、不加额外字段、不做"顺手清理"、不建 helper / 并行入口 / 根目录 CLI
- 如果需要碰范围外文件（即便是 import、README、测试夹具），先停下问，不要自行扩范围
- 用户说 "先不要改 / 只看 / inspect / 先 dry-run"，那一轮禁止调用 Edit / Write / MultiEdit，以及任何会改磁盘或远端状态的 Bash
- 收到"最小修复"/"两行改动"这类指令时，先回读：要改的文件清单 + 预计 diff 行数 + 明确不做的事，拿到 go 再动工具

违反以上任何一条都按范围越界处理，直接回滚。

## Architecture Constraints

### Planned vs Enacted

- `ChapterPlan` 只承载 planned 值（计划时刻的预期、预算、策略意图）
- Enactment 记录只承载 actual 运行时值（真实 token 用量、真实片段切分、真实一致性强度），必须来自执行路径，不能从 plan 复制或回推
- 不要给 `ChapterPlan` 挂运行时字段；不要让 enactment 回填进 plan
- planned 和 enacted 在任何数据结构、日志、audit 里都要保持来源可辨

遇到看似要合并两者的"简化"机会，先停下问，这基本就是违规信号。

## Reuse-first Principle (优先复用原则)

设计新功能时默认复用而非重造。实现顺序：
1. 先复用已有 CLI/API/工具/平台/模块
2. 再写薄胶水层或适配层
3. 再补规则、边界、错误处理、测试和验收
4. 只有现成能力无法满足成本、隐私、稳定性、可控性、离线能力或关键边界时，才自研

本项目关键约束：
- `chapter run` / `chapter batch` 是既有执行入口，不要绕过它们重写执行流
- hooks/tests/pre-merge gate 是安全层，不要用手工约定替代
- OpenClaw 是调度层，不是底层能力重写层
- 新方案必须说明复用了什么、新增了什么、为什么需要新增

## Frozen Designs

以下设计主题已明确评估并冻结。除非用户明确重新打开该主题，否则不允许实现、预重构、或做任何前置准备。

### `chapter stream --dry-run` — FROZEN

**状态：** 已推迟，不属于 Phase A 范围。

**原因：** stdout/stderr 契约歧义。`chapter stream` 保留 stdout 用于流式翻译输出，加入 `--dry-run` 需要一个尚未做出的显式接口决策（输出到 stderr？切换到不同输出模式？）。

**范围边界：**
- 这不是 bug，不是遗漏，不是下一批默认候选。
- `chapter run` 主路径 Phase A 已完成。
- 不允许修改 CLI parser、stdout/stderr 处理、stream output contract、或相关测试结构来"为这个功能做准备"。
- 只有当用户明确说"重新打开 stream dry-run 设计"或等价表述时，才允许进入 discovery。在此之前，任何发现或实现尝试都视为范围越界。

## Verification Before Claims

- 不要猜 API 签名、字段名、文件位置；先用 Read / Grep 读一手
- 不要声称"文件已 commit / 服务已启动 / 测试已通过 / venv 已激活"，除非刚刚用 Bash 验证过
- 长探索之前，先让 Task agent 去查，再回主会话做 edit —— 避免主上下文被探索吃光
- 当前批次过半或 exploration 较长时，先写一段 checkpoint（任务 / 改动文件 / 测试状态 / 下一步 / 阻塞点）再继续，别等 context 爆了才补

## Collaboration Mode

### 协作模式
- 你是执行者，不是来逐项征求用户选择的
- 用户负责批次目标、范围边界和最终验收
- 你负责在既定边界内自主推进并完成整批工作
- 默认不要把用户拖进每一个局部实现决策

### Interrupt Handling

When the user interrupts, rejects a tool call, or says to stop: **immediately halt the current tool sequence.** Do not continue, retry, or proceed with the rejected plan in a different form. Pause, identify what was rejected and why, then re-clarify the corrected intent before taking any further action.

This applies especially when:
- A tool call is denied or rejected — do not attempt a different approach to the same objective
- The user says "stop", "no", "不要", "先不改", or similar — halt all edits
- The user corrects scope or direction — do not finish the "almost done" work

Continuing down a rejected path is the fastest way to waste session budget and hit context limits.

### 默认工作模式
- 默认按批次推进，而不是逐项征求确认
- 默认不要逐行贴大段 patch / diff / 长代码块
- 默认只做批次级汇报
- 普通编辑 / 测试 / 小实现，由你自己推进
- 删除 / restore / commit 这类高风险动作再停下来确认

### 批次级汇报格式
除非用户明确要求，否则只输出精简版，详见 `docs/CLOSEOUT_REPORT_TEMPLATE.md` 的完整模板。精简版包含：
1. 改了哪些文件
2. 每个文件一句话摘要
3. 跑了哪些测试 / 验证
4. 是否通过
5. 有没有碰到边界禁区
6. 是否达到本批次完成标准
7. 还剩什么没做

### 只有这些情况才允许停下来问
- 必须碰禁区文件才能继续
- 当前批次必须扩范围才能成立
- 出现两条明显不同且会影响主线的产品方向
- 准备执行高风险动作（删除文件 / git restore / git commit）
- 当前本地状态与既有判断明显冲突

### 上下文控制
- 不要重复复述已确认背景
- 不要粘贴大段代码 / patch / diff，除非用户明确要求
- 不要输出冗长计划
- 当前批次完成后直接收口，不要自动开启下一批
- 如果对话变长，先输出短 checkpoint，而不是继续堆上下文

### Tool approval behavior

Some commands may still trigger approval prompts because of the tool/runtime safety layer. This does not mean the user should be pulled back into routine implementation decisions.

Default rule:

- If a command is low risk and clearly belongs to the current batch, proceed within the current batch logic.
- Do not treat every approval prompt as a new product or planning question.
- Approval prompts are often a tool-layer requirement, not a signal that the project direction is unclear.

Only escalate the decision back to the user when the command would:

- expand the current batch scope
- touch a forbidden file or boundary
- perform a high-risk action such as delete / git restore / git commit
- reveal a conflict with the already confirmed local project state

In other words:

- tool approval is a runtime/safety concern
- whether something belongs to the current batch is an execution judgment you should usually make yourself

### Batch approval rule

For bounded batches with a stated goal, boundaries, acceptance criteria, and stop point, routine in-scope actions are pre-approved:

- reading relevant files
- editing in-scope files (including fixing test failures caused by in-scope changes)
- running tests
- checking git diff/status/log
- preparing and making requested commits when acceptance is met
- reporting final results

Only stop and ask if:
- the task scope needs to change
- unrelated files must be touched
- destructive actions are needed
- secrets/network credentials are needed
- merge to main/master is about to happen
- a genuine product/architecture decision cannot be resolved from existing direction

### Review Gate

**What it is:** A mandatory review step between batch completion and merge. The gate ensures scope discipline, acceptance verification, and explicit approval before any merge to `main`. It prevents three specific failure modes: scope expansion during review, implementation disguised as review, and merging without approval.

**When it fires:** After a batch's implementation work is complete and before any merge or next-batch work begins. If the CLAUDE.md "Batch approval rule" pre-approves routine in-scope actions during implementation, this gate is the point where the operator explicitly confirms the batch is done and approved.

**Gate steps:**

1. **Stop implementation work.** The batch implementation phase is complete. Do not add features, fix bugs, or make improvements not already in scope — even if they are small, obvious, or related.

2. **Present a compact review summary** using the template at `docs/CLOSEOUT_REPORT_TEMPLATE.md`. The summary must include:
   - Branch name and HEAD commit
   - List of changed files (one file per line)
   - Summary of changes (one clear sentence per file)
   - Acceptance criteria and whether each is met (✓ / ✗)
   - Test / gate evidence: test results, pre-merge gate status
   - Working tree status (clean / dirty — any uncommitted changes)
   - Remaining risk or known limitations (one sentence max per item)
   - Whether runtime behavior changed (yes / no — if yes, what and why)
   - Whether any scope boundary was approached or touched (and how it was handled)

3. **Wait for explicit approval.** The summary must be presented to the operator and explicitly approved before any of the following may proceed:
   - Squash-merge to `main`
   - Starting the next batch
   - Continuing implementation on the same batch

   While waiting:
   - Do not expand scope based on observations from the completed work
   - Do not start implementation on issues noticed during review
   - Do not merge without explicit approval

4. **If approval is denied,** identify the specific concern from the rejection. Fix only what was raised. Do not use a rejection as permission for broader changes, cleanup, or refactoring. After fixing, re-present the review summary.

5. **After approval,** proceed with the merge steps defined in "Merging back to main" below.

**What the review gate is NOT:**
- Not a license to expand scope based on what the completed code looks like
- Not a license to start feature work or fix observed issues outside the batch boundary
- Not a license to clean up or refactor code the batch did not touch
- Not a substitute for the Pre-merge Gate (mechanical), the Prompt Change Gate, or the Canonization Gate

If something outside the batch scope needs attention during review, record it as a finding for a separate batch — do not act on it in the same batch.

**Relationship to other gates in this project:**

| Gate | Location | Controls |
|------|----------|----------|
| Review Gate (this section) | `CLAUDE.md` | Batch completion and merge approval |
| Pre-merge Gate | `CLAUDE.md` + `scripts/checks/pre_merge_gate.sh` | Working-tree cleanliness, generated-output tracking |
| Prompt Change Gate | `docs/QUALITY_LOOP.md` | Changes to `prompts/prompt_a.md` / `prompts/prompt_b.md` |
| Canonization Gate | `docs/QUALITY_LOOP.md` + `app/chapter/canonization.py` | New `project_assets/` entries |

The gates are independent — passing one does not satisfy another.

## gstack (REQUIRED — global install)

**Before doing ANY work, verify gstack is installed:**

```bash
test -d ~/.claude/skills/gstack/bin && echo "GSTACK_OK" || echo "GSTACK_MISSING"
```

If GSTACK_MISSING: STOP. Do not proceed. Tell the user:

> gstack is required for all AI-assisted work in this repo.
> Install it:
> ```bash
> git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
> cd ~/.claude/skills/gstack && ./setup --team
> ```
> Then restart your AI coding tool.

Do not skip skills, ignore gstack errors, or work around missing gstack.

Using gstack skills: After install, skills like /qa, /ship, /review, /investigate,
and /browse are available. Use /browse for all web browsing.
Use ~/.claude/skills/gstack/... for gstack file paths (the global path).

## Local PR-style long-run workflow

This repo uses a lightweight, **local** PR-style workflow for Claude/gstack
long-running tasks. There is no GitHub PR, no remote bot, no CI, no
auto-push, no auto-merge. The workflow exists so long sessions can run
unattended without putting `main` at risk.

### Branch model

- `main` — stable seal point. Every commit on `main` should be a
  green, atomically describable batch. `main` is what future sessions
  resume from.
- `work/<topic>` — 施工区. All Claude/gstack long-running work lives
  on a `work/<topic>` branch. Inside a work branch you may freely create:
  - batch commits
  - WIP commits
  - checkpoint commits (e.g. `SESSION_CHECKPOINT.md` updates)
- The work branch is private to the session/operator. Force-push or
  rebase inside the work branch is fine; just never force-push to `main`.

### Merging back to main

Before merging `work/<topic>` into `main`:

0. **Pass the Review Gate (see above).** The Review Gate is a separate
   human-approval step. It must pass and receive explicit approval
   before any mechanical merge steps begin. Do not skip, merge without
   approval, or treat the mechanical steps below as a substitute.
1. Run the **pre-merge gate**: `./scripts/checks/pre_merge_gate.sh`
2. Gate must exit 0 (PASS). On FAIL, do not merge, do not "work
   around", do not bypass — fix the underlying issue first.
3. Run the test suite (gate intentionally does not):
   `venv/bin/python -m pytest app/tests/`
4. Merge **squash-first** into `main`, so `main` keeps a clean
   one-commit-per-batch history. The full WIP history stays on the
   work branch (which can be deleted or kept for reference).
5. Update `STATUS.md` / `SESSION_CHECKPOINT.md` on `main` if the batch
   changed user-visible capabilities or the resume state.

The gate is a merge-readiness check, not a substitute for tests, and
not a quality verdict. It only verifies that the local repo is in a
shape where a squash-merge into `main` will not leak generated outputs
or half-staged WIP.

### Pre-merge gate

Script: `scripts/checks/pre_merge_gate.sh`

What it checks (all local, offline, no model backend, no Fishhead):

- inside the project git repo
- working tree has no uncommitted tracked-file changes
- generated-output paths (`data/output/`, `data/exports/`, `outputs/`)
  are not tracked in git
- current branch hint: `work/<topic>` expected; warn-only on `main`
  or detached HEAD

Exit codes: `0` = PASS, `1` = FAIL. FAIL must halt the merge flow.

What the gate does NOT do: run pytest, call models, contact Fishhead,
or verify translation quality. Those are operator responsibilities (or
batch-level acceptance), not gate concerns.

### Fishhead / 3090 usage boundary

Fishhead (the local 3090 host) is a controlled engineering resource,
not an automated quality oracle.

#### Fishhead SSH target-resolution rule

Before any Fishhead remote call, resolve the active SSH target with
`ssh -G` rather than hard-coding an IP.

- Do not use stale `192.168.68.61`.
- The current working Fishhead address is expected to end in `.51`,
  not `.61`.
- Prefer configured SSH aliases such as `Fishhead-Core` or `fishhead`.
- Inspect the active target with:
  `ssh -G Fishhead-Core | grep -E '^(hostname|user|port|identityfile) '`
  and/or:
  `ssh -G fishhead | grep -E '^(hostname|user|port|identityfile) '`
- Trust `ssh -G` output over stale docs, memory, or checkpoint text.
- If Fishhead is not required for the current batch, do not block the
  batch on Fishhead access.
- If Fishhead is required and resolution/auth fails, report it as a
  remote-access blocker, not as proof that Fishhead itself is unreachable.

Allowed without prior per-batch approval:
- read-only health / connectivity checks
  (`ssh Fishhead-Core 'hostname && nvidia-smi'`)
- contract checks against the wrapper (e.g. shape of
  `http://192.168.68.51:8001/generate` response on a tiny synthetic prompt)
- protocol / reachability probes
- small synthetic-input integration checks tied to an explicit batch goal

Not allowed without explicit per-batch user approval:
- real-sample translation acceptance runs
- full chapter live runs against the real model
- long-form literary quality evaluation
- unbounded smoke / live runs
- using real model output to retroactively justify or drive
  prompt / workflow / orchestrator changes inside the same batch

Operational facts:
- Fishhead host: `192.168.68.51`, user `ambrosia`,
  SSH alias `Fishhead-Core`, project path `/home/ambrosia/rubato-asr`,
  venv `/home/ambrosia/rubato-asr/.venv`. Update these in this
  document if anything changes.
- Wrapper URL (when up): `http://192.168.68.51:8001/generate`
- Any generated artifacts from Fishhead runs (translations, manifests,
  logs) must stay under `data/output/`, `data/exports/`, or
  `outputs/`, all of which are gitignored. They must not be committed.
- Fishhead being unreachable is not a blocker for the gate or for
  non-model batches.

### Boundaries this section establishes

This workflow section is infrastructure, not a feature. It does not
authorize:
- modifying application logic, orchestrator, consistency/quality
  modules, Prompt A, or Prompt B
- starting Batch 5C (chapter-level HTTP/API integration)
- enabling continuous gstack checkpointing, GitHub Actions, remote
  PRs, auto-push, or auto-merge bots
- automated long-task scheduling

Those require their own batch with explicit user approval.
