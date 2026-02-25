import asyncio
import pytest

from app.transfer.emby import _build_video_action, pick_romanized_title, resolve_media_category, resolve_tmdb_naming_info
from app.transfer.renamer import Renamer


def test_sanitize_for_emby_special_chars():
    renamer = Renamer()
    text = 'Spider-Man: No Way Home? / AC|DC * "Hello"'
    assert renamer.sanitize_for_emby(text) == "Spider-Man- No Way Home - AC-DC Hello"


def test_build_episode_filename():
    renamer = Renamer()
    name = renamer.build_episode_filename("Karakai Jouzu no Takagi-san", 2018, 1, 2, ".mkv")
    assert name == "Karakai Jouzu no Takagi-san (2018) - S01E02.mkv"


def test_pick_romanized_title_prefers_romaji():
    renamer = Renamer()
    alt_titles = [
        {"iso_3166_1": "US", "title": "Teasing Master Takagi-san", "type": ""},
        {"iso_3166_1": "JP", "title": "Karakai Jouzu no Takagi-san", "type": "Romaji"},
        {"iso_3166_1": "JP", "title": "Karakai Jōzu no Takagi-san", "type": "Hepburn Romanization"},
    ]
    assert pick_romanized_title(alt_titles, renamer) == "Karakai Jouzu no Takagi-san"


def test_resolve_media_category_detects_anime():
    assert resolve_media_category("tv", [{"id": 16, "name": "Animation"}]) == "anime"
    assert resolve_media_category("tv", [{"id": 18, "name": "Drama"}]) == "tv"
    assert resolve_media_category("movie", [{"id": 16, "name": "Animation"}]) == "movie"


def test_extract_episode_info_with_chinese_season():
    renamer = Renamer()
    season, episode = renamer.extract_episode_info("第一季 [03].mkv")
    assert season == 1
    assert episode == 3


class _FakeTmdbClient:
    def __init__(self):
        self.alt_called = 0
        self.search_tv_calls = 0

    async def search_movies(self, query, year=None):
        return []

    async def search_tv(self, query, year=None):
        self.search_tv_calls += 1
        assert query
        return [{"id": 75865, "first_air_date": "2018-01-08", "popularity": 1.0}]

    async def details(self, media_type, item_id, language_override=None):
        if item_id == 74532:
            if language_override == "zh-CN":
                return {
                    "id": 74532,
                    "name": "塔姆隆厅犯罪档案",
                    "first_air_date": "2013-09-01",
                    "number_of_seasons": 6,
                    "genres": [{"id": 18, "name": "Drama"}],
                }
            return {
                "id": 74532,
                "name": "Deadline: Crime with Tamron Hall",
                "first_air_date": "2013-09-01",
                "number_of_seasons": 6,
                "genres": [{"id": 18, "name": "Drama"}],
            }
        if language_override == "zh-CN":
            return {
                "id": 75865,
                "name": "擅长捉弄的高木同学",
                "original_name": "からかい上手の高木さん",
                "first_air_date": "2018-01-08",
                "number_of_seasons": 3,
                "genres": [{"id": 16, "name": "Animation"}],
            }
        return {
            "id": 75865,
            "name": "Teasing Master Takagi-san",
            "original_name": "からかい上手の高木さん",
            "first_air_date": "2018-01-08",
            "number_of_seasons": 3,
            "genres": [{"id": 16, "name": "Animation"}],
        }

    async def alternative_titles(self, media_type, item_id):
        self.alt_called += 1
        return [{"iso_3166_1": "JP", "type": "Romaji", "title": "Karakai Jouzu no Takagi-san"}]


def test_resolve_tmdb_naming_info_fallback_from_wrong_tmdb_id():
    client = _FakeTmdbClient()
    info = asyncio.run(
        resolve_tmdb_naming_info(
            client,
            Renamer(),
            media_type="tv",
            tmdb_id=74532,
            title="擅长捉弄的高木同学",
            year=2018,
        )
    )
    assert info.tmdb_id == 74532
    assert info.category == "tv"
    assert info.title == "塔姆隆厅犯罪档案"
    assert info.year == 2013
    assert info.season_count == 6
    assert client.alt_called == 0
    assert client.search_tv_calls == 0


def test_build_video_action_fallback_keeps_chinese_suffix():
    renamer = Renamer()
    title = "\u5929\u9f99\u516b\u90e8"
    old_name = "\u5929\u9f99\u516b\u90e8.\u7b2c\u4e00\u5b63.S01E01.2160p.WEB-DL.mkv"
    action = _build_video_action(
        item={
            "fid": "f1",
            "file_name": old_name,
            "size": 123,
            "parent_fid": "p1",
        },
        title=title,
        year=1997,
        media_type="tv",
        renamer=renamer,
        season=1,
        episode=1,
    )
    assert action["fallback_name"] is not None
    assert "\u5929\u9f99\u516b\u90e8" in action["fallback_name"]


class _FakeTmdbClientInferredMismatch:
    def __init__(self):
        self.search_tv_calls = 0

    async def search_movies(self, query, year=None):
        return []

    async def search_tv(self, query, year=None):
        self.search_tv_calls += 1
        if self.search_tv_calls == 1:
            return [{"id": 11111, "first_air_date": "2013-01-01", "popularity": 1.0}]
        return [{"id": 75865, "first_air_date": "2018-01-08", "popularity": 1.0}]

    async def details(self, media_type, item_id, language_override=None):
        if item_id == 11111:
            if language_override == "zh-CN":
                return {
                    "id": 11111,
                    "name": "其他剧集",
                    "first_air_date": "2013-01-01",
                    "number_of_seasons": 1,
                    "genres": [{"id": 18, "name": "Drama"}],
                }
            return {
                "id": 11111,
                "name": "Other Show",
                "first_air_date": "2013-01-01",
                "number_of_seasons": 1,
                "genres": [{"id": 18, "name": "Drama"}],
            }

        if language_override == "zh-CN":
            return {
                "id": 75865,
                "name": "擅长捉弄的高木同学",
                "first_air_date": "2018-01-08",
                "number_of_seasons": 3,
                "genres": [{"id": 16, "name": "Animation"}],
            }
        return {
            "id": 75865,
            "name": "Teasing Master Takagi-san",
            "first_air_date": "2018-01-08",
            "number_of_seasons": 3,
            "genres": [{"id": 16, "name": "Animation"}],
        }

    async def alternative_titles(self, media_type, item_id):
        return []


@pytest.mark.parametrize("tmdb_id", [None, 0])
def test_resolve_tmdb_naming_info_inferred_tmdb_id_allows_research(tmdb_id):
    client = _FakeTmdbClientInferredMismatch()
    info = asyncio.run(
        resolve_tmdb_naming_info(
            client,
            Renamer(),
            media_type="tv",
            tmdb_id=tmdb_id,
            title="擅长捉弄的高木同学",
            year=2018,
        )
    )

    assert info.tmdb_id == 75865
    assert info.category == "anime"
    assert info.title == "擅长捉弄的高木同学"
    assert info.year == 2018
    assert info.season_count == 3
    assert client.search_tv_calls == 2
