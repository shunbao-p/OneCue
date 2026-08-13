from __future__ import annotations

import json
import hashlib
import subprocess
import unittest
from pathlib import Path

from PIL import Image


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PHASE7_ROOT = PACKAGE_ROOT / "experiments" / "short_video_v2_phase7"
TEMPLATES = PHASE7_ROOT / "templates"
README = PHASE7_ROOT / "README.md"
BRIEF = TEMPLATES / "layered_motion_brief_v1.md"
ASSET_MANIFEST = TEMPLATES / "asset_manifest_v1.json"
SCORECARD = TEMPLATES / "scorecard_v1.json"
CASE_A_ROOT = (
    PACKAGE_ROOT
    / "成片"
    / "短视频V2样片"
    / "phase7-hyperframes-micro-motion"
    / "case-a-controlled"
)
CASE_A_MANIFEST = CASE_A_ROOT / "asset-manifest.json"
CASE_B_ROOT = (
    PACKAGE_ROOT
    / "成片"
    / "短视频V2样片"
    / "phase7-hyperframes-micro-motion"
    / "case-b-project-migration"
)
CASE_B_MANIFEST = CASE_B_ROOT / "asset-manifest.json"
REVIEW_ROOT = CASE_A_ROOT.parent / "review-batch5"
REVIEW_MANIFEST = REVIEW_ROOT / "review-manifest.json"
FINAL_MANIFEST = CASE_A_ROOT.parent / "final-manifest.json"
ROUND2_MANIFEST = CASE_A_ROOT.parent / "round2-reopen" / "round2-manifest.json"
ROUND2_ROOT = ROUND2_MANIFEST.parent
ROUND2_REVIEW_MANIFEST = ROUND2_ROOT / "review-batch7" / "review-manifest.json"
ROUND2_REVISION_ROOT = ROUND2_ROOT / "revision-batch8"
ROUND2_RECIPE_MANIFEST = ROUND2_REVISION_ROOT / "recipe-manifest.json"
ROUND2_REVISION_REVIEW_MANIFEST = (
    ROUND2_ROOT / "review-batch8" / "review-manifest.json"
)
ROUND2_BATCH9_REVISION_ROOT = ROUND2_ROOT / "revision-batch9"
ROUND2_BATCH9_RECIPE_MANIFEST = ROUND2_BATCH9_REVISION_ROOT / "recipe-manifest.json"
ROUND2_BATCH9_HASH_LEDGER = ROUND2_BATCH9_REVISION_ROOT / "artifact-sha256.txt"
ROUND2_BATCH9_REVIEW_MANIFEST = ROUND2_ROOT / "review-batch9" / "review-manifest.json"
ROUND2_BATCH9_COLD_REPORT = ROUND2_ROOT / "diagnostics" / "batch9-cold-replay-report.json"
ROUND2_FINAL_CAUSAL_ROOT = ROUND2_ROOT / "final-causal-exception"
ROUND2_FINAL_CAUSAL_REPORT = ROUND2_FINAL_CAUSAL_ROOT / "final-causal-report.json"
ROUND2_FINAL_CAUSAL_LEDGER = ROUND2_FINAL_CAUSAL_ROOT / "artifact-sha256.txt"
MOTION_FEASIBILITY = PACKAGE_ROOT / "docs" / "short_video_v2" / "motion_feasibility_v1.md"
MOTION_PLAYBOOK = PACKAGE_ROOT / "docs" / "short_video_v2" / "motion_experiment_playbook_v1.md"
OVERALL_PLAN = PACKAGE_ROOT.parent / "短视频V2规划文档" / "短视频V2总体目标与阶段规划.md"
EXECUTION_RECORD = (
    PACKAGE_ROOT.parent
    / "短视频V2规划文档"
    / "执行记录"
    / "07-HyperFrames拆层微动态专项验证执行记录.md"
)
PLAN07_CACHE_ROOT = Path("/Users/yuh/Library/Caches/text-video-plan07-hyperframes")
PLAN04_FROZEN_ROOT = Path(
    "/Users/yuh/Library/Caches/text-video-plan04-feasibility/hyperframes"
)


class Phase7HyperFramesMicroMotionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README.read_text(encoding="utf-8")
        cls.brief = BRIEF.read_text(encoding="utf-8")
        cls.asset_manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
        cls.scorecard = json.loads(SCORECARD.read_text(encoding="utf-8"))

    def test_required_contract_files_exist(self) -> None:
        for path in (README, BRIEF, ASSET_MANIFEST, SCORECARD):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)

    def test_cases_variants_layers_and_static_gate_are_explicit(self) -> None:
        for token in (
            "案例 A",
            "案例 B",
            "S：",
            "W：",
            "L：",
            "镜头层",
            "场景层",
            "主体层",
            "局部状态层",
            "静态不成立禁止进入动画",
        ):
            self.assertIn(token, self.readme)
        self.assertEqual(
            [item["id"] for item in self.asset_manifest["variants"]],
            ["S", "W", "L"],
        )
        self.assertEqual(
            self.asset_manifest["motion_layers"],
            ["camera", "scene", "subject", "local_state"],
        )

    def test_asset_roles_and_traceability_are_generic_and_complete(self) -> None:
        roles = self.asset_manifest["required_asset_roles"]
        self.assertEqual(
            roles["character_or_animal"],
            [
                "master",
                "background-clean",
                "subject-cutout",
                "body",
                "head",
                "eyelid-or-eyes-closed",
                "foreground",
            ],
        )
        self.assertIn("leaf-01", roles["plant"])
        asset = self.asset_manifest["assets"][0]
        for field in (
            "role",
            "path",
            "source",
            "prompt_or_operation",
            "width",
            "height",
            "has_alpha",
            "sha256",
            "purpose",
            "version",
        ):
            self.assertIn(field, asset)
        for forbidden_fixture in ("小羊", "sheep", "once-only-sha"):
            self.assertNotIn(
                forbidden_fixture,
                json.dumps(self.asset_manifest, ensure_ascii=False).lower(),
            )

    def test_resource_path_and_command_policy_are_bounded(self) -> None:
        isolation = self.asset_manifest["isolation"]
        self.assertEqual(Path(isolation["cache_root"]), PLAN07_CACHE_ROOT)
        self.assertNotEqual(PLAN07_CACHE_ROOT, PLAN04_FROZEN_ROOT)
        self.assertIn(str(PLAN04_FROZEN_ROOT), isolation["protected_roots"])
        self.assertTrue(isolation["forbid_symlink_escape"])
        resource = self.asset_manifest["resource_policy"]
        self.assertEqual(resource["new_download_cache_limit_bytes"], 1024**3)
        self.assertTrue(resource["requires_pause_above_limit"])
        self.assertTrue(resource["new_model_requires_pause"])
        self.assertTrue(resource["third_party_provider_requires_pause"])
        self.assertTrue(resource["cloud_api_or_fee_requires_pause"])
        command = self.asset_manifest["command_policy"]
        self.assertEqual(command["argv_type"], "list[str]")
        self.assertIs(command["shell"], False)
        self.assertTrue(command["finite_timeout_required"])
        self.assertTrue(command["runtime_network_forbidden"])

    def test_media_timeline_and_proof_pose_contract(self) -> None:
        media = self.asset_manifest["media_spec"]
        self.assertEqual(
            (media["width"], media["height"], media["fps"]),
            (1080, 1920, 30),
        )
        self.assertEqual((media["duration_sec_min"], media["duration_sec_max"]), (4, 6))
        self.assertEqual((media["codec"], media["pixel_format"]), ("h264", "yuv420p"))
        self.assertEqual(media["audio_streams"], 0)
        timeline = self.asset_manifest["timeline_contract"]
        self.assertTrue(timeline["single_paused_timeline"])
        self.assertTrue(timeline["parent_child_layers"])
        self.assertTrue(timeline["finite_repeats"])
        self.assertTrue(timeline["seeded_or_explicit_particles"])
        self.assertEqual(
            self.asset_manifest["proof_poses"],
            [
                "first_frame",
                "pre_action_hold",
                "subject_peak",
                "local_state_peak",
                "return_to_rest",
                "final_minus_hold",
                "final_frame",
            ],
        )

    def test_brief_forbids_fake_subject_motion_and_nondeterminism(self) -> None:
        for token in (
            "整图左右晃动",
            "滤镜或粒子冒充主体动作",
            "repeat:-1",
            "Date.now",
            "performance.now",
            "Math.random",
            "运行时 fetch",
            "末帧黑屏或复位",
        ):
            self.assertIn(token, self.brief)

    def test_scorecard_and_user_gate_cannot_be_auto_passed(self) -> None:
        self.assertEqual(
            set(self.scorecard["metrics"]),
            {
                "subject_motion_perceptibility",
                "motion_naturalness",
                "identity_stability",
                "seam_and_occlusion_quality",
                "scene_depth_and_environment",
                "camera_comfort",
                "engineering_complexity",
                "overall_usability",
            },
        )
        self.assertEqual(len(self.scorecard["blind_review_questions"]), 5)
        policy = self.scorecard["review_policy"]
        self.assertTrue(policy["private_mapping_required"])
        self.assertTrue(policy["tool_identity_hidden"])
        self.assertTrue(policy["codex_scores_sealed_before_user_review"])
        self.assertTrue(policy["user_reply_required_for_batch6"])
        self.assertEqual(policy["maximum_verdict_before_user_reply"], "CONDITIONAL")
        gate = self.asset_manifest["review_gate"]
        self.assertEqual(gate["batch5_status"], "awaiting_user_review")
        self.assertTrue(gate["batch6_forbidden_before_user_reply"])

    def test_case_a_frozen_layers_are_traceable_and_pixel_valid(self) -> None:
        manifest = json.loads(CASE_A_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn(manifest["status"], {"frozen_batch_2", "frozen_batch_3"})
        self.assertEqual(manifest["case_id"], "case-a")
        self.assertEqual(manifest["canvas"], {"width": 1080, "height": 1920})
        self.assertEqual(manifest["generation"]["bounded_asset_revisions"], 1)

        roles = {asset["role"] for asset in manifest["assets"]}
        self.assertTrue(
            {
                "master",
                "background-clean",
                "subject-cutout",
                "body",
                "head",
                "neck-cover",
                "eyelid-or-eyes-closed",
                "foreground-left",
                "foreground-right",
            }.issubset(roles)
        )

        for asset in (*manifest["source_assets"], *manifest["assets"]):
            path = CASE_A_ROOT / asset["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, asset["sha256"], path)
            self.assertRegex(asset["sha256"], r"^[0-9a-f]{64}$")
            with Image.open(path) as image:
                self.assertEqual(image.size, (asset["width"], asset["height"]))
                alpha_range = (
                    image.getchannel("A").getextrema()
                    if "A" in image.getbands()
                    else (255, 255)
                )
                self.assertEqual(alpha_range[0] < 255, asset["has_alpha"])

        for proof in manifest["static_proofs"].values():
            if not isinstance(proof, dict) or "path" not in proof:
                continue
            path = CASE_A_ROOT / proof["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), proof["sha256"])
        self.assertTrue(manifest["static_proofs"]["passed"])
        self.assertFalse(manifest["visual_review"]["hard_alpha_fringe_after_revision"])

        if manifest["status"] == "frozen_batch_3":
            self.assertEqual({item["variant"] for item in manifest["videos"]}, {"S", "W", "L"})
            for video in manifest["videos"]:
                path = CASE_A_ROOT / video["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), video["sha256"])
                self.assertEqual((video["width"], video["height"], video["fps"]), (1080, 1920, 30))
                self.assertEqual((video["codec"], video["pixel_format"]), ("h264", "yuv420p"))
                self.assertEqual(video["audio_streams"], 0)
                self.assertTrue(video["full_decode_ok"])

    def test_case_b_frozen_migration_is_traceable_and_pixel_valid(self) -> None:
        manifest = json.loads(CASE_B_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "frozen_batch_4")
        self.assertEqual(manifest["case_id"], "case-b")
        self.assertEqual(manifest["source_kind"], "current-project-migration")
        self.assertEqual(manifest["canvas"], {"width": 1080, "height": 1920})
        self.assertEqual(manifest["generation"]["bounded_asset_revisions"], 1)
        self.assertEqual(manifest["hyperframes"]["action_parameter_revisions"], 0)

        roles = {asset["role"] for asset in manifest["assets"]}
        self.assertTrue(
            {
                "master",
                "background-clean",
                "subject-cutout",
                "stem-base",
                "leaf-top",
                "leaf-left",
                "leaf-right",
                "foreground",
                "seam-covers",
            }.issubset(roles)
        )

        for asset in (*manifest["source_assets"], *manifest["assets"]):
            path = CASE_B_ROOT / asset["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, asset["sha256"], path)
            self.assertRegex(asset["sha256"], r"^[0-9a-f]{64}$")
            with Image.open(path) as image:
                self.assertEqual(image.size, (asset["width"], asset["height"]))
                alpha_range = (
                    image.getchannel("A").getextrema()
                    if "A" in image.getbands()
                    else (255, 255)
                )
                self.assertEqual(alpha_range[0] < 255, asset["has_alpha"])

        for proof in manifest["static_proofs"].values():
            if not isinstance(proof, dict) or "path" not in proof:
                continue
            path = CASE_B_ROOT / proof["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), proof["sha256"])

        self.assertTrue(manifest["static_proofs"]["passed"])
        self.assertFalse(manifest["visual_review"]["hard_partition_seam_after_revision"])
        self.assertEqual({item["variant"] for item in manifest["videos"]}, {"S", "W", "L"})
        for video in manifest["videos"]:
            path = CASE_B_ROOT / video["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), video["sha256"])
            self.assertEqual((video["width"], video["height"], video["fps"]), (1080, 1920, 30))
            self.assertEqual(video["frames"], 150)
            self.assertEqual((video["codec"], video["pixel_format"]), ("h264", "yuv420p"))
            self.assertEqual(video["audio_streams"], 0)
            self.assertTrue(video["full_decode_ok"])

    def test_batch5_anonymous_review_set_is_frozen_and_sealed(self) -> None:
        manifest = json.loads(REVIEW_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "awaiting_user_review")
        self.assertEqual(manifest["mapping"], "private/mapping.json")
        self.assertEqual(manifest["codex_scores"], "private/codex-scores.json")
        self.assertTrue(manifest["review_policy"]["tool_identity_hidden"])
        self.assertTrue(manifest["review_policy"]["quality_hint_hidden"])
        self.assertTrue(manifest["review_policy"]["codex_scores_sealed_before_user_review"])
        self.assertTrue(manifest["review_policy"]["user_reply_required_for_batch6"])
        self.assertEqual(
            manifest["review_policy"]["maximum_verdict_before_user_reply"],
            "CONDITIONAL",
        )

        public_videos = []
        for item in manifest["public_files"]:
            path = REVIEW_ROOT / item["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
            self.assertNotRegex(path.name.lower(), r"(^|[-_])(s|w|l)([-_.]|$)")
            if path.suffix == ".mp4":
                public_videos.append(path)

        self.assertEqual(len(public_videos), 6)
        self.assertEqual(
            {path.parent.name for path in public_videos},
            {"case-01", "case-02"},
        )
        self.assertTrue((REVIEW_ROOT / "public/review-guide.md").is_file())
        self.assertTrue((REVIEW_ROOT / "public/technical-ledger.md").is_file())

        for item in manifest["private_artifacts"]:
            path = REVIEW_ROOT / item["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

        mapping = json.loads((REVIEW_ROOT / manifest["mapping"]).read_text(encoding="utf-8"))
        scores = json.loads((REVIEW_ROOT / manifest["codex_scores"]).read_text(encoding="utf-8"))
        self.assertTrue(mapping["do_not_disclose_before_batch6"])
        self.assertEqual(mapping["status"], "sealed_before_user_review")
        self.assertEqual(scores["status"], "sealed_before_user_review")
        self.assertTrue(scores["policy"]["does_not_replace_user_judgment"])

    def test_batch6_final_rejection_is_traceable_without_media_rewrite(self) -> None:
        manifest = json.loads(FINAL_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["director_mode"], "Resume")
        self.assertEqual(manifest["plan_grade"], "FAIL")
        self.assertEqual(manifest["classification"], "rejected")
        self.assertFalse(manifest["revision"]["performed"])
        self.assertEqual(manifest["revision"]["bounded_revision_budget_used"], 0)
        self.assertFalse(manifest["revision"]["media_changed_after_user_review"])
        self.assertFalse(manifest["revision"]["rerendered_after_user_review"])
        self.assertTrue(
            manifest["codex_score_reconciliation"]["user_judgment_overrides_automatic_score"]
        )
        self.assertEqual(
            manifest["preserved_capabilities"]["hyperframes_information_design"],
            "manual_only",
        )
        self.assertFalse(
            manifest["preserved_capabilities"]["formal_micro_motion_provider_created"]
        )
        self.assertEqual(
            manifest["failure_classification"]["visual_quality"],
            "failed_user_gate",
        )

        evidence_root = FINAL_MANIFEST.parent
        for case in manifest["final_media"].values():
            if not isinstance(case, dict) or not {"S", "W", "L"}.issubset(case):
                continue
            for variant in ("S", "W", "L"):
                item = case[variant]
                path = evidence_root / item["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

        for path in (MOTION_FEASIBILITY, OVERALL_PLAN, README):
            text = path.read_text(encoding="utf-8")
            self.assertIn("rejected", text)
        self.assertIn("FAIL", MOTION_FEASIBILITY.read_text(encoding="utf-8"))
        self.assertIn("FAIL / rejected", OVERALL_PLAN.read_text(encoding="utf-8"))
        self.assertIn("FAIL", README.read_text(encoding="utf-8"))

    def test_round2_reopen_manifest_is_additive_and_records_final_user_gate(self) -> None:
        self.assertEqual(
            hashlib.sha256(FINAL_MANIFEST.read_bytes()).hexdigest(),
            "d63a67e9ab0d945f46935de83d6103d52f2735fd63384f7f8931081443cd342b",
        )
        self.assertTrue(ROUND2_MANIFEST.is_file(), ROUND2_MANIFEST)
        self.assertNotEqual(ROUND2_MANIFEST, FINAL_MANIFEST)

        manifest = json.loads(ROUND2_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["schema"], "short-video-v2.phase7.round2-reopen-manifest.v1"
        )
        self.assertEqual(manifest["round"], 2)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["plan_grade"], "CONDITIONAL")
        self.assertEqual(manifest["classification"], "manual_only")
        self.assertFalse(manifest["supersedes_round1"])
        self.assertEqual(manifest["parent_round1_manifest"]["path"], "../final-manifest.json")
        self.assertEqual(
            manifest["parent_round1_manifest"]["sha256"],
            "d63a67e9ab0d945f46935de83d6103d52f2735fd63384f7f8931081443cd342b",
        )
        self.assertEqual(manifest["round1_verdict"]["plan_grade"], "FAIL")
        self.assertEqual(manifest["round1_verdict"]["classification"], "rejected")
        self.assertEqual(
            manifest["reopen_trigger"]["invalidated_stop_reason"],
            "no_actionable_bounded_revision_target",
        )
        self.assertTrue(manifest["reopen_trigger"]["does_not_retract_round1_evidence"])
        self.assertEqual(
            manifest["review"]["maximum_verdict_before_user_reply"], "CONDITIONAL"
        )
        self.assertEqual(manifest["integration_decision"], "not_reopened_for_production")
        final_decision = manifest["final_decision"]
        self.assertEqual(
            final_decision["accepted_narrow_recipe"],
            "controlled_animal_blink_and_single_ear_v1",
        )
        self.assertEqual(
            final_decision["rejected_recipe"],
            "plant_unique_ownership_multi_leaf_sway_v2",
        )
        self.assertEqual(
            final_decision["rejected_reason"],
            "user_rejected_due_to_ghosting",
        )
        self.assertEqual(
            final_decision["ordinary_natural_subject_production_route"],
            "closed",
        )
        self.assertTrue(
            final_decision["user_visual_gate_overrides_automatic_visual_gate"]
        )
        self.assertEqual(
            manifest["user_review_batch8"]["case-a"]["outcome"],
            "user_accepted",
        )
        self.assertEqual(
            manifest["user_review_batch8"]["case-b"]["outcome"],
            "revision_requested",
        )
        self.assertEqual(
            set(manifest["user_review_batch8"]["case-b"]["reasons"]),
            {
                "motion_amplitude_too_small_to_confirm",
                "at_least_two_leaves_should_move_concurrently",
            },
        )
        review_state = manifest["current_review"]
        self.assertEqual(review_state["batch"], "review-batch9")
        self.assertEqual(review_state["status"], "closed")
        self.assertTrue(review_state["no_longer_waiting"])
        self.assertFalse(
            review_state["user_reply_required_before_case_b_acceptance"]
        )
        self.assertTrue(
            review_state["production_or_majority_shot_claim_forbidden"]
        )
        batch9_review = manifest["user_review_batch9"]
        self.assertTrue(batch9_review["received"])
        self.assertEqual(
            batch9_review["feedback"],
            {
                "motion_visibility": "动作明显。",
                "wind_coherence": "像一阵风。",
                "visual_defect": "明显重影。",
            },
        )
        self.assertEqual(batch9_review["motion_visibility"], "PASS")
        self.assertEqual(batch9_review["wind_coherence"], "PASS")
        self.assertEqual(batch9_review["artifact_gate"], "FAIL")
        self.assertEqual(
            batch9_review["outcome"], "user_rejected_due_to_ghosting"
        )
        self.assertEqual(
            batch9_review["automatic_visual_gate_assessment"], "false_negative"
        )
        self.assertTrue(batch9_review["user_visual_gate_has_priority"])
        forensics = manifest["post_review_forensics"]
        self.assertEqual(forensics["status"], "structural_ghosting_reproduced")
        self.assertEqual(
            forensics["visible_frame_window_zero_based"],
            {"broad": [38, 90], "strongest": [50, 66]},
        )
        self.assertIn("crossfade_between_states", forensics["excluded_primary_causes"])
        self.assertIn(
            "semantic_deformation_purity_inside_each_connected_dynamic_layer",
            forensics["automatic_gate_gaps"],
        )
        self.assertIn("coarse semantic clusters", forensics["important_contributing_mechanism"])
        self.assertEqual(
            forensics["causal_boundary_after_final_exception"],
            "important contributing mechanism, not established as the unique or complete root cause",
        )
        self.assertNotIn("primary_cause", forensics)
        self.assertIn("77 of 149", forensics["secondary_cause"])
        breadth = manifest["feasibility_breadth_gate"]
        self.assertEqual(breadth["current_status"], "not_run")
        self.assertEqual(
            breadth["final_disposition"],
            "cancelled_due_to_failed_prerequisite",
        )
        self.assertEqual(
            breadth["failed_prerequisite"], "case_b_user_visual_gate"
        )

        for candidate in manifest["candidates"].values():
            path = ROUND2_ROOT / candidate["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), candidate["sha256"])
            media = candidate["media"]
            self.assertEqual((media["width"], media["height"], media["fps"]), (1080, 1920, 30))
            self.assertEqual(media["frames"], 150)
            self.assertEqual((media["codec"], media["pixel_format"]), ("h264", "yuv420p"))
            self.assertEqual(media["audio_streams"], 0)
            self.assertTrue(media["full_decode_ok"])

        review = json.loads(ROUND2_REVIEW_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(review["status"], "awaiting_user_review")
        self.assertTrue(review["review_policy"]["only_affected_round2_candidates_are_shown"])
        self.assertTrue(review["review_policy"]["local_slow_views_are_companions_not_candidates"])
        self.assertTrue(review["review_policy"]["user_reply_required_before_final_round2_verdict"])
        self.assertEqual(
            review["review_policy"]["maximum_verdict_before_user_reply"],
            "CONDITIONAL",
        )
        review_root = ROUND2_REVIEW_MANIFEST.parent
        for item in (*review["public_files"], *review["private_artifacts"]):
            path = review_root / item["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

    def test_round2_revision_is_replay_verified_but_not_promoted(self) -> None:
        self.assertTrue(MOTION_PLAYBOOK.is_file(), MOTION_PLAYBOOK)
        playbook = MOTION_PLAYBOOK.read_text(encoding="utf-8")
        for token in (
            "production_recipe",
            "3 个真实视频 × 每个 4 类镜头 = 12 镜",
            "至少 9/12",
            "45 分钟即停止",
            "semantic_motion_required",
        ):
            self.assertIn(token, playbook)

        recipe = json.loads(ROUND2_RECIPE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            recipe["status"], "replay_verified_awaiting_revision_review"
        )
        self.assertFalse(recipe["supersedes_round1"])
        self.assertTrue(recipe["project"]["self_contained"])
        self.assertTrue(recipe["project"]["strict_check"]["ok"])
        self.assertTrue(
            recipe["recipes"]["controlled_animal_blink_and_single_ear_v1"]
            ["seek_repeat"]["same_time_png_sha256_match"]
        )
        plant = recipe["recipes"]["plant_unique_ownership_leaf_sway_v1"]
        self.assertEqual(plant["hard_gate"]["alpha_thresholds_checked"], 256)
        self.assertEqual(plant["hard_gate"]["holes"], 0)
        self.assertEqual(plant["hard_gate"]["extras"], 0)
        self.assertEqual(plant["hard_gate"]["pairwise_overlap"], 0)
        self.assertTrue(recipe["promotion_gate"]["user_revision_review_required"])
        self.assertTrue(
            recipe["promotion_gate"]["breadth_gate_required_for_production_recipe"]
        )

        for item in recipe["recipes"].values():
            path = ROUND2_REVISION_ROOT / item["final_media"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)

        review = json.loads(
            ROUND2_REVISION_REVIEW_MANIFEST.read_text(encoding="utf-8")
        )
        self.assertEqual(review["status"], "awaiting_revision_review")
        self.assertTrue(
            review["review_policy"]["user_reply_required_before_recipe_promotion"]
        )
        self.assertEqual(
            review["review_policy"]["maximum_claim_before_user_reply"],
            "replay_verified_technical_candidate",
        )
        review_root = ROUND2_REVISION_REVIEW_MANIFEST.parent
        for item in (*review["public_files"], *review["private_artifacts"]):
            path = review_root / item["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"]
            )

    def test_batch9_is_case_b_only_replay_verified_and_not_promoted(self) -> None:
        frozen_hashes = {
            FINAL_MANIFEST: "d63a67e9ab0d945f46935de83d6103d52f2735fd63384f7f8931081443cd342b",
            CASE_A_MANIFEST: "665ba91ba51f916495522619fad20fbd91471f14206a721a83b49068f0ed2883",
            ROUND2_RECIPE_MANIFEST: "4174b4eb1e4a419690a8f1dc16d7651c46041cc4f6cce087eb63c7330e018000",
            ROUND2_REVISION_ROOT / "artifact-sha256.txt": "c5891d556e1f1c3ab4f57c4aeae5ecdc0b5c244e94aff45d301060ad8d1df37d",
            ROUND2_REVISION_REVIEW_MANIFEST: "6752d439ce272bb82ff98160fa74f2b149ebf6fce74d0e0262024af1123763ff",
            ROUND2_REVISION_ROOT / "videos/case-a-revision-high.mp4": "d301e9818d62ffc18b95c4b8ecb1e3ec789a7f394ac87b3671e0955804cea6ba",
            ROUND2_REVISION_ROOT / "videos/case-b-revision-high.mp4": "2958770ddfd5ad9940903f07bd33ce1ed47da4b77c9b20cd938f4ee7de02ed02",
            ROUND2_BATCH9_RECIPE_MANIFEST: "7a45795d1d43739166d45012489a89a06404260f41e4719ba3017c1862dc1904",
            ROUND2_BATCH9_HASH_LEDGER: "1791fdd6fc5d14b76e47d73194dad707d4350dc8990902d5e94c47919214131f",
            ROUND2_BATCH9_REVIEW_MANIFEST: "e65a6be5055b30f8986c3dad72d22402dd96344e8a98abbc64582dfdef75564e",
            ROUND2_BATCH9_COLD_REPORT: "c0d654e8a966bc8b69aaa11cab812d8ebb78f82b3a1b2e691bfc4469a1ed14b2",
            ROUND2_BATCH9_REVISION_ROOT / "videos/case-b-plant-multi-leaf-high.mp4": "94a59bd1740b8444ec4d823ffaadf6825dfe9f0ed6b2abb3aa25b518da254822",
        }
        for path, expected in frozen_hashes.items():
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, path)

        total = json.loads(ROUND2_MANIFEST.read_text(encoding="utf-8"))
        batch9 = total["revision_batch9"]
        self.assertEqual(batch9["scope"], "case-b-only")
        self.assertEqual(batch9["status"], "user_review_received")
        self.assertEqual(batch9["case-a"]["status"], "user_accepted_preserved")
        self.assertFalse(batch9["case-a"]["modified"])
        self.assertFalse(batch9["case-a"]["shown_again"])
        self.assertEqual(
            batch9["case-a"]["sha256"],
            "d301e9818d62ffc18b95c4b8ecb1e3ec789a7f394ac87b3671e0955804cea6ba",
        )
        self.assertTrue(batch9["revision_budget"]["automatic_batch10_forbidden"])
        self.assertEqual(
            batch9["case-b"]["technical_status"],
            "replay_verified_technical_candidate",
        )
        self.assertEqual(
            batch9["case-b"]["status"], "user_rejected_due_to_ghosting"
        )
        self.assertEqual(batch9["case-b"]["user_visual_gate"], "FAIL")
        cold = batch9["cold_replay"]
        self.assertEqual(cold["path"], "diagnostics/batch9-cold-replay-report.json")
        self.assertEqual(cold["status"], "PASS")
        self.assertTrue(cold["frozen_media_bit_identical"])
        self.assertEqual(
            cold["validated_recipe_sha256"],
            "7a45795d1d43739166d45012489a89a06404260f41e4719ba3017c1862dc1904",
        )
        self.assertTrue(ROUND2_BATCH9_COLD_REPORT.is_file())
        self.assertEqual(
            hashlib.sha256(ROUND2_BATCH9_COLD_REPORT.read_bytes()).hexdigest(),
            cold["sha256"],
        )
        cold_report = json.loads(ROUND2_BATCH9_COLD_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(cold_report["verdict"]["cold_replay"], "PASS")
        self.assertTrue(cold_report["cold_high_render"]["mp4_bytes_identical"])
        self.assertEqual(
            cold_report["frozen_hashes"]["recipe_manifest_sha256"],
            cold["validated_recipe_sha256"],
        )
        self.assertEqual(
            cold_report["frozen_hashes"]["artifact_ledger_sha256"],
            cold["validated_artifact_ledger_sha256"],
        )

        recipe = json.loads(ROUND2_BATCH9_RECIPE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(recipe["scope"], "case-b-only")
        self.assertEqual(
            recipe["parent_batch8_recipe"]["sha256"],
            "4174b4eb1e4a419690a8f1dc16d7651c46041cc4f6cce087eb63c7330e018000",
        )
        self.assertTrue(recipe["parent_batch8_recipe"]["preserved_unchanged"])
        self.assertTrue(recipe["project"]["self_contained_for_check_and_render"])
        self.assertTrue(recipe["project"]["fresh_frozen_check"]["ok"])
        provenance = recipe["project"]["diagnostic_provenance"]
        self.assertTrue(provenance["historical_cache_reports_retained_verbatim"])
        self.assertFalse(provenance["runtime_dependency_on_historical_absolute_paths"])
        self.assertEqual(set(recipe["recipes"]), {"plant_unique_ownership_multi_leaf_sway_v2"})
        plant = recipe["recipes"]["plant_unique_ownership_multi_leaf_sway_v2"]
        self.assertFalse(plant["camera_motion"])
        self.assertFalse(plant["runtime_seam_cover"])
        self.assertFalse(plant["crossfade"])
        self.assertTrue(plant["single_paused_gsap_timeline"])
        self.assertGreater(plant["motion"]["leaf_top_peak_tip_displacement_px"], 13.45)
        self.assertGreater(plant["motion"]["leaf_left_peak_tip_displacement_px"], 6.96)
        self.assertGreaterEqual(
            plant["motion"]["concurrent_two_main_leaves"]["frames"], 15
        )
        self.assertTrue(plant["motion"]["concurrent_two_main_leaves"]["passed"])
        self.assertEqual(plant["high_visual_gate"]["status"], "PASS")
        self.assertTrue(
            recipe["promotion_gate"]["production_or_majority_shot_claim_forbidden"]
        )
        self.assertEqual(recipe["promotion_gate"]["breadth_gate_status"], "not_run")
        self.assertTrue(recipe["revision_budget"]["automatic_batch10_forbidden"])
        commands = recipe["commands"]
        self.assertEqual(commands["working_directory"], "project")
        self.assertEqual(commands["fresh_check_argv"][0:3], ["npx", "--yes", "hyperframes@0.7.107"])
        self.assertIn("--strict", commands["fresh_check_argv"])
        self.assertIn("--strict-all", commands["high_render_argv"])
        self.assertEqual(commands["seek_repeat_argv"][0], "node")
        self.assertEqual(commands["frame_sweep_argv"][0], "node")
        self.assertEqual(commands["policy"]["argv_type"], "list[str]")
        self.assertFalse(commands["policy"]["shell"])
        self.assertTrue(commands["policy"]["runtime_network_forbidden"])

        semantic_report = json.loads(
            (
                ROUND2_BATCH9_REVISION_ROOT
                / "project/diagnostics/case-b-semantic-v3/ownership-report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(semantic_report["validation_threshold_count"], 256)
        self.assertTrue(semantic_report["hard_gate"]["passed"])
        self.assertEqual(semantic_report["identity"]["outputs_to_normalized_subject_rgba_max_error"], 0)
        self.assertEqual(semantic_report["identity"]["zero_pose_background_composite_rgba_max_error"], 0)
        for threshold in semantic_report["thresholds"].values():
            self.assertEqual(threshold["holes"], 0)
            self.assertEqual(threshold["extras"], 0)
            self.assertTrue(threshold["passed"])
            self.assertTrue(all(value == 0 for value in threshold["pairwise_overlap"].values()))

        mesh_report = json.loads(
            (
                ROUND2_BATCH9_REVISION_ROOT
                / "project/diagnostics/case-b-l4/mesh-assets-report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(mesh_report["hard_gate"]["passed"])
        for layer in mesh_report["layers"].values():
            self.assertEqual(layer["rest_crop_max_rgba_error"], 0)
            self.assertEqual(layer["pin"]["max_rgba_error_all_states"], 0)
            self.assertLessEqual(layer["theoretical_adjacent_tip_step_px"], 1.5)
            self.assertEqual(layer["unique_state_hashes"], 31)

        review = json.loads(ROUND2_BATCH9_REVIEW_MANIFEST.read_text(encoding="utf-8"))
        # review-batch9 is frozen pre-review evidence; the aggregate manifest,
        # rather than this historical artifact, records the user's final answer.
        self.assertEqual(review["status"], "awaiting_plant_revision_review")
        self.assertEqual(review["scope"], "case-02-only")
        self.assertTrue(review["review_policy"]["accepted_case_a_is_not_reshown_or_modified"])
        self.assertTrue(review["review_policy"]["automatic_batch10_forbidden"])
        review_root = ROUND2_BATCH9_REVIEW_MANIFEST.parent
        public_videos = []
        for item in (*review["public_files"], *review["private_artifacts"]):
            path = review_root / item["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
            if path.suffix == ".mp4":
                public_videos.append(path)
        self.assertEqual(len(public_videos), 1)
        self.assertEqual(public_videos[0].parent.name, "case-02")

        media = public_videos[0]
        self.assertEqual(
            hashlib.sha256(media.read_bytes()).hexdigest(),
            "94a59bd1740b8444ec4d823ffaadf6825dfe9f0ed6b2abb3aa25b518da254822",
        )
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_name,codec_type,width,height,pix_fmt,r_frame_rate,nb_frames",
                "-of", "json", str(media),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        probe_data = json.loads(probe.stdout)
        video_streams = [stream for stream in probe_data["streams"] if stream["codec_type"] == "video"]
        audio_streams = [stream for stream in probe_data["streams"] if stream["codec_type"] == "audio"]
        self.assertEqual(len(video_streams), 1)
        self.assertEqual(len(audio_streams), 0)
        stream = video_streams[0]
        self.assertEqual((stream["width"], stream["height"]), (1080, 1920))
        self.assertEqual(stream["r_frame_rate"], "30/1")
        self.assertEqual(stream["nb_frames"], "150")
        self.assertEqual((stream["codec_name"], stream["pix_fmt"]), ("h264", "yuv420p"))
        self.assertEqual(float(probe_data["format"]["duration"]), 5.0)
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(media), "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(decoded.returncode, 0, decoded.stderr)

        self.assertTrue(ROUND2_BATCH9_HASH_LEDGER.is_file())
        ledger_entries = ROUND2_BATCH9_HASH_LEDGER.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(ledger_entries), 130)
        for line in ledger_entries:
            expected, relative = line.split("  ", 1)
            path = PACKAGE_ROOT.parent / relative
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, path)

    def test_final_causal_exception_is_bounded_hashed_and_permanently_stopped(self) -> None:
        expected_hashes = {
            "artifact-sha256.txt": "e05bce3885643202ae992eb86eb8257976f7a4b5aa382915224976ac7718c7bb",
            "config.json": "5bb0142ac73564c852f798b6027f1670dc7ebd95f0c85c7d7e7470b7d6a01b75",
            "final-causal-report.json": "27d4b76de4fc63c6a52eba3bf986a64091e27d054894cea965d149f88afe2182",
            "generate_unified_mesh.swift": "474fda5e6031d5bf24858dda84477a620f705ed8c1110bd704ebf572f254887e",
            "hard-gate-report.json": "4cf1305b1131a11bb7eea45d4034fd5bd15506fc270a7ac23167cf2d6e54c990",
            "project/assets/mesh-geometry.json": "2ce99e1364ea1b7f6234723221fba8042168ad6096a72d8d841d878386ab585f",
            "project/assets/subject-states/rest-warp.png": "50d1e4dff914187f1227e6d9ff95600ac5ee13d98197b1bddd60e99fe848e8ed",
            "proofs/frame-46.png": "4a96f7bd657219857dea8803b42b84ed59fce44c226f76d407525b1a0e1fdbc8",
            "proofs/frame-53.png": "e15374397d1ddabc1619d4b44c8829fea84920e6d67a4150954da29e6d3f2b8c",
            "proofs/frame-60.png": "6d6b9a486cd618d94e1ab440eb992b028bc60db4879ebbd637422d27583715b0",
            "proofs/pressure-46-53-60.png": "96633a6891e671840b6b6911297fc6649f327d6d82fad90dff3bd6ab5edfce11",
            "strain-ghost-report.json": "1d3d70d6750c82f0f8bd2aee94aa2df5caa8756b6634e8706263aa7c4ac9af87",
            "verify_hard_gates.py": "f8325a428c5577ae198681cd2596920e5fbc6f287c25bd6202b6099f143cec90",
            "verify_strain_ghost.py": "6eb801835d20a8a9a77fc7d471d877708f2b9da3c0e25d356d57ec698ca73d6a",
        }
        self.assertTrue(ROUND2_FINAL_CAUSAL_ROOT.is_dir())
        self.assertFalse(ROUND2_FINAL_CAUSAL_ROOT.is_symlink())
        for path in ROUND2_FINAL_CAUSAL_ROOT.rglob("*"):
            self.assertFalse(path.is_symlink(), path)

        actual_files = {
            path.relative_to(ROUND2_FINAL_CAUSAL_ROOT).as_posix()
            for path in ROUND2_FINAL_CAUSAL_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual_files, set(expected_hashes))
        for relative, expected in expected_hashes.items():
            path = ROUND2_FINAL_CAUSAL_ROOT / relative
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, path)

        ledger_entries = {}
        for line in ROUND2_FINAL_CAUSAL_LEDGER.read_text(encoding="utf-8").splitlines():
            expected, relative = line.split("  ", 1)
            ledger_entries[relative] = expected
        self.assertEqual(
            ledger_entries,
            {
                relative: expected
                for relative, expected in expected_hashes.items()
                if relative != "artifact-sha256.txt"
            },
        )

        manifest = json.loads(ROUND2_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["plan_grade"], "CONDITIONAL")
        self.assertEqual(manifest["classification"], "manual_only")
        self.assertEqual(manifest["integration_decision"], "not_reopened_for_production")
        exception = manifest["final_causal_exception"]
        self.assertEqual(
            exception,
            {
                "evidence_root": "final-causal-exception",
                "report": {
                    "path": "final-causal-exception/final-causal-report.json",
                    "sha256": expected_hashes["final-causal-report.json"],
                },
                "artifact_ledger": {
                    "path": "final-causal-exception/artifact-sha256.txt",
                    "sha256": expected_hashes["artifact-sha256.txt"],
                },
                "frozen_inputs": {
                    "subject": {
                        "path": "revision-batch9/project/assets/case-b/subject-cutout.png",
                        "sha256": "65fdab0cd3987e5058448202e235b7ece1f707aeaf38ff0723d49709b0d19225",
                    },
                    "background": {
                        "path": "revision-batch9/project/assets/case-b/background-clean.png",
                        "sha256": "0b39c25141235462b85723ede5a0be1aac0f59e8e8d89adc6253d22d72327dc7",
                    },
                },
            },
        )
        for frozen in exception["frozen_inputs"].values():
            path = ROUND2_ROOT / frozen["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), frozen["sha256"])

        report = json.loads(ROUND2_FINAL_CAUSAL_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(
            report["schema"],
            "short-video-v2.phase7.final-causal-exception-report.v1",
        )
        self.assertEqual(
            report["authorization"]["basis"],
            "user_authorized_final_causal_exception",
        )
        self.assertEqual(
            report["authorization"]["round_classification"],
            "not_batch10/not_round3",
        )
        self.assertTrue(report["authorization"]["preserves_round2_status_and_classification"])
        self.assertTrue(report["authorization"]["preserves_frozen_batch8_and_batch9"])
        self.assertEqual(report["scope"]["result_run"], "only_valid_run")
        self.assertEqual(report["scope"]["valid_run_count"], 1)
        self.assertFalse(report["scope"]["uncalibrated_early_outputs_are_results"])
        self.assertFalse(report["effective_run"]["parameter_revision_after_result"])

        g4 = report["gates"]["g4"]
        self.assertEqual(g4["status"], "PASS")
        self.assertEqual(g4["simultaneous_10_to_18px_source_frames"], [57, 58, 59, 60])
        self.assertEqual(g4["top_max_adjacent_step_px"], 1.1052748609490886)
        self.assertEqual(g4["left_max_adjacent_step_px"], 0.7056290390179525)
        g5 = report["gates"]["g5"]
        self.assertEqual(g5["status"], "FAIL")
        self.assertTrue(g5["used_for_stop"])
        self.assertEqual(
            {
                key: g5[key]
                for key in (
                    "sigma_min",
                    "sigma_max",
                    "condition_max",
                    "area_min",
                    "area_max",
                    "area_p01",
                    "area_p99",
                    "edge_stretch_p05",
                    "edge_stretch_p95",
                )
            },
            {
                "sigma_min": 0.4356269491426868,
                "sigma_max": 1.6225781559159698,
                "condition_max": 2.435135276382128,
                "area_min": 0.46211766403766275,
                "area_max": 1.5526969937060449,
                "area_p01": 0.7859413722531491,
                "area_p99": 1.3244949151589778,
                "edge_stretch_p05": 0.9893953951197354,
                "edge_stretch_p95": 1.0270136679765456,
            },
        )
        zero_warp = report["gates"]["zero_warp"]
        self.assertEqual(zero_warp["status"], "zero_warp_drift_disclosed")
        self.assertTrue(zero_warp["direct_rest_rgba_exact"])
        self.assertFalse(zero_warp["same_renderer_zero_warp_rgba_exact"])
        self.assertEqual(zero_warp["zero_warp_max_rgba_error"], 255)
        self.assertEqual(zero_warp["alpha_changed_pixels"], 122011)
        self.assertEqual(zero_warp["alpha_max_difference"], 86)
        self.assertEqual(zero_warp["alpha_difference_gt_8_pixels"], 39766)
        g6 = report["gates"]["g6"]
        self.assertEqual(g6["raw_proxy_status"], "FAIL")
        self.assertEqual(g6["adjudication"], "invalid_proxy_not_used_for_stop")
        self.assertFalse(g6["used_for_stop"])

        self.assertEqual(
            report["causal_conclusion"]["prior_multilayer_interpenetration"],
            "important_contributing_factor_not_unique_root_cause",
        )
        self.assertEqual(
            report["final_disposition"]["status"],
            "plant_route_permanently_stopped",
        )
        self.assertFalse(report["final_disposition"]["further_parameter_tuning_allowed"])
        for field in (
            "hyperframes_project_created",
            "hyperframes_checks_run",
            "draft_video_created",
            "candidate_video_created",
            "second_parameter_revision",
            "compiled_generator_copied",
            "runtime_dependency_on_cache",
        ):
            self.assertFalse(report["artifact_boundary"][field], field)
        self.assertEqual(report["artifact_boundary"]["copied_action_state_png_count"], 0)

        self.assertFalse((ROUND2_ROOT / "revision-batch10").exists())
        self.assertFalse((ROUND2_FINAL_CAUSAL_ROOT / "generate_unified_mesh").exists())
        self.assertEqual(list(ROUND2_FINAL_CAUSAL_ROOT.rglob("state-*.png")), [])
        for relative in actual_files:
            self.assertNotIn(Path(relative).suffix.lower(), {".mp4", ".mov", ".webm"})
            self.assertFalse(
                any(token in relative.lower() for token in ("hyperframes", "draft", "candidate")),
                relative,
            )

    def test_plan07_final_user_gate_is_synchronized_across_current_docs(self) -> None:
        current_docs = (
            EXECUTION_RECORD,
            MOTION_FEASIBILITY,
            MOTION_PLAYBOOK,
            README,
            OVERALL_PLAN,
        )
        for path in current_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("CONDITIONAL", text, path)
            self.assertIn("manual_only", text, path)
            self.assertIn("user_rejected_due_to_ghosting", text, path)

        for path in (EXECUTION_RECORD, MOTION_FEASIBILITY, MOTION_PLAYBOOK, README):
            text = path.read_text(encoding="utf-8")
            self.assertIn("假阴性", text, path)
            self.assertIn("用户视觉门", text, path)
            self.assertIn("cancelled_due_to_failed_prerequisite", text, path)

        record = EXECUTION_RECORD.read_text(encoding="utf-8")
        for feedback in ("动作明显", "像一阵风", "明显重影"):
            self.assertIn(feedback, record)
        self.assertIn("automatic_batch10_forbidden=true", record)


if __name__ == "__main__":
    unittest.main()
