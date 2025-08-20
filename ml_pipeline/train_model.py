import pandas as pd
import lightgbm as lgb
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os

# === Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")  # keep inside ml_pipeline/models
MODEL_PATH = os.path.join(MODEL_DIR, "model_v1.pkl")
CSV_PATH = r"C:\Users\AHMED AL BALUSHI\Montalaq_2\pipeline_outputs\preprocess_output_20250810_203106.csv"

# Ensure model dir exists
os.makedirs(MODEL_DIR, exist_ok=True)

# === Load Data ===
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"Preprocessed CSV not found at: {CSV_PATH}")

df = pd.read_csv(CSV_PATH)

# === Target Column Creation ===
# Replace with your actual target logic
if 'ema_20' not in df.columns:
    raise ValueError("Column 'ema_20' not found in preprocessed data.")

df['target'] = (df['close'] > df['ema_20']).astype(int)

# === Feature Selection ===
feature_cols = [
    col for col in df.columns
    if col not in ['timestamp', 'provider', 'target'] and pd.api.types.is_numeric_dtype(df[col])
]

if not feature_cols:
    raise ValueError("No numeric feature columns found for training.")

X = df[feature_cols]
y = df['target']

# === Train/Test Split ===
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

# === LightGBM Dataset ===
dtrain = lgb.Dataset(X_train, label=y_train)
dtest = lgb.Dataset(X_test, label=y_test, reference=dtrain)

# === Model Parameters ===
params = {
    'objective': 'binary',
    'metric': 'binary_error',
    'verbosity': -1
}

# === Train Model ===
model = lgb.train(
    params,
    dtrain,
    valid_sets=[dtrain, dtest],
    num_boost_round=50,
    callbacks=[lgb.early_stopping(stopping_rounds=5)]
)

# === Save Model ===
joblib.dump(model, MODEL_PATH)
print(f"✅ Model saved to: {MODEL_PATH}")

# === Evaluate Model ===
y_pred = (model.predict(X_test) > 0.5).astype(int)
acc = accuracy_score(y_test, y_pred)
print(f"Validation Accuracy: {acc:.4f}")
