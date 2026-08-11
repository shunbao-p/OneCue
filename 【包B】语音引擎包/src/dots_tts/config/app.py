from __future__ import annotations

from pathlib import Path

import yaml

from dots_tts.config.base import StrictConfigBase
from dots_tts.config.data import DataConfig
from dots_tts.config.train import TrainConfig
from dots_tts.models.dots_tts.config import LossConfig

DEFAULT_CONFIG_PATH = "configs/dots_tts.yaml"


class AppConfig(StrictConfigBase):
    train_data: DataConfig
    val_data: DataConfig | None = None
    loss: LossConfig
    train: TrainConfig

    @classmethod
    def from_yaml(cls, config_path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
        with Path(config_path).open(encoding="utf-8") as fin:
            raw_config = yaml.safe_load(fin)
        return cls.model_validate(raw_config)


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    return AppConfig.from_yaml(config_path)


__all__ = ["AppConfig", "DEFAULT_CONFIG_PATH", "load_config"]
