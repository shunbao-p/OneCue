# Quality and revision

This reference governs only the **Static V1 route** and its Job Bundle artifacts. Review or revise a Codex-owned footage edit with [video-material-workflow.md](video-material-workflow.md) instead.

## Inspect without mutation

For an existing Job Bundle, read the task record if it already exists and run `validate --json`. Inspect the render report, cache manifest, final hash, ffprobe facts, and complete decode as requested. Do not create or update a task record, render, modify the formal bundle, or regenerate media merely to answer whether it can continue; report facts in the reply.

## Diagnose failures

Read `output/render_report.json`, `cache/manifest.json`, and structured events before retrying. Keep the same evidence path; do not hide a repeated failure by renaming a directory or rerunning a long job.

Contract failures must stop before TTS/FFmpeg. Runtime failures must preserve the old valid final where the existing pipeline contract guarantees it. Report any remaining narrow atomicity boundary honestly.

## Review

Use the repository review template to separate:

- contract and service facts;
- codec, size, frame rate, pixel format, audio, duration, and complete decode;
- per-shot content, static image, voice, caption, and hard-cut observations;
- cache hits/rebuilds and protected hashes;
- user feedback and the first unmet gate.

Do not infer detailed voice quality from technical probes. Do not replace user review with automated scores.

## Minimal revision

Map the request to a `shot_id`, time point, and affected layer:

- text or caption: change only the necessary shot and adjacent continuity;
- voice: rebuild only affected audio/shot dependencies;
- focus or crop: change only `visual.focus` for that shot and keep motion `static/low`;
- keyframe composition: edit or regenerate only that keyframe, then update its SHA-256;
- hard-cut or cross-shot pacing: keep `cut/0`; allow final recomposition while reusing valid audio/shot caches.

Snapshot the old final/report hashes, validate again, then use `--shot` to limit allowed rebuilding. Add `--force` only when the selected cache must be invalidated. Verify affected cache counts, report, final hash, ffprobe, and complete decode.

Never regenerate every image, every voice, or the whole video for a bounded shot problem. Never switch providers as a revision shortcut.

## Active visual wording

Describe the active result as multiple static storyboard images that change with the narration. Do not promise or invoke image animation, virtual-camera motion, crossfades, HyperFrames, DepthFlow, or I2V. Schema support for older motion presets is compatibility, not an invitation to select them in a new task.
