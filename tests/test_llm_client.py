"""vLLM LlmClient 구현(VllmClient) 테스트. vLLM의 /metrics와 /v1/chat/completions를 흉내 내는 HTTP 서버를 띄워 확인한다."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from transfer_recommender.llm_client import LlmFailure, LlmOutput, VllmClient

MESSAGES = [{"role": "system", "content": "지시문"}, {"role": "user", "content": "{}"}]
WAITING_0 = 'vllm:num_requests_waiting{engine="0",model_name="m"} 0.0\n'


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["a", "b"]


class FakeVllm(ThreadingHTTPServer):
    """테스트마다 /metrics 본문과 chat completions 응답을 정해 둔다. 받은 chat completions 요청 본문을 기록한다."""

    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.metrics = WAITING_0
        self.content = '{"label": "a"}'
        self.finish_reason = "stop"
        self.status = 200
        self.delay_seconds = 0.0
        self.chat_requests: list[dict] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Handler(BaseHTTPRequestHandler):
    server: FakeVllm

    def do_GET(self):
        self._send(200, self.server.metrics.encode(), "text/plain")

    def do_POST(self):
        self.server.chat_requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        time.sleep(self.server.delay_seconds)
        body = {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": self.server.content},
                    "finish_reason": self.server.finish_reason,
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        self._send(self.server.status, json.dumps(body).encode(), "application/json")

    def _send(self, status: int, body: bytes, content_type: str):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 제한 시간 초과 테스트에서 클라이언트가 먼저 연결을 끊는다.

    def log_message(self, format, *args):
        pass


@pytest.fixture
def vllm():
    server = FakeVllm()
    # serve_forever 기본 폴링 간격(0.5초)이면 shutdown()이 테스트마다 최대 0.5초를 기다린다.
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _invoke(vllm: FakeVllm, timeout: float = 3.0, max_waiting_requests: int = 8):
    client = VllmClient(url=vllm.url, model="m", max_waiting_requests=max_waiting_requests)
    return client.invoke(MESSAGES, Answer, timeout)


def test_success_returns_parsed_and_raw_output(vllm):
    """정상 출력이면 출력 모델로 파싱한 값과 LLM 원문 출력을 반환하는지 확인한다."""
    assert _invoke(vllm) == LlmOutput(parsed=Answer(label="a"), raw='{"label": "a"}')


def test_request_uses_messages_json_schema_and_temperature_0(vllm):
    """메시지 목록을 그대로 보내고, 출력 모델의 JSON 스키마로 structured outputs를 요청하고, temperature 0을 쓰는지 확인한다."""
    _invoke(vllm)

    [request] = vllm.chat_requests
    assert request["model"] == "m"
    assert request["messages"] == MESSAGES
    assert request["temperature"] == 0
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["schema"]["properties"]["label"]["enum"] == ["a", "b"]


@pytest.mark.parametrize(
    ("content", "finish_reason"),
    [('{"label": "c"}', "stop"), ('{"label": ', "stop"), ('{"label": "a"}', "length")],
    ids=["value-outside-schema", "invalid-json", "truncated-by-length"],
)
def test_invalid_output_is_validation_failure(vllm, content, finish_reason):
    """출력이 스키마에 맞지 않거나, JSON이 아니거나, 길이 제한에 걸려 잘리면 검증 실패인지 확인한다."""
    vllm.content = content
    vllm.finish_reason = finish_reason

    assert _invoke(vllm) == LlmFailure.VALIDATION_FAILED


def test_slow_response_is_timeout(vllm):
    """응답이 제한 시간보다 늦으면 제한 시간 초과인지 확인한다. 재시도하지 않으므로 요청은 1건이다."""
    vllm.delay_seconds = 1.0

    assert _invoke(vllm, timeout=0.2) == LlmFailure.TIMEOUT
    assert len(vllm.chat_requests) == 1


@pytest.mark.parametrize(
    ("metrics", "failure"),
    [
        ('vllm:num_requests_waiting{engine="0",model_name="m"} 9.0\n', LlmFailure.QUEUE_FULL),
        (
            'vllm:num_requests_waiting{engine="0",model_name="m"} 5.0\n'
            'vllm:num_requests_waiting{engine="1",model_name="m"} 4.0\n',
            LlmFailure.QUEUE_FULL,
        ),
        ("vllm:num_requests_running 0.0\n", LlmFailure.CALL_FAILED),
    ],
    ids=["over-limit", "sum-of-engines-over-limit", "metric-missing"],
)
def test_waiting_requests_checked_before_call(vllm, metrics, failure):
    """대기 요청 수(엔진이 여러 개면 합)가 상한(8)을 넘거나 지표가 없으면 LLM을 호출하지 않는지 확인한다."""
    vllm.metrics = metrics

    assert _invoke(vllm) == failure
    assert vllm.chat_requests == []


def test_waiting_requests_at_limit_calls_llm(vllm):
    """대기 요청 수가 상한과 같으면 호출하는지 확인한다. 이름이 이어지는 다른 지표(_by_reason)는 세지 않는다."""
    vllm.metrics = (
        "# HELP vllm:num_requests_waiting Number of requests waiting.\n"
        'vllm:num_requests_waiting{engine="0",model_name="m"} 8.0\n'
        'vllm:num_requests_waiting_by_reason{engine="0",model_name="m",reason="capacity"} 100.0\n'
    )

    assert isinstance(_invoke(vllm), LlmOutput)


def test_server_error_is_call_failure(vllm):
    """vLLM이 오류 응답을 보내면 호출 실패인지 확인한다."""
    vllm.status = 500

    assert _invoke(vllm) == LlmFailure.CALL_FAILED


def test_unreachable_server_is_call_failure():
    """vLLM 서버에 연결할 수 없으면 호출 실패인지 확인한다."""
    server = FakeVllm()
    url = server.url
    server.server_close()  # 포트를 닫아 연결이 거부되게 한다.

    assert VllmClient(url=url, model="m").invoke(MESSAGES, Answer, 3.0) == LlmFailure.CALL_FAILED
