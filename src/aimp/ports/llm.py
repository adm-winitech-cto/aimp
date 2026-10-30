"""LLM 호출 인터페이스. 환자 상태 판단(A1), 진료 역량 규칙 엔진(C)의 진료불가 메시지 판단, 최종 선정(E)이 함께 쓴다.

- 인터페이스는 OpenAI chat 형식을 따른다. 메시지는 vLLM /v1/chat/completions에 그대로 보낼 수 있는 형식이고,
  매개변수 이름은 OpenAI SDK의 chat.completions.parse()와 같다.
- 스키마 검사는 LlmClient 구현이 한다. 호출하는 단계는 파싱된 출력만 받는다.
- 구현은 예외를 밖으로 던지지 않고 실패 사유를 반환한다.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypedDict

from pydantic import BaseModel


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
