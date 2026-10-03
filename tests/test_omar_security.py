import os

import pytest
from fastapi import HTTPException

from omar_core.security import require_api_key


def test_security_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("OMAR_API_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_api_key(None)
    assert exc.value.status_code == 503


def test_security_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("OMAR_API_KEY", "correct-secret")
    with pytest.raises(HTTPException) as exc:
        require_api_key("wrong-secret")
    assert exc.value.status_code == 401


def test_security_accepts_correct_key(monkeypatch):
    monkeypatch.setenv("OMAR_API_KEY", "correct-secret")
    assert require_api_key("correct-secret") is None
