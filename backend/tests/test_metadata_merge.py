"""tests/test_metadata_merge.py — metadata_merge 단위 테스트."""
import pytest
from pipeline.metadata_merge import (
    merge_metadata,
    _exact_vote,
    _best_trust_str,
    _merge_list_by_trust,
    _merge_cast,
    _mad_filter_ints,
)
from pipeline.metadata_schema import validate_metadata


def _meta(**kwargs):
    return validate_metadata(kwargs)


class TestExactVote:
    def test_majority_wins(self):
        pairs = [("movie", 0.9), ("movie", 0.8), ("series", 0.5)]
        assert _exact_vote(pairs) == "movie"

    def test_trust_weighted(self):
        # series 1개지만 trust가 압도적으로 높으면 선택
        pairs = [("movie", 0.3), ("series", 0.9)]
        assert _exact_vote(pairs) == "series"

    def test_none_ignored(self):
        pairs = [(None, 0.9), ("movie", 0.5)]
        assert _exact_vote(pairs) == "movie"

    def test_empty(self):
        assert _exact_vote([]) is None


class TestBestTrustStr:
    def test_best_trust_wins(self):
        pairs = [("짧은", 0.9), ("조금더긴", 0.8)]
        assert _best_trust_str(pairs) == "짧은"

    def test_tie_prefers_longer(self):
        pairs = [("짧은", 0.9), ("더긴문자열", 0.9)]
        assert _best_trust_str(pairs) == "더긴문자열"

    def test_none_skipped(self):
        assert _best_trust_str([(None, 1.0)]) is None


class TestMergeListByTrust:
    def test_threshold_adoption(self):
        # 기여 trust 합=1.4, threshold=0.476 → 채택
        items = [(["액션", "드라마"], 0.9), (["드라마", "코미디"], 0.5)]
        result = _merge_list_by_trust(items)
        assert "드라마" in result   # 0.9+0.5=1.4 ≥ 0.476 (34%)
        assert "액션" in result     # 0.9 ≥ 0.476

    def test_low_trust_rejected(self):
        items = [(["희귀장르"], 0.1), (["공포"], 0.9)]
        result = _merge_list_by_trust(items)
        assert "희귀장르" not in result   # 0.1 < 1.0*0.34
        assert "공포" in result

    def test_abstaining_source_does_not_dilute(self):
        """필드를 비워둔 소스(빈 리스트)는 분모에서 제외 — 제공 소스 항목 보존.

        회귀: 기생충 genres가 TMDB(미제공) 2건 + KMDb([드라마]) 조합에서
        total_trust 분모(2.51) 때문에 0.85 < 0.853 으로 탈락하던 버그.
        """
        items = [([], 0.95), ([], 0.71), (["드라마"], 0.85)]
        result = _merge_list_by_trust(items)
        assert result == ["드라마"]   # 기여 trust=0.85, threshold=0.289


class TestMergeCast:
    def test_dedup_by_name(self):
        cast_a = [{"name": "이정재", "role": "성기훈"}, {"name": "박해수", "role": None}]
        cast_b = [{"name": "이정재", "role": "성기훈"}]
        result = _merge_cast([(cast_a, 0.9), (cast_b, 0.5)])
        names = [c["name"] for c in result]
        assert names.count("이정재") == 1

    def test_high_trust_first(self):
        cast_a = [{"name": "A", "role": None}]
        cast_b = [{"name": "B", "role": None}]
        result = _merge_cast([(cast_a, 0.9), (cast_b, 0.5)])
        assert result[0]["name"] == "A"

    def test_limit_10(self):
        cast_entries = [([{"name": str(i), "role": None} for i in range(15)], 0.9)]
        result = _merge_cast(cast_entries)
        assert len(result) == 10


class TestMADFilter:
    def test_outlier_removed(self):
        # 100, 102, 105, 103, 101, 600 → 600은 MAD outlier
        vals = [100, 102, 105, 103, 101, 600]
        filtered = _mad_filter_ints(vals)
        assert filtered[-1] is None

    def test_small_sample_no_filter(self):
        vals = [90, 120]
        assert _mad_filter_ints(vals) == [90, 120]


class TestMergeMetadata:
    def test_empty_entries(self):
        m = merge_metadata([])
        assert m["content_type"] is None
        assert m["genres"] == []
        assert m["confidence"] is not None

    def test_single_entry_passthrough(self):
        entry = _meta(content_type="movie", production_year=2019, genres=["드라마"])
        m = merge_metadata([(entry, 0.85)], provider_names=["omdb"])
        assert m["content_type"] == "movie"
        assert m["production_year"] == 2019

    def test_production_year_vote(self):
        e1 = _meta(content_type="movie", production_year=2019)
        e2 = _meta(content_type="movie", production_year=2019)
        e3 = _meta(content_type="movie", production_year=2020)
        m = merge_metadata([(e1, 0.8), (e2, 0.8), (e3, 0.5)])
        assert m["production_year"] == 2019

    def test_runtime_mad_outlier_excluded(self):
        e1 = _meta(content_type="movie", runtime_minutes=132)
        e2 = _meta(content_type="movie", runtime_minutes=130)
        e3 = _meta(content_type="movie", runtime_minutes=131)
        e4 = _meta(content_type="movie", runtime_minutes=600)  # outlier
        m = merge_metadata([(e1, 0.9), (e2, 0.8), (e3, 0.7), (e4, 0.5)])
        assert m["runtime_minutes"] < 200

    def test_genres_threshold(self):
        e1 = _meta(content_type="movie", genres=["드라마", "스릴러"])
        e2 = _meta(content_type="movie", genres=["드라마"])
        e3 = _meta(content_type="movie", genres=["드라마", "로맨스"])
        m = merge_metadata([(e1, 0.8), (e2, 0.8), (e3, 0.8)])
        assert "드라마" in m["genres"]

    def test_genre_en_normalized(self):
        e1 = _meta(genres=["Action"])
        e2 = _meta(genres=["액션"])
        m = merge_metadata([(e1, 0.8), (e2, 0.8)])
        # 정규화 후 같은 "액션"으로 집계
        assert m["genres"].count("액션") == 1

    def test_genres_not_diluted_by_abstaining_providers(self):
        """회귀: genres 미제공 provider가 분모를 키워 KMDb 장르를 탈락시키지 않음.

        실제 기생충 시나리오 — TMDB 2건(genres 미매핑) + KMDb([드라마]).
        """
        tmdb1 = _meta(content_type="movie", production_year=2019)        # genres 없음
        tmdb2 = _meta(content_type="movie", production_year=2019)        # genres 없음
        kmdb = _meta(content_type="movie", production_year=2019, genres=["드라마"], countries=["대한민국"])
        m = merge_metadata(
            [(tmdb1, 0.95), (tmdb2, 0.71), (kmdb, 0.85)],
            provider_names=["tmdb", "tmdb", "kmdb"],
        )
        assert m["genres"] == ["드라마"]
        assert m["countries"] == ["대한민국"]
        assert "kmdb" in m["_provenance"]["genres"]

    def test_provenance_generated(self):
        e1 = _meta(content_type="movie", genres=["드라마"])
        m = merge_metadata([(e1, 0.8)], provider_names=["omdb"])
        assert "genres" in m["_provenance"]
        assert "omdb" in m["_provenance"]["genres"]

    def test_cast_dedup(self):
        e1 = _meta(cast=[{"name": "이정재", "role": "성기훈"}])
        e2 = _meta(cast=[{"name": "이정재", "role": "성기훈"}])
        m = merge_metadata([(e1, 0.9), (e2, 0.8)])
        assert sum(1 for c in m["cast"] if c["name"] == "이정재") == 1

    def test_series_fields_merged(self):
        e1 = _meta(content_type="series", series={
            "total_seasons": 2, "total_episodes": 16,
            "first_air_date": "2021-09-17", "air_status": "ended",
            "networks": ["Netflix"],
        })
        e2 = _meta(content_type="series", series={
            "total_seasons": 2, "total_episodes": 16,
            "air_status": "ended", "networks": ["Netflix", "tvN"],
        })
        m = merge_metadata([(e1, 0.9), (e2, 0.8)])
        assert m["series"]["total_seasons"] == 2
        assert m["series"]["air_status"] == "ended"
        assert "Netflix" in m["series"]["networks"]

    def test_story_best_trust(self):
        e1 = _meta(story="짧은스토리")
        e2 = _meta(story="더자세한스토리내용")
        m = merge_metadata([(e1, 0.95), (e2, 0.7)])
        # trust 높은 쪽
        assert m["story"] == "짧은스토리"

    def test_movie_series_none(self):
        e1 = _meta(content_type="movie", series=None)
        m = merge_metadata([(e1, 0.9)])
        assert m["series"] is None

    def test_coverage_attached(self):
        e1 = _meta(content_type="movie")
        m = merge_metadata([(e1, 0.9)], source_types=["synopsis"])
        assert m["_coverage"]["source_count"] == 1
        assert 0.0 < m["confidence"] <= 1.0
