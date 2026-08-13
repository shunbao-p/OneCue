import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
DOC_ROOT = PACKAGE_ROOT / "docs" / "short_video_v2"
ACCEPTANCE_PATH = DOC_ROOT / "workflow_acceptance_v1.md"
SKILL_ROOT = REPOSITORY_ROOT / "skills" / "short-video-director"


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


if __name__ == "__main__":
    unittest.main()
