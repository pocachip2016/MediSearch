"""pipeline/facet_merge.py — trust 가중 facet 병합 + outlier 제거.

merge_facets(entries, source_types?) → dict
  1) 구조 outlier 제거 (facet ≥3 시 평균 Jaccard < 임계)
  2) score 필드별 MAD 기반 극단값 마킹
  3) trust 가중 병합 (score=가중평균, enum=가중투표, list=trust 임계, text=최고신뢰)
  4) attach_coverage → confidence 계산
"""
from __future__ import annotations

import statistics
from collections import Counter

from pipeline.facets import (
    ENUM_VOCAB,
    FREE_LIST_FIELDS,
    LIST_VOCAB,
    SCORE_FIELDS,
    TEXT_FIELDS,
    _safety_flags,
    attach_coverage,
    empty_facet,
    facet_overlap_score,
)

_OVERLAP_THRESHOLD = 0.15   # 평균 Jaccard 미만이면 구조 outlier
_MAD_MULTIPLIER = 3.0       # |val - median| > 3·MAD 이면 score outlier
_LIST_TRUST_RATIO = 0.34    # 항목 채택: Σtrust ≥ 전체 trust × 34%
_MAX_FREE_LIST = 8


def _remove_structural_outliers(
    entries: list[tuple[dict, float]],
) -> list[tuple[dict, float]]:
    """facet ≥3 시 평균 overlap < 임계인 소스 배제."""
    if len(entries) < 3:
        return entries

    kept = []
    for i, (fi, ti) in enumerate(entries):
        others = [fj for j, (fj, _) in enumerate(entries) if j != i]
        mean_ov = statistics.mean(facet_overlap_score(fi, fj) for fj in others)
        if mean_ov >= _OVERLAP_THRESHOLD:
            kept.append((fi, ti))

    return kept if kept else entries  # 전부 배제 방지


def _mad_filter(values: list[float | None]) -> list[float | None]:
    """score 열에서 MAD 극단값을 None으로 마킹."""
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


def merge_facets(
    entries: list[tuple[dict, float]],
    source_types: list[str] | None = None,
) -> dict:
    """N개 (facet, trust) 쌍을 trust 가중 병합.

    Args:
        entries: [(facet_dict, trust_score), …]
        source_types: 전체 소스 타입 목록 (coverage 계산용; None → 빈 coverage)

    Returns:
        병합 facet (_coverage + confidence 포함)
    """
    st = source_types or []

    if not entries:
        return attach_coverage(empty_facet(), st)

    if len(entries) == 1:
        facet = dict(entries[0][0])
        return attach_coverage(facet, st)

    # ── 1) 구조 outlier 제거 ────────────────────────────────
    clean = _remove_structural_outliers(entries)

    trusts = [t for _, t in clean]
    total_trust = sum(trusts)

    # ── 2) score MAD 마킹 ────────────────────────────────────
    score_cols: dict[str, list[float | None]] = {
        field: _mad_filter([f.get(field) for f, _ in clean])
        for field in SCORE_FIELDS
    }

    merged: dict = {}

    # ── 3a) score: trust 가중평균 ────────────────────────────
    for field in SCORE_FIELDS:
        pairs = [
            (v, trusts[i])
            for i, v in enumerate(score_cols[field])
            if v is not None
        ]
        if pairs:
            merged[field] = round(
                sum(v * t for v, t in pairs) / sum(t for _, t in pairs), 4
            )
        else:
            merged[field] = None

    # ── 3b) enum: trust 합 최대인 값 ─────────────────────────
    for field in ENUM_VOCAB:
        vote: dict[str, float] = {}
        for (facet, trust) in clean:
            val = facet.get(field)
            if val is not None:
                vote[val] = vote.get(val, 0.0) + trust
        merged[field] = max(vote, key=vote.__getitem__) if vote else None

    # ── 3c) list vocab: Σtrust ≥ 34% 채택 ───────────────────
    for field in LIST_VOCAB:
        item_trust: dict[str, float] = {}
        for (facet, trust) in clean:
            for item in facet.get(field) or []:
                item_trust[item] = item_trust.get(item, 0.0) + trust
        threshold = total_trust * _LIST_TRUST_RATIO
        merged[field] = [item for item, t in item_trust.items() if t >= threshold]

    # ── 3d) free list: 빈도 상위 N ───────────────────────────
    for field in FREE_LIST_FIELDS:
        counter: Counter = Counter()
        for (facet, _) in clean:
            counter.update(facet.get(field) or [])
        merged[field] = [item for item, _ in counter.most_common(_MAX_FREE_LIST)]

    # ── 3e) text: trust 최대 소스 채택 ───────────────────────
    for field in TEXT_FIELDS:
        best_val, best_trust = "", 0.0
        for (facet, trust) in clean:
            val = facet.get(field) or ""
            if val and trust > best_trust:
                best_val, best_trust = val, trust
        merged[field] = best_val

    # 파생: safety_flags 재계산
    merged["safety_flags"] = _safety_flags(merged)

    return attach_coverage(merged, st)
