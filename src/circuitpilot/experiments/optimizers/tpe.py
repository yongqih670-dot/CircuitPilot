"""Optuna TPESampler adapter for the common CircuitPilot ask/tell interface."""

from __future__ import annotations

import base64
from dataclasses import asdict
import pickle
from pathlib import Path
from typing import Any, Mapping

import optuna
from optuna.samplers import TPESampler
from optuna.trial import Trial, TrialState

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig, ParameterType, ParameterValue
from circuitpilot.experiments.optimizers.base import (
    Optimizer, OptimizerFeedback, read_json_state, state_signature,
    validate_feedback, write_json_state,
)
from circuitpilot.experiments.seeding import SeedContext


class TPEOptimizer(Optimizer):
    """Optuna TPE with failures represented as failed trials, never penalties."""

    STATE_SCHEMA_VERSION = 1

    def __init__(self, config: ExperimentConfig, seed_context: SeedContext) -> None:
        if config.method != "tpe":
            raise ValueError("TPEOptimizer requires method='tpe'")
        self._config = config
        self._seed = seed_context.registry.optuna_sampler
        self._startup = int(config.optimizer_config["n_startup_trials"])
        self._multivariate = bool(config.optimizer_config["multivariate"])
        self._study = self._new_study()
        self._pending_trial: Trial | None = None
        self._pending: dict[str, ParameterValue] | None = None
        self._phase = "initialization"
        self._history: list[OptimizerFeedback] = []

    def _new_study(self) -> optuna.study.Study:
        sampler = TPESampler(
            seed=self._seed,
            n_startup_trials=self._startup,
            multivariate=self._multivariate,
        )
        return optuna.create_study(direction="minimize", sampler=sampler)

    def ask(self) -> dict[str, ParameterValue]:
        if self._pending is not None:
            raise ResearchExperimentError("optimizer.ask called before previous tell")
        trial = self._study.ask()
        candidate: dict[str, ParameterValue] = {}
        for definition in self._config.search_space:
            if definition.parameter_type is ParameterType.CATEGORICAL:
                value = trial.suggest_categorical(definition.name, list(definition.choices))
            elif definition.parameter_type is ParameterType.INTEGER:
                assert definition.low is not None and definition.high is not None
                value = trial.suggest_int(definition.name, int(definition.low), int(definition.high), log=definition.log)
            else:
                assert definition.low is not None and definition.high is not None
                value = trial.suggest_float(definition.name, definition.low, definition.high, log=definition.log)
            candidate[definition.name] = value
        self._phase = "initialization" if len(self._study.trials) <= self._startup else "model_based"
        self._pending_trial = trial
        self._pending = candidate
        return dict(candidate)

    def tell(self, parameters: Mapping[str, ParameterValue], metrics: Mapping[str, float], objective: float | None, simulation_status: str) -> None:
        feedback = validate_feedback(self._pending, parameters, metrics, objective, simulation_status)
        if self._pending_trial is None:
            raise ResearchExperimentError("TPE trial is missing for pending candidate")
        if feedback.simulation_status == "success" and feedback.objective is not None:
            self._study.tell(self._pending_trial, feedback.objective)
        else:
            self._study.tell(self._pending_trial, state=TrialState.FAIL)
        self._history.append(feedback)
        self._pending_trial = None
        self._pending = None

    def get_last_ask_metadata(self) -> dict[str, str]:
        return {"optimizer_phase": self._phase}

    def save_state(self, path: str | Path) -> Path:
        if self._pending_trial is not None:
            raise ResearchExperimentError("TPE state may only be saved after tell")
        try:
            encoded = base64.b64encode(pickle.dumps(self._study, protocol=pickle.HIGHEST_PROTOCOL)).decode("ascii")
        except (pickle.PickleError, TypeError) as exc:
            raise ResearchExperimentError(f"failed to serialize Optuna study: {exc}") from exc
        return write_json_state(path, {
            "schema_version": self.STATE_SCHEMA_VERSION,
            "signature": state_signature(self._config),
            "optuna_version": optuna.__version__,
            "study_pickle_base64": encoded,
            "pending": None,
            "phase": self._phase,
            "history": [asdict(item) for item in self._history],
        })

    def load_state(self, path: str | Path) -> None:
        payload = read_json_state(path)
        if payload.get("schema_version") != self.STATE_SCHEMA_VERSION or payload.get("signature") != state_signature(self._config):
            raise ResearchExperimentError("optimizer state does not match the current experiment configuration")
        if payload.get("optuna_version") != optuna.__version__:
            raise ResearchExperimentError("TPE state requires the recorded Optuna version")
        try:
            study = pickle.loads(base64.b64decode(payload["study_pickle_base64"], validate=True))
            if not isinstance(study, optuna.study.Study):
                raise TypeError("serialized object is not an Optuna Study")
            self._study = study
            self._phase = payload["phase"]
            self._pending = None
            self._pending_trial = None
            self._history = [OptimizerFeedback(**item) for item in payload["history"]]
        except (KeyError, TypeError, ValueError, pickle.PickleError) as exc:
            raise ResearchExperimentError(f"invalid TPE optimizer state: {exc}") from exc

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        return tuple(self._history)
