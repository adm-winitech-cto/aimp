"""로깅 설정.

- 앱은 로그를 표준 출력으로 내보낸다. 컨테이너에서는 Docker가 표준 출력을 수집하고,
  docker-compose.yml의 logging 설정으로 로그 파일을 순환한다.
- 로그 레벨은 LOG_LEVEL 환경 변수로 정한다(기본 INFO).
- 요청 본문은 INFO 레벨로 남는다(main.log_request_body). 요청 본문에는 환자 정보(나이, 위치, 비고 등)가 들어 있다.
"""

import logging.config
import os

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": LOG_FORMAT}},
            "handlers": {
                "stdout": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
            },
            "root": {"handlers": ["stdout"], "level": level},
            # uvicorn이 붙인 자체 핸들러를 떼고 root 핸들러로 보내서, uvicorn 로그도 같은 형식과 같은 레벨로 출력한다.
            "loggers": {
                name: {"handlers": [], "propagate": True, "level": level}
                for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
            },
        }
    )
