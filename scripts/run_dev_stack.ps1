# Dev convenience script
$env:DJANGO_SETTINGS_MODULE="montalaq_project.settings"
$env:PYTHONPATH="$PWD"

Write-Host "Applying migrations..."
python manage.py migrate

Write-Host "Starting Celery worker + beat (TEMPORARY bridge)..."
celery -A montalaq_project worker -B -l info
