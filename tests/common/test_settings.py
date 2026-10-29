"""설정값 파일(config/settings.yaml) 로드 테스트."""

import pytest
import yaml

from aimp.common import settings as settings_module
from aimp.common.settings import CONFIG_DIR


def _remove_key(config):
    del config["recommend_count"]


def _unknown_key(config):
    config["recommend_cnt"] = 3


def _wrong_type(config):
    config["assessment_timeout_seconds"] = "3초"


@pytest.mark.parametrize("mutate", [_remove_key, _unknown_key, _wrong_type])
def test_malformed_settings_fail_to_load(tmp_path, mutate):
    """실제 설정값 파일에서 키를 빼거나, 모르는 키(오타)를 넣거나, 값의 타입을 틀리게 바꾸면 읽지 못하는지 확인한다."""
    config = yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8"))
    mutate(config)
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValueError):
        settings_module.load(path)


def test_duplicate_key_fails_to_load(tmp_path):
    """같은 키를 두 번 적으면 마지막 값을 쓰지 않고 설정값 파일을 읽지 못하는지 확인한다."""
    text = (CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8")
    path = tmp_path / "settings.yaml"
    path.write_text(text + "recommend_count: 5\n", encoding="utf-8")

    with pytest.raises(ValueError, match="recommend_count"):
        settings_module.load(path)
