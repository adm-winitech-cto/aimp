"""LLM 호출 인터페이스와 vLLM 구현. 환자 상태 판단(A1)과 최종 선정(E)이 함께 쓴다.

- 인터페이스는 OpenAI chat 형식을 따른다. 메시지는 vLLM /v1/chat/completions에 그대로 보낼 수 있는 형식이고,
  매개변수 이름은 OpenAI SDK의 chat.completions.parse()와 같다.
- 스키마 검사는 LlmClient 구현이 한다. 호출하는 단계는 파싱된 출력만 받는다.
- 구현은 예외를 밖으로 던지지 않고 실패 사유를 반환한다.
- LangChain은 이 파일 안에서만 쓴다.
"""

import logging
import re
import time
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypedDict

import openai
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from transfer_recommender.settings import settings

logger = logging.getLogger(__name__)


class ChatMessage(TypedDict):
    """OpenAI chat 형식의 메시지 하나."""

    role: Literal["system", "user", "assistant"]
    content: str


class LlmFailure(StrEnum):
    """LLM 호출 실패 사유."""

    CALL_FAILED = "호출 실패"  # 연결 오류처럼 vLLM이 응답하지 못함
    VALIDATION_FAILED = "검증 실패"  # LLM 출력이 출력 모델의 스키마 검증을 통과하지 못함
    TIMEOUT = "제한 시간 초과"
    QUEUE_FULL = "vLLM 대기 요청 초과"  # 대기 요청 수가 상한을 넘어 LLM을 호출하지 않음


@dataclass(frozen=True)
class LlmOutput[T: BaseModel]:
    parsed: T  # 출력 모델로 파싱한 출력
    raw: str  # LLM 원문 출력. 감사 로그에 저장한다.


class LlmClient(Protocol):
    def invoke[T: BaseModel](
        self, messages: list[ChatMessage], response_format: type[T], timeout: float
    ) -> LlmOutput[T] | LlmFailure:
        """response_format은 출력 모델, timeout은 제한 시간(초)이다."""
        ...


# vLLM /metrics(Prometheus 형식)의 대기 요청 수 지표. 예: vllm:num_requests_waiting{engine="0",model_name="..."} 0.0
# 이름이 이어지는 다른 지표(vllm:num_requests_waiting_by_reason)는 제외한다.
_WAITING_REQUESTS = re.compile(r"^vllm:num_requests_waiting(?:\{[^}]*\})? (\S+)$", re.MULTILINE)


class VllmClient:
    """LangChain ChatOpenAI로 vLLM의 OpenAI 호환 API를 호출하는 LlmClient 구현.

    - 호출 전에 vLLM /metrics의 대기 요청 수를 읽고, 상한을 넘으면 LLM을 호출하지 않는다.
    - timeout은 대기 요청 수 확인과 LLM 호출을 합친 시간이다.
    - 재시도하지 않는다(max_retries=0). 재시도하면 제한 시간을 넘길 수 있다.
    """

    def __init__(
        self,
        url: str = settings.vllm_url,
        model: str = settings.vllm_model,
        max_waiting_requests: int = settings.vllm_max_waiting_requests,
    ):
        self._metrics_url = f"{url}/metrics"
        self._max_waiting_requests = max_waiting_requests
        # vLLM은 API 키를 검사하지 않지만 ChatOpenAI는 값이 있어야 한다.
        # Qwen3 계열은 기본으로 추론(thinking) 토큰을 수천 개 생성해 호출이 수십 초 걸리므로 끈다.
        self._llm = ChatOpenAI(
            base_url=f"{url}/v1",
            api_key="EMPTY",
            model=model,
            temperature=0,
            max_retries=0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

    def invoke[T: BaseModel](
        self, messages: list[ChatMessage], response_format: type[T], timeout: float
    ) -> LlmOutput[T] | LlmFailure:
        deadline = time.monotonic() + timeout
        try:
            waiting = self._waiting_requests(timeout)
        except Exception:
            logger.warning("vLLM 대기 요청 수 확인 실패 url=%s", self._metrics_url, exc_info=True)
            return LlmFailure.CALL_FAILED
        if waiting > self._max_waiting_requests:
            logger.warning("vLLM 대기 요청 초과 waiting=%s limit=%s", waiting, self._max_waiting_requests)
            return LlmFailure.QUEUE_FULL
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return LlmFailure.TIMEOUT

        # 제한 시간은 요청마다 OpenAI SDK에 넘긴다. 호출마다 ChatOpenAI를 만들면 LangChain이 제한 시간 값마다
        # HTTP 클라이언트를 새로 만들어 캐시에 쌓는다.
        structured = self._llm.with_structured_output(
            response_format, method="json_schema", include_raw=True, timeout=remaining
        )
        try:
            result = structured.invoke(messages)
        except openai.APITimeoutError:
            return LlmFailure.TIMEOUT
        except (ValidationError, openai.LengthFinishReasonError):
            # OpenAI SDK가 출력을 출력 모델로 파싱하다 실패하거나, 출력이 길이 제한에 걸려 잘렸다.
            logger.warning("LLM 출력 검증 실패", exc_info=True)
            return LlmFailure.VALIDATION_FAILED
        except Exception:
            logger.warning("LLM 호출 실패", exc_info=True)
            return LlmFailure.CALL_FAILED
        if result["parsing_error"] is not None or result["parsed"] is None:
            logger.warning("LLM 출력 검증 실패 error=%r", result["parsing_error"])
            return LlmFailure.VALIDATION_FAILED
        return LlmOutput(parsed=result["parsed"], raw=result["raw"].content)

    def _waiting_requests(self, timeout: float) -> float:
        """vLLM 대기 요청 수. 엔진이 여러 개면 합친다."""
        with urllib.request.urlopen(self._metrics_url, timeout=timeout) as resp:
            values = _WAITING_REQUESTS.findall(resp.read().decode())
        if not values:
            raise ValueError("vLLM /metrics에 vllm:num_requests_waiting 지표가 없습니다")
        return sum(float(value) for value in values)
