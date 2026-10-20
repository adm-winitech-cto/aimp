"""로깅 설정 테스트."""

import logging

from transfer_recommender.logging_config import configure_logging


def test_log_level_applies_to_uvicorn_loggers(monkeypatch):
    """LOG_LEVEL 환경 변수가 앱 로그뿐 아니라 uvicorn 로그(access log 포함)에도 적용되는지 확인한다."""
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()
    try:
        assert not logging.getLogger("transfer_recommender.main").isEnabledFor(logging.INFO)
        assert not logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO)
        assert not logging.getLogger("uvicorn.error").isEnabledFor(logging.INFO)
    finally:
        # 다른 테스트에 영향을 주지 않도록 기본 설정(INFO)으로 되돌린다.
        monkeypatch.delenv("LOG_LEVEL")
        configure_logging()
