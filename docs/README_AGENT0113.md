# Agent 011.3 — ML Integration & Composite Score (Stabilized)

## Run locally
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
celery -A montalaq_project worker -B -l info
