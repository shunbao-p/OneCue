---
name: prompt-writer
description: Create or revise staged execution prompt documents from implementation plans, handoff notes, issue analyses, or user requirements, and provide one or more copy-ready master prompts in chat that let a new Codex session read the document and execute its stages autonomously. Use when the user wants Codex/agents to carry out a written plan across multiple stages with validation, execution records, human checkpoints, or cross-session handoff, especially when the user should normally copy only one master prompt instead of pasting every stage prompt manually.
---

# Prompt Writer

## Purpose

Turn an approved plan into an execution package that a new Codex session can follow with little user mediation.

Produce by default:

1. One staged execution prompt document saved near the plan or at the user-specified path.
2. One copy-ready master prompt shown directly in the final chat response.
3. An execution-record path that the future execution session creates or updates.

Do not create a separate master-prompt file unless the user explicitly asks for one. Do not implement the target plan unless the user explicitly asks for implementation in the same request.

## Artifact responsibilities

Keep the execution chain clear by assigning each artifact one job:

- **Plan and specifications:** authoritative target, scope, architecture, constraints, and acceptance criteria.
- **Staged prompt document:** background preflight, stage-specific scope, concrete actions, validations, gates, and deliverables.
- **Master prompt shown in chat:** controller contract that tells the new session what to read, how to progress, when to continue automatically, when to pause, and how to close the work.
- **Execution record:** durable factual state—completed stages, actual changes, validation evidence, decisions, blockers, and next-stage readiness.

Do not copy the full plan into either prompt artifact. Reference source files precisely and repeat only execution-critical facts that would otherwise be ambiguous.

Unless the user or project defines another order, resolve conflicts with this default: the user's latest explicit instruction first; then approved product requirements and specifications; then the approved plan; then the staged prompt document; then recorded implementation rulings. Treat current code and tests as evidence of present reality, not as automatic authority to cancel an approved change. Material conflicts that cannot be resolved without changing product intent are blockers; safe implementation-detail discrepancies may be ruled on, recorded, and resolved without pausing.

## Workflow

### 1. Gather source context

- Read every user-provided plan, specification, handoff, issue analysis, execution record, and prompt template that materially governs the task.
- Inspect the current project state when available. Use current code and tests as factual reality, but do not let an outdated implementation silently override approved product requirements.
- If earlier stages already ran, read their records and adapt the next execution package to proven reality rather than mechanically preserving stale plan wording.
- Preserve the user's established document location, naming style, language, and level of detail unless these would impair execution.
- Do not invent a handoff path, test command, tool, interface, or project fact.

### 2. Build a requirement coverage map

Before drafting, internally map each material plan requirement to:

`requirement -> execution stage -> validation evidence -> human involvement, if any`

Use this map to detect omissions, duplicated work, stages without meaningful validation, and unnecessary human gates. Include the map in the staged document only when the task is sufficiently complex that it materially helps later review; otherwise use it as a private self-check.

### 3. Divide the work into executable stages

Do not equate plan headings with execution stages automatically. Define a stage as the smallest useful unit that:

- produces a coherent deliverable;
- has its own meaningful validation cycle;
- can be accepted or rejected without making neighboring stages unintelligible; and
- remains reviewable in one execution slice.

Merge work when it touches mostly the same files or interfaces, shares one validation surface, or would cause repeated churn if separated. Fold setup, scaffolding, configuration, and supporting documentation into the stage whose deliverable actually needs them.

Keep stages separate when one freezes a contract or test baseline, establishes a foundation required by later work, changes risky or externally visible behavior, crosses a real human gate, or performs final end-to-end acceptance.

Do not create stages merely for ceremony, low-impact polish, duplicated review, or work that the plan does not require. Do not over-simplify work whose security, correctness, compatibility, recovery, or user-visible quality genuinely needs separate validation.

Assign stable IDs such as `S01`, `S02`, and stable gate IDs such as `G01` so the master prompt and execution record can refer to them unambiguously.

### 4. Identify real human gates

Default to no human gate. Generate one master prompt whenever Codex can safely execute the whole plan without user action.

A human gate is justified only when progress truly requires something Codex cannot or should not do autonomously, such as:

- login, MFA, CAPTCHA, device approval, or credentials the user must provide;
- a product, visual, editorial, or media acceptance decision reserved for the user;
- missing business information or a materially branching preference only the user can decide;
- physical-device or off-machine action;
- explicit approval for destructive, irreversible, security-sensitive, paid, public-production, publishing, or shared-branch actions.

Ordinary implementation decisions, recoverable test failures, lint errors, code review findings, long-running work, stage boundaries, and low-risk local edits are not human gates. Instruct the executor to diagnose, repair, revalidate, and continue.

For each genuine gate, define:

- gate ID and the stage that reaches it;
- the exact user action or decision required;
- the evidence the executor should verify afterward;
- what must be written to the execution record before pausing; and
- the first stage or step to resume after the gate.

### 5. Write the staged execution prompt document

Use readable Markdown. The stage bodies are primarily instructions for the master session to read from disk, so do not compress them into giant single-line prompts and do not repeat the full global contract in every stage.

Use this default structure, adapting it to the task:

```markdown
# <任务名>分阶段执行提示词

主计划：`...`
其他依据：`...`
执行记录：`...`
总提示词：由当前会话直接提供，不另建文件。

## 文档权威性与使用方式

## 全局执行契约

## 背景加载与执行前预检

## 阶段总览

| ID | 阶段 | 主要交付物 | 验证 | 下一状态 |
| --- | --- | --- | --- | --- |

## S01：<阶段名>

### 目标与非目标
### 开始前读取
### 实施要求
### 验证与验收
### 执行记录更新
### 完成条件与下一状态

## 人工门（仅在确有需要时）

## 最终验收与收尾
```

#### Global execution contract

Put shared rules in `全局执行契约` once. Tailor them to the actual plan rather than pasting an unrelated universal checklist. Cover as applicable:

- source-of-truth and conflict handling;
- minimal, reviewable, reversible changes;
- preservation of unrelated user work and dirty worktrees;
- dependency, secret, data, network, production, and destructive-action boundaries;
- relevant subagent policy—use bounded subagents only when they materially improve independent research, mapping, review, debugging, or verification, and never make them mandatory without cause;
- required validation and evidence standards;
- continuous execution and the limited stop conditions;
- execution-record maintenance.

Do not inject irrelevant boilerplate such as media-quality rules into ordinary software work or TDD/Git requirements that the source plan does not require.

#### Background preflight

Keep a `背景加载与执行前预检` instruction before the stages. It must tell the executor to:

- read the governing documents, current code/tests, and existing execution record;
- compare plan assumptions with current reality;
- identify the first unfinished stage and construct a stage task list;
- record material discrepancies and resolve safe, local ones using the stated authority rules;
- begin execution automatically when no genuine blocker or human gate exists.

Background preflight is not a separate user-copy round and not a default pause point. It may update the execution record but must not force the user to paste another prompt merely to start `S01`.

#### Stage content

Each stage must state:

- stable ID, goal, non-goals, dependencies, and entry condition;
- exact source documents and relevant project areas to inspect;
- stage-specific implementation requirements and boundaries;
- the smallest meaningful validation plus any required broader regression or end-to-end check;
- what counts as pass, conditional pass, or failure when those distinctions are useful;
- the execution-record fields to update after validation;
- the next stage, human gate, or final state.

Prefer exact file paths, interfaces, commands, and acceptance evidence when the source material supports them. When they cannot be known until execution, instruct the executor how to discover them instead of inventing values.

Write background and stage sections as direct imperative instructions to the future executor, not as commentary about what a good executor might do.

### 6. Define the execution record

Include an execution-record path unless the user explicitly opts out. Place it near the task documents, following the project's existing convention.

The master session should create the record during preflight or before the first implementation stage if it does not exist. Later stages must read existing entries and append or update only the relevant stage state.

Keep the record factual and moderately detailed. Recommended fields are:

- `阶段状态`
- `执行目标`
- `实际完成`
- `关键改动与文件`
- `验证命令及结果`
- `问题、处理与重要决策`
- `剩余风险或延期项`
- `下一状态`

Treat the record as the progress authority after context compaction or session interruption: never redo a stage already recorded as complete unless fresh evidence invalidates it.

### 7. Write the master prompt or prompts

Show master prompts directly in the final chat response inside copy-ready fenced text blocks. Do not save them to a separate file unless the user asks.

Default to exactly one master prompt. Split it only around known, genuine human gates. Do not create separate master prompts for ordinary stage transitions.

The first master prompt must tell the new execution session to:

1. read the full plan, staged prompt document, relevant source documents, current code/tests, and execution record;
2. apply the document authority rules and run background preflight;
3. build or update a task list from the stable stage IDs;
4. find the first unfinished stage;
5. before each stage, reread the global contract, that stage, and the latest execution record;
6. implement only that stage's scope, self-review, validate, repair failures when safe, and update the record;
7. continue automatically into the next stage without asking for permission;
8. pause only at a named human gate, a genuinely unrecoverable blocker, or completion;
9. finish with the required final validation and an evidence-based report.

If the record shows completed stages, resume at the first unfinished stage rather than repeating work. This instruction provides ordinary interruption tolerance; do not generate a separate generic recovery prompt.

When known human gates exist:

- Master prompt 1 executes continuously up to the first named gate and pauses with the exact user action required.
- Each later master prompt verifies the corresponding user action, rereads the plan, staged document, and execution record, then continues from the stated stage until the next gate or completion.
- Keep later prompts self-sufficient for their gate and continuation point without restating the whole plan.

Do not put model recommendations inside copy-ready master prompts. Give a short recommendation immediately before the prompt block only when it helps the user choose a session configuration. Recommend per master session or gate-separated continuation session, not mechanically per internal stage.

Use this compact control shape as a guide rather than a phrase-by-phrase template:

```text
你负责执行<任务名>。先完整读取<计划路径>、<分阶段提示词路径>、其他权威依据、当前代码与测试，以及存在时的<执行记录路径>。以分阶段提示词中的全局执行契约和稳定阶段ID建立任务清单，完成背景预检后从首个未完成阶段开始；每阶段开始前重读该阶段要求和最新执行记录，只实施本阶段范围，随后自审、验证、修复可安全处理的问题并更新执行记录。阶段通过后自动进入下一阶段，不要因普通阶段切换、可恢复失败或低风险实施判断向用户询问是否继续。仅在文档标明的人工门、无法安全解决的实质阻塞或全部完成时停止；若执行记录已有完成阶段，不得无故重做。最终完成文档要求的整体验收，并报告实际改动、验证证据、重要决策、剩余风险和总体结论。
```

### 8. Review before delivery

Perform a fresh review against the plan and the user's latest instructions:

- Every material requirement maps to a stage and validation.
- No stage lacks a coherent deliverable or meaningful completion condition.
- Shared rules appear in the global contract rather than being repeated in every stage.
- Stage-specific details have not been moved so high that executors could miss them.
- The background preflight flows directly into `S01` unless a real blocker exists.
- The master prompt reads the entire staged document, not merely its opening.
- The master prompt count is one unless named human gates prove otherwise.
- Every human gate requires actual user participation and has precise pause/resume evidence.
- The execution record supports continuation without a separate recovery prompt.
- No paths, commands, APIs, tools, test results, or project facts were invented.
- Low-impact optional work is not promoted into a hard gate, while necessary correctness and safety work remains intact.
- The final report contract requests changed files, key decisions, validations and results, remaining risks, execution-record status, and overall completion/readiness.

Revise the artifacts until these checks pass.

## Final response contract

Lead with what was created or revised. Provide:

1. a clickable absolute link to the staged execution prompt document;
2. the number and reason for any human-gate splits;
3. a concise model/reasoning recommendation if useful; and
4. the copy-ready master prompt block or blocks directly in chat.

Do not make the user open another file merely to obtain the master prompt. Do not ask the user to copy background and stage prompts one by one when the master prompt can govern the sequence.

## Quality bar

The skill succeeds when the user normally copies one master prompt into a fresh Codex session, that session accurately loads the plan and staged document, executes every stage in order with evidence, continues without unnecessary check-ins, pauses only for genuine user actions, records durable progress, and finishes without losing plan requirements or drowning the executor in repeated boilerplate.
