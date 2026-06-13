"""pipeline/metadata_merge.py — trust 가중 메타 병합.

merge_metadata(entries, source_types?) → dict
  필드별 전략:
    - exact vote: content_type, production_year, total_seasons/episodes, air_status
    - MAD → trust 가중 중앙값: runtime_minutes
    - trust Σ≥34% 합집합: genres, countries, directors
    - trust union + name dedup: cast
    - best-trust: story, original_title, first_air_date, last_air_date
    - 빈도 상위 N: keywords
    - union: networks
  _provenance: field→[provider_domain] 자동 생성
"""
from __future__ import annotations

import statistics
from collections import Counter

from pipeline.facets import attach_coverage
from pipeline.metadata_schema import (
    GENRE_NORMALIZE_MAP,
    COUNTRY_NORMALIZE_MAP,
    _normalize_genre,
    _normalize_country,
    validate_metadata,
    empty_metadata,
)

_LIST_TRUST_RATIO = 0.34    # facet_merge과 동일 기준
_MAD_MULTIPLIER = 3.0
_MAX_KEYWORDS = 8
_MAX_CAST = 10
_MAX_DIRECTORS = 5


def _mad_filter_ints(values: list[int | None]) -> list[int | None]:
    """int 열 MAD 극단값을 None으로 마킹."""
    valid = [v for v in values if v is not None]
    if len(valid) < 3:
        return values
    med = statistics.median(valid)
    mad = statistics.median(abs(v - med) for v in valid)
    if mad == 0:
        return values
    return [
        None if (v is not None and abs(v - med) > _MAD_MULTIPLIER * mad) else v
        for v in values
    ]


def _exact_vote(values_with_trust: list[tuple]) -> object:
    """가장 높은 Σtrust를 얻은 값."""
    vote: dict = {}
    for val, trust in values_with_trust:
        if val is not None:
            vote[val] = vote.get(val, 0.0) + trust
    return max(vote, key=vote.__getitem__) if vote else None


def _best_trust_str(values_with_trust: list[tuple[str | None, float]]) -> str | None:
    """trust 최고 소스의 값 (동률은 긴 쪽)."""
    best_val: str | None = None
    best_trust = -1.0
    for val, trust in values_with_trust:
        if val and (trust > best_trust or (trust == best_trust and len(val) > len(best_val or ""))):
            best_val, best_trust = val, trust
    return best_val


def _merge_list_by_trust(
    items_per_entry: list[tuple[list[str], float]],
    normalizer=None,
) -> list[str]:
    """Σtrust ≥ 34% 기준 합집합. 분모는 해당 필드를 제공한 소스의 trust 합.

    필드를 비워둔(abstain) 소스의 trust는 분모에서 제외 — 미제공이 반대표로
    작용해 제공 소스의 항목을 희석하는 것을 막는다. (예: TMDB가 genres를
    매핑하지 않아도 KMDb의 장르가 탈락하지 않도록.)
    normalizer 있으면 정규화 후 집계.
    """
    item_trust: dict[str, float] = {}
    contributing_trust = 0.0
    for items, trust in items_per_entry:
        if items:
            contributing_trust += trust
        for item in items:
            key = normalizer(item) if normalizer else item
            item_trust[key] = item_trust.get(key, 0.0) + trust
    threshold = contributing_trust * _LIST_TRUST_RATIO
    return [item for item, t in item_trust.items() if t >= threshold]


def _merge_cast(
    cast_per_entry: list[tuple[list[dict], float]],
) -> list[dict]:
    """trust 내림차순 union, name exact dedup (ko/en 교차 안 함)."""
    seen_names: set[str] = set()
    result: list[dict] = []
    # 높은 trust 소스 먼저
    for cast_list, _trust in sorted(cast_per_entry, key=lambda x: -x[1]):
        for item in cast_list:
            name = item.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            result.append(item)
    return result[:_MAX_CAST]


def merge_metadata(
    entries: list[tuple[dict, float]],
    source_types: list[str] | None = None,
    provider_names: list[str] | None = None,
) -> dict:
    """N개 (metadata, trust) 쌍을 trust 가중 병합.

    Args:
        entries: [(meta_dict, trust_score), …]  meta_dict은 validate_metadata 통과 결과
        source_types: coverage 계산용
        provider_names: provenance 기록용 (entries와 길이 같아야 함)

    Returns:
        병합 metadata (_coverage + confidence + _provenance 포함)
    """
    st = source_types or []
    pvdr = provider_names or (["unknown"] * len(entries))

    if not entries:
        merged = empty_metadata()
        merged["_provenance"] = {}
        return attach_coverage(merged, st)

    if len(entries) == 1:
        merged = dict(entries[0][0])
        merged["_provenance"] = {k: [pvdr[0]] for k in merged if merged[k] not in (None, [], {})}
        return attach_coverage(merged, st)

    provenance: dict[str, list[str]] = {}
    merged: dict = {}

    # ── content_type ─────────────────────────────────────────
    ct_pairs = [(e.get("content_type"), t) for (e, t) in zip([m for m, _ in entries], [t for _, t in entries])]
    merged["content_type"] = _exact_vote(ct_pairs)
    if merged["content_type"]:
        provenance["content_type"] = [pvdr[i] for i, (e, _) in enumerate(entries) if e.get("content_type") == merged["content_type"]]

    # ── original_title ───────────────────────────────────────
    ot_pairs = [(e.get("original_title"), t) for e, t in entries]
    merged["original_title"] = _best_trust_str(ot_pairs)
    if merged["original_title"]:
        provenance["original_title"] = [pvdr[i] for i, (e, _) in enumerate(entries) if e.get("original_title")]

    # ── production_year (exact vote) ─────────────────────────
    year_pairs = [(e.get("production_year"), t) for e, t in entries]
    merged["production_year"] = _exact_vote(year_pairs)
    if merged["production_year"]:
        provenance["production_year"] = [pvdr[i] for i, (e, _) in enumerate(entries) if e.get("production_year") == merged["production_year"]]

    # ── runtime_minutes (MAD → 가중 중앙값) ──────────────────
    rts = [e.get("runtime_minutes") for e, _ in entries]
    rts_filtered = _mad_filter_ints(rts)
    valid_pairs = [(v, entries[i][1]) for i, v in enumerate(rts_filtered) if v is not None]
    if valid_pairs:
        # trust 가중 중앙값 근사: trust 크기 순 정렬 후 가중 중간점
        sorted_pairs = sorted(valid_pairs, key=lambda x: x[0])
        cum, total = 0.0, sum(t for _, t in sorted_pairs)
        half = total / 2.0
        rt_median = sorted_pairs[0][0]
        for val, trust in sorted_pairs:
            cum += trust
            if cum >= half:
                rt_median = val
                break
        merged["runtime_minutes"] = rt_median
        provenance["runtime_minutes"] = [pvdr[i] for i, (e, _) in enumerate(entries) if e.get("runtime_minutes") is not None]
    else:
        merged["runtime_minutes"] = None

    # ── genres ───────────────────────────────────────────────
    g_per_entry = [([_normalize_genre(g) for g in e.get("genres", [])], t) for e, t in entries]
    merged["genres"] = _merge_list_by_trust(g_per_entry)
    if merged["genres"]:
        provenance["genres"] = list(dict.fromkeys(pvdr[i] for i, (e, _) in enumerate(entries) if e.get("genres")))

    # ── countries ────────────────────────────────────────────
    c_per_entry = [([_normalize_country(c) for c in e.get("countries", [])], t) for e, t in entries]
    merged["countries"] = _merge_list_by_trust(c_per_entry)
    if merged["countries"]:
        provenance["countries"] = list(dict.fromkeys(pvdr[i] for i, (e, _) in enumerate(entries) if e.get("countries")))

    # ── directors ────────────────────────────────────────────
    d_per_entry = [(e.get("directors", []), t) for e, t in entries]
    merged["directors"] = _merge_list_by_trust(d_per_entry)[:_MAX_DIRECTORS]
    if merged["directors"]:
        provenance["directors"] = list(dict.fromkeys(pvdr[i] for i, (e, _) in enumerate(entries) if e.get("directors")))

    # ── cast ─────────────────────────────────────────────────
    cast_per_entry = [(e.get("cast", []), t) for e, t in entries]
    merged["cast"] = _merge_cast(cast_per_entry)
    if merged["cast"]:
        provenance["cast"] = list(dict.fromkeys(pvdr[i] for i, (e, _) in enumerate(entries) if e.get("cast")))

    # ── story (best-trust) ───────────────────────────────────
    story_pairs = [(e.get("story"), t) for e, t in entries]
    merged["story"] = _best_trust_str(story_pairs)
    if merged["story"]:
        provenance["story"] = [pvdr[i] for i, (e, _) in enumerate(entries) if e.get("story")]

    # ── keywords (빈도 상위 N) ────────────────────────────────
    kw_counter: Counter = Counter()
    for e, _ in entries:
        kw_counter.update(e.get("keywords") or [])
    merged["keywords"] = [k for k, _ in kw_counter.most_common(_MAX_KEYWORDS)]
    if merged["keywords"]:
        provenance["keywords"] = list(dict.fromkeys(pvdr[i] for i, (e, _) in enumerate(entries) if e.get("keywords")))

    # ── series 필드 ──────────────────────────────────────────
    if merged.get("content_type") == "series":
        series_entries = [(e.get("series") or {}, t) for e, t in entries]

        total_seasons_pairs = [(s.get("total_seasons"), t) for s, t in series_entries]
        total_episodes_pairs = [(s.get("total_episodes"), t) for s, t in series_entries]
        fad_pairs = [(s.get("first_air_date"), t) for s, t in series_entries]
        lad_pairs = [(s.get("last_air_date"), t) for s, t in series_entries]
        status_pairs = [(s.get("air_status"), t) for s, t in series_entries]
        networks_lists = [(s.get("networks") or [], t) for s, t in series_entries]

        merged["series"] = {
            "total_seasons": _exact_vote(total_seasons_pairs),
            "total_episodes": _exact_vote(total_episodes_pairs),
            "first_air_date": _best_trust_str(fad_pairs),
            "last_air_date": _best_trust_str(lad_pairs),
            "air_status": _exact_vote(status_pairs),
            "networks": list(dict.fromkeys(
                n for nets, _ in networks_lists for n in nets
            )),
        }
    else:
        merged["series"] = None

    merged["_provenance"] = provenance
    return attach_coverage(merged, st)
