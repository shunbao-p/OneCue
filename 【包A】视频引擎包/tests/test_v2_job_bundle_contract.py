# -*- coding: utf-8 -*-
"""V2 Job Bundle Schema v1 的结构、运行校验与只读接口契约。"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"
SCHEMA_DIR = ENGINE_DIR / "video_v2" / "schemas"
FIXTURE_ROOT = TESTS_DIR / "fixtures" / "v2_job_bundle"
VALID_MINIMAL = FIXTURE_ROOT / "valid_minimal"
PHASE1_MIGRATED = FIXTURE_ROOT / "phase1_migrated"
BUNDLED_PYTHON = PACKAGE_ROOT / "程序文件" / "runtime" / "bin" / "python3"
PACKAGE_PYTHON = BUNDLED_PYTHON if BUNDLED_PYTHON.is_file() else Path(sys.executable)

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def base_project() -> dict:
    return {
        "schema_version": 1,
        "project_id": "contract-test",
        "title": "中文 契约测试",
        "language": "zh-CN",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "defaults": {
            "voice": "女播音.wav",
            "timing": {"head_pad_sec": 0.15, "tail_pad_sec": 0.25},
        },
        "captions": {"enabled": True, "style_preset": "default_lower_third"},
    }


def base_storyboard(path: str, digest: str) -> dict:
    return {
        "schema_version": 1,
        "project_id": "contract-test",
        "shots": [
            {
                "id": "shot-001",
                "purpose": "验证正式契约",
                "speech": {"kind": "narration", "text": "风从城门外吹来。"},
                "visual": {
                    "keyframe": {"path": path, "sha256": digest},
                    "focus": {"x": 0.5, "y": 0.45},
                },
                "motion": {"preset": "slow_push_in", "strength": "low"},
                "caption": {"mode": "speech"},
                "transition_out": {"type": "cut", "duration_sec": 0},
            }
        ],
    }


class BundleCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job_dir = Path(self.temp.name) / "含 空格的任务"
        self.asset = self.job_dir / "assets" / "keyframes" / "关键帧 01.png"
        self.asset.parent.mkdir(parents=True)
        self.asset.write_bytes(b"v2-contract-test-image\n")
        self.project = base_project()
        self.storyboard = base_storyboard(
            "assets/keyframes/关键帧 01.png", sha256_bytes(self.asset.read_bytes())
        )
        self.write()

    def write(self):
        self.job_dir.mkdir(parents=True, exist_ok=True)
        (self.job_dir / "project.json").write_text(
            json.dumps(self.project, ensure_ascii=False, allow_nan=True), encoding="utf-8"
        )
        (self.job_dir / "storyboard.json").write_text(
            json.dumps(self.storyboard, ensure_ascii=False, allow_nan=True), encoding="utf-8"
        )

    @staticmethod
    def contract():
        return importlib.import_module("video_v2")

    def validate(self):
        return self.contract().validate_job_bundle(self.job_dir)

    def assert_error(self, code: str):
        result = self.validate()
        self.assertFalse(result.ok)
        self.assertIn(code, [issue.code for issue in result.errors])
        return result


class StaticContractTests(unittest.TestCase):
    def test_schema_files_exist_and_are_draft_2020_12(self):
        for name in ("project.schema.json", "storyboard.schema.json"):
            path = SCHEMA_DIR / name
            self.assertTrue(path.is_file(), path)
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertTrue(document["$id"].startswith("urn:text-av-generator:"))
            self.assertFalse(document["additionalProperties"])

    def test_committed_fixtures_exist_and_load(self):
        video_v2 = importlib.import_module("video_v2")
        minimal = video_v2.load_job_bundle(VALID_MINIMAL)
        migrated = video_v2.load_job_bundle(PHASE1_MIGRATED)
        self.assertEqual(minimal.project.project_id, "minimal-contract")
        self.assertEqual(len(minimal.shots), 1)
        self.assertEqual(migrated.project.project_id, "phase1-three-shot")
        self.assertEqual(len(migrated.shots), 3)

    def test_public_models_are_frozen_and_import_has_no_write_side_effect(self):
        before = sorted(str(path.relative_to(FIXTURE_ROOT)) for path in FIXTURE_ROOT.rglob("*"))
        video_v2 = importlib.import_module("video_v2")
        bundle = video_v2.load_job_bundle(VALID_MINIMAL)
        with self.assertRaises(FrozenInstanceError):
            bundle.project.title = "被修改"
        after = sorted(str(path.relative_to(FIXTURE_ROOT)) for path in FIXTURE_ROOT.rglob("*"))
        self.assertEqual(before, after)

    def test_schema_and_python_constants_remain_aligned(self):
        contract = importlib.import_module("video_v2.contract")
        project = json.loads((SCHEMA_DIR / "project.schema.json").read_text(encoding="utf-8"))
        storyboard = json.loads((SCHEMA_DIR / "storyboard.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(project["required"]), contract.PROJECT_REQUIRED)
        self.assertEqual(set(storyboard["required"]), contract.STORYBOARD_REQUIRED)
        shot_schema = storyboard["$defs"]["shot"]
        self.assertEqual(set(shot_schema["required"]), contract.SHOT_REQUIRED)
        for definition, constant in (
            ("timing", contract.TIMING_REQUIRED),
            ("speech", contract.SPEECH_REQUIRED),
            ("keyframe", contract.KEYFRAME_REQUIRED),
            ("focus", contract.FOCUS_REQUIRED),
            ("visual", contract.VISUAL_REQUIRED),
            ("motion", contract.MOTION_REQUIRED),
            ("caption", contract.CAPTION_REQUIRED),
            ("transition", contract.TRANSITION_REQUIRED),
        ):
            self.assertEqual(set(storyboard["$defs"][definition]["required"]), constant)
        self.assertEqual(set(storyboard["$defs"]["motion"]["properties"]["preset"]["enum"]), contract.MOTION_PRESETS)
        self.assertEqual(set(storyboard["$defs"]["motion"]["properties"]["strength"]["enum"]), contract.MOTION_STRENGTHS)
        self.assertEqual(set(storyboard["$defs"]["speech"]["properties"]["kind"]["enum"]), contract.SPEECH_KINDS)
        self.assertEqual(set(storyboard["$defs"]["caption"]["properties"]["mode"]["enum"]), contract.CAPTION_MODES)
        self.assertEqual(set(storyboard["$defs"]["transition"]["properties"]["type"]["enum"]), contract.TRANSITION_TYPES)
        self.assertEqual(project["properties"]["schema_version"]["const"], contract.SCHEMA_VERSION)
        self.assertEqual(storyboard["properties"]["schema_version"]["const"], contract.SCHEMA_VERSION)
        object_contracts = (
            (project, contract.PROJECT_REQUIRED, contract.PROJECT_FIELDS),
            (storyboard, contract.STORYBOARD_REQUIRED, contract.STORYBOARD_FIELDS),
            (storyboard["$defs"]["shot"], contract.SHOT_REQUIRED, contract.SHOT_FIELDS),
            (storyboard["$defs"]["speech"], contract.SPEECH_REQUIRED, contract.SPEECH_REQUIRED | {"voice", "speaker_id"}),
            (storyboard["$defs"]["keyframe"], contract.KEYFRAME_REQUIRED, contract.KEYFRAME_REQUIRED),
            (storyboard["$defs"]["focus"], contract.FOCUS_REQUIRED, contract.FOCUS_REQUIRED),
            (storyboard["$defs"]["visual"], contract.VISUAL_REQUIRED, contract.VISUAL_REQUIRED),
            (storyboard["$defs"]["motion"], contract.MOTION_REQUIRED, contract.MOTION_REQUIRED | {"intent"}),
            (storyboard["$defs"]["caption"], contract.CAPTION_REQUIRED, contract.CAPTION_REQUIRED | {"text"}),
            (storyboard["$defs"]["transition"], contract.TRANSITION_REQUIRED, contract.TRANSITION_REQUIRED),
        )
        for schema, required, allowed in object_contracts:
            self.assertEqual(set(schema["required"]), required)
            self.assertEqual(set(schema["properties"]), allowed)
            self.assertFalse(schema["additionalProperties"])
        self.assertEqual(project["$defs"]["voice"], storyboard["$defs"]["voice"])
        self.assertEqual(project["$defs"]["voice"]["minLength"], 5)
        self.assertEqual(project["$defs"]["voice"]["maxLength"], 255)
        self.assertEqual(storyboard["$defs"]["shot"]["properties"]["hero"]["default"], False)
        self.assertEqual(storyboard["properties"]["shots"]["minItems"], 1)
        self.assertEqual(storyboard["properties"]["shots"]["maxItems"], 100)

    def test_error_code_registry_matches_documented_v1_set(self):
        contract = importlib.import_module("video_v2.contract")
        self.assertEqual(
            contract.ERROR_CODES,
            frozenset(
                {
                    "bundle.root_invalid", "bundle.file_missing", "json.invalid",
                    "schema.version_unsupported", "schema.required", "schema.unknown_field",
                    "schema.type_invalid", "schema.value_invalid", "schema.condition_failed",
                    "project.id_mismatch", "shot.id_duplicate", "shot.order_invalid",
                    "path.format_invalid", "path.outside_bundle", "path.symlink_forbidden",
                    "asset.missing", "asset.type_unsupported", "asset.hash_mismatch",
                }
            ),
        )

    def test_public_contract_has_no_command_or_service_escape_hatches(self):
        forbidden_imports = {"subprocess", "socket", "http", "urllib", "requests", "importlib"}
        for name in ("contract.py", "models.py"):
            path = ENGINE_DIR / "video_v2" / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_roots.add(node.module.split(".", 1)[0])
                elif isinstance(node, ast.Call):
                    for keyword in node.keywords:
                        if keyword.arg == "shell":
                            self.assertTrue(
                                isinstance(keyword.value, ast.Constant) and keyword.value.value is False,
                                f"{name} 若传 shell，只允许字面 False",
                            )
                    if isinstance(node.func, ast.Name) and node.func.id in {"__import__", "eval", "exec"}:
                        self.fail(f"{name} 不得动态导入或执行代码：{node.func.id}")
                    if (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                        and node.func.attr == "system"
                    ):
                        self.fail(f"{name} 不得调用 os.system")
            self.assertTrue(imported_roots.isdisjoint(forbidden_imports), (name, imported_roots))

        approved_fields = {
            "project.schema.json": {
                "canvas", "captions", "defaults", "enabled", "fps", "head_pad_sec",
                "height", "language", "project_id", "schema_version", "style_preset",
                "tail_pad_sec", "target_duration_sec", "timing", "title", "voice", "width",
            },
            "storyboard.schema.json": {
                "caption", "duration_sec", "focus", "head_pad_sec", "hero", "id", "intent",
                "keyframe", "kind", "mode", "motion", "path", "preset", "project_id", "purpose",
                "schema_version", "sha256", "shots", "speaker_id", "speech", "strength",
                "tail_pad_sec", "text", "timing", "transition_out", "type", "visual", "voice",
                "x", "y",
            },
        }
        for path in SCHEMA_DIR.glob("*.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            property_names: set[str] = set()

            def collect_properties(value):
                if isinstance(value, dict):
                    properties = value.get("properties")
                    if isinstance(properties, dict):
                        property_names.update(str(item).lower() for item in properties)
                    for child in value.values():
                        collect_properties(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_properties(child)

            collect_properties(schema)
            self.assertEqual(property_names, approved_fields[path.name])


class PositiveValidationTests(BundleCase):
    def test_minimal_bundle_validates_and_loads_defaults(self):
        video_v2 = self.contract()
        result = video_v2.validate_job_bundle(self.job_dir)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.project_id, "contract-test")
        self.assertEqual(result.shot_count, 1)
        bundle = video_v2.load_job_bundle(self.job_dir)
        shot = bundle.shots[0]
        self.assertEqual(shot.voice, "女播音.wav")
        self.assertEqual(shot.head_pad_sec, 0.15)
        self.assertEqual(shot.tail_pad_sec, 0.25)
        self.assertFalse(shot.hero)
        self.assertEqual(shot.caption_text, "风从城门外吹来。")
        self.assertEqual(shot.keyframe_path, self.asset.resolve())

    def test_optional_fields_and_all_enums_are_accepted(self):
        self.project["target_duration_sec"] = 30.0
        self.storyboard["shots"][0].update(
            {
                "speech": {
                    "kind": "dialogue",
                    "text": "请立刻关门！",
                    "voice": "角色 一.wav",
                    "speaker_id": "guard-1",
                },
                "motion": {
                    "preset": "tilt_up",
                    "strength": "high",
                    "intent": "由信物缓慢抬向警灯",
                },
                "timing": {"head_pad_sec": 0.1, "tail_pad_sec": 0.2},
                "caption": {"mode": "custom", "text": "快关城门！"},
                "transition_out": {"type": "crossfade", "duration_sec": 0.3},
                "hero": True,
            }
        )
        self.write()
        bundle = self.contract().load_job_bundle(self.job_dir)
        self.assertEqual(bundle.shots[0].caption_text, "快关城门！")
        self.assertEqual(bundle.shots[0].voice, "角色 一.wav")
        self.assertTrue(bundle.shots[0].hero)

    def test_caption_none_is_normalized_to_no_text(self):
        self.storyboard["shots"][0]["caption"] = {"mode": "none"}
        self.write()
        self.assertIsNone(self.contract().load_job_bundle(self.job_dir).shots[0].caption_text)


class StructuralValidationTests(BundleCase):
    def test_missing_file_and_invalid_json(self):
        (self.job_dir / "storyboard.json").unlink()
        self.assert_error("bundle.file_missing")
        (self.job_dir / "storyboard.json").write_bytes(b"\xff")
        self.assert_error("json.invalid")

    def test_required_json_symlink_is_rejected(self):
        outside = self.job_dir.parent / "outside-project.json"
        outside.write_text(json.dumps(self.project), encoding="utf-8")
        (self.job_dir / "project.json").unlink()
        (self.job_dir / "project.json").symlink_to(outside)
        self.assert_error("path.symlink_forbidden")

    def test_oversized_json_is_rejected_before_parse(self):
        (self.job_dir / "project.json").write_bytes(b" " * (8 * 1024 * 1024 + 1))
        self.assert_error("schema.value_invalid")

    def test_excessively_nested_json_is_a_contract_error(self):
        depth = 20000
        (self.job_dir / "project.json").write_text(
            '{"a":' * depth + "0" + "}" * depth,
            encoding="utf-8",
        )
        self.assert_error("json.invalid")

    def test_version_type_and_value_are_distinct(self):
        self.project["schema_version"] = "1"
        self.write()
        self.assert_error("schema.type_invalid")
        self.project["schema_version"] = 2
        self.write()
        self.assert_error("schema.version_unsupported")

    def test_required_unknown_type_and_value_errors(self):
        del self.project["title"]
        self.write()
        self.assert_error("schema.required")
        self.project = base_project()
        self.project["command"] = "anything"
        self.write()
        self.assert_error("schema.unknown_field")
        self.project = base_project()
        self.project["captions"]["enabled"] = 1
        self.write()
        self.assert_error("schema.type_invalid")
        self.project = base_project()
        self.project["canvas"]["fps"] = 25
        self.write()
        self.assert_error("schema.value_invalid")

    def test_voice_and_text_length_boundaries_match_schema(self):
        self.project["defaults"]["voice"] = ".wav"
        self.write()
        self.assert_error("schema.value_invalid")
        self.project = base_project()
        self.project["defaults"]["voice"] = " voice.wav"
        self.write()
        self.assert_error("schema.value_invalid")
        self.project = base_project()
        self.project["defaults"]["voice"] = "voice .wav"
        self.write()
        self.assert_error("schema.value_invalid")
        self.project = base_project()
        self.project["title"] = "题" * 120 + " "
        self.write()
        self.assert_error("schema.value_invalid")

    def test_nonfinite_numbers_are_rejected(self):
        self.storyboard["shots"][0]["visual"]["focus"]["x"] = float("nan")
        self.write()
        self.assert_error("json.invalid")

    def test_all_motion_presets_and_strengths_are_accepted(self):
        contract = importlib.import_module("video_v2.contract")
        for preset in sorted(contract.MOTION_PRESETS):
            for strength in sorted(contract.MOTION_STRENGTHS):
                with self.subTest(preset=preset, strength=strength):
                    self.storyboard["shots"][0]["motion"] = {
                        "preset": preset,
                        "strength": strength,
                    }
                    self.write()
                    self.assertTrue(self.validate().ok, self.validate().errors)

    def test_caption_and_transition_conditions(self):
        self.storyboard["shots"][0]["caption"] = {"mode": "custom"}
        self.write()
        self.assert_error("schema.condition_failed")
        self.storyboard["shots"][0]["caption"] = {"mode": "none", "text": "不应存在"}
        self.write()
        self.assert_error("schema.condition_failed")
        self.storyboard["shots"][0]["caption"] = {"mode": "speech"}
        self.storyboard["shots"][0]["transition_out"] = {"type": "cut", "duration_sec": 0.2}
        self.write()
        self.assert_error("schema.condition_failed")

    def test_project_id_mismatch_duplicate_and_order(self):
        self.storyboard["project_id"] = "other"
        self.write()
        self.assert_error("project.id_mismatch")
        self.storyboard = base_storyboard("assets/keyframes/关键帧 01.png", sha256_bytes(self.asset.read_bytes()))
        duplicate = copy.deepcopy(self.storyboard["shots"][0])
        self.storyboard["shots"].append(duplicate)
        self.write()
        self.assert_error("shot.id_duplicate")
        self.storyboard["shots"][1]["id"] = "shot-003"
        self.write()
        self.assert_error("shot.order_invalid")


class PathAndAssetValidationTests(BundleCase):
    def set_path(self, value: str):
        self.storyboard["shots"][0]["visual"]["keyframe"]["path"] = value
        self.write()

    def test_rejects_format_and_absolute_paths(self):
        for value, code in (
            ("assets\\keyframes\\x.png", "path.format_invalid"),
            (" assets/keyframes/x.png", "path.format_invalid"),
            ("assets/keyframes/x.png ", "path.format_invalid"),
            ("https://example.com/x.png", "path.format_invalid"),
            ("file:///tmp/x.png", "path.format_invalid"),
            ("C:\\temp\\x.png", "path.format_invalid"),
            ("C:/temp/x.png", "path.outside_bundle"),
            ("//server/share/x.png", "path.outside_bundle"),
            ("/tmp/x.png", "path.outside_bundle"),
            ("../x.png", "path.outside_bundle"),
            ("assets/./keyframes/x.png", "path.outside_bundle"),
            ("assets//keyframes/x.png", "path.outside_bundle"),
        ):
            with self.subTest(value=value):
                self.set_path(value)
                self.assert_error(code)

    def test_rejects_missing_empty_directory_extension_and_hash(self):
        self.set_path("assets/keyframes/missing.png")
        self.assert_error("asset.missing")
        empty = self.job_dir / "assets" / "keyframes" / "empty.png"
        empty.touch()
        self.set_path("assets/keyframes/empty.png")
        self.assert_error("asset.type_unsupported")
        directory = self.job_dir / "assets" / "keyframes" / "directory.png"
        directory.mkdir()
        self.set_path("assets/keyframes/directory.png")
        self.assert_error("asset.type_unsupported")
        bad = self.job_dir / "assets" / "keyframes" / "x.gif"
        bad.write_bytes(b"gif")
        self.set_path("assets/keyframes/x.gif")
        self.assert_error("asset.type_unsupported")
        self.set_path("assets/keyframes/关键帧 01.png")
        self.storyboard["shots"][0]["visual"]["keyframe"]["sha256"] = "0" * 64
        self.write()
        self.assert_error("asset.hash_mismatch")

    def test_filesystem_unrepresentable_segment_is_stable_path_error(self):
        self.set_path("assets/" + "x" * 300 + ".png")
        self.assert_error("path.format_invalid")

    def test_rejects_root_ancestor_and_target_symlinks(self):
        real_root = self.job_dir
        link_root = real_root.parent / "bundle-link"
        link_root.symlink_to(real_root, target_is_directory=True)
        result = self.contract().validate_job_bundle(link_root)
        self.assertIn("bundle.root_invalid", [issue.code for issue in result.errors])

        outside = real_root.parent / "outside"
        outside.mkdir()
        (outside / "x.png").write_bytes(b"outside")
        ancestor = real_root / "assets" / "linked"
        ancestor.symlink_to(outside, target_is_directory=True)
        self.set_path("assets/linked/x.png")
        self.assert_error("path.symlink_forbidden")

        target = real_root / "assets" / "keyframes" / "linked.png"
        target.symlink_to(self.asset)
        self.set_path("assets/keyframes/linked.png")
        self.assert_error("path.symlink_forbidden")

    def test_invalid_hash_format_is_schema_error(self):
        for value in ("abc", "A" * 64, "g" * 64, " " + "0" * 64):
            with self.subTest(value=value):
                self.storyboard["shots"][0]["visual"]["keyframe"]["sha256"] = value
                self.write()
                self.assert_error("schema.value_invalid")

    def test_enum_and_identifier_whitespace_is_not_silently_trimmed(self):
        self.storyboard["shots"][0]["motion"]["preset"] = " slow_push_in"
        self.write()
        self.assert_error("schema.value_invalid")
        self.storyboard["shots"][0]["motion"]["preset"] = "slow_push_in"
        self.project["project_id"] = " contract-test"
        self.write()
        self.assert_error("schema.value_invalid")


class InterfaceAndCliTests(BundleCase):
    def snapshot(self):
        return {
            str(path.relative_to(self.job_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.job_dir.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }

    def run_cli(self, job_dir: Path):
        return subprocess.run(
            [
                str(PACKAGE_PYTHON), "-B", "-m", "video_v2", "validate",
                "--job-dir", str(job_dir), "--json",
            ],
            cwd=ENGINE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_validation_is_read_only(self):
        before = self.snapshot()
        self.assertTrue(self.validate().ok)
        self.assertEqual(before, self.snapshot())
        for name in ("audio", "shots", "captions", "cache", "evidence", "output"):
            self.assertFalse((self.job_dir / name).exists())

    def test_load_raises_structured_exception(self):
        video_v2 = self.contract()
        self.project["schema_version"] = 2
        self.write()
        with self.assertRaises(video_v2.JobBundleValidationError) as caught:
            video_v2.load_job_bundle(self.job_dir)
        self.assertEqual(caught.exception.issues[0].code, "schema.version_unsupported")

    def test_cli_success_and_contract_failure(self):
        success = self.run_cli(self.job_dir)
        self.assertEqual(success.returncode, 0, success.stderr)
        payload = json.loads(success.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["contract"], "short-video-v2-job-bundle")
        self.project["schema_version"] = 2
        self.write()
        failure = self.run_cli(self.job_dir)
        self.assertEqual(failure.returncode, 2, failure.stderr)
        payload = json.loads(failure.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "schema.version_unsupported")
        self.assertNotIn("Traceback", failure.stderr)

    def test_multiple_errors_have_deterministic_api_and_cli_order(self):
        self.project["command"] = "not-allowed"
        self.project["canvas"]["fps"] = 25
        self.storyboard["project_id"] = "other"
        self.storyboard["shots"][0]["id"] = "shot-002"
        self.storyboard["shots"][0]["motion"]["preset"] = "zoom_fast"
        self.write()
        first = self.validate()
        second = self.validate()
        expected = tuple((item.code, item.document, item.location) for item in first.errors)
        self.assertEqual(
            expected,
            (
                ("schema.unknown_field", "project.json", "$.command"),
                ("schema.value_invalid", "project.json", "$.canvas.fps"),
                ("shot.order_invalid", "storyboard.json", "$.shots[0].id"),
                ("schema.value_invalid", "storyboard.json", "$.shots[0].motion.preset"),
            ),
        )
        self.assertEqual(expected, tuple((item.code, item.document, item.location) for item in second.errors))
        cli = self.run_cli(self.job_dir)
        self.assertEqual(cli.returncode, 2, cli.stderr)
        cli_errors = json.loads(cli.stdout)["errors"]
        self.assertEqual(expected, tuple((item["code"], item["document"], item["location"]) for item in cli_errors))

    def test_unprobeable_root_is_contract_failure_in_api_and_cli(self):
        long_root = Path(tempfile.gettempdir()) / ("x" * 300)
        result = self.contract().validate_job_bundle(long_root)
        self.assertEqual([item.code for item in result.errors], ["bundle.root_invalid"])
        cli = self.run_cli(long_root)
        self.assertEqual(cli.returncode, 2, cli.stderr)
        self.assertEqual(json.loads(cli.stdout)["errors"][0]["code"], "bundle.root_invalid")

    def test_cli_internal_error_uses_exit_1(self):
        main_module = importlib.import_module("video_v2.__main__")
        with mock.patch.object(main_module, "validate_job_bundle", side_effect=RuntimeError("boom")):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                code = main_module.main(["validate", "--job-dir", str(self.job_dir), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["errors"][0]["code"], "internal.error")
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
