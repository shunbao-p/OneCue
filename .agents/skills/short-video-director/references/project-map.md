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
- `mvp_acceptance_v1.md`: accepted MVP baseline
- `workflow_acceptance_v1.md`: accepted director workflow and skill boundary
- `templates/brief_v1.md`: optional content-design aid
- `templates/review_v1.md`: optional review and revision aid

Do not substitute older root-level vision documents for these frozen v1 facts.

内部阶段计划、执行提示词、执行记录与动态化实验不随 v1.0.0 当前发布树分发。只有用户明确要求审计旧版本时，才查阅 Git 历史；不得让旧实验改变当前静态路线。

## Evidence and records

Task-local Job Bundles, reports, cache, final videos, and acceptance evidence normally live under ignored `成片/` directories. Treat any existing formal acceptance bundle and final as protected. Validate it read-only and use an isolated copy for failure injection or revision rehearsal.

不要假定仓库包含内部规划或历史执行记录。续接依据应来自用户指定的任务目录及其中的实际产物。

## CLI and services

Pass the resolved engine module root through the process environment and execute `python3` with explicit argv:

- `python3 -m video_v2 validate --job-dir <absolute-job-dir> --json`
- `python3 -m video_v2 render --job-dir <absolute-job-dir> --json`
- `python3 -m video_v2 render --job-dir <absolute-job-dir> --shot <shot-id> --json`

Check package A at `http://127.0.0.1:8787/api/health` and package B through package A at `http://127.0.0.1:8787/api/dots_status`. Do not start, stop, or restart services for an inspection request.
