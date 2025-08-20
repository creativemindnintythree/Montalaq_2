# C:\Users\AHMED AL BALUSHI\Montalaq_2\provider_manager\manager.py

import yaml
import os
import time
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()  # Load from .env

class ProviderManager:
    _instance = None

    def __init__(self, config_path="C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\provider_manager\\providers.yaml"):
        with open(config_path, "r") as f:
            self.providers = yaml.safe_load(f)

        self.usage = defaultdict(lambda: {
            "second": {"count": 0, "reset": time.time() + 1},
            "minute": {"count": 0, "reset": time.time() + 60},
            "daily": {"count": 0, "reset": time.time() + 86400}
        })

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def reset_window_if_needed(self, provider_name):
        usage = self.usage[provider_name]
        now = time.time()

        if now > usage["second"]["reset"]:
            usage["second"]["count"] = 0
            usage["second"]["reset"] = now + 1

        if now > usage["minute"]["reset"]:
            usage["minute"]["count"] = 0
            usage["minute"]["reset"] = now + 60

        if now > usage["daily"]["reset"]:
            usage["daily"]["count"] = 0
            usage["daily"]["reset"] = now + 86400

    def is_under_limit(self, provider_name):
        self.reset_window_if_needed(provider_name)
        limits = self.providers[provider_name]["rate_limit"]
        usage = self.usage[provider_name]

        for period in ["second", "minute", "daily"]:
            if period in limits:
                max_allowed = limits[period]
                if usage[period]["count"] >= 0.75 * max_allowed:
                    return False
        return True

    def choose_available_providers(self, required_endpoint=""):
        valid = []
        for name in self.providers:
            if self.is_under_limit(name):
                if required_endpoint:
                    if self.providers[name].get("endpoint"):
                        valid.append(name)
                else:
                    valid.append(name)
        return valid

    def get_provider_config(self, name):
        return self.providers.get(name)

    def get_api_key(self, name):
        var_name = self.providers[name]["api_key_env_var"]
        return os.getenv(var_name)

    def record_usage(self, name, calls=1):
        self.reset_window_if_needed(name)
        for period in ["second", "minute", "daily"]:
            self.usage[name][period]["count"] += calls

