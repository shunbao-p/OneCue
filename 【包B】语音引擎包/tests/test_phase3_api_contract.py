from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
for item in (PACKAGE_ROOT, PACKAGE_ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from apps.gradio import api_contract as contract


class Result:
    audio_path = "/tmp/out.wav"
    status = "完成"
    metrics = {
        "resolved_model_name_or_path": "dots-tts-mf",
        "device_policy": {"actual_device": "mps", "actual_precision": "float32"},
    }


class ContractTests(unittest.TestCase):
    def test_speed_processing_falls_back_to_bundled_ffmpeg(self):
        source = (PACKAGE_ROOT / "apps/gradio/service.py").read_text(encoding="utf-8")
        method = source[
            source.index("    def _apply_speed("):
            source.index("    @staticmethod\n    def _compress_silence", source.index("    def _apply_speed("))
        ]
        self.assertIn('"rubberband",', method)
        self.assertIn("required=False", method)
        self.assertIn('"ffmpeg",', method)
        self.assertIn('f"atempo={speed:.4f}"', method)

    def test_version_name_fields_and_defaults_are_fixed(self):
        self.assertEqual(contract.API_VERSION, "dots-tts.synthesize.v1")
        self.assertEqual(contract.API_NAME, "/synthesize_v1")
        self.assertEqual(contract.REQUEST_PARAMETER, "request")
        result = contract.normalize_request({"text": " 测试 "})
        self.assertEqual(result["text"], "测试")
        for key, value in contract.REQUEST_DEFAULTS.items():
            self.assertEqual(result[key], value)

    def test_invalid_and_unknown_inputs_have_stable_codes(self):
        cases = [
            (None, "invalid_request"),
            ({"text": ""}, "invalid_text"),
            ({"text": "x", "surprise": 1}, "unknown_field"),
            ({"text": "x", "num_steps": 1.5}, "invalid_type"),
            ({"text": "x", "speed": 3}, "out_of_range"),
            ({"text": "x", "prompt_audio_path": "/tmp/a.wav"}, "missing_prompt_text"),
        ]
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(contract.ContractError) as caught:
                contract.normalize_request(payload)
            self.assertEqual(caught.exception.code, code)

    def test_success_and_error_envelopes_are_versioned(self):
        metadata = {
            "default_model_name_or_path": "dots-tts-mf",
            "loaded_model_name_or_path": "dots-tts-mf",
            "configured_device": "auto",
            "loaded_device": "mps",
            "configured_precision": "auto",
            "loaded_precision": "float32",
        }
        success = contract.success_response(Result(), metadata)
        self.assertTrue(success["ok"])
        self.assertEqual(success["api_version"], contract.API_VERSION)
        self.assertEqual(success["device"]["loaded"], "mps")
        failure = contract.error_response(contract.ContractError("bad", "broken"))
        self.assertEqual(failure["error"], {"code": "bad", "message": "broken"})
        unexpected = contract.error_response(RuntimeError("boom"))
        self.assertEqual(unexpected["error"]["code"], "synthesis_failed")

    def test_launcher_state_version_matches_api_contract(self):
        path = PACKAGE_ROOT / "_internal" / "macos_launcher.py"
        spec = importlib.util.spec_from_file_location("phase3_launcher", path)
        launcher = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(launcher)
        self.assertEqual(launcher.API_VERSION, contract.API_VERSION)

    def test_fake_service_handler_maps_success_and_exception(self):
        from apps.gradio.app import make_synthesize_v1_handler

        config = mock.Mock(
            default_model_name_or_path="dots-tts-mf",
            execution_mode="generate",
            default_speaker_scale=1.0,
            default_num_steps=4,
        )
        service = mock.Mock()
        service.generate.return_value = Result()
        service.metadata.return_value = {"configured_device": "auto"}
        request_type = mock.Mock()
        handler = make_synthesize_v1_handler(config, service, request_type)
        audio, payload = handler({"text": "测试"})
        self.assertEqual(audio, "/tmp/out.wav")
        self.assertTrue(payload["ok"])
        self.assertEqual(request_type.call_args.kwargs["num_steps"], 4)
        handler({"text": "测试", "num_steps": 10})
        self.assertEqual(request_type.call_args.kwargs["num_steps"], 10)
        service.generate.side_effect = RuntimeError("fake failure")
        audio, payload = handler({"text": "测试"})
        self.assertIsNone(audio)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "synthesis_failed")

    def test_real_gradio_api_info_exposes_exact_v1_shape_when_available(self):
        try:
            import gradio as gr
            from apps.gradio.app import build_demo
            from apps.gradio.service import GradioAppConfig
        except ImportError as exc:
            self.skipTest(f"当前环境无 Gradio runtime: {exc}")
        config = GradioAppConfig(
            host="127.0.0.1", port=7860, execution_mode="generate",
            device="auto", precision="auto", optimize=False,
            output_dir=PACKAGE_ROOT / "tmp", prompts_dir=PACKAGE_ROOT / "pretrained_models" / "prompts",
            output_retention_count=2, max_generate_length=8192,
            default_model_name_or_path="dots-tts-mf", prompt_presets=(),
            default_prompt_name="__none__", default_prompt_audio_path=None,
            default_prompt_text="", default_precision="auto", default_num_steps=10,
            default_guidance_scale=1.2, default_speaker_scale=1.0,
            default_max_generate_length=8192, local_model_choices=("dots-tts-mf",),
            repo_root=PACKAGE_ROOT,
        )
        service = mock.Mock()
        service.list_prompt_presets.return_value = ()
        service.metadata.return_value = {}
        demo = build_demo(gr, config, service)
        info = demo.get_api_info()
        endpoint = info["named_endpoints"][contract.API_NAME]
        names = tuple(item["parameter_name"] for item in endpoint["parameters"])
        self.assertEqual(names, (contract.REQUEST_PARAMETER,))
        self.assertEqual(len(endpoint["returns"]), 2)


if __name__ == "__main__":
    unittest.main()
