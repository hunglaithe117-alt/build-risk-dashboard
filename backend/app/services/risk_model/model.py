"""
Bayesian LSTM Risk Model Definitions.

This module defines the PyTorch model architecture for build risk prediction.
It should match the training script exactly (hunglt/training.py).

Model Architecture:
- Temporal Branch: LSTM with Attention for sequence features (build history)
- Static Branch: Bayesian MLP for point-in-time features
- Classifier: Fused output → 3-class risk prediction (Low/Medium/High)
"""

import torch
import torch.nn as nn


# Default hyperparameters (should match training - hunglt/training_on_colab.ipynb)
LSTM_HIDDEN_DIM = 96
LSTM_LAYERS = 2
LSTM_DROPOUT = 0.2
TEMPORAL_DROPOUT = 0.2
SEQ_LEN = 10
MIN_SEQ_LEN = 4


class BayesianLSTM(nn.Module):
    """
    LSTM layer with attention for temporal features.

    Supports packed sequences for variable-length inputs.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        num_layers: int = 1,
        dropout: float = 0.0,
        temporal_dropout: float = 0.0,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_dim,
            hidden_dim,
            batch_first=True,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.attn = nn.Linear(hidden_dim, 1)
        self.temporal_dropout = nn.Dropout(temporal_dropout)

    def forward(self, x, lengths=None):
        if lengths is not None:
            # Use packed sequence for variable-length inputs
            lengths_cpu = lengths.to("cpu")
            packed = nn.utils.rnn.pack_padded_sequence(
                x,
                lengths_cpu,
                batch_first=True,
                enforce_sorted=False,
            )
            packed_out, _ = self.lstm(packed)
            h, _ = nn.utils.rnn.pad_packed_sequence(
                packed_out,
                batch_first=True,
                total_length=x.size(1),
            )

            # Mask attention for padding
            max_len = h.size(1)
            mask = torch.arange(max_len, device=lengths.device).unsqueeze(0) < lengths.unsqueeze(1)
            attn_scores = self.attn(h).squeeze(-1)
            attn_scores = attn_scores.masked_fill(~mask, -1e9)
            weights = torch.softmax(attn_scores, dim=1).unsqueeze(-1)
            context = (weights * h).sum(dim=1)
        else:
            # Simple forward without packed sequence
            h, _ = self.lstm(x)
            weights = torch.softmax(self.attn(h), dim=1)
            context = (weights * h).sum(dim=1)

        return self.temporal_dropout(context)


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

    def __init__(
        self,
        temporal_dim: int,
        static_dim: int,
        lstm_hidden_dim: int = LSTM_HIDDEN_DIM,
        lstm_layers: int = LSTM_LAYERS,
        lstm_dropout: float = LSTM_DROPOUT,
        temporal_dropout: float = TEMPORAL_DROPOUT,
    ):
        super().__init__()
        self.temporal = BayesianLSTM(
            temporal_dim,
            lstm_hidden_dim,
            num_layers=lstm_layers,
            dropout=lstm_dropout,
            temporal_dropout=temporal_dropout,
        )
        self.static = BayesianMLP(static_dim)
        self.classifier = nn.Sequential(
            nn.Linear(lstm_hidden_dim + 64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 3),
        )

    def forward(self, seq, static, lengths=None):
        t = self.temporal(seq, lengths)
        s = self.static(static)
        x = torch.cat([t, s], dim=1)
        return self.classifier(x)
