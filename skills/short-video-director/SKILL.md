---
name: short-video-director
description: Direct OneCue's short-video V2 workflow from natural-language content or an existing Schema v1 Job Bundle. Use when Codex is working in a OneCue checkout and needs to plan, create, resume, inspect, render, or revise a short video, including Brief and storyboard design, Image 2 keyframe planning, Job Bundle validation, package A/B rendering, evidence review, user review, and shot-scoped repair.
---

# Short Video Director

Act only as a thin director and navigation layer over the repository's established workflow. The core Codex → Image 2 → package B → package A/FFmpeg chain does not depend on this skill. Do not implement image, TTS, video, FFmpeg, cache, schema, or state-machine capabilities here.

## Route the request

Choose exactly one primary mode, then record it:

- **Plan**: Produce the Brief, script, and shot draft. Do not generate images, synthesize speech, or render.
- **Create**: Advance from content to a candidate video through the existing project workflow. Stop for user review after the candidate is ready.
- **Resume**: Read the task record and existing artifacts first. Continue from the first unmet hard gate.
- **Inspect**: Perform read-only checks of a Job Bundle, report, cache, final, services, or current state.
- **Render**: Validate an existing Job Bundle before calling the existing `video_v2 render` CLI.
- **Revise**: Identify the shot and affected layer. Make the smallest change and scope rebuilding with `--shot` when applicable.

Infer safe defaults for low-impact omissions. Ask only when missing information changes facts, brand/content direction, external cost or authorization, or the candidate result materially.

## Read only what the mode needs

- Read [references/project-map.md](references/project-map.md) to locate the checkout, authoritative documents, CLI, services, records, and protected baselines.
- Read [references/workflow-and-gates.md](references/workflow-and-gates.md) for Plan, Create, Resume, Render, mode transitions, automatic continuation, and pause conditions.
- Read [references/quality-and-revision.md](references/quality-and-revision.md) for Inspect, review, failure diagnosis, cache interpretation, media evidence, and minimal revision.
- Read the repository's `director_workflow_v1.md` before executing any plan, create, render, or revision path. Follow its linked contracts instead of copying them into this skill.

## Preserve the project contract

- Locate the repository from the current workspace or the path supplied by the user. Do not assume one person's absolute checkout path.
- Treat natural language as an upstream Codex input. Feed package A only a valid, self-contained Schema v1 Job Bundle.
- Use the existing `python3 -m video_v2 validate|render` CLI. Do not import the pipeline to create another orchestrator.
- Preserve the user's dirty worktree, existing Job Bundles, reports, cache, and final files. Never reset, checkout, clean, or overwrite unrelated work.
- Use explicit argv, `shell=False`, and finite timeouts for external commands. Never turn user text into shell syntax.
- Do not add a wrapper script by default. Consider one only if two independent real cases prove the existing CLI cannot express the same deterministic step, with tests and a minimal design first. Never add a second Schema, cache, timeline, caption system, media checker, Web UI, or provider routing layer.

## Continue and stop safely

Continue through authorized, local, reversible work: read-only checks, task-local records, content design, validation, targeted tests, report reading, and bounded contract repair.

Pause for material ambiguity; new third-party/paid/cloud APIs, credentials, downloads, payment, or publishing; destructive deletion or cache cleanup; a need to change Schema/core pipeline/tool scope; and final user review of a candidate video. When the user has explicitly requested creation, the current session's built-in Image 2 capability is the established keyframe route, not a new external API expansion.

Never describe FFmpeg push, pull, pan, tilt, or drift as natural semantic motion. Rain, water flow, vehicle travel, breathing, body motion, and similar object-level movement remain unimplemented; the formal advanced-provider count is zero.
