"""scripts/scan_namu_contamination.py — 나무위키 오염 소스 스캔 + 재평가 리셋 (일회성).

사용법:
    # dry-run (기본)
    python scripts/scan_namu_contamination.py

    # 적용 (MediSearch facet 캐시 + mediaX facet 삭제)
    python scripts/scan_namu_contamination.py --apply

dry-run 결과를 반드시 확인 후 --apply 실행. 삭제는 비가역.

오염 감지 기준:
    ms_search_sources.source_domain = 'namu.wiki'
    AND _normalize_title(title) ≠ _normalize_title(movie_query)
    → 잘못된 영화 문서가 병합된 가능성 있음.
"""
from __future__ import annotations

import argparse
import sys
import os

# 스크립트 루트가 backend/인지 아닌지 무관하게 import 보장
_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared.config import settings
from search.namu_provider import _normalize_title


def _make_session(url: str):
    engine = create_engine(url)
    return sessionmaker(bind=engine)()


def scan(db_url: str) -> list[dict]:
    """ms_search_sources에서 title/movie_query 불일치 namu 소스 탐색."""
    db = _make_session(db_url)
    try:
        rows = db.execute(text(
            "SELECT id, movie_query, title, url "
            "FROM ms_search_sources "
            "WHERE source_domain = 'namu.wiki'"
        )).fetchall()
    finally:
        db.close()

    contaminated = []
    for row in rows:
        if not row.title:
            continue
        if _normalize_title(row.title) != _normalize_title(row.movie_query):
            # 양방향 포함도 합법적 — e.g. "올드보이(영화)" vs "올드보이"
            a = _normalize_title(row.title)
            b = _normalize_title(row.movie_query)
            if a in b or b in a:
                continue  # 정상 — 괄호 접미사 차이 등
            contaminated.append({
                "source_id": row.id,
                "movie_query": row.movie_query,
                "namu_title": row.title,
                "url": row.url,
            })
    return contaminated


def _affected_queries(contaminated: list[dict]) -> set[str]:
    return {c["movie_query"] for c in contaminated}


def apply_reset(ms_url: str, mx_url: str | None, affected: set[str], dry_run: bool) -> dict:
    """MediSearch facet 캐시 삭제 + mediaX facet 삭제."""
    if not affected:
        return {"ms_deleted": 0, "mx_deleted": 0}

    ms_deleted = mx_deleted = 0

    # ── MediSearch ms_movie_facets 삭제 ──────────────────────────────────────
    ms_db = _make_session(ms_url)
    try:
        for query in affected:
            result = ms_db.execute(
                text("SELECT COUNT(*) FROM ms_movie_facets WHERE movie_query = :q"),
                {"q": query},
            )
            cnt = result.scalar()
            if cnt:
                if not dry_run:
                    ms_db.execute(
                        text("DELETE FROM ms_movie_facets WHERE movie_query = :q"),
                        {"q": query},
                    )
                ms_deleted += cnt
        if not dry_run:
            ms_db.commit()
    finally:
        ms_db.close()

    # ── mediaX tmdb_movie_facets 삭제 ─────────────────────────────────────────
    if mx_url:
        mx_db = _make_session(mx_url)
        try:
            for query in affected:
                result = mx_db.execute(
                    text("SELECT COUNT(*) FROM tmdb_movie_facets WHERE movie_query = :q"),
                    {"q": query},
                )
                cnt = result.scalar()
                if cnt:
                    if not dry_run:
                        mx_db.execute(
                            text("DELETE FROM tmdb_movie_facets WHERE movie_query = :q"),
                            {"q": query},
                        )
                    mx_deleted += cnt
            if not dry_run:
                mx_db.commit()
        finally:
            mx_db.close()

    return {"ms_deleted": ms_deleted, "mx_deleted": mx_deleted}


def main():
    parser = argparse.ArgumentParser(description="나무위키 오염 소스 스캔 + 재평가 리셋")
    parser.add_argument("--apply", action="store_true", help="삭제 실행 (기본: dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply

    ms_url = settings.DATABASE_URL
    mx_url = getattr(settings, "MEDIAX_DATABASE_URL", None)

    print(f"[scan] MediSearch DB: {ms_url}")
    print(f"[scan] mediaX DB:     {mx_url or '미설정 — 건너뜀'}")
    print(f"[scan] 모드: {'dry-run' if dry_run else '⚠️  APPLY'}")
    print()

    contaminated = scan(ms_url)

    if not contaminated:
        print("[scan] ✓ 오염 소스 없음.")
        return

    print(f"[scan] 오염 의심 소스 {len(contaminated)}건:")
    for c in contaminated:
        print(f"  source_id={c['source_id']}  query={c['movie_query']!r}  namu={c['namu_title']!r}")

    affected = _affected_queries(contaminated)
    print(f"\n[scan] 영향 movie_query {len(affected)}건: {sorted(affected)}")

    result = apply_reset(ms_url, mx_url, affected, dry_run=dry_run)
    tag = "[dry-run]" if dry_run else "[apply]"
    print(f"\n{tag} ms_movie_facets 삭제 예정/실행: {result['ms_deleted']}건")
    print(f"{tag} tmdb_movie_facets 삭제 예정/실행: {result['mx_deleted']}건")

    if dry_run:
        print("\n⚠️  dry-run 완료. 실제 삭제: --apply 플래그 추가 후 재실행.")
    else:
        print("\n✓ apply 완료. 해당 tmdb_id가 mediaX pending으로 복귀됩니다.")


if __name__ == "__main__":
    main()
