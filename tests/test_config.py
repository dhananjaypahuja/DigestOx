import pytest

from customer_pulse.config import load_config
from customer_pulse.errors import PulseError


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_apply_without_a_config_file(tmp_path):
    config = load_config(None, tmp_path)
    assert config.file is None
    assert config.timezone.key == "UTC"
    assert config.db_path == (tmp_path / ".pulse" / "pulse.db").resolve()


def test_pulse_toml_in_the_working_directory_is_used(tmp_path):
    write(tmp_path / "pulse.toml", '[pulse]\ntimezone = "America/Los_Angeles"\n')
    config = load_config(None, tmp_path)
    assert config.file == (tmp_path / "pulse.toml").resolve()
    assert config.timezone.key == "America/Los_Angeles"


def test_relative_paths_resolve_against_the_config_file(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    config_file = write(project / "pulse.toml", '[pulse]\nstate_dir = "state"\n')
    config = load_config(config_file, elsewhere)
    assert config.state_dir == (project / "state").resolve()


def test_an_explicit_config_must_exist(tmp_path):
    with pytest.raises(PulseError) as caught:
        load_config(tmp_path / "missing.toml", tmp_path)
    assert caught.value.code == "config_not_found"


@pytest.mark.parametrize(
    "text",
    [
        '[pulse]\ntimezone = "Mars/Olympus"\n',  # unknown timezone
        "[pulse]\ntimezone = 7\n",  # wrong type
        '[pulse]\ntimezon = "UTC"\n',  # a typo must not fall back to a default
        '[llm]\nmodel = "x"\n',  # a table this version doesn't know
        'timezone = "UTC"\n',  # a key outside any table
        "[pulse\n",  # not TOML
        '[pulse]\nstate_dir = ""\n',  # empty path
    ],
)
def test_invalid_config_is_a_clear_error(tmp_path, text):
    write(tmp_path / "pulse.toml", text)
    with pytest.raises(PulseError) as caught:
        load_config(None, tmp_path)
    assert caught.value.code == "invalid_config"
