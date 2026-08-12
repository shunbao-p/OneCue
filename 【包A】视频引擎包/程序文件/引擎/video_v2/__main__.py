"""短视频 V2 Job Bundle 校验与本地核心渲染命令。"""

from __future__ import annotations

import argparse
import json
import sys

from .contract import validate_job_bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m video_v2")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="只读校验 V2 Job Bundle")
    validate.add_argument("--job-dir", required=True, help="Job Bundle 根目录")
    validate.add_argument("--json", action="store_true", help="stdout 只输出一个 JSON 对象")
    render = commands.add_parser("render", help="渲染 V2 Job Bundle")
    render.add_argument("--job-dir", required=True, help="Job Bundle 根目录")
    render.add_argument("--shot", action="append", default=None, help="只重渲指定镜头，可重复")
    render.add_argument("--force", action="store_true", help="禁用本次请求范围内的缓存")
    render.add_argument("--json", action="store_true", help="stdout 只输出一个 JSON 对象")
    return parser


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    if payload["ok"]:
        print(f"PASS: {payload['project_id']} ({payload['shot_count']} shots)")
        return
    for issue in payload["errors"]:
        print(
            f"{issue['code']} {issue['document']} {issue['location']}: {issue['message']}",
            file=sys.stderr,
        )


def _run_validate(args: argparse.Namespace) -> int:
    try:
        result = validate_job_bundle(args.job_dir)
        _emit(result.to_dict(), as_json=args.json)
        return 0 if result.ok else 2
    except Exception as exc:
        payload = {
            "ok": False,
            "contract": "short-video-v2-job-bundle",
            "schema_version": 1,
            "project_id": None,
            "shot_count": 0,
            "warnings": [],
            "errors": [
                {
                    "code": "internal.error",
                    "document": "bundle",
                    "location": "$",
                    "message": "验证器发生未预期错误",
                }
            ],
        }
        _emit(payload, as_json=args.json)
        print(f"video_v2 validate internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _render_payload_error(error) -> dict:
    issue = error.to_dict() if hasattr(error, "to_dict") else {
        "code": "pipeline.internal_error",
        "stage": "pipeline",
        "shot_id": None,
        "retryable": False,
        "message": "渲染器发生未预期错误",
    }
    return {"ok": False, "status": "failed", "errors": [issue], "warnings": []}


def _run_render(args: argparse.Namespace) -> int:
    from .errors import PipelineCancelled, RenderError
    from .models import JobBundleValidationError
    from .pipeline import render_job

    def on_event(event: dict) -> None:
        if args.json:
            print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        else:
            message = event.get("message") or event.get("code") or event.get("stage")
            if message:
                print(message, file=sys.stderr)

    try:
        result = render_job(
            args.job_dir,
            selected_shot_ids=args.shot,
            force=args.force,
            on_event=on_event,
        )
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"PASS: {payload.get('final_path', 'output/final.mp4')}")
        return 0
    except JobBundleValidationError as exc:
        payload = {
            "ok": False,
            "status": "contract_error",
            "warnings": [],
            "errors": [issue.to_dict() for issue in exc.issues],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            for issue in payload["errors"]:
                print(f"{issue['code']}: {issue['message']}", file=sys.stderr)
        return 2
    except PipelineCancelled as exc:
        payload = _render_payload_error(exc)
        payload["status"] = "cancelled"
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            print(exc, file=sys.stderr)
        return 130
    except RenderError as exc:
        payload = _render_payload_error(exc)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            print(exc, file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        payload = _render_payload_error(
            PipelineCancelled("pipeline.cancelled", "pipeline", "用户取消")
        )
        payload["status"] = "cancelled"
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 130
    except Exception as exc:
        payload = _render_payload_error(exc)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        print(f"video_v2 render internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        return _run_validate(args)
    return _run_render(args)


if __name__ == "__main__":
    raise SystemExit(main())
