---
name: short-video-director
description: Direct OneCue short-video work from natural-language content, an existing Schema v1 Job Bundle, or user-supplied footage. Use when Codex needs to plan, create, resume, inspect, render, or revise either the established static-storyboard route or a Codex-owned footage edit built with general-video, media-use, and HyperFrames.
---

# Short Video Director

Act only as a thin director and navigation layer. Route established static-storyboard work to the repository workflow, and route selected user-supplied footage to Codex's media workflow. Do not implement image, TTS, video, FFmpeg, cache, schema, or state-machine capabilities here.

## Route the request

Choose exactly one primary mode, then record it:

- **Plan**: Produce the brief, script, source decisions, and shot draft. Do not generate media, synthesize speech, edit, or render.
- **Create**: Advance from content and selected sources to a candidate through the chosen material route. Stop for user review after the candidate is ready.
- **Resume**: Read the chosen route's task record or composition and existing artifacts first. Continue from the first unmet hard gate.
- **Inspect**: Perform read-only checks of supplied media or the chosen route's bundle, composition, reports, cache, final, services, and current state.
- **Render**: In Static V1, validate the Job Bundle before `video_v2 render`; in Codex footage, check the HyperFrames composition before its established render loop.
- **Revise**: Identify the timestamp, source or shot, and affected layer. Make the smallest change; use `--shot` only in Static V1 when applicable.

Infer safe defaults for low-impact omissions. Ask only when missing information changes facts, brand/content direction, external cost or authorization, or the candidate result materially.

## Choose the material route

After choosing the primary mode, choose one orthogonal material route:

- **Static V1 route**: Use when the result is built from independent Image 2 stills. Keep the established Codex → Image 2 → package B → package A/FFmpeg contract unchanged.
- **Codex footage route**: Use when the user supplies video for assessment or possible use. Mixed video-and-image work also uses this route. Codex owns the footage analysis, edit plan, media operations, composition, audio treatment, rendering, and review through general-video, media-use, and HyperFrames; package A and package B do not process this route.
- If supplied footage is irrelevant, redundant, unreadable, or weaker than another truthful visual, record why it was omitted. Supplying footage is permission to assess it, not an obligation to force it into the edit. After an `omit` decision, switch to the Static V1 route only if the remaining requested result actually fits that contract.

## Read only what the mode needs

- For the Static V1 route, read [references/project-map.md](references/project-map.md), [references/workflow-and-gates.md](references/workflow-and-gates.md), and [references/quality-and-revision.md](references/quality-and-revision.md). Read the repository's `director_workflow_v1.md` before executing any plan, create, render, or revision path.
- For the Codex footage route, read [references/video-material-workflow.md](references/video-material-workflow.md). Then load the installed hyperframes, general-video, and media-use skills as that reference directs. Do not load the static Job Bundle contracts unless the request also contains a separate Static V1 task.

## Preserve the project contract

- The following Schema, CLI, cache, and shot rules apply only to the Static V1 route.
- Locate the repository from the current workspace or the path supplied by the user. Do not assume one person's absolute checkout path.
- Treat natural language as an upstream Codex input. Feed package A only a valid, self-contained Schema v1 Job Bundle.
- For every newly created V1 shot, set `motion.preset` to `static`, `motion.strength` to `low`, and `transition_out` to `cut` with `duration_sec: 0`. Keep `visual.focus` for crop placement. Do not choose motion or crossfade presets merely because Schema v1 still accepts them.
- Use the existing `python3 -m video_v2 validate|render` CLI. Do not import the pipeline to create another orchestrator.
- Preserve the user's dirty worktree, existing Job Bundles, reports, cache, and final files. Never reset, checkout, clean, or overwrite unrelated work.
- Use explicit argv, `shell=False`, and finite timeouts for external commands. Never turn user text into shell syntax.
- Do not add a wrapper script by default. Consider one only if two independent real cases prove the existing CLI cannot express the same deterministic step, with tests and a minimal design first. Never add a second Schema, cache, timeline, caption system, media checker, Web UI, or provider routing layer.
- The Codex footage route is deliberately outside Schema v1. Never place supplied video in a V1 Job Bundle, claim package A or package B supports it, or create a parallel OneCue schema or runner. Keep originals intact and store only task-local plans, derivatives, compositions, renders, and review evidence.

## Continue and stop safely

Continue through authorized, local, reversible work: read-only checks, task-local records, content design, validation, targeted tests, report reading, and bounded contract repair.

Pause for material ambiguity; new third-party/paid/cloud APIs, credentials, downloads, payment, or publishing; destructive deletion or cache cleanup; a need to change Schema/core pipeline/tool scope; and final user review of a candidate video. In the Static V1 route, also pause for any request to expand the active route into image animation. When the user has explicitly requested creation, the current session's built-in Image 2 capability is the established keyframe route, not a new external API expansion.

The active V1 result is a sequence of distinct static storyboard images, not one image for the whole narration and not animated stills. In that static route, do not invoke FFmpeg push/pull/pan/tilt/drift, crossfades, HyperFrames, DepthFlow, I2V, BGM, environmental audio, or SFX. The Codex footage route is the separate scope in which HyperFrames may be used, under its own review gates.
