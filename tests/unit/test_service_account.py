"""FIREBASE_CREDENTIALS_JSON may be a file path or the raw JSON document."""
import json

import pytest

from sim.adapters.auth.service_account import service_account_info

_DOC = {"type": "service_account", "project_id": "p", "client_email": "x@p.iam"}


def test_sa01_none_when_unset(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert service_account_info("") is None


def test_sa02_path(tmp_path):
    f = tmp_path / "sa.json"
    f.write_text(json.dumps(_DOC), encoding="utf-8")
    assert service_account_info(str(f))["client_email"] == "x@p.iam"


def test_sa03_inline_json():
    assert service_account_info(json.dumps(_DOC))["project_id"] == "p"


def test_sa04_google_application_credentials_fallback(tmp_path, monkeypatch):
    f = tmp_path / "gac.json"
    f.write_text(json.dumps(_DOC), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(f))
    assert service_account_info("")["type"] == "service_account"


def test_sa05_bad_inputs(tmp_path):
    with pytest.raises(RuntimeError):
        service_account_info("{not json")
    with pytest.raises(RuntimeError):
        service_account_info(json.dumps({"type": "authorized_user"}))
    with pytest.raises(RuntimeError):
        service_account_info(str(tmp_path / "missing.json"))
