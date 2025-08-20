import os
import pickle
import hashlib
from typing import Any, Optional

_MODEL = None
_MODEL_PATH = os.environ.get(
    "ML_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "models", "model_v1.pkl")
)
_MODEL_VERSION = "v1"  # keep in sync with training metadata
_MODEL_HASH_PREFIX: Optional[str] = None


def _compute_hash_prefix(path: str, n: int = 8) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def get() -> Optional[Any]:
    global _MODEL, _MODEL_HASH_PREFIX
    if _MODEL is None:
        if not os.path.exists(_MODEL_PATH):
            return None
        with open(_MODEL_PATH, "rb") as f:
            _MODEL = pickle.load(f)
        _MODEL_HASH_PREFIX = _compute_hash_prefix(_MODEL_PATH)
    return _MODEL


def get_version() -> str:
    return _MODEL_VERSION


def get_hash_prefix() -> Optional[str]:
    return _MODEL_HASH_PREFIX


def configure_model_path(path: str) -> None:
    global _MODEL, _MODEL_PATH, _MODEL_HASH_PREFIX
    _MODEL = None
    _MODEL_HASH_PREFIX = None
    _MODEL_PATH = path
