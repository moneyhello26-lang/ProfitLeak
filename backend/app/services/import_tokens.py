import base64
import hashlib
import hmac
import json
import time
from uuid import UUID

from app.core.config import get_settings
from app.services.import_parser import FileProblem


def signature(payload: str) -> str:
    key = get_settings().import_signing_key.get_secret_value().encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def issue_token(business_id: UUID, kind: str, file_sha256: str) -> tuple[str, int]:
    expires = int(time.time()) + get_settings().import_token_ttl_seconds
    content = json.dumps(
        {"business": str(business_id), "kind": kind, "sha256": file_sha256, "expires": expires},
        sort_keys=True,
    )
    payload = base64.urlsafe_b64encode(content.encode()).decode()
    return payload + "." + signature(payload), expires


def verify_token(token: str, business_id: UUID, kind: str, file_sha256: str):
    try:
        payload, supplied = token.split(".")
        if not hmac.compare_digest(signature(payload), supplied):
            raise ValueError("Invalid signature")
        receipt = json.loads(base64.urlsafe_b64decode(payload))
        if receipt["expires"] <= int(time.time()):
            raise FileProblem("preview_expired", "Предпросмотр истёк. Проверьте файл снова.", 409)
        if (receipt["business"], receipt["kind"], receipt["sha256"]) != (
            str(business_id),
            kind,
            file_sha256,
        ):
            raise ValueError("Receipt does not match upload")
    except FileProblem:
        raise
    except (ValueError, TypeError, KeyError) as error:
        raise FileProblem(
            "invalid_preview_token", "Файл или параметры изменились. Проверьте файл снова.", 409
        ) from error
