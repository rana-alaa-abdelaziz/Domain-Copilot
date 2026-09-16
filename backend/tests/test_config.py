import importlib

import pytest


def test_missing_secret_key_in_production_raises(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    
    from backend.infrastructure import config
    importlib.reload(config)
    
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.Settings()


def test_short_secret_key_raises(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "too_short")
    
    from backend.infrastructure import config
    importlib.reload(config)
    
    with pytest.raises(RuntimeError, match="32 bytes"):
        config.Settings()


def test_development_mode_generates_a_usable_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    
    from backend.infrastructure import config
    importlib.reload(config)
    
    settings = config.Settings()
    assert len(settings.secret_key.encode("utf-8")) >= 32
