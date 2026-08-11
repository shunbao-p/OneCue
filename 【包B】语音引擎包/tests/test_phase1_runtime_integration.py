from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
for import_root in (PACKAGE_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

try:
    import torch
    from apps.gradio.service import GradioAppService, build_gradio_app_config
    from dots_tts.runtime import DotsTtsRuntime
except ImportError as exc:  # Local review hosts may intentionally have no ML runtime.
    torch = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"ML dependencies unavailable: {IMPORT_ERROR}")
class RuntimeIntegrationTests(unittest.TestCase):
    def test_runtime_cpu_auto_uses_float32_without_model_weights(self):
        class Core:
            def __init__(self):
                self.dtype = None

            def to(self, *, dtype):
                self.dtype = dtype
                return self

        class Model:
            def __init__(self):
                self.core = Core()
                self.config = type(
                    "Config",
                    (),
                    {"vocoder": type("Vocoder", (), {"sample_rate": 48000})()},
                )()
                self.device = None
                self.optimize = None

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                return self

            def set_optimize(self, enabled):
                self.optimize = enabled

        model = Model()
        runtime = DotsTtsRuntime(
            model,
            Path("/tmp/no-model-load"),
            device="cpu",
            precision="auto",
            optimize=False,
        )
        self.assertEqual(runtime.device.type, "cpu")
        self.assertEqual(runtime.precision, "float32")
        self.assertIs(model.core.dtype, torch.float32)
        self.assertFalse(model.optimize)

    def test_gradio_passes_device_precision_and_optimize_to_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "pretrained_models" / "dots-tts-mf"
            prompts = root / "prompts"
            model.mkdir(parents=True)
            prompts.mkdir()
            (model / "config.json").write_text(json.dumps({"meanflow": {"enabled": True}}))
            config = build_gradio_app_config(
                repo_root=root,
                prompts_dir=prompts,
                prompt_source_dir=prompts,
                model_name_or_path=str(model),
                output_dir=root / "outputs",
                device="mps",
                precision="float32",
                optimize=False,
            )
            fake_runtime = mock.Mock()
            with mock.patch.object(
                DotsTtsRuntime, "from_pretrained", return_value=fake_runtime
            ) as loader:
                service = GradioAppService(config)
                loaded, _ = service._get_runtime(str(model))
            self.assertIs(loaded, fake_runtime)
            loader.assert_called_once_with(
                str(model.resolve()),
                device="mps",
                precision="float32",
                optimize=False,
                max_generate_length=config.max_generate_length,
            )


if __name__ == "__main__":
    unittest.main()
