from backend.models import NotificationChannel

def run():
    defaults = [
        {"name": "email", "config": {"enabled": False, "to": []}},
        {"name": "webhook", "config": {"enabled": False, "url": ""}},
        {"name": "slack", "config": {"enabled": False, "webhook_url": ""}},
    ]

    for d in defaults:
        obj, created = NotificationChannel.objects.get_or_create(
            name=d["name"], defaults={"config": d["config"]}
        )
        if created:
            print(f"✅ Created channel: {obj.name}")
        else:
            print(f"⚡ Already exists: {obj.name}")

if __name__ == "__main__":
    run()
