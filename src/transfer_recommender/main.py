"""FastAPI 앱 진입점."""

import logging

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from transfer_recommender.api.routes import router
from transfer_recommender.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

MAX_LOGGED_BODY_BYTES = 64 * 1024

app = FastAPI(title="응급환자 이송 병원 추천")
app.include_router(router)


@app.middleware("http")
async def log_request_body(request: Request, call_next: RequestResponseEndpoint) -> Response:
    # 요청 검증 전에 남기므로 검증에 실패한 요청과 처리 중 예외가 난 요청의 본문도 기록된다.
    # 요청 본문에는 환자 정보(나이, 위치, 비고 등)가 그대로 들어간다.
    body = await request.body()
    if body:
        logger.info(
            "요청 본문 path=%s body=%r",
            request.url.path,
            body[:MAX_LOGGED_BODY_BYTES].decode("utf-8", errors="replace"),
        )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_to_400(request: Request, exc: RequestValidationError) -> JSONResponse:
    # interface.md '필수 여부 규칙': 요청 검증에 실패하면 FastAPI 기본값인 422 대신 400을 반환한다.
    # 오류의 input 항목은 환자 정보를 담은 요청 본문을 그대로 되돌려 주므로 응답에서 뺀다.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    # 요청 본문은 log_request_body가 남기므로, 여기서는 오류 위치와 종류만 한 줄로 남긴다.
    logger.warning(
        "요청 검증 실패 path=%s errors=%s",
        request.url.path,
        ", ".join(f"{'.'.join(map(str, e['loc']))}:{e['type']}" for e in errors),
    )
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": errors})
