"""
PredictionService - Local Bayesian LSTM model inference.

This service uses the local RiskModelService to make predictions.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Result from risk prediction model."""

    risk_level: str  # LOW, MEDIUM, HIGH
    risk_score: float  # 0.0 - 1.0 (confidence)
    uncertainty: float  # Bayesian uncertainty
    model_version: str
    error: Optional[str] = None


class PredictionService:
    """
    Service for making risk predictions using local Bayesian LSTM model.

    Features:
    - Uses local RiskModelService for inference
    - Supports batch predictions
    - Lazy loading of model for efficiency
    """

    _risk_model_service = None

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._init_local_model()

    def _init_local_model(self):
        """Initialize local model service (lazy, singleton)."""
        if PredictionService._risk_model_service is None:
            try:
                from app.services.risk_model import RiskModelService

                PredictionService._risk_model_service = RiskModelService()
                if PredictionService._risk_model_service.is_loaded():
                    logger.info("✅ Local risk model initialized")
                else:
                    logger.warning("⚠️ Local risk model not loaded")
            except Exception as e:
                logger.error(f"Failed to initialize local model: {e}")
                PredictionService._risk_model_service = None

    def is_model_loaded(self) -> bool:
        """Check if model is loaded and ready."""
        return (
            PredictionService._risk_model_service is not None
            and PredictionService._risk_model_service.is_loaded()
        )

    def predict(
        self,
        features: Dict[str, Any],
        temporal_history: Optional[List[Dict[str, Any]]] = None,
        use_prescaled: bool = False,
    ) -> PredictionResult:
        """
        Make prediction using local model.

        Args:
            features: Current build features dict (raw or pre-scaled)
            temporal_history: Optional list of previous builds' features for LSTM
            use_prescaled: If True, skip scaling (features are already normalized)

        Returns:
            PredictionResult with prediction or error.
        """
        if not self.is_model_loaded():
            return PredictionResult(
                risk_level="UNKNOWN",
                risk_score=0.0,
                uncertainty=1.0,
                model_version="not-loaded",
                error="Model not loaded",
            )

        try:
            result = PredictionService._risk_model_service.predict(
                features=features,
                temporal_history=temporal_history,
                n_samples=30,
                use_prescaled=use_prescaled,
            )

            if result.get("error"):
                return PredictionResult(
                    risk_level="UNKNOWN",
                    risk_score=0.0,
                    uncertainty=1.0,
                    model_version="bayesian-lstm-v1.0",
                    error=result["error"],
                )

            return PredictionResult(
                risk_level=result.get("predicted_label", "UNKNOWN").upper(),
                risk_score=result.get("confidence", 0.0),
                uncertainty=result.get("uncertainty", 0.0),
                model_version="bayesian-lstm-v1.0",
            )

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return PredictionResult(
                risk_level="UNKNOWN",
                risk_score=0.0,
                uncertainty=1.0,
                model_version="bayesian-lstm-v1.0",
                error=str(e),
            )

    def normalize_features(
        self,
        features: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Normalize features for model input using the model's scalers.

        This performs ACTUAL normalization/standardization using the same
        scalers that RiskModelService uses for prediction.

        Args:
            features: Raw feature dict from Hamilton DAG

        Returns:
            Dict with scaled feature values (TEMPORAL + STATIC features only)
        """
        if not self.is_model_loaded():
            # Fallback: just filter and convert types without scaling
            return self._filter_model_features(features)

        try:
            import numpy as np
            import pandas as pd

            from app.services.risk_model.inference import STATIC_FEATURES, TEMPORAL_FEATURES

            model_service = PredictionService._risk_model_service

            # Extract temporal features
            temporal_values = []
            for f in TEMPORAL_FEATURES:
                val = features.get(f)
                if val is None:
                    val = 0.0
                elif isinstance(val, bool):
                    val = 1.0 if val else 0.0
                temporal_values.append(float(val))

            # Extract static features
            static_values = []
            for f in STATIC_FEATURES:
                val = features.get(f)
                if val is None:
                    val = 0.0
                elif isinstance(val, bool):
                    val = 1.0 if val else 0.0
                static_values.append(float(val))

            # Scale temporal features
            temporal_arr = np.array([temporal_values], dtype=np.float32)
            if model_service._scaler_temporal:
                temporal_df = pd.DataFrame(temporal_arr, columns=TEMPORAL_FEATURES)
                temporal_scaled = model_service._scaler_temporal.transform(temporal_df)
                temporal_values = temporal_scaled[0].tolist()

            # Scale static features
            static_arr = np.array([static_values], dtype=np.float32)
            if model_service._scaler_static:
                static_df = pd.DataFrame(static_arr, columns=STATIC_FEATURES)
                static_scaled = model_service._scaler_static.transform(static_df)
                static_values = static_scaled[0].tolist()

            # Build normalized dict
            normalized = {}
            for i, f in enumerate(TEMPORAL_FEATURES):
                normalized[f] = round(float(temporal_values[i]), 6)
            for i, f in enumerate(STATIC_FEATURES):
                normalized[f] = round(float(static_values[i]), 6)

            return normalized

        except Exception as e:
            logger.warning(f"Failed to normalize features: {e}")
            return self._filter_model_features(features)

    def _filter_model_features(
        self,
        features: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Filter and convert features to model format without scaling.

        Fallback when model/scalers are not available.
        """
        try:
            from app.services.risk_model.inference import STATIC_FEATURES, TEMPORAL_FEATURES

            normalized = {}
            for f in TEMPORAL_FEATURES + STATIC_FEATURES:
                val = features.get(f)
                if val is None:
                    normalized[f] = 0.0
                elif isinstance(val, bool):
                    normalized[f] = 1.0 if val else 0.0
                else:
                    normalized[f] = float(val) if val is not None else 0.0
            return normalized
        except Exception:
            return {}

    def predict_batch(
        self,
        feature_list: List[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], PredictionResult]]:
        """
        Batch prediction for multiple builds.

        Args:
            feature_list: List of feature dicts

        Returns:
            List of (features, prediction_result) tuples
        """
        if not feature_list:
            return []

        results = []
        for features in feature_list:
            prediction = self.predict(features)
            results.append((features, prediction))

        return results

    def predict_build(
        self,
        raw_features: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], PredictionResult]:
        """
        Convenience method: predict for a single build.

        Returns:
            (features, prediction_result)
        """
        result = self.predict(raw_features)
        return raw_features, result
