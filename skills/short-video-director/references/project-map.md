# Project map

## Locate the repository

Use the current workspace or the user-supplied path. The repository root is the nearest directory that contains both `【包A】视频引擎包` and `【包B】语音引擎包`. Resolve it once and derive all later paths from that root; do not embed a developer's home directory.

- Package A: `<repo-root>/【包A】视频引擎包`
- Package B: `<repo-root>/【包B】语音引擎包`
- Engine working directory: package A
- Python module root: `<package-a>/程序文件/引擎`

## Authoritative documents

Read these from `<package-a>/docs/short_video_v2/` as needed:

- `director_workflow_v1.md`: workflow authority and commands
- `job_bundle_v1.md`: machine input contract
- `image_workflow_v1.md`: Image 2 keyframe method
- `core_pipeline_v1.md`: rendering, cache, failure, and CLI behavior
- `motion_feasibility_v1.md`: honest motion boundary
- `mvp_acceptance_v1.md`: accepted MVP baseline
- `workflow_acceptance_v1.md`: accepted director workflow and skill boundary
- `templates/brief_v1.md`: optional content-design aid
- `templates/review_v1.md`: optional review and revision aid

Do not substitute older root-level vision documents for these frozen v1 facts.

## Evidence and records

Task-local Job Bundles, reports, cache, final videos, and acceptance evidence normally live under ignored `成片/` directories. Treat any existing formal acceptance bundle and final as protected. Validate it read-only and use an isolated copy for failure injection or revision rehearsal.

Planning and historical execution records live under `<repo-root>/短视频V2规划文档/`. They explain earlier decisions but do not override frozen Schema v1 or the authoritative workflow documents.

## CLI and services

Pass the resolved engine module root through the process environment and execute `python3` with explicit argv:

- `python3 -m video_v2 validate --job-dir <absolute-job-dir> --json`
- `python3 -m video_v2 render --job-dir <absolute-job-dir> --json`
- `python3 -m video_v2 render --job-dir <absolute-job-dir> --shot <shot-id> --json`

Check package A at `http://127.0.0.1:8787/api/health` and package B through package A at `http://127.0.0.1:8787/api/dots_status`. Do not start, stop, or restart services for an inspection request.
