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
    ) -> PredictionResult:
        """
        Make prediction using local model.

        Args:
            features: Current build features dict
            temporal_history: Optional list of previous builds' features for LSTM

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
