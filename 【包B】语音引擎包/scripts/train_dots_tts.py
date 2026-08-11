#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path

import torch
import yaml
from accelerate import Accelerator
from accelerate.utils import DistributedDataParallelKwargs, ProjectConfiguration
from torch.optim import AdamW
from transformers import get_cosine_schedule_with_warmup

from dots_tts.config import app as app_config
from dots_tts.data import builders as data_module
from dots_tts.models.dots_tts import model as dots_tts_model
from dots_tts.training import checkpoint as train_checkpoint
from dots_tts.training import losses as loss_ops
from dots_tts.training import utils as train_utils
from dots_tts.utils import util as util_module

_EMPTY_EPOCH_TOLERANCE = 32
_DEBUG_BATCH_LIMIT = 3
_DEBUG_GRAD_EARLY_STEP_LIMIT = 3


# region Training Step State
@dataclass(slots=True)
class _PreparedTrainingStep:
    micro_batches: list[dict]
    consumed_counts: list[int]
    global_denominators: dict[str, float]


@dataclass(slots=True)
class _AccumulatedTrainingStep:
    loss_totals: dict[str, float]
    loss_denominators: dict[str, float]
    source_loss_totals: dict[str, dict[str, float]]
    source_loss_denominators: dict[str, dict[str, float]]
    completed_optimizer_step: bool
    grad_norm: torch.Tensor | None


@dataclass(slots=True)
class _CompletedTrainingStep:
    reduced_metrics: dict[str, float]
    learning_rate: float
    grad_norm_value: float

# endregion Training Step State

class DotsTtsTrainingRun:
    # region Lifecycle
    def __init__(self, cfg: app_config.AppConfig, *, debug_enabled: bool = False):
        self.cfg = cfg
        self.progress = train_utils.TrainProgress()
        self.max_train_steps = int(cfg.train.max_train_steps)
        self.grad_accumulation_steps = int(cfg.train.gradient_accumulation_steps)
        self.last_validation_step: int | None = None
        self.consecutive_empty_epochs = 0
        self.saved_latest_checkpoint = False
        self._last_log_step = 0
        self._last_log_time = 0.0
        self._debug_enabled = bool(debug_enabled)
        self._debug_batch_count = 0
        self._debug_audio_sample_rate = int(self.cfg.train_data.train_audio_sample_rate)

        project_config = ProjectConfiguration(
            project_dir=self.cfg.train.output_dir,
            total_limit=self.cfg.train.max_checkpoints_to_keep,
        )
        ddp_kwargs = DistributedDataParallelKwargs(find_unused_parameters=False)
        self.accelerator = Accelerator(
            kwargs_handlers=[ddp_kwargs],
            gradient_accumulation_steps=self.grad_accumulation_steps,
            log_with="tensorboard",
            project_config=project_config,
            step_scheduler_with_optimizer=False,
        )

        util_module.seed_everything(self.cfg.train.seed)

        model = dots_tts_model.DotsTtsModel.from_pretrained(
            self.cfg.train.pretrained_model_path
        )
        # model.set_cfg_droprate(
        #     cfg_droprate=self.cfg.train.cfg_droprate,
        #     xvec_drop_rate=self.cfg.train.xvec_drop_rate,
        # )
        optimizer = AdamW(
            (param for param in model.parameters() if param.requires_grad),
            lr=self.cfg.train.learning_rate,
            weight_decay=self.cfg.train.weight_decay,
        )
        scheduler = get_cosine_schedule_with_warmup(
            optimizer,
            num_warmup_steps=self.cfg.train.warmup_steps,
            num_training_steps=self.max_train_steps,
        )
        self.model, self.optimizer, self.scheduler = self.accelerator.prepare(
            model,
            optimizer,
            scheduler,
        )
        self.unwrapped_model = self.accelerator.unwrap_model(self.model)
        expected_sample_rate = int(self.unwrapped_model.config.vocoder.sample_rate)
        expected_audio_samples_per_llm_token = (
            int(self.unwrapped_model.hop_size) * int(self.unwrapped_model.config.patch_size)
        )
        if int(self.cfg.train_data.train_audio_sample_rate) != expected_sample_rate:
            raise ValueError(
                f"train_data.train_audio_sample_rate={int(self.cfg.train_data.train_audio_sample_rate)} "
                f"does not match the pretrained model sample rate {expected_sample_rate}."
            )
        if (
            int(self.cfg.train_data.audio_samples_per_llm_token)
            != expected_audio_samples_per_llm_token
        ):
            raise ValueError(
                "train_data.audio_samples_per_llm_token="
                f"{int(self.cfg.train_data.audio_samples_per_llm_token)} "
                "does not match the pretrained model audio token contract "
                f"{expected_audio_samples_per_llm_token}."
            )
        if self.cfg.val_data is not None:
            if int(self.cfg.val_data.train_audio_sample_rate) != expected_sample_rate:
                raise ValueError(
                    f"val_data.train_audio_sample_rate={int(self.cfg.val_data.train_audio_sample_rate)} "
                    f"does not match the pretrained model sample rate {expected_sample_rate}."
                )
            if (
                int(self.cfg.val_data.audio_samples_per_llm_token)
                != expected_audio_samples_per_llm_token
            ):
                raise ValueError(
                    "val_data.audio_samples_per_llm_token="
                    f"{int(self.cfg.val_data.audio_samples_per_llm_token)} "
                    "does not match the pretrained model audio token contract "
                    f"{expected_audio_samples_per_llm_token}."
                )

        if self.accelerator.is_main_process:
            total_params = sum(param.numel() for param in self.unwrapped_model.parameters())
            trainable_params = sum(
                param.numel()
                for param in self.unwrapped_model.parameters()
                if param.requires_grad
            )
            self.accelerator.print(f"Total parameters: {total_params:,}")
            self.accelerator.print(f"Trainable parameters: {trainable_params:,}")
            self.accelerator.print(
                f"Distributed type: {self.accelerator.distributed_type}"
            )

        tokenizer = self.unwrapped_model.tokenizer
        self.tokenizer = tokenizer
        train_dataset = data_module.build_training_dataset(
            self.cfg.train_data,
            tokenizer=tokenizer,
            seed=int(self.cfg.train.seed),
            accelerator=self.accelerator,
        )
        self.train_loader = data_module.build_training_dataloader(
            train_dataset,
            self.cfg.train_data,
            tokenizer=tokenizer,
        )

        self.val_loader = None
        if (
            self.cfg.train.eval_interval is not None
            or self.cfg.train.run_eval_on_start
        ):
            if self.cfg.val_data is None:
                raise ValueError(
                    "Validation requires val_data when eval_interval or "
                    "run_eval_on_start is enabled."
                )
            validation_data_cfg = self.cfg.val_data.model_copy(deep=True)
            validation_data_cfg.num_tokens_per_epoch = None
            val_dataset = data_module.build_validation_dataset(
                validation_data_cfg,
                tokenizer=tokenizer,
                seed=int(self.cfg.train.seed),
                accelerator=self.accelerator,
            )
            self.val_loader = data_module.build_validation_dataloader(
                val_dataset,
                validation_data_cfg,
                tokenizer=tokenizer,
            )

        self._resume_if_available()
        self.train_loader.set_epoch(self.progress.epoch)

    def run(self) -> int:
        self.accelerator.init_trackers("dots_tts")
        self._write_run_config()
        self.optimizer.zero_grad(set_to_none=True)

        try:
            if self.cfg.train.run_eval_on_start:
                self._run_validation()
                self.last_validation_step = self.progress.global_step

            self._last_log_step = self.progress.global_step
            self._last_log_time = time.perf_counter()

            while self.progress.global_step < self.max_train_steps:
                self._run_training_step()

            if (
                self.cfg.train.eval_interval is not None
                and self.val_loader is not None
                and self.progress.global_step > 0
                and self.last_validation_step != self.progress.global_step
            ):
                self._run_validation()

            if not self.saved_latest_checkpoint:
                self._save_checkpoint(float(self.optimizer.param_groups[0]["lr"]))
            return 0
        finally:
            try:
                self._close_data_streams()
            finally:
                self.accelerator.end_training()

    def _write_run_config(self) -> None:
        if not bool(getattr(self.accelerator, "is_main_process", True)):
            return
        output_dir = Path(self.cfg.train.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        config_path = output_dir / "config.yml"
        with config_path.open("w", encoding="utf-8") as fout:
            yaml.safe_dump(
                self.cfg.to_dict(),
                fout,
                sort_keys=False,
                allow_unicode=True,
            )

    def _close_data_streams(self) -> None:
        for loader_name in ("train_loader", "val_loader"):
            loader = getattr(self, loader_name, None)
            close = getattr(loader, "close", None)
            if callable(close):
                close()
            setattr(self, loader_name, None)

    def _resume_if_available(self) -> None:
        try:
            resume_dir = train_checkpoint.resolve_latest_train_checkpoint(
                self.cfg.train.output_dir
            )
        except FileNotFoundError:
            return

        resume_state = train_checkpoint.load_train_checkpoint(
            self.accelerator,
            self.model,
            self.optimizer,
            self.progress,
            resume_dir,
            self.scheduler,
        )
        saved_max_train_steps = int(resume_state["scheduler_state"]["max_train_steps"])
        if saved_max_train_steps != self.max_train_steps:
            self.accelerator.print(
                "Warning: resumed scheduler was saved with "
                f"max_train_steps={saved_max_train_steps}, but current run uses "
                f"{self.max_train_steps}."
            )

        self.train_loader.load_state_dict(resume_state["data_state"])
        self.accelerator.print(
            "Resumed training from "
            f"{resume_dir} at step {self.progress.global_step}. "
            "Restored committed data state. "
            "In-memory prefetch and batching state is rebuilt on restart, so only "
            "committed sample progress is resumed."
        )
    # endregion Lifecycle

    # region Training Step Pipeline
    def _run_training_step(self) -> None:
        try:
            self.model.train()
            # Stage 1: collect one synchronized accumulation window and its
            # normalization factors before touching model state.
            prepared_step = self._prepare_training_step()

            # Stage 2: run forward/backward over the prepared micro-batches and
            # accumulate overall/source statistics for the completed optimizer step.
            accumulated_step = self._accumulate_training_step(prepared_step)

            # Stage 3: advance counters, reduce metrics, then trigger side effects
            # (logging, validation, checkpointing) only after a real optimizer step.
            self._apply_consumed_counts(prepared_step.consumed_counts)
            if not accumulated_step.completed_optimizer_step:
                return
            completed_step = self._finalize_completed_training_step(accumulated_step)
            if train_utils.should_log_training_step(
                self.progress.global_step,
                int(self.cfg.train.log_interval),
            ):
                reduced_by_source = train_utils.reduce_source_metrics(
                    accumulated_step.source_loss_totals,
                    accumulated_step.source_loss_denominators,
                    device=self.accelerator.device,
                    loss_config=self.cfg.loss,
                )
                current_time = time.perf_counter()
                report = train_utils.build_train_step_report(
                    completed_step.reduced_metrics,
                    learning_rate=completed_step.learning_rate,
                    grad_norm=completed_step.grad_norm_value,
                    current_time=current_time,
                    last_log_step=self._last_log_step,
                    last_log_time=self._last_log_time,
                    progress=self.progress,
                    max_train_steps=self.max_train_steps,
                    reduced_by_source=reduced_by_source,
                )
                self.accelerator.log(
                    report.log_values,
                    step=self.progress.global_step,
                )
                self.accelerator.print(report.console_line)
                self._last_log_step = self.progress.global_step
                self._last_log_time = current_time

            if (
                self.cfg.train.eval_interval is not None
                and self.progress.global_step % self.cfg.train.eval_interval == 0
            ):
                self._run_validation()
                self.last_validation_step = self.progress.global_step

            if self.progress.global_step % self.cfg.train.save_interval == 0:
                self._save_checkpoint(completed_step.learning_rate)
                self.saved_latest_checkpoint = True
        except BaseException as exc:
            train_utils.abort_on_out_of_memory(
                exc,
                stage="train",
                batch=None,
                progress=self.progress,
                device=self.accelerator.device,
                process_index=int(getattr(self.accelerator, "process_index", 0)),
                num_processes=int(getattr(self.accelerator, "num_processes", 1)),
            )
            raise

    def _prepare_training_step(self) -> _PreparedTrainingStep:
        micro_batches: list[dict] = []
        local_denominators: dict[str, float] = {}

        while len(micro_batches) < self.grad_accumulation_steps:
            batch, has_batch = self.train_loader.peek_batch()
            if train_utils.any_rank_true(not has_batch, device=self.accelerator.device):
                self._advance_epoch_after_empty_batch(has_local_batch=has_batch)
                continue

            self.consecutive_empty_epochs = 0
            self.train_loader.commit_batch()
            prepared_batch = self.unwrapped_model.prepare_training_batch(batch)
            self._maybe_debug_training_batch(prepared_batch)
            batch_denominators = loss_ops.to_host_named_scalars(
                loss_ops.collapse_loss_masks(prepared_batch["loss_masks"])
            )
            if not local_denominators:
                local_denominators = {name: 0.0 for name in batch_denominators}
            loss_ops.accumulate_named_scalars_(local_denominators, batch_denominators)
            micro_batches.append(prepared_batch)

        consumed_counts = train_utils.sum_integer_counters_across_ranks(
            [
                sum(int(batch["input_ids_lengths"].sum().item()) for batch in micro_batches),
                sum(int(batch["num_audio_tokens"].sum().item()) for batch in micro_batches),
                sum(int(batch["num_text_tokens"].sum().item()) for batch in micro_batches),
            ],
            device=self.accelerator.device,
        )
        global_denominators = loss_ops.sum_named_scalars_across_ranks(
            local_denominators,
            device=self.accelerator.device,
        )
        return _PreparedTrainingStep(
            micro_batches=micro_batches,
            consumed_counts=consumed_counts,
            global_denominators=global_denominators,
        )

    def _advance_epoch_after_empty_batch(self, *, has_local_batch: bool) -> None:
        if has_local_batch:
            self.train_loader.discard_batch()
        self.progress.epoch += 1
        self.train_loader.set_epoch(self.progress.epoch)
        self.consecutive_empty_epochs += 1
        if self.consecutive_empty_epochs > _EMPTY_EPOCH_TOLERANCE:
            raise RuntimeError(
                "Unable to obtain a synchronized training batch across ranks. "
                "Check shard assignment, dataset size, and filtering constraints."
            )

    def _accumulate_training_step(
        self,
        prepared_step: _PreparedTrainingStep,
    ) -> _AccumulatedTrainingStep:
        accumulated_loss_totals: dict[str, float] = {}
        accumulated_loss_denominators: dict[str, float] = {}
        accumulated_source_loss_totals: dict[str, dict[str, float]] = {}
        accumulated_source_loss_denominators: dict[str, dict[str, float]] = {}
        completed_optimizer_step = False
        grad_norm = None

        for batch in prepared_step.micro_batches:
            batch = train_utils.move_to_device(batch, self.accelerator.device)
            with self.accelerator.accumulate(self.model):
                with self.accelerator.autocast():
                    loss_terms = self.model(batch)
                    loss = loss_ops.compute_gradient_loss(
                        loss_terms,
                        global_normalizers=prepared_step.global_denominators,
                        loss_config=self.cfg.loss,
                        ddp_world_size=int(self.accelerator.num_processes),
                        gradient_accumulation_steps=self.grad_accumulation_steps,
                    )

                batch_loss_totals, batch_loss_denominators = (
                    loss_ops.collapse_loss_terms(loss_terms)
                )
                batch_loss_totals = loss_ops.to_host_named_scalars(batch_loss_totals)
                batch_loss_denominators = loss_ops.to_host_named_scalars(
                    batch_loss_denominators
                )
                if not accumulated_loss_totals:
                    accumulated_loss_totals = {name: 0.0 for name in batch_loss_totals}
                    accumulated_loss_denominators = {
                        name: 0.0 for name in batch_loss_denominators
                    }
                loss_ops.accumulate_named_scalars_(
                    accumulated_loss_totals,
                    batch_loss_totals,
                )
                loss_ops.accumulate_named_scalars_(
                    accumulated_loss_denominators,
                    batch_loss_denominators,
                )

                batch_source_totals, batch_source_denominators = (
                    loss_ops.collapse_loss_terms_by_source(
                        loss_terms,
                        source_names=batch["source_names"],
                    )
                )
                loss_ops.accumulate_grouped_named_scalars_(
                    accumulated_source_loss_totals,
                    batch_source_totals,
                )
                loss_ops.accumulate_grouped_named_scalars_(
                    accumulated_source_loss_denominators,
                    batch_source_denominators,
                )

                self.accelerator.backward(loss)
                if self.accelerator.sync_gradients:
                    grad_norm = self.accelerator.clip_grad_norm_(
                        self.model.parameters(),
                        self.cfg.train.grad_clip_norm,
                    )
                    self._maybe_print_gradient_debug(grad_norm)
                    self.optimizer.step()
                    completed_optimizer_step = (
                        not self.accelerator.optimizer_step_was_skipped
                    )
                    if completed_optimizer_step:
                        self.scheduler.step()
                    self.optimizer.zero_grad(set_to_none=True)
            batch.clear()

        return _AccumulatedTrainingStep(
            loss_totals=accumulated_loss_totals,
            loss_denominators=accumulated_loss_denominators,
            source_loss_totals=accumulated_source_loss_totals,
            source_loss_denominators=accumulated_source_loss_denominators,
            completed_optimizer_step=completed_optimizer_step,
            grad_norm=grad_norm,
        )

    def _apply_consumed_counts(self, consumed_counts: list[int]) -> None:
        self.progress.total_tokens += consumed_counts[0]
        self.progress.audio_tokens += consumed_counts[1]
        self.progress.text_tokens += consumed_counts[2]

    def _finalize_completed_training_step(
        self,
        accumulated_step: _AccumulatedTrainingStep,
    ) -> _CompletedTrainingStep:
        if not accumulated_step.loss_totals or not accumulated_step.loss_denominators:
            raise RuntimeError("Training step produced no accumulated loss totals.")
        if all(
            float(value) == 0.0 for value in accumulated_step.loss_denominators.values()
        ):
            raise RuntimeError("Accumulated training step produced no loss statistics.")

        self.progress.global_step += 1
        self.saved_latest_checkpoint = False

        reduced_totals = loss_ops.sum_named_scalars_across_ranks(
            accumulated_step.loss_totals,
            device=self.accelerator.device,
        )
        reduced_denominators = loss_ops.sum_named_scalars_across_ranks(
            accumulated_step.loss_denominators,
            device=self.accelerator.device,
        )
        reduced_metrics = loss_ops.reduce_loss_statistics(
            reduced_totals,
            reduced_denominators,
            loss_config=self.cfg.loss,
        )
        learning_rate = float(self.optimizer.param_groups[0]["lr"])
        grad_norm_value = (
            math.nan
            if accumulated_step.grad_norm is None
            else float(accumulated_step.grad_norm.detach().float().item())
        )
        return _CompletedTrainingStep(
            reduced_metrics=reduced_metrics,
            learning_rate=learning_rate,
            grad_norm_value=grad_norm_value,
        )
    # endregion Training Step Pipeline

    # region Validation
    def _run_validation(self) -> None:
        try:
            if self.val_loader is None:
                raise ValueError(
                    "Validation requested, but validation loader was not initialized."
                )
            self.val_loader.set_epoch(0)

            was_training = bool(self.model.training)
            self.model.eval()

            overall_loss_totals = None
            overall_loss_denominators = None
            source_loss_totals: dict[str, dict[str, float]] = {}
            source_loss_denominators: dict[str, dict[str, float]] = {}
            processed_batches = 0

            # Collect rank-local partial sums using the same batch preparation and
            # loss aggregation path as training.
            with torch.no_grad():
                for batch_idx, batch in enumerate(self.val_loader):
                    if (
                        self.cfg.train.max_eval_batches is not None
                        and batch_idx >= self.cfg.train.max_eval_batches
                    ):
                        break

                    batch = self.unwrapped_model.prepare_training_batch(batch)
                    batch = train_utils.move_to_device(batch, self.accelerator.device)

                    with self.accelerator.autocast():
                        loss_terms = self.model(batch)

                    batch_loss_totals, batch_loss_denominators = (
                        loss_ops.collapse_loss_terms(loss_terms)
                    )
                    batch_loss_totals = loss_ops.to_host_named_scalars(batch_loss_totals)
                    batch_loss_denominators = loss_ops.to_host_named_scalars(
                        batch_loss_denominators
                    )
                    if overall_loss_totals is None:
                        overall_loss_totals = {name: 0.0 for name in batch_loss_totals}
                        overall_loss_denominators = {
                            name: 0.0 for name in batch_loss_denominators
                        }
                    loss_ops.accumulate_named_scalars_(
                        overall_loss_totals,
                        batch_loss_totals,
                    )
                    loss_ops.accumulate_named_scalars_(
                        overall_loss_denominators,
                        batch_loss_denominators,
                    )

                    batch_source_totals, batch_source_denominators = (
                        loss_ops.collapse_loss_terms_by_source(
                            loss_terms,
                            source_names=batch["source_names"],
                        )
                    )
                    loss_ops.accumulate_grouped_named_scalars_(
                        source_loss_totals,
                        batch_source_totals,
                    )
                    loss_ops.accumulate_grouped_named_scalars_(
                        source_loss_denominators,
                        batch_source_denominators,
                    )
                    processed_batches += 1

            # Merge rank-local partial sums with tensor reductions only. Validation
            # runs close to the training memory ceiling, so object collectives are
            # not acceptable here because NCCL materializes pickled payloads on GPU.
            processed_batches = train_utils.sum_integer_counters_across_ranks(
                [processed_batches],
                device=self.accelerator.device,
            )[0]
            overall_loss_totals = loss_ops.sum_named_scalars_across_ranks(
                overall_loss_totals or {},
                device=self.accelerator.device,
            )
            overall_loss_denominators = loss_ops.sum_named_scalars_across_ranks(
                overall_loss_denominators or {},
                device=self.accelerator.device,
            )
            source_loss_totals = loss_ops.sum_grouped_named_scalars_across_ranks(
                source_loss_totals,
                device=self.accelerator.device,
            )
            source_loss_denominators = (
                loss_ops.sum_grouped_named_scalars_across_ranks(
                    source_loss_denominators,
                    device=self.accelerator.device,
                )
            )

            if processed_batches <= 0:
                raise RuntimeError(
                    "Validation produced no batches. Check validation data configuration."
                )
            if not overall_loss_totals or not overall_loss_denominators:
                raise RuntimeError("Validation produced no aggregate loss totals.")

            reduced_metrics = loss_ops.reduce_loss_statistics(
                overall_loss_totals,
                overall_loss_denominators,
                loss_config=self.cfg.loss,
            )
            reduced_by_source = loss_ops.reduce_loss_statistics_by_source(
                source_loss_totals,
                source_loss_denominators,
                loss_config=self.cfg.loss,
            )

            if was_training:
                self.model.train()

            self.accelerator.log(
                train_utils.build_validation_log_dict(
                    reduced_metrics,
                    reduced_by_source=reduced_by_source,
                ),
                step=self.progress.global_step,
            )
            self.accelerator.print(
                train_utils.format_validation_line(
                    reduced_metrics,
                    global_step=self.progress.global_step,
                    reduced_by_source=reduced_by_source,
                )
            )
        except BaseException as exc:
            train_utils.abort_on_out_of_memory(
                exc,
                stage="validation",
                batch=None,
                progress=self.progress,
                device=self.accelerator.device,
                process_index=int(getattr(self.accelerator, "process_index", 0)),
                num_processes=int(getattr(self.accelerator, "num_processes", 1)),
            )
            raise
    # endregion Validation

    # region Checkpointing
    def _save_checkpoint(self, learning_rate: float) -> None:
        train_checkpoint.save_train_checkpoint(
            self.accelerator,
            self.model,
            self.optimizer,
            self.progress,
            self.cfg.train.output_dir,
            self.cfg.train.max_checkpoints_to_keep,
            self.train_loader.state_dict(),
            {
                "type": "transformers_cosine_with_warmup",
                "global_step": int(self.progress.global_step),
                "base_lr": float(self.cfg.train.learning_rate),
                "current_lr": float(learning_rate),
                "warmup_steps": int(self.cfg.train.warmup_steps),
                "max_train_steps": int(self.max_train_steps),
                "state_dict": self.scheduler.state_dict(),
            },
        )
    # endregion Checkpointing

    # region Debug Logging
    def _maybe_debug_training_batch(self, batch: dict[str, object]) -> None:
        if not bool(getattr(self, "_debug_enabled", False)):
            return
        if not bool(getattr(self.accelerator, "is_main_process", True)):
            return
        if self._debug_batch_count >= _DEBUG_BATCH_LIMIT:
            return

        batch_index = self._debug_batch_count
        self._debug_batch_count += 1
        for line in train_utils.build_data_debug_lines(
            batch,
            batch_index=batch_index,
            tokenizer=self.tokenizer,
            sample_rate=self._debug_audio_sample_rate,
        ):
            self.accelerator.print(line)

    def _maybe_print_gradient_debug(self, grad_norm: torch.Tensor | None) -> None:
        if grad_norm is None:
            return
        if not train_utils.should_print_gradient_debug(
            debug_enabled=bool(getattr(self, "_debug_enabled", False)),
            is_main_process=bool(getattr(self.accelerator, "is_main_process", True)),
            next_global_step=self.progress.global_step + 1,
            log_interval=int(self.cfg.train.log_interval),
            early_step_limit=_DEBUG_GRAD_EARLY_STEP_LIMIT,
        ):
            return
        for line in train_utils.build_gradient_debug_lines(
            self.unwrapped_model,
            global_step=self.progress.global_step + 1,
            grad_norm=float(grad_norm.detach().float().item()),
            grad_clip_norm=float(self.cfg.train.grad_clip_norm),
        ):
            self.accelerator.print(line)
    # endregion Debug Logging


# region CLI
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Accelerate training entrypoint for dots.tts."
    )
    parser.add_argument("--config", default=app_config.DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print training debug information.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    return DotsTtsTrainingRun(
        app_config.load_config(args.config),
        debug_enabled=args.debug,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
# endregion CLI
