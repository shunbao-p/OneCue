# Workflow and gates

This reference governs only the **Static V1 route**. If supplied video is selected for the result, stop here and use [video-material-workflow.md](video-material-workflow.md). Do not send that footage through package A or package B.

## Plan

Apply safe defaults when omitted: zh-CN vertical video, 30–45 seconds, 6–10 shots, voice only, independent Image 2 stills, static shots, and hard cuts. Record assumptions and stop before media generation.

## Create

1. Convert the request into a concise Brief, fact boundary, script, and shot plan.
2. Plan or generate independent keyframes through Image 2; preserve references, prompts, ledger entries, and hashes.
3. Assemble only Schema v1 `project.json`, `storyboard.json`, and self-contained assets. Set every new shot to `motion=static/low` and `transition_out=cut/0` while retaining `visual.focus` for crop placement.
4. Run `validate --json`; repair contract input before any TTS or FFmpeg work.
5. Check package A/B readiness and run the existing renderer.
6. Read the report, cache manifest, media evidence, and review template.
7. Present the candidate and pause for user review.

Do not invoke Image 2, package B, or rendering when the request asks only for planning or inspection.

## Resume

Read the current execution record, Job Bundle, output report, cache manifest, and available evidence. Identify the first unmet hard gate. Reuse successful images, audio, shots, final, and test evidence; do not replay completed stages.

## Render

Validate first. Stop on structured contract failure. Use the existing CLI and its reports; do not bypass the contract or call FFmpeg as an alternative video pipeline.

Understand `--shot`: it limits which shots may rebuild. A selected shot with a valid cache may still hit unless `--force` is added. Unselected shots require valid cached dependencies. `--shot <id> --force` forces the selected audio/shot and final to rebuild. Use it only when evidence requires selected cache invalidation.

## Automatic continuation

Continue through read-only checks, task-local directories and records, content design, validation, targeted tests, report reading, and bounded fixes within the authorized outcome.

## Mandatory pause

Pause for:

- material factual, brand, character, or direction ambiguity;
- new third-party/paid/cloud APIs, credentials, downloads, publishing, or new authorization; the established built-in Image 2 route is allowed when creation was explicitly requested;
- destructive deletion, cache cleanup, or edits to unrelated/old formal artifacts;
- a request that requires Schema, core pipeline, or provider-scope changes;
- any request to add image animation, virtual-camera motion, crossfades, HyperFrames, DepthFlow, or I2V to the active V1 route;
- the candidate-video user review gate;
- user rejection of the static-storyboard product direction.

Record the blocking gate and leave evidence intact.
