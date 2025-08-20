import pandas as pd
import joblib
import os
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report

MODEL_DIR = "ml_pipeline/models_storage"
MODEL_FILE = os.path.join(MODEL_DIR, "lgbm_model.pkl")

class ModelEvaluator:
    @staticmethod
    def evaluate(test_df: pd.DataFrame, label_col: str):
        if not os.path.exists(MODEL_FILE):
            raise FileNotFoundError("No trained model found for evaluation.")

        model = joblib.load(MODEL_FILE)
        X_test = test_df.drop(columns=[label_col])
        y_test = test_df[label_col]

        preds = model.predict(X_test)
        pred_labels = preds.argmax(axis=1)

        metrics = {
            'accuracy': accuracy_score(y_test, pred_labels),
            'precision_macro': precision_score(y_test, pred_labels, average='macro', zero_division=0),
            'recall_macro': recall_score(y_test, pred_labels, average='macro', zero_division=0),
            'f1_macro': f1_score(y_test, pred_labels, average='macro', zero_division=0),
            'roc_auc_ovr': roc_auc_score(y_test, preds, multi_class='ovr') if len(set(y_test)) > 2 else None,
            'classification_report': classification_report(y_test, pred_labels)
        }

        return metrics

if __name__ == "__main__":
    # Example usage
    df = pd.read_csv("ml_pipeline/ML_ready_EURUSD.csv")
    label_col = "signal"
    results = ModelEvaluator.evaluate(df, label_col)
    for k, v in results.items():
        print(f"{k}: {v}")