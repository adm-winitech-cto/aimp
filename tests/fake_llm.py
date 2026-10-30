"""테스트용 가짜 LlmClient."""

from dataclasses import dataclass, field

from pydantic import BaseModel

from aimp.ports.llm import ChatMessage, LlmFailure, LlmOutput


@dataclass(frozen=True)
class LlmCall:
    messages: list[ChatMessage]
    response_format: type[BaseModel]
    timeout: float


@dataclass
class FakeLlmClient:
    """정해 둔 결과(정상 출력 또는 실패 사유)를 돌려주고, 받은 호출을 calls에 기록한다."""

    result: LlmOutput | LlmFailure
    calls: list[LlmCall] = field(default_factory=list)

    def invoke[T: BaseModel](
        self, messages: list[ChatMessage], response_format: type[T], timeout: float
    ) -> LlmOutput[T] | LlmFailure:
        self.calls.append(LlmCall(messages, response_format, timeout))
        return self.result
