"""A tiny, dependency-free .env loader so `python -m verdict --live` is turnkey for the demo.

Loads KEY=VALUE lines into os.environ, but NEVER overrides a variable already set in the
real environment (an exported key wins over the file), and skips blanks / comments / empty
values so a `VERDICT_MODEL=` line in a copied .env does not blank the model.
"""
import os

from verdict.env import load_dotenv


def test_load_dotenv_sets_missing_and_respects_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "ANTHROPIC_API_KEY=sk-test-123\n"
        'QUOTED="with spaces"\n'
        "EMPTY=\n"
        "ALREADY=from_file\n"
        "export EXPORTED=yes\n"
    )
    for k in ("ANTHROPIC_API_KEY", "QUOTED", "EMPTY", "EXPORTED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALREADY", "from_real_env")

    load_dotenv(str(env))

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test-123"
    assert os.environ["QUOTED"] == "with spaces"       # surrounding quotes stripped
    assert os.environ["EXPORTED"] == "yes"             # `export ` prefix tolerated
    assert "EMPTY" not in os.environ                    # empty values are skipped, not set blank
    assert os.environ["ALREADY"] == "from_real_env"     # real env wins; file never overrides


def test_load_dotenv_missing_file_is_a_noop(tmp_path):
    load_dotenv(str(tmp_path / "does-not-exist.env"))  # must not raise
