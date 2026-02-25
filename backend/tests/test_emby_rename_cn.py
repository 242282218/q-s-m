from app.quark.api.routes.search import TransferRequest, normalize_title_candidate, resolve_final_title
from app.transfer.renamer import Renamer


def test_normalize_title_candidate_strips_prefix():
    assert normalize_title_candidate("01. 三体") == "三体"


def test_resolve_final_title_prefers_chinese_candidate():
    req = TransferRequest(
        link="https://pan.quark.cn/s/demo",
        title="Three Body",
        resource_name="三体",
        to_dir_name="Three Body S01",
    )
    assert resolve_final_title(req, None) == "三体"


def test_tv_rename_uses_chinese_episode_and_emby_token():
    renamer = Renamer()
    result = renamer.generate_tv_path(
        title="三体",
        year=2023,
        original_filename="The.Three.Body.Problem.S01E02.1080p.WEB-DL.mkv",
    )

    assert result.season == 1
    assert result.episode == 2
    assert result.new_name == "三体 第01季第02集 S01E02.mkv"
    assert "/第01季/" in result.new_path

