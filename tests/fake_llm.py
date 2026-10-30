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
    """정해 둔 결과(정상 출력 또는 실패 사유)를 돌려주고, 받은 호출을 calls에 기록한다.

    results_by_format에 출력 모델별 결과를 두면 그 출력 모델의 호출에는 그 결과를, 나머지 호출에는 result를 돌려준다.
    """

    result: LlmOutput | LlmFailure
    results_by_format: dict[type[BaseModel], LlmOutput | LlmFailure] = field(default_factory=dict)
    calls: list[LlmCall] = field(default_factory=list)

    def invoke[T: BaseModel](
        self, messages: list[ChatMessage], response_format: type[T], timeout: float
    ) -> LlmOutput[T] | LlmFailure:
        self.calls.append(LlmCall(messages, response_format, timeout))
        return self.results_by_format.get(response_format, self.result)
