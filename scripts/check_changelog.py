#!/usr/bin/env python3
"""CHANGELOG.md 를 검사한다 (docs/30_개발가이드/34_체인지로그_정책.md §8).

    python3 scripts/check_changelog.py                        # 구조·중복·링크
    git diff --name-only origin/main...HEAD \\
      | python3 scripts/check_changelog.py --changed -        # 항목 누락까지
    git diff --name-only origin/main...HEAD \\
      | python3 scripts/check_changelog.py --changed - --skip-entry-check   # no-changelog 라벨 PR

항목 하나가 길고 파일이 길어서, 누락·중복·링크 빠짐은 사람이 눈으로 읽어서는 잘 걸러지지
않는다. 머지 충돌 해결 화면에서는 더 안 보인다. 그래서 기계가 본다.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# TOFIX: agent 레포 루트에 CHANGELOG.md를 새로 만들어야 한다. 지금 agent 저장소에는 CHANGELOG.md가 없어 main()이 "CHANGELOG.md 가 없습니다"를 출력하고 1로 끝난다.
CHANGELOG = Path("CHANGELOG.md")
UNRELEASED = "Unreleased"

SECTION_RE = re.compile(r"^##\s+\[([^\]]+)\]")
RELEASE_HEADING_RE = re.compile(
    r"^##\s+\[(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$"
)
SUBSECTION_RE = re.compile(r"^###\s+(.+?)\s*$")
LINK_RE = re.compile(r"^\[([^\]]+)\]:\s+\S+")
ENTRY_PREFIX = "- "

# CHANGELOG 항목이 필요 없는 변경. 쓰는 사람이 보는 동작이 그대로인 것들이다 (정책 §7).
EXEMPT_PATTERNS = (
    re.compile(r"^docs/"),
    re.compile(r"^\.github/ISSUE_TEMPLATE/"),
    re.compile(r"^tests?/"),
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"_test\.py$"),
    re.compile(r"\.test\.tsx?$"),
    re.compile(r"\.spec\.tsx?$"),
    re.compile(r"^CHANGELOG\.md$"),
    re.compile(r"^\.gitignore$"),
    re.compile(r"^LICENSE$"),
    re.compile(r"(^|/)README\.md$"),
)


def strip_comments(text: str) -> str:
    """HTML 주석을 지운다. 주석 안의 안내문이 항목·헤더로 읽히지 않게 한다."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def parse_sections(lines: list[str]) -> dict[str, list[str]]:
    """버전 헤더별 항목 목록. 헤더 순서를 유지한다."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        matched = SECTION_RE.match(line)
        if matched:
            current = matched.group(1)
            sections.setdefault(current, [])
        elif current is not None and line.startswith(ENTRY_PREFIX):
            sections[current].append(line.strip())
    return sections


def check_structure(lines: list[str]) -> list[str]:
    """[Unreleased] 가 맨 위에 있고, 릴리즈 헤더 형식이 맞고, 릴리즈 항목과 겹치지 않는지 본다."""
    errors: list[str] = []
    headings = [line for line in lines if SECTION_RE.match(line)]
    sections = parse_sections(lines)

    if UNRELEASED not in sections:
        errors.append(
            "`## [Unreleased]` 섹션이 없습니다. 다음 릴리즈에 들어갈 항목이 갈 곳이 없으면 "
            "릴리즈를 자를 때 무엇이 새로 들어갔는지 알 수 없습니다."
        )
        return errors

    if SECTION_RE.match(headings[0]).group(1) != UNRELEASED:
        errors.append("`## [Unreleased]` 가 맨 위 섹션이 아닙니다. 새 버전이 위에 오도록 순서를 맞추십시오.")

    for heading in headings:
        name = SECTION_RE.match(heading).group(1)
        if name != UNRELEASED and not RELEASE_HEADING_RE.match(heading):
            errors.append(
                f"릴리즈 헤더 `{heading.strip()}` 의 형식이 `## [X.Y.Z] - YYYY-MM-DD` 가 아닙니다."
            )

    released = {
        entry: name
        for name, entries in sections.items()
        if name != UNRELEASED
        for entry in entries
    }
    for entry in sections[UNRELEASED]:
        if entry in released:
            errors.append(
                f"`[Unreleased]` 의 항목이 이미 릴리즈된 `[{released[entry]}]` 에도 있습니다. "
                f"릴리즈를 자른 뒤 되머지하면 생기는 중복입니다 — `[Unreleased]` 쪽을 지우십시오.\n"
                f"    {entry[:100]}…"
            )
    return errors


def check_duplicate_subsections(lines: list[str]) -> list[str]:
    """한 섹션 안에서 같은 소제목이 두 번 나오는지 본다 (나뉘면 릴리즈를 자를 때 한쪽이 빠진다)."""
    errors: list[str] = []
    current: str | None = None
    seen: dict[str, int] = {}
    for line in lines:
        matched = SECTION_RE.match(line)
        if matched:
            current = matched.group(1)
            seen = {}
            continue
        sub = SUBSECTION_RE.match(line)
        if sub and current is not None:
            name = sub.group(1)
            seen[name] = seen.get(name, 0) + 1
            if seen[name] == 2:
                errors.append(
                    f"`[{current}]` 에 `### {name}` 이 두 번 나옵니다. 소제목당 한 블록으로 합치십시오."
                )
    return errors


def check_links(lines: list[str]) -> list[str]:
    """릴리즈 섹션마다 compare 링크가 있는지 본다 (릴리즈 절차 A-4 누락 방지)."""
    errors: list[str] = []
    released = [name for name in parse_sections(lines) if name != UNRELEASED]
    if not released:
        return errors
    labels = {m.group(1).lower() for m in (LINK_RE.match(line) for line in lines) if m}
    if UNRELEASED.lower() not in labels:
        errors.append(
            "릴리즈가 있는데 파일 끝에 `[unreleased]: …/compare/v<최신>...HEAD` 링크가 없습니다."
        )
    for name in released:
        if name.lower() not in labels:
            errors.append(
                f"`[{name}]` 섹션의 compare 링크가 파일 끝에 없습니다 — `[{name}]: …` 줄을 추가하십시오."
            )
    return errors


def unquote(path: str) -> str:
    """git 이 감싼 따옴표를 벗긴다.

    경로에 한글이 들어가면 git 은 `"docs/30_\\352\\260\\234..."` 처럼 따옴표로 감싸 출력한다.
    그대로 두면 `^docs/` 같은 면제 패턴이 앞의 따옴표에 걸려 빗나가고, 문서만 고친 PR 이
    CHANGELOG 를 요구받는다. 이 저장소는 문서 경로가 한글이라 반드시 걸린다.
    """
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        return path[1:-1]
    return path


def needs_entry(changed: list[str]) -> list[str]:
    """CHANGELOG 항목이 필요한 변경 파일만 남긴다."""
    return [
        path
        for path in changed
        if path and not any(pattern.search(unquote(path)) for pattern in EXEMPT_PATTERNS)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--changed",
        metavar="FILE",
        help="변경된 파일 목록 (한 줄에 하나, '-' 면 stdin). 주면 항목 누락도 검사한다.",
    )
    parser.add_argument(
        "--skip-entry-check",
        action="store_true",
        help="항목 누락 검사를 건너뛴다 (no-changelog 라벨이 붙은 PR).",
    )
    args = parser.parse_args()

    if not CHANGELOG.exists():
        print("CHANGELOG.md 가 없습니다. 저장소 루트에서 실행하십시오.", file=sys.stderr)
        return 1

    lines = strip_comments(CHANGELOG.read_text(encoding="utf-8")).splitlines()
    errors = check_structure(lines)
    errors += check_duplicate_subsections(lines)
    errors += check_links(lines)

    if args.changed and not args.skip_entry_check:
        source = sys.stdin if args.changed == "-" else open(args.changed, encoding="utf-8")
        with source as handle:
            changed = [unquote(line.strip()) for line in handle]
        product_changes = needs_entry(changed)
        if product_changes and "CHANGELOG.md" not in changed:
            listed = "\n".join(f"    {p}" for p in product_changes[:10])
            more = f"\n    … 외 {len(product_changes) - 10}건" if len(product_changes) > 10 else ""
            errors.append(
                "동작이 바뀌는 파일을 고쳤는데 `CHANGELOG.md` 를 고치지 않았습니다. "
                "`## [Unreleased]` 아래에 항목을 추가하십시오.\n"
                f"{listed}{more}\n"
                "    (정말 필요 없다면 PR 에 `no-changelog` 라벨을 붙이고 근거를 PR 본문에 적으십시오.)"
            )

    if errors:
        print("## CHANGELOG 검사 실패\n", file=sys.stderr)
        for index, error in enumerate(errors, start=1):
            print(f"{index}. {error}\n", file=sys.stderr)
        return 1

    print("CHANGELOG 검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
