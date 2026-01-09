import torch
import torch.nn as nn
import torch.nn.functional as F
import joblib
import pandas as pd
import numpy as np

LABEL_COL = "risk_label_numeric"
GROUP_COL = "gh_project_name"
TIME_COL = "gh_build_started_at"
BUILD_ID_COL = "tr_build_id"
PREV_BUILD_COL = "tr_prev_build"
SEQ_LEN = 10
LSTM_HIDDEN_DIM = 64
LSTM_LAYERS = 1
LSTM_DROPOUT = 0.0
TEMPORAL_DROPOUT = 0.0
MIN_SEQ_LEN = 1

TEMPORAL_FEATURES = [
    "is_prev_failed",
    "prev_fail_streak",
    "fail_rate_last_10",
    "avg_src_churn_last_5",
    "time_since_prev_build"
]

STATIC_FEATURES = [
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
    "gh_sloc",
    "gh_repo_age",
    "gh_repo_num_commits",
    "gh_test_lines_per_kloc",
    "gh_test_cases_per_kloc",
    "gh_asserts_cases_per_kloc",
    "gh_team_size",
    "author_ownership",
    "is_new_contributor",
    "days_since_last_author_commit",
    "tr_log_num_jobs",
    "tr_log_tests_run_sum",
    "tr_log_tests_failed_sum",
    "tr_log_tests_skipped_sum",
    "tr_log_tests_ok_sum",
    "tr_log_testduration_sum",
    "tr_log_tests_fail_rate",
    "tr_duration",
    "tr_status_num",
    "build_time_sin",
    "build_time_cos",
    "build_hour_risk_score"
]

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
    "days_since_last_author_commit"
]

STATUS_MAP = {"passed": 0, "failed": 1}

class BayesianLSTM(nn.Module):
    def __init__(self, input_dim, hidden_dim, num_layers=1, dropout=0.0, temporal_dropout=0.0):
        super().__init__()
        self.lstm = nn.LSTM(
            input_dim,
            hidden_dim,
            batch_first=True,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.attn = nn.Linear(hidden_dim, 1)
        self.temporal_dropout = nn.Dropout(temporal_dropout)

    def forward(self, x, lengths):
        lengths_cpu = lengths.to("cpu")
        packed = nn.utils.rnn.pack_padded_sequence(
            x,
            lengths_cpu,
            batch_first=True,
            enforce_sorted=False
        )
        packed_out, _ = self.lstm(packed)
        h, _ = nn.utils.rnn.pad_packed_sequence(
            packed_out,
            batch_first=True,
            total_length=x.size(1)
        )

        max_len = h.size(1)
        mask = torch.arange(max_len, device=lengths.device).unsqueeze(0) < lengths.unsqueeze(1)
        attn_scores = self.attn(h).squeeze(-1)
        attn_scores = attn_scores.masked_fill(~mask, -1e9)
        weights = torch.softmax(attn_scores, dim=1).unsqueeze(-1)
        context = (weights * h).sum(dim=1)
        return self.temporal_dropout(context)

# Bayesian MLP (Static branch)
class BayesianMLP(nn.Module):
  def __init__(self, input_dim):
      super().__init__()
      self.net = nn.Sequential(
          nn.Linear(input_dim, 128),
          nn.ReLU(),
          nn.Dropout(0.4),
          nn.Linear(128, 64),
          nn.ReLU(),
          nn.Dropout(0.4)
      )

  def forward(self, x):
      return self.net(x)

class BayesianRiskModel(nn.Module):
    def __init__(self, temporal_dim, static_dim, lstm_hidden_dim, lstm_layers, lstm_dropout, temporal_dropout):
        super().__init__()

        self.temporal = BayesianLSTM(
            temporal_dim,
            lstm_hidden_dim,
            num_layers=lstm_layers,
            dropout=lstm_dropout,
            temporal_dropout=temporal_dropout
        )
        self.static = BayesianMLP(static_dim)

        self.classifier = nn.Sequential(
            nn.Linear(lstm_hidden_dim + 64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 3)
        )

    def forward(self, seq, static, lengths):
        t = self.temporal(seq, lengths)
        s = self.static(static)
        x = torch.cat([t, s], dim=1)
        return self.classifier(x)
    
# Load model
SAVE_DIR = "./artifacts"
MODEL_PATH = f"{SAVE_DIR}/bayesian_risk_model.pt"
SCALER_STATIC_PATH = f"{SAVE_DIR}/scaler_static.pkl"
SCALER_TEMPORAL_PATH = f"{SAVE_DIR}/scaler_temporal.pkl"

def load_bayesian_model(model_path, device):
    checkpoint = torch.load(model_path, map_location=device)

    lstm_hidden_dim = checkpoint.get("lstm_hidden_dim", LSTM_HIDDEN_DIM)
    lstm_layers = checkpoint.get("lstm_layers", LSTM_LAYERS)
    lstm_dropout = checkpoint.get("lstm_dropout", LSTM_DROPOUT)
    temporal_dropout = checkpoint.get("temporal_dropout", TEMPORAL_DROPOUT)
    min_seq_len = checkpoint.get("min_seq_len", MIN_SEQ_LEN)

    model = BayesianRiskModel(
        temporal_dim=checkpoint["temporal_dim"],
        static_dim=checkpoint["static_dim"],
        lstm_hidden_dim=lstm_hidden_dim,
        lstm_layers=lstm_layers,
        lstm_dropout=lstm_dropout,
        temporal_dropout=temporal_dropout
    )

    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)

    temporal_features = checkpoint.get("temporal_features", TEMPORAL_FEATURES)
    static_features = checkpoint.get("static_features", STATIC_FEATURES)
    log1p_features = checkpoint.get("log1p_features", LOG1P_FEATURES)
    seq_len = checkpoint.get("seq_len", SEQ_LEN)

    return model, temporal_features, static_features, log1p_features, seq_len, min_seq_len

RISK_LABELS = ["Low", "Medium", "High"]

def bayesian_inference(
    model,
    seq_tensor,
    static_tensor,
    lengths_tensor,
    n_samples=30
):
    model.train()  # bật dropout

    probs = []

    for _ in range(n_samples):
        logits = model(seq_tensor, static_tensor, lengths_tensor)
        prob = torch.softmax(logits, dim=1)
        probs.append(prob.detach().cpu().numpy())

    probs = np.stack(probs)

    mean_prob = probs.mean(axis=0)
    uncertainty = probs.var(axis=0).mean(axis=1)

    pred_class = mean_prob.argmax(axis=1)
    pred_label = [RISK_LABELS[i] for i in pred_class]

    return mean_prob, uncertainty, pred_label

def prepare_dataframe(df, temporal_features, static_features, log1p_features):
    if "tr_status" in df.columns:
        df["tr_status_num"] = df["tr_status"].map(STATUS_MAP).fillna(-1).astype(int)
    elif "tr_status_num" not in df.columns and "tr_status_num" in static_features:
        raise ValueError("Missing tr_status for tr_status_num feature.")

    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")

    sort_cols = [GROUP_COL, TIME_COL]
    if "tr_build_number" in df.columns:
        sort_cols.append("tr_build_number")

    required_cols = temporal_features + static_features + [
        GROUP_COL,
        TIME_COL,
        BUILD_ID_COL,
        PREV_BUILD_COL
    ]
    used_cols = list(set(required_cols + sort_cols))
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns for inference: {missing}")

    df = df[used_cols].copy()

    for col in temporal_features + static_features:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in temporal_features + static_features:
        if df[col].isna().sum() > 0:
            if df[col].nunique(dropna=True) <= 2:
                df[col] = df[col].fillna(df[col].mode(dropna=True).iloc[0])
            else:
                df[col] = df[col].fillna(df[col].median())

    log1p_features = [c for c in log1p_features if c in df.columns]
    for col in log1p_features:
        df[col] = np.log1p(df[col].clip(lower=0))

    df[BUILD_ID_COL] = pd.to_numeric(df[BUILD_ID_COL], errors="coerce").fillna(-1).astype("int64")
    df[PREV_BUILD_COL] = pd.to_numeric(df[PREV_BUILD_COL], errors="coerce").fillna(-1).astype("int64")

    df = df.sort_values(sort_cols).reset_index(drop=True)
    return df

def build_sequences_from_prev(
    df,
    temporal_features,
    static_features,
    seq_len,
    min_seq_len=1,
    group_col=GROUP_COL
):
    build_ids = df[BUILD_ID_COL].to_numpy()
    prev_ids = df[PREV_BUILD_COL].to_numpy()
    group_vals = df[group_col].to_numpy()

    id_to_idx = {}
    for idx, build_id in enumerate(build_ids):
        if build_id == -1:
            continue
        id_to_idx[build_id] = idx

    sequences = []
    statics = []
    indices = []
    lengths = []

    for idx in range(len(df)):
        prev_id = prev_ids[idx]
        seq_indices = []
        visited = set()

        while len(seq_indices) < seq_len and prev_id != -1:
            if prev_id in visited:
                break
            visited.add(prev_id)

            prev_idx = id_to_idx.get(prev_id)
            if prev_idx is None:
                break
            if group_vals[prev_idx] != group_vals[idx]:
                break

            seq_indices.append(prev_idx)
            prev_id = prev_ids[prev_idx]

        if len(seq_indices) >= min_seq_len:
            seq_indices = seq_indices[::-1]
            seq = df.iloc[seq_indices][temporal_features].values
            static = df.iloc[idx][static_features].values
            seq_len_actual = len(seq_indices)
            if seq_len_actual < seq_len:
                pad = np.zeros((seq_len - seq_len_actual, seq.shape[1]), dtype=seq.dtype)
                seq = np.concatenate([seq, pad], axis=0)
            sequences.append(seq)
            statics.append(static)
            indices.append(idx)
            lengths.append(seq_len_actual)

    return np.array(sequences), np.array(statics), indices, np.array(lengths)

if __name__ == "__main__":

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model, temporal_features, static_features, log1p_features, seq_len, min_seq_len = load_bayesian_model(
        MODEL_PATH,
        device
    )
    scaler_static = joblib.load(SCALER_STATIC_PATH)
    scaler_temporal = joblib.load(SCALER_TEMPORAL_PATH)

    print("✅ Model loaded")

    # Chuẩn bị dữ liệu inference thực tế (CSV mới)
    # ⚠️ CSV phải có đầy đủ feature giống lúc train
    csv_path = "./final_dataset/test.csv"
    df = pd.read_csv(csv_path)

    df = prepare_dataframe(df, temporal_features, static_features, log1p_features)

    df.loc[:, static_features] = scaler_static.transform(df[static_features])
    df.loc[:, temporal_features] = scaler_temporal.transform(df[temporal_features])

    sequences, statics, indices, lengths = build_sequences_from_prev(
        df,
        temporal_features,
        static_features,
        seq_len,
        min_seq_len=min_seq_len,
        group_col=GROUP_COL
    )

    seq_tensor = torch.tensor(sequences, dtype=torch.float32).to(device)
    static_tensor = torch.tensor(statics, dtype=torch.float32).to(device)
    lengths_tensor = torch.tensor(lengths, dtype=torch.long).to(device)

    print(seq_tensor.shape, static_tensor.shape)


    mean_prob, uncertainty, pred_label = bayesian_inference(
        model,
        seq_tensor,
        static_tensor,
        lengths_tensor,
        n_samples=30
    )

    # Xuất kết quả inference
    results = pd.DataFrame({
        "tr_build_id": df.loc[indices, BUILD_ID_COL].values,
        "gh_project_name": df.loc[indices, GROUP_COL].values,
        "gh_build_started_at": df.loc[indices, TIME_COL].values,
        "risk_prediction": pred_label,
        "prob_low": mean_prob[:, 0],
        "prob_medium": mean_prob[:, 1],
        "prob_high": mean_prob[:, 2],
        "predictive_uncertainty": uncertainty
    })

    print("Test results:")
    print(results)
