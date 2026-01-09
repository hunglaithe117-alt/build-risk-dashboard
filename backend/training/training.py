# Load dữ liệu từ CSV
import copy
import pandas as pd
import numpy as np
import random
import torch

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

DATA_PATH = "./final_dataset/final_clean.csv"

df = pd.read_csv(DATA_PATH)

print(df.shape)
print(df.columns.tolist())

# Display the head of the DataFrame
display(df.head())


# Lọc cột cần thiết
GROUP_COL = "gh_project_name"
TIME_COL = "gh_build_started_at"
BUILD_ID_COL = "tr_build_id"
PREV_BUILD_COL = "tr_prev_build"
LABEL_COL = "risk_label_numeric"

# Temporal features (chuỗi build gần nhất)
TEMPORAL_FEATURES = [
    "is_prev_failed",
    "prev_fail_streak",
    "fail_rate_last_10",
    "avg_src_churn_last_5",
    "time_since_prev_build"
]

# Static features (sau build, trước deploy)
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

# Dataset cho LSTM (sequence theo tr_prev_build)
from torch.utils.data import Dataset

def build_sequences_from_prev(df, seq_len, min_seq_len=1):
    build_ids = df[BUILD_ID_COL].to_numpy()
    prev_ids = df[PREV_BUILD_COL].to_numpy()
    group_vals = df[GROUP_COL].to_numpy()

    id_to_idx = {}
    for idx, build_id in enumerate(build_ids):
        if build_id == -1:
            continue
        id_to_idx[build_id] = idx

    sequences = []
    for idx in range(len(df)):
        prev_id = prev_ids[idx]
        seq = []
        visited = set()

        while len(seq) < seq_len and prev_id != -1:
            if prev_id in visited:
                break
            visited.add(prev_id)

            prev_idx = id_to_idx.get(prev_id)
            if prev_idx is None:
                break
            if group_vals[prev_idx] != group_vals[idx]:
                break

            seq.append(prev_idx)
            prev_id = prev_ids[prev_idx]

        if len(seq) >= min_seq_len:
            seq = seq[::-1]
            sequences.append((seq, idx, len(seq)))

    return sequences

class BuildSequenceDataset(Dataset):
    def __init__(self, df, sequences):
        self.df = df
        self.sequences = sequences

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        seq_indices, label_idx, seq_len = self.sequences[idx]
        seq = self.df.iloc[seq_indices][TEMPORAL_FEATURES].to_numpy(dtype=np.float32)
        static = self.df.iloc[label_idx][STATIC_FEATURES].to_numpy(dtype=np.float32)
        label = int(self.df.iloc[label_idx][LABEL_COL])
        if seq_len < SEQ_LEN:
            pad = np.zeros((SEQ_LEN - seq_len, seq.shape[1]), dtype=np.float32)
            seq = np.concatenate([seq, pad], axis=0)

        return (
            torch.from_numpy(seq),
            torch.from_numpy(static),
            torch.tensor(label, dtype=torch.long),
            torch.tensor(seq_len, dtype=torch.long)
        )

# Làm sạch dữ liệu
df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
df["tr_status_num"] = df["tr_status"].map({"passed": 0, "failed": 1}).fillna(-1).astype(int)

used_cols = (
    TEMPORAL_FEATURES
    + STATIC_FEATURES
    + [LABEL_COL, GROUP_COL, TIME_COL, "tr_build_number", BUILD_ID_COL, PREV_BUILD_COL]
)
df = df[used_cols].copy()

df[LABEL_COL] = pd.to_numeric(df[LABEL_COL], errors="coerce")
df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
df[LABEL_COL] = df[LABEL_COL].astype(int)

for col in TEMPORAL_FEATURES + STATIC_FEATURES:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df[BUILD_ID_COL] = pd.to_numeric(df[BUILD_ID_COL], errors="coerce").fillna(-1).astype("int64")
df[PREV_BUILD_COL] = pd.to_numeric(df[PREV_BUILD_COL], errors="coerce").fillna(-1).astype("int64")

sort_cols = [GROUP_COL, TIME_COL]
if "tr_build_number" in df.columns:
    sort_cols.append("tr_build_number")
df = df.sort_values(sort_cols).reset_index(drop=True)

def split_by_repo_time_indices(df, group_col=GROUP_COL, val_ratio=0.2):
    train_idx = []
    val_idx = []
    for _, g in df.groupby(group_col, sort=False):
        cut = int(len(g) * (1 - val_ratio))
        train_idx.extend(g.index[:cut])
        val_idx.extend(g.index[cut:])
    return train_idx, val_idx

train_indices, val_indices = split_by_repo_time_indices(df)
train_df = df.loc[train_indices]

for col in TEMPORAL_FEATURES + STATIC_FEATURES:
    if df[col].isna().sum() > 0:
        if train_df[col].nunique(dropna=True) <= 2:
            fill_value = train_df[col].mode(dropna=True).iloc[0]
        else:
            fill_value = train_df[col].median()
        df[col] = df[col].fillna(fill_value)

LOG1P_FEATURES = [c for c in LOG1P_FEATURES if c in df.columns]
for col in LOG1P_FEATURES:
    df[col] = np.log1p(df[col].clip(lower=0))

train_df = df.loc[train_indices]

def drop_constant(features, ref_df):
    return [c for c in features if ref_df[c].nunique(dropna=False) > 1]

TEMPORAL_FEATURES = drop_constant(TEMPORAL_FEATURES, train_df)
STATIC_FEATURES = drop_constant(STATIC_FEATURES, train_df)
LOG1P_FEATURES = [c for c in LOG1P_FEATURES if c in TEMPORAL_FEATURES + STATIC_FEATURES]

# Chuẩn hoá feature
from sklearn.preprocessing import StandardScaler

scaler_static = StandardScaler()
scaler_temporal = StandardScaler()

scaler_static.fit(train_df[STATIC_FEATURES])
scaler_temporal.fit(train_df[TEMPORAL_FEATURES])

df.loc[:, STATIC_FEATURES] = scaler_static.transform(df[STATIC_FEATURES])
df.loc[:, TEMPORAL_FEATURES] = scaler_temporal.transform(df[TEMPORAL_FEATURES])


# Tạo Dataset cho Bayesian LSTM
from torch.utils.data import DataLoader

SEQ_LEN = 10
MIN_SEQ_LEN = 4
BATCH_SIZE = 256
PIN_MEMORY = torch.cuda.is_available()

all_sequences = build_sequences_from_prev(df, SEQ_LEN, MIN_SEQ_LEN)
train_index_set = set(train_indices)
val_index_set = set(val_indices)
train_sequences = [s for s in all_sequences if s[1] in train_index_set]
val_sequences = [s for s in all_sequences if s[1] in val_index_set]

train_dataset = BuildSequenceDataset(df, train_sequences)
val_dataset = BuildSequenceDataset(df, val_sequences)

train_loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True,
    num_workers=4,
    pin_memory=PIN_MEMORY
)

val_loader = DataLoader(
    val_dataset,
    batch_size=BATCH_SIZE,
    shuffle=False,
    pin_memory=PIN_MEMORY
)

num_classes = int(df[LABEL_COL].max()) + 1
train_labels = np.array(
    [int(df.iloc[label_idx][LABEL_COL]) for _, label_idx, _ in train_sequences],
    dtype=np.int64
)
class_counts = np.bincount(train_labels, minlength=num_classes)
total_count = class_counts.sum()
class_weights = np.zeros(num_classes, dtype=np.float32)
nonzero = class_counts > 0
class_weights[nonzero] = total_count / (num_classes * class_counts[nonzero])

print(
    f"Sequences -> train: {len(train_sequences)}, val: {len(val_sequences)} "
    f"| min_len: {MIN_SEQ_LEN}"
)
print(f"Train label distribution: {class_counts.tolist()}")

import os

SAVE_DIR = "./artifacts"
os.makedirs(SAVE_DIR, exist_ok=True)
CKPT_PATH = f"{SAVE_DIR}/ckpt_best.pt"

# Xây dựng kiến trúc model
import torch.nn as nn
import torch.nn.functional as F

LSTM_HIDDEN_DIM = 96
LSTM_LAYERS = 2
LSTM_DROPOUT = 0.2
TEMPORAL_DROPOUT = 0.2
LABEL_SMOOTHING = 0.03

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
    def __init__(self, temporal_dim, static_dim):
        super().__init__()

        self.temporal = BayesianLSTM(
            temporal_dim,
            LSTM_HIDDEN_DIM,
            num_layers=LSTM_LAYERS,
            dropout=LSTM_DROPOUT,
            temporal_dropout=TEMPORAL_DROPOUT
        )
        self.static = BayesianMLP(static_dim)

        self.classifier = nn.Sequential(
            nn.Linear(LSTM_HIDDEN_DIM + 64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 3)
        )

    def forward(self, seq, static, lengths):
        t = self.temporal(seq, lengths)
        s = self.static(static)
        x = torch.cat([t, s], dim=1)
        return self.classifier(x)

model = BayesianRiskModel(
    temporal_dim=len(TEMPORAL_FEATURES),
    static_dim=len(STATIC_FEATURES)
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32, device=device)

LR = 1e-3
WEIGHT_DECAY = 1e-4
EPOCHS = 20
EARLY_STOP_PATIENCE = 5
MIN_DELTA = 1e-4
GRAD_CLIP_NORM = 1.0

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
criterion = nn.CrossEntropyLoss(
    weight=class_weights_tensor,
    label_smoothing=LABEL_SMOOTHING
)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer,
    mode="max",
    factor=0.5,
    patience=2,
    min_lr=1e-5
)

from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

def evaluate(model, data_loader, criterion, device, num_classes):
    model.eval()
    total_loss = 0.0
    all_labels = []
    all_preds = []

    with torch.no_grad():
        for seq, static, label, lengths in data_loader:
            seq = seq.to(device)
            static = static.to(device)
            label = label.to(device)
            lengths = lengths.to(device)

            logits = model(seq, static, lengths)
            loss = criterion(logits, label)
            total_loss += loss.item()

            preds = torch.argmax(logits, dim=1)
            all_labels.append(label.cpu().numpy())
            all_preds.append(preds.cpu().numpy())

    avg_loss = total_loss / len(data_loader) if len(data_loader) > 0 else 0.0
    if all_labels:
        y_true = np.concatenate(all_labels)
        y_pred = np.concatenate(all_preds)
        acc = accuracy_score(y_true, y_pred)
        f1 = f1_score(y_true, y_pred, average="macro")
        cm = confusion_matrix(y_true, y_pred, labels=list(range(num_classes)))
    else:
        acc = 0.0
        f1 = 0.0
        cm = np.zeros((num_classes, num_classes), dtype=int)

    return avg_loss, acc, f1, cm

# Training loop
best_f1 = -1.0
best_state = None
best_epoch = -1
patience_counter = 0

for epoch in range(EPOCHS):
    model.train()
    total_loss = 0.0

    for seq, static, label, lengths in train_loader:
        seq = seq.to(device)
        static = static.to(device)
        label = label.to(device)
        lengths = lengths.to(device)

        optimizer.zero_grad()
        logits = model(seq, static, lengths)
        loss = criterion(logits, label)
        loss.backward()
        if GRAD_CLIP_NORM is not None:
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
        optimizer.step()

        total_loss += loss.item()

    avg_train_loss = total_loss / len(train_loader) if len(train_loader) > 0 else 0.0
    val_loss, val_acc, val_f1, val_cm = evaluate(
        model, val_loader, criterion, device, num_classes
    )
    scheduler.step(val_f1)
    current_lr = optimizer.param_groups[0]["lr"]

    print(
        f"[Epoch {epoch+1}] Train Loss: {avg_train_loss:.4f} | "
        f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f} | "
        f"Val F1(macro): {val_f1:.4f} | LR: {current_lr:.2e}"
    )

    if val_f1 > best_f1 + MIN_DELTA:
        best_f1 = val_f1
        best_state = copy.deepcopy(model.state_dict())
        best_epoch = epoch
        patience_counter = 0

        torch.save({
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "temporal_dim": len(TEMPORAL_FEATURES),
            "static_dim": len(STATIC_FEATURES),
            "temporal_features": TEMPORAL_FEATURES,
            "static_features": STATIC_FEATURES,
            "log1p_features": LOG1P_FEATURES,
            "seq_len": SEQ_LEN,
            "min_seq_len": MIN_SEQ_LEN,
            "lstm_hidden_dim": LSTM_HIDDEN_DIM,
            "lstm_layers": LSTM_LAYERS,
            "lstm_dropout": LSTM_DROPOUT,
            "temporal_dropout": TEMPORAL_DROPOUT,
            "label_smoothing": LABEL_SMOOTHING,
            "val_f1_macro": val_f1
        }, CKPT_PATH)
    else:
        patience_counter += 1
        if patience_counter >= EARLY_STOP_PATIENCE:
            print(f"Early stopping at epoch {epoch+1}")
            break

if best_state is not None:
    model.load_state_dict(best_state)
    final_val_loss, final_val_acc, final_val_f1, final_val_cm = evaluate(
        model, val_loader, criterion, device, num_classes
    )
    print(
        f"Best epoch: {best_epoch + 1} | "
        f"Val Loss: {final_val_loss:.4f} | Val Acc: {final_val_acc:.4f} | "
        f"Val F1(macro): {final_val_f1:.4f}"
    )
    print("Confusion matrix (val):")
    print(final_val_cm)

# Export model
import joblib

MODEL_PATH = f"{SAVE_DIR}/bayesian_risk_model.pt"
SCALER_STATIC_PATH = f"{SAVE_DIR}/scaler_static.pkl"
SCALER_TEMPORAL_PATH = f"{SAVE_DIR}/scaler_temporal.pkl"

# Save model
torch.save({
    "model_state_dict": model.state_dict(),
    "temporal_dim": len(TEMPORAL_FEATURES),
    "static_dim": len(STATIC_FEATURES),
    "temporal_features": TEMPORAL_FEATURES,
    "static_features": STATIC_FEATURES,
    "log1p_features": LOG1P_FEATURES,
    "seq_len": SEQ_LEN,
    "min_seq_len": MIN_SEQ_LEN,
    "lstm_hidden_dim": LSTM_HIDDEN_DIM,
    "lstm_layers": LSTM_LAYERS,
    "lstm_dropout": LSTM_DROPOUT,
    "temporal_dropout": TEMPORAL_DROPOUT,
    "label_smoothing": LABEL_SMOOTHING
}, MODEL_PATH)

# Save scalers
joblib.dump(scaler_static, SCALER_STATIC_PATH)
joblib.dump(scaler_temporal, SCALER_TEMPORAL_PATH)

print("✅ Model & scalers saved")

# Hàm inference Bayesian

def mc_dropout_predict(model, seq, static, lengths, n_samples=30):
    model.train()  # quan trọng: bật dropout

    probs = []
    for _ in range(n_samples):
        logits = model(seq, static, lengths)
        probs.append(torch.softmax(logits, dim=1).detach().cpu().numpy())

    probs = np.stack(probs)
    mean_prob = probs.mean(axis=0)
    uncertainty = probs.var(axis=0).mean(axis=1)

    return mean_prob, uncertainty

# Validation + Uncertainty
model.eval()

with torch.no_grad():
    seq, static, label, lengths = next(iter(val_loader))
    seq = seq.to(device)
    static = static.to(device)
    lengths = lengths.to(device)

mean_prob, uncertainty = mc_dropout_predict(
    model, seq, static, lengths, n_samples=30
)

print("Mean Prob:", mean_prob[:5])
print("Uncertainty:", uncertainty[:5])
