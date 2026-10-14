"""Small in-memory response cache and quota pause for the selected provider key."""

import hashlib
import json
import math
import time
from collections import OrderedDict
from threading import RLock

from app.core.config import Settings

_lock = RLock()
_answers = OrderedDict()
_pauses = OrderedDict()
MAX_ENTRIES = 128


def identity(settings: Settings) -> str:
    value = settings.llm_provider + "/" + settings.provider_api_key
    return hashlib.sha256(value.encode()).hexdigest()


def cache_key(settings: Settings, business_id, payload: dict) -> str:
    value = json.dumps(
        [identity(settings), str(business_id), payload],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


def get(key: str, enabled: bool):
    if not enabled:
        return None
    with _lock:
        found = _answers.get(key)
        if found and found[0] > time.monotonic():
            _answers.move_to_end(key)
            return found[1]
        _answers.pop(key, None)
    return None


def put(key: str, value, ttl: int):
    if not ttl:
        return
    with _lock:
        _answers[key] = (time.monotonic() + ttl, value)
        _answers.move_to_end(key)
        while len(_answers) > MAX_ENTRIES:
            _answers.popitem(last=False)


def pause(settings: Settings, reason: str, seconds: int):
    with _lock:
        key = identity(settings)
        _pauses[key] = (time.monotonic() + seconds, reason)
        _pauses.move_to_end(key)
        while len(_pauses) > MAX_ENTRIES:
            _pauses.popitem(last=False)


def paused(settings: Settings):
    with _lock:
        key = identity(settings)
        found = _pauses.get(key)
        if found:
            remaining = math.ceil(found[0] - time.monotonic())
            if remaining > 0:
                return found[1], remaining
            _pauses.pop(key, None)
    return None


def clear():
    with _lock:
        _answers.clear()
        _pauses.clear()
