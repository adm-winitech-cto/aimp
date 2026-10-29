# Changelog

이 파일에는 이 저장소의 주요 변경을 버전별로 기록한다.

형식은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)를 따르고,
버전은 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)을 따른다.
작성 규칙은 [docs/30_개발가이드/34_체인지로그_정책.md](docs/30_개발가이드/34_체인지로그_정책.md),
릴리즈 절차는 [docs/30_개발가이드/33_릴리즈_정책.md](docs/30_개발가이드/33_릴리즈_정책.md)에 있다.

## [Unreleased]

### Changed
- **추천 응답의 `hospitalId`가 응급의료기관 기관ID(hpid)로 바뀐다**: 정적 병원 목록
  (`selection/static_hospitals.py`)의 병원 ID를 8자리 숫자 코드에서 hpid(예: `A2100040`)로 바꿨다.
  hpid가 없는 임신분만 병원 2곳은 병원 ID를 비워 두고 프롬프트 병원 목록과 LLM 출력의 병원 ID 값
  목록에서 빼서, 이 두 병원은 추천하지 않는다.
