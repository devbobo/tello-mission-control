import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("current", "legacy", "expected"),
    [
        (None, None, "192.168.10.1"),
        ("192.0.2.1", None, "192.0.2.1"),
        (None, "192.0.2.2", "192.0.2.2"),
        ("192.0.2.1", "192.0.2.2", "192.0.2.1"),
    ],
)
def test_drone_host_environment_names(monkeypatch, current, legacy, expected):
    monkeypatch.delenv("TELLO_HOST", raising=False)
    monkeypatch.delenv("TELLO_TELLO_HOST", raising=False)
    if current is not None:
        monkeypatch.setenv("TELLO_HOST", current)
    if legacy is not None:
        monkeypatch.setenv("TELLO_TELLO_HOST", legacy)

    assert Settings(_env_file=None).tello_host == expected


def test_drone_host_names_in_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("TELLO_HOST", raising=False)
    monkeypatch.delenv("TELLO_TELLO_HOST", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TELLO_HOST=192.0.2.1\nTELLO_TELLO_HOST=192.0.2.2\n")

    assert Settings(_env_file=env_file).tello_host == "192.0.2.1"


def test_drone_host_can_be_set_directly(monkeypatch):
    monkeypatch.delenv("TELLO_HOST", raising=False)
    monkeypatch.delenv("TELLO_TELLO_HOST", raising=False)

    assert Settings(_env_file=None, tello_host="192.0.2.3").tello_host == "192.0.2.3"


@pytest.mark.parametrize(
    ("environment_name", "file_name"),
    [
        ("TELLO_HOST", "TELLO_TELLO_HOST"),
        ("TELLO_TELLO_HOST", "TELLO_HOST"),
    ],
)
def test_current_host_name_takes_precedence_across_sources(
    monkeypatch, tmp_path, environment_name, file_name
):
    monkeypatch.delenv("TELLO_HOST", raising=False)
    monkeypatch.delenv("TELLO_TELLO_HOST", raising=False)
    monkeypatch.setenv(environment_name, "192.0.2.1")
    env_file = tmp_path / ".env"
    env_file.write_text(f"{file_name}=192.0.2.2\n")
    expected = "192.0.2.1" if environment_name == "TELLO_HOST" else "192.0.2.2"

    assert Settings(_env_file=env_file).tello_host == expected


def test_explicit_drone_host_takes_precedence_over_environment(monkeypatch):
    monkeypatch.setenv("TELLO_HOST", "192.0.2.1")
    monkeypatch.delenv("TELLO_TELLO_HOST", raising=False)

    assert Settings(_env_file=None, tello_host="192.0.2.3").tello_host == "192.0.2.3"
