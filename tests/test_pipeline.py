"""처리 흐름 테스트."""

from aimp.api.routes import RECOMMEND_PATH


def test_example_request_is_recommended_through_pipeline(client, example_request):
    """예시 요청을 보내면 pipeline.py를 거쳐 200과 recommendCount개 이하의 추천 병원을 1순위부터 반환하는지 확인한다."""
    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 200
    body = response.json()
    assert body["incidentId"] == example_request["incidentId"]
    assert body["requestSeq"] == example_request["requestSeq"]
    ranks = [r["rank"] for r in body["recommendations"]]
    assert 0 < len(ranks) <= example_request["recommendCount"]
    assert ranks == list(range(1, len(ranks) + 1))
