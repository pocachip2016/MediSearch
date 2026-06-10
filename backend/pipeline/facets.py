"""facets.py — 영화 Content Understanding Profile (추천 시스템용 타입 구동 스키마)

mediaX backend/api/programming/scheduling/facets.py 의 통제어휘 로직을 이식하되,
추천 시스템 우선순위(1순위 MVP)에 맞춰 **타입 체계**로 재설계.

타입별 쓰임:
  - score (0~1)      : 랭킹/필터 축 (tension, immersion, boredom_risk, …)
  - enum (단일)       : 라우팅/분기 (primary_genre, ending_type, …)
  - vocab list (다중) : 매칭 (theme, mood, emotional_aftertaste, sub_genre)
  - free list         : 롱테일 태그 (micro_genre)
  - text              : 설명 (premise, one_liner)

보완(채택):
  - safety_flags : 안전 score 임계 초과 시 hard-filter용 boolean + age 파생
  - _coverage / confidence : 원본 폐기 원칙상 신뢰도의 유일한 신호 (소스 수/타입)
  - rewatch_value : 재시청 의향 (강한 추천 신호)
"""
from __future__ import annotations

from collections import Counter

# ── 통제어휘: enum (단일 선택) ─────────────────────────────
ENUM_VOCAB: dict[str, list[str]] = {
    "primary_genre": [
        "액션", "드라마", "코미디", "로맨스", "스릴러", "공포", "SF", "판타지",
        "애니메이션", "다큐멘터리", "범죄", "미스터리", "어드벤처", "전쟁", "역사", "음악", "느와르",
    ],
    "conflict":       ["내적갈등", "대인갈등", "사회갈등", "생존갈등", "도덕갈등", "운명갈등"],
    "ending_type":    ["해피엔딩", "새드엔딩", "열린결말", "반전결말", "비극", "잔잔한결말"],
    "pacing_reaction": ["느리다", "적절하다", "빠르다"],
    "ending_reaction": ["만족", "호불호갈림", "실망", "충격"],
}

# ── 통제어휘: list (다중 선택) ─────────────────────────────
LIST_VOCAB: dict[str, list[str]] = {
    "sub_genre": [
        "범죄스릴러", "심리드라마", "블랙코미디", "로맨틱코미디", "재난", "성장물",
        "느와르", "법정물", "수사물", "정치물", "가족드라마", "청춘물", "복수극",
    ],
    "theme": [
        "성장", "복수", "우정", "가족", "생존", "범죄", "사랑", "전쟁", "음모",
        "정의", "구원", "상실", "계급", "정체성",
    ],
    "mood": ["경쾌", "감성", "긴장", "따뜻", "어두움", "코믹", "로맨틱", "비장", "몽환", "불안"],
    "emotional_aftertaste": [
        "여운", "먹먹함", "통쾌함", "씁쓸함", "따뜻함", "공허함", "카타르시스", "불편함", "희망",
    ],
}

# ── score (0.0~1.0) ────────────────────────────────────────
SCORE_FIELDS: list[str] = [
    # 감정
    "tension",
    # 리뷰 반응
    "immersion", "boredom_risk", "rewatch_value",
    # 시청 상황
    "attention_required", "emotional_energy_required",
    # 안전/회피
    "violence", "gore", "sexual_content", "spoiler_sensitivity",
    # 종합
    "sentiment_score",
]

# ── free list (롱테일 태그, 정규화만) ──────────────────────
FREE_LIST_FIELDS: list[str] = ["micro_genre"]

# ── text (자유 서술) ───────────────────────────────────────
TEXT_FIELDS: list[str] = ["premise", "one_liner"]

# ── 안전 hard-filter ───────────────────────────────────────
SAFETY_SCORE_FIELDS: list[str] = ["violence", "gore", "sexual_content"]
# score 필드명 → hard-filter boolean flag 이름
SAFETY_FLAG_NAMES: dict[str, str] = {
    "violence": "is_violent",
    "gore": "is_gory",
    "sexual_content": "is_sexual",
}
SAFETY_THRESHOLD = 0.5

_MAX_STR_LEN = 600
_MAX_LIST_ITEMS = 8

# 전체 통제어휘 평탄화 (검색/검증 보조)
FLAT_VOCAB: set[str] = (
    {v for vals in ENUM_VOCAB.values() for v in vals}
    | {v for vals in LIST_VOCAB.values() for v in vals}
)


# ── 검증 유틸 ──────────────────────────────────────────────

def _clamp_score(val) -> float | None:
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return None


def _norm_str(val) -> str:
    if not isinstance(val, str):
        val = str(val) if val is not None else ""
    return val.strip()[:_MAX_STR_LEN]


def _norm_list(val) -> list[str]:
    if isinstance(val, str):
        val = [val]
    if not isinstance(val, list):
        return []
    return [str(v).strip()[:_MAX_STR_LEN] for v in val if v][:_MAX_LIST_ITEMS]


def _safety_flags(facet: dict) -> dict:
    """안전 score → hard-filter용 boolean flag + age 파생."""
    peak = 0.0
    flags: dict = {}
    for f in SAFETY_SCORE_FIELDS:
        score = facet.get(f) or 0.0
        flags[SAFETY_FLAG_NAMES[f]] = score >= SAFETY_THRESHOLD
        peak = max(peak, score)

    if peak >= 0.8:
        age = "청소년관람불가"
    elif peak >= 0.5:
        age = "15세이상관람가"
    elif peak >= 0.3:
        age = "12세이상관람가"
    else:
        age = "전체관람가"
    flags["age_suggestion"] = age
    return flags


def validate_movie_facet(raw: dict) -> dict:
    """LLM 출력 facet을 타입 스키마로 검증·정규화.

    - enum 필드: 통제어휘 외 값 → None
    - list vocab 필드: 통제어휘 외 값 제거
    - score 필드: 0~1 clamp (실패 시 None)
    - free list / text: 타입 정규화
    - 파생: safety_flags
    """
    facet: dict = {}

    # enum (단일)
    for key, allowed in ENUM_VOCAB.items():
        val = raw.get(key)
        if isinstance(val, list):
            val = val[0] if val else None
        facet[key] = val if val in allowed else None

    # list vocab (다중)
    for key, allowed in LIST_VOCAB.items():
        vals = raw.get(key, [])
        if isinstance(vals, str):
            vals = [vals]
        if not isinstance(vals, list):
            vals = []
        facet[key] = [v for v in vals if v in allowed]

    # score
    for key in SCORE_FIELDS:
        facet[key] = _clamp_score(raw.get(key))

    # free list
    for key in FREE_LIST_FIELDS:
        facet[key] = _norm_list(raw.get(key, []))

    # text
    for key in TEXT_FIELDS:
        facet[key] = _norm_str(raw.get(key, ""))

    # 파생 — 안전 hard-filter
    facet["safety_flags"] = _safety_flags(facet)

    return facet


# ── 신뢰도 (원본 폐기 원칙 보완) ───────────────────────────

def build_coverage(source_types: list[str]) -> dict:
    """소스 타입 분포 → coverage 메타. 각 facet 신뢰도의 근거."""
    c = Counter(source_types)
    return {
        "source_count": sum(c.values()),
        "by_type": dict(c),
        "has_synopsis": c.get("synopsis", 0) > 0,
        "has_expert": c.get("expert_review", 0) > 0,
        "has_user": c.get("user_review", 0) > 0,
    }


def coverage_confidence(coverage: dict) -> float:
    """coverage → 0~1 신뢰도 휴리스틱.

    소스 수(최대 6 기준) 80% + 전문가/관객 평 동시 확보 보너스.
    """
    n = coverage.get("source_count", 0)
    base = min(1.0, n / 6.0) * 0.8
    bonus = 0.0
    if coverage.get("has_expert"):
        bonus += 0.1
    if coverage.get("has_user"):
        bonus += 0.1
    return round(min(1.0, base + bonus), 3)


def attach_coverage(facet: dict, source_types: list[str]) -> dict:
    """facet에 _coverage + confidence 부착."""
    coverage = build_coverage(source_types)
    facet["_coverage"] = coverage
    facet["confidence"] = coverage_confidence(coverage)
    return facet


# ── 유사도 (추천 매칭) ─────────────────────────────────────

def facet_overlap_score(facets_a: dict, facets_b: dict) -> float:
    """두 facet의 통제어휘(enum + list vocab) Jaccard 유사도 (0.0~1.0).

    score/text/free/메타 필드는 비교 제외 — vocab 필드만.
    enum/list 값은 키 prefix로 토큰화해 필드 간 충돌 방지.
    """
    def _flat(f: dict) -> set[str]:
        out: set[str] = set()
        for key in ENUM_VOCAB:
            v = f.get(key)
            if v:
                out.add(f"{key}:{v}")
        for key in LIST_VOCAB:
            for v in f.get(key, []) or []:
                out.add(f"{key}:{v}")
        return out

    a, b = _flat(facets_a), _flat(facets_b)
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def empty_facet() -> dict:
    """폴백용 빈 facet (LLM 실패 시)."""
    return validate_movie_facet({})
