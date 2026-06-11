"""tests/test_metadata_schema.py — metadata_schema 단위 테스트."""
import pytest
from pipeline.metadata_schema import (
    validate_metadata,
    empty_metadata,
    GENRE_NORMALIZE_MAP,
    COUNTRY_NORMALIZE_MAP,
    _parse_year,
    _parse_runtime,
)


class TestValidateMetadata:
    def test_empty_input_returns_empty_meta(self):
        m = validate_metadata({})
        assert m["content_type"] is None
        assert m["production_year"] is None
        assert m["genres"] == []
        assert m["cast"] == []
        assert m["series"] is None

    def test_none_input_returns_empty_meta(self):
        m = validate_metadata(None)
        assert m == empty_metadata()

    def test_content_type_valid(self):
        assert validate_metadata({"content_type": "movie"})["content_type"] == "movie"
        assert validate_metadata({"content_type": "series"})["content_type"] == "series"

    def test_content_type_invalid_becomes_none(self):
        assert validate_metadata({"content_type": "anime"})["content_type"] is None

    def test_production_year_clamp_low(self):
        m = validate_metadata({"production_year": 1800})
        assert m["production_year"] is None

    def test_production_year_string(self):
        m = validate_metadata({"production_year": "2003"})
        assert m["production_year"] == 2003

    def test_production_year_year_range_string(self):
        m = validate_metadata({"production_year": "2024–2025"})
        assert m["production_year"] == 2024

    def test_runtime_string_parse(self):
        m = validate_metadata({"runtime_minutes": "132 min"})
        assert m["runtime_minutes"] == 132

    def test_runtime_out_of_range(self):
        m = validate_metadata({"runtime_minutes": 700})
        assert m["runtime_minutes"] is None

    def test_genre_normalize_english(self):
        m = validate_metadata({"genres": ["Action", "Drama"]})
        assert "액션" in m["genres"]
        assert "드라마" in m["genres"]

    def test_genre_passthrough_korean(self):
        m = validate_metadata({"genres": ["스릴러"]})
        assert "스릴러" in m["genres"]

    def test_country_normalize(self):
        m = validate_metadata({"countries": ["South Korea", "United States"]})
        assert "한국" in m["countries"]
        assert "미국" in m["countries"]

    def test_directors_limit(self):
        m = validate_metadata({"directors": ["a", "b", "c", "d", "e", "f"]})
        assert len(m["directors"]) == 5

    def test_cast_str_list(self):
        m = validate_metadata({"cast": ["이정재", "박해수"]})
        assert len(m["cast"]) == 2
        assert m["cast"][0] == {"name": "이정재", "role": None}

    def test_cast_dict_list(self):
        m = validate_metadata({"cast": [{"name": "이정재", "role": "성기훈"}]})
        assert m["cast"][0]["role"] == "성기훈"

    def test_cast_limit(self):
        m = validate_metadata({"cast": [{"name": str(i), "role": None} for i in range(15)]})
        assert len(m["cast"]) == 10

    def test_story_truncated(self):
        long = "x" * 100
        m = validate_metadata({"story": long})
        assert len(m["story"]) == 60

    def test_keywords_limit(self):
        m = validate_metadata({"keywords": list("abcdefghij")})
        assert len(m["keywords"]) == 8

    def test_series_fields_present(self):
        m = validate_metadata({
            "content_type": "series",
            "series": {
                "total_seasons": 2,
                "total_episodes": 16,
                "first_air_date": "2021-09-17",
                "air_status": "ended",
                "networks": ["Netflix"],
            }
        })
        assert m["series"]["total_seasons"] == 2
        assert m["series"]["air_status"] == "ended"

    def test_series_none_for_movie(self):
        m = validate_metadata({
            "content_type": "movie",
            "series": {"total_seasons": 2},
        })
        assert m["series"] is None

    def test_series_invalid_air_status(self):
        m = validate_metadata({
            "content_type": "series",
            "series": {"air_status": "unknown"},
        })
        assert m["series"]["air_status"] is None

    def test_synopsis_raw_not_stored(self):
        """synopsis_raw 임시 키는 validate 후 없어야 함."""
        m = validate_metadata({"synopsis_raw": "original long text"})
        assert "synopsis_raw" not in m

    def test_empty_metadata_factory(self):
        m = empty_metadata()
        assert m["content_type"] is None
        assert m["genres"] == []
        assert m["cast"] == []


class TestParseHelpers:
    def test_parse_year_int(self):
        assert _parse_year(2003) == 2003

    def test_parse_year_out_of_range(self):
        assert _parse_year(1879) is None
        assert _parse_year(2100) is None

    def test_parse_runtime_int(self):
        assert _parse_runtime(120) == 120

    def test_parse_runtime_string(self):
        assert _parse_runtime("88 min") == 88

    def test_parse_runtime_none(self):
        assert _parse_runtime(None) is None


class TestNormalizeMaps:
    def test_genre_map_coverage(self):
        assert GENRE_NORMALIZE_MAP["Action"] == "액션"
        assert GENRE_NORMALIZE_MAP["Science Fiction"] == "SF"

    def test_country_map_coverage(self):
        assert COUNTRY_NORMALIZE_MAP["South Korea"] == "한국"
        assert COUNTRY_NORMALIZE_MAP["USA"] == "미국"
