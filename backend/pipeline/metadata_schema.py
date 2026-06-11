"""metadata_schema.py — 영화/시리즈 기본 메타 스키마 (enrich 파이프라인용).

facets.py와 대칭 구조:
  - validate_metadata(raw) → 타입 강제 + clamp
  - empty_metadata()       → 폴백용 빈 메타
  - attach_coverage()      → facets.py 재사용

저장 원칙: story(≤60자 재작성)만 저장 — 원문 시놉시스(synopsis_raw) 미저장.
"""
from __future__ import annotations

import datetime
import re

from pipeline.facets import attach_coverage, coverage_confidence  # noqa: F401 (re-export)

# ── 정규화 맵 ─────────────────────────────────────────────────
GENRE_NORMALIZE_MAP: dict[str, str] = {
    "Action": "액션", "Drama": "드라마", "Comedy": "코미디",
    "Romance": "로맨스", "Thriller": "스릴러", "Horror": "공포",
    "Sci-Fi": "SF", "Science Fiction": "SF", "Fantasy": "판타지",
    "Animation": "애니메이션", "Documentary": "다큐멘터리",
    "Crime": "범죄", "Mystery": "미스터리", "Adventure": "어드벤처",
    "War": "전쟁", "History": "역사", "Music": "음악", "Noir": "느와르",
    "Family": "가족", "Biography": "전기", "Sport": "스포츠",
    "Western": "서부극", "Short": "단편",
}

COUNTRY_NORMALIZE_MAP: dict[str, str] = {
    "South Korea": "한국", "Korea": "한국", "Republic of Korea": "한국",
    "United States": "미국", "USA": "미국", "US": "미국",
    "Japan": "일본", "China": "중국", "France": "프랑스",
    "United Kingdom": "영국", "UK": "영국", "Germany": "독일",
    "India": "인도", "Italy": "이탈리아", "Spain": "스페인",
    "Canada": "캐나다", "Australia": "호주", "Mexico": "멕시코",
    "Brazil": "브라질", "Russia": "러시아", "Taiwan": "대만",
    "Hong Kong": "홍콩", "Thailand": "태국", "Vietnam": "베트남",
}

_CURRENT_YEAR = datetime.date.today().year
_YEAR_MIN = 1880
_YEAR_MAX = _CURRENT_YEAR + 2
_RUNTIME_MIN = 1
_RUNTIME_MAX = 600

_MAX_STORY_LEN = 60
_MAX_DIRECTORS = 5
_MAX_CAST = 10
_MAX_KEYWORDS = 8
_MAX_NETWORKS = 10


def _normalize_genre(g: str) -> str:
    return GENRE_NORMALIZE_MAP.get(g.strip(), g.strip())


def _normalize_country(c: str) -> str:
    return COUNTRY_NORMALIZE_MAP.get(c.strip(), c.strip())


def _split_comma(val) -> list[str]:
    if not val or not isinstance(val, str):
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


def _parse_year(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        y = val
    else:
        m = re.match(r"(\d{4})", str(val))
        if not m:
            return None
        y = int(m.group(1))
    if _YEAR_MIN <= y <= _YEAR_MAX:
        return y
    return None


def _parse_runtime(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        m = val
    else:
        match = re.search(r"(\d+)", str(val))
        if not match:
            return None
        m = int(match.group(1))
    if _RUNTIME_MIN <= m <= _RUNTIME_MAX:
        return m
    return None


def _norm_str(val, max_len: int) -> str | None:
    if not val or not isinstance(val, str):
        return None
    s = val.strip()[:max_len]
    return s or None


def _norm_list(val, max_items: int) -> list[str]:
    if isinstance(val, str):
        val = _split_comma(val)
    if not isinstance(val, list):
        return []
    return [str(v).strip() for v in val if v and str(v).strip()][:max_items]


def _norm_cast(val) -> list[dict]:
    """cast: list[str] | list[{name, role}] → list[{name: str, role: str|None}]"""
    if not isinstance(val, list):
        return []
    result = []
    for item in val[:_MAX_CAST]:
        if isinstance(item, str) and item.strip():
            result.append({"name": item.strip(), "role": None})
        elif isinstance(item, dict) and item.get("name"):
            result.append({"name": str(item["name"]).strip(), "role": _norm_str(item.get("role"), 100)})
    return result


def _norm_series(val) -> dict | None:
    if not isinstance(val, dict):
        return None
    s: dict = {}

    for key in ("total_seasons", "total_episodes"):
        v = val.get(key)
        try:
            s[key] = int(v) if v is not None else None
        except (ValueError, TypeError):
            s[key] = None

    for key in ("first_air_date", "last_air_date"):
        s[key] = _norm_str(val.get(key), 10)

    status = val.get("air_status")
    s["air_status"] = status if status in ("ongoing", "ended") else None

    s["networks"] = _norm_list(val.get("networks", []), _MAX_NETWORKS)

    return s


def validate_metadata(raw: dict | None) -> dict:
    """LLM/구조화 소스 출력을 메타 스키마로 검증·정규화.

    synopsis_raw 등 파이프라인 임시 키는 제거.
    """
    if not raw:
        raw = {}

    meta: dict = {}

    # content_type
    ct = raw.get("content_type")
    meta["content_type"] = ct if ct in ("movie", "series") else None

    # original_title
    meta["original_title"] = _norm_str(raw.get("original_title"), 500)

    # production_year
    meta["production_year"] = _parse_year(raw.get("production_year"))

    # runtime_minutes
    meta["runtime_minutes"] = _parse_runtime(raw.get("runtime_minutes"))

    # countries
    raw_countries = _norm_list(raw.get("countries", []), 20)
    meta["countries"] = [_normalize_country(c) for c in raw_countries]

    # genres
    raw_genres = _norm_list(raw.get("genres", []), 20)
    meta["genres"] = [_normalize_genre(g) for g in raw_genres]

    # directors
    meta["directors"] = _norm_list(raw.get("directors", []), _MAX_DIRECTORS)

    # cast
    meta["cast"] = _norm_cast(raw.get("cast", []))

    # story (≤60자 재작성 결과만 저장 — 원문 미저장)
    meta["story"] = _norm_str(raw.get("story"), _MAX_STORY_LEN)

    # keywords
    meta["keywords"] = _norm_list(raw.get("keywords", []), _MAX_KEYWORDS)

    # series
    meta["series"] = _norm_series(raw.get("series"))
    if meta["content_type"] == "movie":
        meta["series"] = None

    return meta


def empty_metadata() -> dict:
    """폴백용 빈 메타 (LLM 실패 / 소스 없음)."""
    return validate_metadata({})
