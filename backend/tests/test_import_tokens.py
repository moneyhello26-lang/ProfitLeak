from uuid import uuid4

import pytest

from app.services import import_tokens
from app.services.import_parser import FileProblem
from app.services.import_tokens import issue_token, verify_token


def test_valid_token_and_tampering():
    business = uuid4()
    token, _ = issue_token(business, "sales", "a" * 64)
    verify_token(token, business, "sales", "a" * 64)
    for candidate, owner, kind, digest in [
        (token + "0", business, "sales", "a" * 64),
        (token, uuid4(), "sales", "a" * 64),
        (token, business, "expenses", "a" * 64),
        (token, business, "sales", "b" * 64),
        ("invalid", business, "sales", "a" * 64),
    ]:
        with pytest.raises(FileProblem) as error:
            verify_token(candidate, owner, kind, digest)
        assert error.value.code == "invalid_preview_token"


def test_expired_token(monkeypatch):
    business = uuid4()
    token, expires = issue_token(business, "sales", "a" * 64)
    monkeypatch.setattr(import_tokens.time, "time", lambda: expires)
    with pytest.raises(FileProblem) as error:
        verify_token(token, business, "sales", "a" * 64)
    assert error.value.code == "preview_expired"
