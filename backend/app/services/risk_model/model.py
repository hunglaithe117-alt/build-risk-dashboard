"""
Bayesian LSTM Risk Model Definitions.

This module defines the PyTorch model architecture for build risk prediction.
It should match the training script exactly.
"""

import torch
import torch.nn as nn


class BayesianLSTM(nn.Module):
    """LSTM layer with attention for temporal features."""

    def __init__(self, input_dim: int, hidden_dim: int):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True, dropout=0.3)
        self.attn = nn.Linear(hidden_dim, 1)

    def forward(self, x):
        h, _ = self.lstm(x)
        weights = torch.softmax(self.attn(h), dim=1)
        context = (weights * h).sum(dim=1)
        return context


class BayesianMLP(nn.Module):
    """MLP layer for static features with dropout for uncertainty."""

    def __init__(self, input_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.4),
        )

    def forward(self, x):
        return self.net(x)


class BayesianRiskModel(nn.Module):
    """
    Dual-branch Bayesian model for build risk prediction.

    Architecture:
    - Temporal branch: LSTM with attention for sequence features
    - Static branch: MLP for point-in-time features
    - Classifier: Combined features → 3-class output (Low/Medium/High)
    """

    def __init__(self, temporal_dim: int, static_dim: int):
        super().__init__()
        self.temporal = BayesianLSTM(temporal_dim, 64)
        self.static = BayesianMLP(static_dim)
        self.classifier = nn.Sequential(
            nn.Linear(64 + 64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 3),
        )

    def forward(self, seq, static):
        t = self.temporal(seq)
        s = self.static(static)
        x = torch.cat([t, s], dim=1)
        return self.classifier(x)
