import json
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
DOC_ROOT = PACKAGE_ROOT / "docs" / "short_video_v2"
ACCEPTANCE_PATH = DOC_ROOT / "workflow_acceptance_v1.md"
SKILL_ROOT = REPOSITORY_ROOT / ".agents" / "skills" / "short-video-director"
ROOT_README = REPOSITORY_ROOT / "README.md"
PACKAGE_B_ROOT = REPOSITORY_ROOT / "【包B】语音引擎包"


class DirectorWorkflowDocumentationTests(unittest.TestCase):
    def test_required_workflow_documents_exist(self):
        for relative in (
            "director_workflow_v1.md",
            "templates/brief_v1.md",
            "templates/review_v1.md",
            "workflow_acceptance_v1.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((DOC_ROOT / relative).is_file())

        self.assertTrue(ACCEPTANCE_PATH.is_file())

    def test_repository_skill_is_discoverable_and_versioned(self):
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertEqual((SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.1.0")
        self.assertFalse((REPOSITORY_ROOT / "skills" / "short-video-director").exists())

    def test_public_readme_is_local_only_and_one_sentence_ready(self):
        text = ROOT_README.read_text(encoding="utf-8")
        for required in (
            "Apple Silicon",
            "Codex Plus 或以上会员账号",
            ".agents/skills/short-video-director/",
            "用 $short-video-director",
            "final.mp4",
            "只提供本地使用方式",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        for forbidden in (
            "onecue_gateway",
            "onecue-public",
            "Quick Tunnel",
            "onecue invite",
            "从私有仓库克隆",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_package_b_and_package_a_default_to_loopback(self):
        constants = (PACKAGE_B_ROOT / "apps" / "gradio" / "constants.py").read_text(
            encoding="utf-8"
        )
        package_b_readme = (PACKAGE_B_ROOT / "README.md").read_text(encoding="utf-8")
        package_a_web = (PACKAGE_ROOT / "程序文件" / "网站" / "kt_web.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('DEFAULT_HOST = "127.0.0.1"', constants)
        self.assertIn('DEFAULT_PROMPT_NAME = "女播音"', constants)
        self.assertIn('REPO_ROOT / "apps" / "gradio" / "default_prompts"', constants)
        self.assertNotIn("http://0.0.0.0:7860", package_b_readme)
        self.assertIn('PRODUCTION_HOST = "127.0.0.1"', package_a_web)

        default_prompts = PACKAGE_B_ROOT / "apps" / "gradio" / "default_prompts"
        self.assertGreater((default_prompts / "女播音.wav").stat().st_size, 100_000)
        self.assertIn("女播音 |", (default_prompts / "prompt_text").read_text(encoding="utf-8"))

    def test_model_manifests_pin_immutable_upstream_revisions(self):
        for name in ("macos-mf-model.json", "macos-soar-model.json"):
            manifest = json.loads(
                (PACKAGE_B_ROOT / "manifests" / name).read_text(encoding="utf-8")
            )
            with self.subTest(name=name):
                self.assertRegex(manifest["revision"], r"^[0-9a-f]{40}$")
                self.assertTrue(manifest["repository"].startswith("rednote-hilab/"))
                self.assertEqual(manifest["license"], "Apache-2.0")

        downloader = (REPOSITORY_ROOT / "scripts" / "download_macos_models.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('revision = str(manifest["revision"])', downloader)
        self.assertIn('os.environ.setdefault("HF_HUB_DISABLE_XET", "1")', downloader)
        self.assertIn("max_workers=2", downloader)
        self.assertNotIn('"--revision"', downloader)

        setup = (REPOSITORY_ROOT / "scripts" / "setup_macos_source.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"pip==25.0.1"', setup)
        self.assertNotIn('"--upgrade", "pip"', setup)

    def test_public_release_files_have_no_developer_home_path(self):
        paths = (
            ROOT_README,
            REPOSITORY_ROOT / "scripts" / "setup_macos_source.py",
            REPOSITORY_ROOT / "scripts" / "download_macos_models.py",
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references" / "project-map.md",
            SKILL_ROOT / "references" / "workflow-and-gates.md",
            SKILL_ROOT / "references" / "quality-and-revision.md",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"/Users/[^/]+/")

    def test_workflow_routes_to_existing_contract_and_cli(self):
        text = (DOC_ROOT / "director_workflow_v1.md").read_text(encoding="utf-8")
        for required in (
            "策划模式",
            "新建模式",
            "续接模式",
            "检查模式",
            "渲染模式",
            "返修模式",
            "job_bundle_v1.md",
            "python3 -m video_v2 validate",
            "python3 -m video_v2 render",
            "--shot",
            "用户终审",
            "motion.preset: static",
            "transition_out.type: cut",
            "轻量导演/导航层",
            "而非主链的技术依赖",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_templates_are_human_aids_not_machine_contracts(self):
        brief = (DOC_ROOT / "templates" / "brief_v1.md").read_text(encoding="utf-8")
        review = (DOC_ROOT / "templates" / "review_v1.md").read_text(encoding="utf-8")
        self.assertIn("不是 Job Bundle Schema", brief)
        self.assertIn("可裁剪", brief)
        self.assertIn("用户反馈", review)
        self.assertIn("最小返修", review)

    def test_static_storyboard_is_the_active_product_profile(self):
        director = (DOC_ROOT / "director_workflow_v1.md").read_text(encoding="utf-8")
        job_bundle = (DOC_ROOT / "job_bundle_v1.md").read_text(encoding="utf-8")
        brief = (DOC_ROOT / "templates" / "brief_v1.md").read_text(encoding="utf-8")
        review = (DOC_ROOT / "templates" / "review_v1.md").read_text(encoding="utf-8")
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        gates = (SKILL_ROOT / "references" / "workflow-and-gates.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("第一版活跃范围", director)
        self.assertIn("static + low + cut(0)", director)
        self.assertIn('motion.preset: "static"', job_bundle)
        self.assertIn('transition_out.type: "cut"', job_bundle)
        self.assertIn("每镜一张静态图", brief)
        self.assertIn("没有非预期推拉", review)
        self.assertIn("sequence of distinct static storyboard images", skill)
        self.assertIn("motion=static/low", gates)
        self.assertNotIn("默认基础 FFmpeg 虚拟摄影机运动", director)
        self.assertNotIn("basic FFmpeg camera motion", gates)

    def test_supplied_footage_uses_a_codex_owned_route(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow_path = SKILL_ROOT / "references" / "video-material-workflow.md"
        self.assertEqual((SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.1.0")
        self.assertTrue(workflow_path.is_file())
        workflow = workflow_path.read_text(encoding="utf-8")

        for required in (
            "Codex footage route",
            "general-video",
            "media-use",
            "HyperFrames",
            "package A and package B do not process this route",
        ):
            with self.subTest(required=required):
                self.assertIn(required, skill)

        for required in (
            "Preflight suitability review",
            "Post-build review",
            "use`, `partial use`, or `omit",
            "Package A and package B are outside this route",
            "voice loudness remains stable",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)
        self.assertNotRegex(workflow, r"/Users/[^/]+/")

    def test_open_source_review_borrows_principles_without_runtime(self):
        evidence = ACCEPTANCE_PATH.read_text(encoding="utf-8")
        for source in ("OpenMontage", "PixVerse Skills", "ffmpeg-ai"):
            self.assertIn(source, evidence)
        self.assertIn("没有 clone 或安装这些项目", evidence)
        self.assertIn("core_workflow_verdict", evidence)
        self.assertIn("skill_verdict", evidence)

    def test_frozen_acceptance_splits_core_and_skill_verdicts(self):
        text = ACCEPTANCE_PATH.read_text(encoding="utf-8")
        for required in (
            "core_workflow_verdict=PASS",
            "skill_verdict=PASS",
            "user_workflow_verdict=PASS",
            "overall_verdict=PASS",
            "six_plan_round_complete=true",
            "Skill 不是视频主链的技术依赖",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_internal_planning_material_is_not_distributed(self):
        for path in (
            REPOSITORY_ROOT / "短视频V2规划文档",
            REPOSITORY_ROOT / "短视频V2核心需求与完整方案.md",
            REPOSITORY_ROOT / "项目交接文档.md",
        ):
            with self.subTest(path=path):
                self.assertFalse(path.exists())

    def test_historical_experiments_are_excluded_from_production_imports(self):
        markers = ("short_video_v2_phase4", "short_video_v2_phase7")
        for source in (PACKAGE_ROOT / "程序文件").rglob("*.py"):
            text = source.read_text(encoding="utf-8", errors="replace")
            for marker in markers:
                with self.subTest(source=source, marker=marker):
                    self.assertNotIn(marker, text)

        for relative in (
            "experiments/short_video_v2_phase4/README.md",
            "experiments/short_video_v2_phase7/README.md",
        ):
            readme = PACKAGE_ROOT / relative
            if not readme.exists():
                continue
            text = readme.read_text(encoding="utf-8")
            self.assertIn("历史实验目录", text)
            self.assertIn("发布构建", text)


if __name__ == "__main__":
    unittest.main()
