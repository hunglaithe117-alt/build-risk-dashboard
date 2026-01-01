"""
Risk Model Inference Service.

This module provides the inference logic for the Bayesian LSTM risk model.
It loads the model and scalers, processes feature dicts, and returns predictions.

Feature definitions match training script (hunglt/training.py).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import torch

from app.services.risk_model.model import (
    LSTM_DROPOUT,
    LSTM_HIDDEN_DIM,
    LSTM_LAYERS,
    MIN_SEQ_LEN,
    SEQ_LEN,
    TEMPORAL_DROPOUT,
    BayesianRiskModel,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Feature definitions matching training (hunglt/training.py)
# =============================================================================

# Temporal features (used in LSTM sequence - build history patterns)
TEMPORAL_FEATURES = [
    "is_prev_failed",
    "prev_fail_streak",
    "fail_rate_last_10",
    "avg_src_churn_last_5",
    "time_since_prev_build",
]

# Static features (point-in-time values for current build)
STATIC_FEATURES = [
    # Code churn features
    "git_diff_src_churn",
    "gh_diff_files_added",
    "gh_diff_files_deleted",
    "gh_diff_files_modified",
    "gh_diff_tests_added",
    "gh_diff_tests_deleted",
    "gh_diff_src_files",
    "gh_diff_doc_files",
    "gh_diff_other_files",
    "gh_num_commits_on_files_touched",
    "files_modified_ratio",
    "change_entropy",
    "churn_ratio_vs_avg",
    # Repository metrics
    "gh_sloc",
    "gh_repo_age",
    "gh_repo_num_commits",
    "gh_test_lines_per_kloc",
    "gh_test_cases_per_kloc",
    "gh_asserts_cases_per_kloc",  # Note: plural 'cases' to match model training
    # Team features
    "gh_team_size",
    "author_ownership",
    "is_new_contributor",
    "days_since_last_author_commit",
    # Test metrics from build logs
    "tr_log_num_jobs",
    "tr_log_tests_run_sum",
    "tr_log_tests_failed_sum",
    "tr_log_tests_skipped_sum",
    "tr_log_tests_ok_sum",
    "tr_log_testduration_sum",
    "tr_log_tests_fail_rate",
    "tr_duration",
    "tr_status_num",
    # Time features
    "build_time_sin",
    "build_time_cos",
    "build_hour_risk_score",
]

# Features that need log1p transformation
LOG1P_FEATURES = [
    "git_diff_src_churn",
    "gh_diff_files_added",
    "gh_diff_files_deleted",
    "gh_diff_files_modified",
    "gh_diff_tests_added",
    "gh_diff_tests_deleted",
    "gh_diff_src_files",
    "gh_diff_doc_files",
    "gh_diff_other_files",
    "gh_num_commits_on_files_touched",
    "gh_sloc",
    "gh_repo_age",
    "gh_repo_num_commits",
    "tr_log_num_jobs",
    "tr_log_tests_run_sum",
    "tr_log_tests_failed_sum",
    "tr_log_tests_skipped_sum",
    "tr_log_tests_ok_sum",
    "tr_log_testduration_sum",
    "tr_duration",
    "time_since_prev_build",
    "days_since_last_author_commit",
]

RISK_LABELS = ["Low", "Medium", "High"]


class RiskModelService:
    """
    Service for making risk predictions using the Bayesian LSTM model.

    Handles:
    - Model loading (lazy, singleton)
    - Feature preprocessing (log1p transformation, scaling)
    - MC Dropout inference for uncertainty estimation
    """

    _instance = None
    _model = None
    _scaler_static = None
    _scaler_temporal = None
    _device = None
    _seq_len = SEQ_LEN
    _min_seq_len = MIN_SEQ_LEN

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is None:
            self._load_model()

    def _get_artifacts_dir(self) -> Path:
        """Get path to model artifacts directory."""
        return Path(__file__).parent / "artifacts"

    def _load_model(self):
        """Load model and scalers from artifacts."""
        artifacts_dir = self._get_artifacts_dir()

        model_path = artifacts_dir / "bayesian_risk_model.pt"
        scaler_static_path = artifacts_dir / "scaler_static.pkl"
        scaler_temporal_path = artifacts_dir / "scaler_temporal.pkl"

        if not model_path.exists():
            logger.warning(f"Model file not found: {model_path}")
            return

        try:
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            # Load model checkpoint
            checkpoint = torch.load(model_path, map_location=self._device, weights_only=False)

            # Get hyperparameters from checkpoint or use defaults
            lstm_hidden_dim = checkpoint.get("lstm_hidden_dim", LSTM_HIDDEN_DIM)
            lstm_layers = checkpoint.get("lstm_layers", LSTM_LAYERS)
            lstm_dropout = checkpoint.get("lstm_dropout", LSTM_DROPOUT)
            temporal_dropout = checkpoint.get("temporal_dropout", TEMPORAL_DROPOUT)
            self._seq_len = checkpoint.get("seq_len", SEQ_LEN)
            self._min_seq_len = checkpoint.get("min_seq_len", MIN_SEQ_LEN)

            # Initialize model with checkpoint parameters
            self._model = BayesianRiskModel(
                temporal_dim=checkpoint["temporal_dim"],
                static_dim=checkpoint["static_dim"],
                lstm_hidden_dim=lstm_hidden_dim,
                lstm_layers=lstm_layers,
                lstm_dropout=lstm_dropout,
                temporal_dropout=temporal_dropout,
            )
            self._model.load_state_dict(checkpoint["model_state_dict"])
            self._model.to(self._device)
            self._model.eval()

            # Load scalers
            if scaler_static_path.exists():
                self._scaler_static = joblib.load(scaler_static_path)
            if scaler_temporal_path.exists():
                self._scaler_temporal = joblib.load(scaler_temporal_path)

            logger.info(
                f"✅ Risk model loaded successfully "
                f"(seq_len={self._seq_len}, min_seq_len={self._min_seq_len})"
            )

        except Exception as e:
            logger.error(f"Failed to load risk model: {e}")
            self._model = None

    def is_loaded(self) -> bool:
        """Check if model is loaded and ready."""
        return self._model is not None

    def _apply_log1p(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Apply log1p transformation to specified features."""
        result = features.copy()
        for f in LOG1P_FEATURES:
            if f in result and result[f] is not None:
                val = float(result[f])
                result[f] = np.log1p(max(0, val))
        return result

    def _extract_features(
        self, features: Dict[str, Any], apply_log1p: bool = True
    ) -> Tuple[List[float], List[float]]:
        """
        Extract temporal and static features from feature dict.

        Args:
            features: Raw feature dict
            apply_log1p: Whether to apply log1p transformation

        Returns:
            Tuple of (temporal_values, static_values)
        """
        if apply_log1p:
            features = self._apply_log1p(features)

        temporal_values = []
        for f in TEMPORAL_FEATURES:
            val = features.get(f)
            if val is None:
                val = 0.0
            elif isinstance(val, bool):
                val = 1.0 if val else 0.0
            temporal_values.append(float(val))

        static_values = []
        for f in STATIC_FEATURES:
            val = features.get(f)
            if val is None:
                val = 0.0
            elif isinstance(val, bool):
                val = 1.0 if val else 0.0
            static_values.append(float(val))

        return temporal_values, static_values

    def _create_sequence(
        self, temporal_history: List[List[float]], seq_len: Optional[int] = None
    ) -> Tuple[np.ndarray, int]:
        """
        Create sequence tensor from temporal feature history.

        If history is shorter than seq_len, pad with zeros at the end.

        Returns:
            Tuple of (sequence_array, actual_length)
        """
        if seq_len is None:
            seq_len = self._seq_len

        actual_length = min(len(temporal_history), seq_len)

        if len(temporal_history) >= seq_len:
            # Use last seq_len entries
            seq = temporal_history[-seq_len:]
        else:
            # Pad with zeros at the end (not beginning)
            padding_count = seq_len - len(temporal_history)
            zero_row = [0.0] * len(TEMPORAL_FEATURES)
            seq = temporal_history + [zero_row] * padding_count

        return np.array(seq, dtype=np.float32), actual_length

    def predict(
        self,
        features: Dict[str, Any],
        temporal_history: Optional[List[Dict[str, Any]]] = None,
        n_samples: int = 30,
        use_prescaled: bool = False,
    ) -> Dict[str, Any]:
        """
        Make risk prediction for a build.

        Args:
            features: Current build features dict (raw or pre-scaled)
            temporal_history: List of feature dicts from previous builds (for LSTM)
            n_samples: Number of MC Dropout samples for uncertainty
            use_prescaled: If True, skip scaling (features are already normalized)

        Returns:
            Dict with keys:
            - predicted_label: "Low", "Medium", or "High"
            - confidence: Confidence probability
            - uncertainty: Uncertainty score (0-1)
            - probabilities: Dict of {label: probability}
        """
        if not self.is_loaded():
            return {
                "predicted_label": None,
                "confidence": None,
                "uncertainty": None,
                "probabilities": None,
                "error": "Model not loaded",
            }

        try:
            # Extract features (with log1p if not prescaled)
            apply_log1p = not use_prescaled
            temporal_values, static_values = self._extract_features(features, apply_log1p)

            # Build sequence from history
            if temporal_history:
                history_temporal = [
                    self._extract_features(h, apply_log1p)[0] for h in temporal_history
                ]
                history_temporal.append(temporal_values)
            else:
                history_temporal = [temporal_values]

            seq, seq_length = self._create_sequence(history_temporal)

            # Check minimum sequence length requirement
            if seq_length < self._min_seq_len:
                return {
                    "predicted_label": None,
                    "confidence": None,
                    "uncertainty": None,
                    "probabilities": None,
                    "error": f"Insufficient history: {seq_length} < {self._min_seq_len}",
                }

            # Scale only if not using pre-scaled features
            if use_prescaled:
                # Features are already scaled, just reshape
                seq = seq.reshape(1, -1, len(TEMPORAL_FEATURES))
                static_arr = np.array([static_values], dtype=np.float32)
            else:
                # Apply scaling
                if self._scaler_temporal:
                    seq_flat = seq.reshape(-1, len(TEMPORAL_FEATURES))
                    import pandas as pd

                    seq_df = pd.DataFrame(seq_flat, columns=TEMPORAL_FEATURES)
                    seq_flat = self._scaler_temporal.transform(seq_df)
                    seq = seq_flat.reshape(1, -1, len(TEMPORAL_FEATURES))
                else:
                    seq = seq.reshape(1, -1, len(TEMPORAL_FEATURES))

                static_arr = np.array([static_values], dtype=np.float32)
                if self._scaler_static:
                    import pandas as pd

                    static_df = pd.DataFrame(static_arr, columns=STATIC_FEATURES)
                    static_arr = self._scaler_static.transform(static_df)

            # Convert to tensors
            seq_tensor = torch.tensor(seq, dtype=torch.float32).to(self._device)
            static_tensor = torch.tensor(static_arr, dtype=torch.float32).to(self._device)
            lengths_tensor = torch.tensor([seq_length], dtype=torch.long).to(self._device)

            # MC Dropout inference
            self._model.train()  # Enable dropout
            probs_list = []

            with torch.no_grad():
                for _ in range(n_samples):
                    logits = self._model(seq_tensor, static_tensor, lengths_tensor)
                    prob = torch.softmax(logits, dim=1)
                    probs_list.append(prob.cpu().numpy())

            probs = np.stack(probs_list)
            mean_prob = probs.mean(axis=0)[0]
            uncertainty = probs.var(axis=0).mean()

            pred_class = int(mean_prob.argmax())
            pred_label = RISK_LABELS[pred_class]
            confidence = float(mean_prob[pred_class])

            return {
                "predicted_label": pred_label,
                "confidence": round(confidence, 4),
                "uncertainty": round(float(uncertainty), 4),
                "probabilities": {
                    "Low": round(float(mean_prob[0]), 4),
                    "Medium": round(float(mean_prob[1]), 4),
                    "High": round(float(mean_prob[2]), 4),
                },
            }

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {
                "predicted_label": None,
                "confidence": None,
                "uncertainty": None,
                "probabilities": None,
                "error": str(e),
            }

    def predict_batch(
        self,
        features_list: List[Dict[str, Any]],
        n_samples: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Batch prediction for multiple builds.

        Optimized for processing multiple builds at once.
        """
        results = []
        for features in features_list:
            result = self.predict(features, n_samples=n_samples)
            results.append(result)
        return results
