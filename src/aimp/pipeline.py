"""처리 흐름. PRD_v0.1.md §3 '처리 순서'대로 처리 단계를 호출하고, 각 단계가 낸 경고를 모은다.

아직 붙이지 않은 처리 단계: 진료 역량 규칙 엔진(#23), 최종 선정(#18), 최종 선정 fallback(#19).
최종 선정 fallback을 붙이기 전까지는 후보 병원 중 직선거리가 가까운 병원 N개를 추천한다.
"""

from aimp.api.request import RecommendRequest
from aimp.classification import patient_assessment, severe_resource, severity
from aimp.common.settings import settings
from aimp.domain.eta import EtaMethod
from aimp.domain.hospital import Hospital
from aimp.domain.recommendation import PipelineResult, RecommendedHospital
from aimp.domain.types import Level, WarningCode
from aimp.engines import guideline, travel
from aimp.ports.eta_provider import EtaProvider
from aimp.ports.hospital_repository import HospitalRepository
from aimp.ports.llm import LlmClient


def run(
    req: RecommendRequest,
    llm_client: LlmClient,
    hospital_repository: HospitalRepository,
    eta_provider: EtaProvider,
) -> PipelineResult:
    warnings: list[WarningCode] = []  # 각 단계가 경고를 이 목록에 추가
    if req.patient.vital_signs is None:  # 4대 중증 환자를 포함한 모든 환자
        warnings.append(WarningCode.NO_VITAL_SIGNS)
    severe_judgment = severe_resource.judge(req.patient)  # A0
    assessment = patient_assessment.assess(req.patient, llm_client, warnings)  # A1, 모든 환자. LLM이 실패하면 None
    # A2, 4대 중증이 아닐 때만. assessment가 None이면 비외상 기준
    category = severe_judgment.category or severity.judge(req.patient, assessment)
    special = severity.special_situations(req.patient, category, assessment)  # 외상 환자만

    levels = guideline.levels_for(category)  # B: [L0 조건, L1 조건]
    location = req.patient.location
    # C0: L0·L1 조건의 병원 분류를 합쳐 한 번만 조회한다. 조회가 실패하면 HospitalLookupError가 그대로 나간다.
    hospitals = hospital_repository.find_by_categories(
        location.longitude, location.latitude, frozenset().union(*(condition.categories for condition in levels))
    )
    level: Level | None = None
    candidates: list[Hospital] = []
    for condition in levels:  # C: 후보 병원이 0곳이면 다음 레벨. L1 조건으로도 0곳이면 추천하지 않는다
        candidates = [hospital for hospital in hospitals if hospital.categories & condition.categories]
        if candidates:
            level = condition.level
            break

    # C: 도착시간·거리 규칙 엔진. 직선거리가 가까운 후보 병원 M개(llm_candidate_count)만 남긴다
    candidates = travel.nearest(candidates)

    # E 자리: 최종 선정 fallback(#19)을 붙이기 전까지 직선거리가 가까운 병원 N개를 추천한다.
    picked = candidates[: req.recommend_count or settings.recommend_count]

    # F: 선정된 N개에만 ETA를 구한다. 순위는 바꾸지 않는다
    etas = eta_provider.estimate(location.longitude, location.latitude, picked) if picked else []
    if any(eta.method == EtaMethod.STRAIGHT_LINE for eta in etas):
        warnings.append(WarningCode.ETA_FAILED)
    return PipelineResult(
        recommendations=tuple(
            RecommendedHospital(
                hospital_id=h.hospital_id, hospital_name=h.name, reason=f"직선거리 {h.distance_km:.1f}km", eta=eta
            )
            for h, eta in zip(picked, etas, strict=True)
        ),
        warnings=tuple(warnings),
        severe_judgment=severe_judgment,
        assessment=assessment,
        category=category,
        special_situations=special,
        level=level,
    )
