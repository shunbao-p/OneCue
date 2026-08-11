from __future__ import annotations

from pydantic import Field

from dots_tts.config.base import StrictConfigBase


class TrainConfig(StrictConfigBase):
    pretrained_model_path: str
    output_dir: str
    seed: int = 42
    learning_rate: float
    cfg_droprate: float = 0.0
    xvec_drop_rate: float = 0.5
    weight_decay: float = 0.01
    warmup_steps: int = 0
    max_train_steps: int
    gradient_accumulation_steps: int = Field(default=1, ge=1)
    grad_clip_norm: float = 1.0
    save_interval: int = Field(default=1000, ge=1)
    max_checkpoints_to_keep: int = 10
    log_interval: int = Field(default=10, ge=1)
    eval_interval: int | None = Field(default=None, ge=1)
    max_eval_batches: int | None = None
    run_eval_on_start: bool = False


__all__ = ["TrainConfig"]
