import time
from celery.result import AsyncResult
from celery_tasks.preprocess_features import run_feature_engineering
from backend.models import MarketDataFeatures
import django
import os
import sys

# Set up Django environment before importing models
def setup_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")
    django.setup()

def test_celery_preprocess(symbol):
    print(f"\U0001F680 Sending Celery preprocessing task for {symbol}...")
    task = run_feature_engineering.delay(symbol)
    print(f"\u2705 Task sent! Task ID: {task.id}")

    print("\u23f3 Waiting for task to complete...")
    start_time = time.time()
    while True:
        result = AsyncResult(task.id)
        if result.ready():
            break
        time.sleep(2)

    duration = time.time() - start_time
    if result.successful():
        print(f"\u2705 Task completed in {duration:.2f} seconds.")
        try:
            count = MarketDataFeatures.objects.count()
            print(f"\U0001F4C8 Total rows in MarketDataFeatures: {count}")
        except Exception as e:
            print(f"\u26A0 Could not fetch DB row count: {e}")
    else:
        print(f"\u274C Task failed after {duration:.2f} seconds.")
        print(f"Error: {result.result}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python celery_tester.py <SYMBOL>")
        sys.exit(1)
    setup_django()
    test_celery_preprocess(sys.argv[1])
