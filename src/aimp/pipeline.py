"""처리 흐름. PRD_v0.1.md §3 '처리 순서'대로 처리 단계를 호출하고, 각 단계가 낸 경고를 모은다.

아직 붙이지 않은 처리 단계: 최종 선정(#18).
최종 선정 LLM을 붙이기 전까지는 최종 선정 대신 최종 선정 fallback으로 후보 병원 중 직선거리가 가까운 병원 N개를 추천한다.
"""

from datetime import datetime, timedelta, timezone

from aimp.api.request import RecommendRequest
from aimp.classification import patient_assessment, severe_resource, severity
from aimp.common.settings import settings
from aimp.domain.eta import EtaMethod
from aimp.domain.recommendation import PipelineResult, RecommendedHospital
from aimp.domain.types import WarningCode
from aimp.engines import capability, guideline, travel
from aimp.engines.capability import CandidateHospital
from aimp.engines.guideline import LevelCondition
from aimp.ports.eta_provider import EtaProvider
from aimp.ports.hospital_repository import HospitalRepository
from aimp.ports.llm import LlmClient
from aimp.selection import fallback
from aimp.selection.reasons import PatientContext

KST = timezone(timedelta(hours=9))  # 병원 데이터의 병상 갱신 시각(beds_updated_at)은 시간대 정보 없는 KST다


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
    # 병원정보 조회 시각. 진료 역량 규칙 엔진이 병상 데이터 신선도를 판정할 때 쓴다
    queried_at = datetime.now(KST).replace(tzinfo=None)
    # C0: L0·L1 조건의 병원 분류를 합쳐 한 번만 조회한다. 조회가 실패하면 HospitalLookupError가 그대로 나간다.
    hospitals = hospital_repository.find_by_categories(
        location.longitude, location.latitude, frozenset().union(*(condition.categories for condition in levels))
    )
    chosen: LevelCondition | None = None  # 후보 병원을 고른 레벨의 조건. 추천 사유의 병원 분류 조건 충족에 쓴다
    candidates: list[CandidateHospital] = []
    for condition in levels:  # C: 후보 병원이 0곳이면 다음 레벨. L1 조건으로도 0곳이면 추천하지 않는다
        matched = [hospital for hospital in hospitals if hospital.categories & condition.categories]
        capability_warnings: list[WarningCode] = []
        # C: 진료 역량 규칙 엔진. 진료 역량 조건은 레벨이 내려가도 낮추지 않는다.
        # 엔진이 붙인 태그(병상 정보 오래됨, 분만 가능)는 추천 사유에 쓰므로 후보 병원에 붙인 채 넘긴다
        if settings.capability_engine_enabled:
            candidates, capability_warnings = capability.filter_candidates(
                matched, severe_judgment, assessment, category, queried_at, llm_client
            )
        else:
            candidates = [CandidateHospital(hospital, stale_beds=False) for hospital in matched]
        if candidates:
            chosen = condition
            warnings.extend(capability_warnings)  # 추천에 쓰는 레벨의 경고만 넣는다
            break

    # C: 도착시간·거리 규칙 엔진. 직선거리가 가까운 후보 병원 M개(llm_candidate_count)만 남긴다
    candidates = travel.nearest(candidates)

    recommendations: tuple[RecommendedHospital, ...] = ()
    if chosen is not None:  # L1 조건으로도 후보 병원이 0곳이면 병원을 고르지 않고 ETA도 구하지 않는다
        # E: 최종 선정 LLM(#18)을 붙이기 전까지 최종 선정 fallback으로 고른다
        count = req.recommend_count or settings.recommend_count
        picked = fallback.select(candidates, count, req.patient.remark, warnings)

        # F: 선정된 N개에만 ETA를 구한다. 순위는 바꾸지 않는다
        etas = eta_provider.estimate(location.longitude, location.latitude, [c.hospital for c in picked])
        if any(eta.method == EtaMethod.STRAIGHT_LINE for eta in etas):
            warnings.append(WarningCode.ETA_FAILED)
        patient = PatientContext(chosen, severe_judgment, assessment)
        recommendations = tuple(
            RecommendedHospital(
                hospital_id=candidate.hospital.hospital_id,
                hospital_name=candidate.hospital.name,
                reason=fallback.reason(candidate, patient, eta),
                eta=eta,
            )
            for candidate, eta in zip(picked, etas, strict=True)
        )
    return PipelineResult(
        recommendations=recommendations,
        warnings=tuple(warnings),
        severe_judgment=severe_judgment,
        assessment=assessment,
        category=category,
        special_situations=special,
        level=chosen.level if chosen else None,
        fallback=chosen is not None,
        fallback_reason=None,  # 최종 선정 LLM을 붙이기 전이라 LLM을 부르지 않았다
    )
