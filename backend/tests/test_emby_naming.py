import asyncio

from app.transfer.emby import pick_romanized_title, resolve_media_category, resolve_tmdb_naming_info
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
    async def search_movies(self, query, year=None):
        return []

    async def search_tv(self, query, year=None):
        assert query
        return [{"id": 75865, "first_air_date": "2018-01-08", "popularity": 1.0}]

    async def details(self, media_type, item_id, language_override=None):
        if item_id == 74532:
            return {
                "id": 74532,
                "name": "Deadline: Crime with Tamron Hall",
                "first_air_date": "2013-09-01",
                "number_of_seasons": 6,
                "genres": [{"id": 18, "name": "Drama"}],
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
        return [{"iso_3166_1": "JP", "type": "Romaji", "title": "Karakai Jouzu no Takagi-san"}]


def test_resolve_tmdb_naming_info_fallback_from_wrong_tmdb_id():
    info = asyncio.run(
        resolve_tmdb_naming_info(
            _FakeTmdbClient(),
            Renamer(),
            media_type="tv",
            tmdb_id=74532,
            title="擅长捉弄的高木同学",
            year=2018,
        )
    )
    assert info.tmdb_id == 75865
    assert info.category == "anime"
    assert info.title == "Karakai Jouzu no Takagi-san"
    assert info.season_count == 3
