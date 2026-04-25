# novel-translation-workbench

This project provides a translation workflow for Chinese novel chapters into English.

## Local development

Working directory must be `~/novel-translation-workbench` before any file operation. Do NOT operate from `/Users/ambrosiazheng` or any parent directory. If `pwd` is wrong, stop and ask — do not create files (including `CLAUDE.md`) at the wrong level.

Always use the project venv (`venv/bin/python`), not system `python3`.

| Action | Command |
|--------|---------|
| Run tests | `python -m pytest app/tests/` |
| Run pipeline | `python -m app.cli run` |
| Start service | `python run_translation_service.py` |

Commands assume `source venv/bin/activate` first. Without activation, prefix each command with `venv/bin/python` (e.g., `venv/bin/python -m pytest app/tests/`).

## Governing documents

This project is governed by the following document priority:

1. `SKILL.md` — highest-level translation standard, scope, style rules, consistency rules, and project-memory behavior
2. `WORKFLOW.md` — default execution workflow for this project
3. local prompt wording, adapter logic, and implementation details

If these sources ever conflict, follow:

`SKILL.md` > `WORKFLOW.md` > local implementation

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

### 默认工作模式
- 默认按批次推进，而不是逐项征求确认
- 默认不要逐行贴大段 patch / diff / 长代码块
- 默认只做批次级汇报
- 普通编辑 / 测试 / 小实现，由你自己推进
- 删除 / restore / commit 这类高风险动作再停下来确认

### 批次级汇报格式
除非用户明确要求，否则只输出：
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
