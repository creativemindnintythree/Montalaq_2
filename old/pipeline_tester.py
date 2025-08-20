import os
import sys
import pandas as pd
from datetime import datetime

# === Ensure project root is in path ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# === Setup Django before importing models or Celery tasks ===
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")
import django
django.setup()

# Stage imports (fixed import path for data_preprocessor)
from fetchers.test_alltick_focused import fetch_alltick_data as fetch_data
from ml_pipeline.data_preprocessor import process_data  # fixed path
from ml_pipeline.ml_model import load_model, run_inference
from celery_tasks.preprocess_features import run_feature_engineering  # NEW import

# === Paths ===
OUTPUT_DIR = os.path.join(BASE_DIR, "pipeline_outputs")
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")
FETCH_CSV = os.path.join(BASE_DIR, "outputs", "focused_EURUSD.csv")
MODEL_PATH = os.path.join(BASE_DIR, "ml_pipeline", "models", "model_v1.pkl")

# Ensure dirs exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

def save_stage_output(df: pd.DataFrame, stage_prefix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(ARCHIVE_DIR, f"{stage_prefix}_output_{timestamp}.csv")
    df.to_csv(archive_path, index=False)

    # Update consistent latest file
    latest_path = os.path.join(OUTPUT_DIR, f"{stage_prefix}_output.csv")
    if os.path.exists(latest_path):
        existing_df = pd.read_csv(latest_path)
        df = pd.concat([existing_df, df]).drop_duplicates().reset_index(drop=True)
    df.to_csv(latest_path, index=False)

    return archive_path

def load_latest_output(stage_prefix: str) -> pd.DataFrame:
    latest_file = os.path.join(OUTPUT_DIR, f"{stage_prefix}_output.csv")
    if not os.path.exists(latest_file):
        raise FileNotFoundError(f"No consistent {stage_prefix} output CSV found.")
    return pd.read_csv(latest_file)

# === Stage Runners ===

def run_fetch():
    try:
        df = fetch_data()
    except Exception as e:
        print(f"⚠ Live fetch failed ({e}), using CSV fallback.")
        if os.path.exists(FETCH_CSV):
            df = pd.read_csv(FETCH_CSV)
        else:
            raise FileNotFoundError("No fetch method or CSV found.")
    path = save_stage_output(df, "fetch")
    print(f"✅ Fetch complete — {len(df)} rows. Archived to {path}")
    return df

def run_preprocess():
    try:
        df = load_latest_output("fetch")
    except FileNotFoundError:
        print("⚠ No fetch output found, running fetch stage...")
        df = run_fetch()
    processed_df = process_data(df)
    path = save_stage_output(processed_df, "preprocess")
    print(f"✅ Preprocess complete — {len(processed_df)} rows. Archived to {path}")
    return processed_df

def run_ml():
    try:
        df = load_latest_output("preprocess")
    except FileNotFoundError:
        print("⚠ No preprocess output found, running preprocess stage...")
        df = run_preprocess()
    model = load_model(MODEL_PATH)
    predictions_df = run_inference(model, df)
    path = save_stage_output(predictions_df, "ml")
    print(f"✅ ML inference complete — {len(predictions_df)} rows. Archived to {path}")
    return predictions_df

def run_full():
    try:
        df = load_latest_output("ml")
    except FileNotFoundError:
        print("⚠ No ml output found, running ML stage...")
        df = run_ml()
    path = save_stage_output(df, "full")
    print(f"🏁 Full pipeline complete — {len(df)} rows. Archived to {path}")
    return df

def run_celery_preprocess(symbol="EUR/USD"):
    print(f"🚀 Sending Celery preprocessing task for {symbol}...")
    task = run_feature_engineering.delay(symbol)
    print(f"✅ Task sent! Task ID: {task.id}")
    print("📡 Check Celery worker logs for progress and results.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline_tester.py [fetch|preprocess|ml|full|celery_preprocess]")
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode == "fetch":
        run_fetch()
    elif mode == "preprocess":
        run_preprocess()
    elif mode == "ml":
        run_ml()
    elif mode == "full":
        run_full()
    elif mode == "celery_preprocess":
        symbol = sys.argv[2] if len(sys.argv) > 2 else "EUR/USD"
        run_celery_preprocess(symbol)
    else:
        print(f"Unknown mode: {mode}")
