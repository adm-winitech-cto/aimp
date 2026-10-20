"""설정값. design.md '미결 사항'의 설정값 항목이며 아직 확정되지 않았다.

design.md에 예시값이 있으면 예시값을, 없으면 임시값을 쓴다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    recommend_count: int = 3  # N: 추천 개수 (design.md 기본값)
    llm_candidate_count: int = 15  # M: LLM 프롬프트에 넣는 후보 수 (design.md 예시 범위 10~15)
    detour_threshold_km: float = 3.0  # X: 우회 판정 거리 기준 (임시값)
    bed_data_max_age_minutes: int = 15  # 병상 데이터 신선도 임계치 (design.md 예시 범위 10~15분)
    require_icu_beds: bool = False  # 중증 환자에게 중환자실 가용병상 조건 적용 여부 (임시값, 의료진 확인 필요)
    llm_timeout_seconds: float = 5.0  # 최종 선정 LLM 호출 제한 시간 (design.md 예시값)
    vllm_max_waiting_requests: int = 8  # vLLM 대기 요청 수가 이 값을 넘으면 LLM을 호출하지 않음 (임시값)
    eta_speed_kmh: float = 40.0  # 직선거리 기반 ETA 추정 속도 (임시값)
    prompt_version: str = "final_selection_v1"  # 최종 선정 프롬프트 버전


settings = Settings()
