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


def test_load_dotenv_strips_only_matched_quote_pairs(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'QUOTED="claude-opus-4-8"\n'
        'MISMATCHED="value"garbage\n'
        "APOSTROPHE=it's\n"
    )
    for k in ("QUOTED", "MISMATCHED", "APOSTROPHE"):
        monkeypatch.delenv(k, raising=False)

    load_dotenv(str(env))

    assert os.environ["QUOTED"] == "claude-opus-4-8"     # matched surrounding pair stripped
    assert os.environ["MISMATCHED"] == '"value"garbage'   # unbalanced -> left intact, not half-stripped
    assert os.environ["APOSTROPHE"] == "it's"             # inner apostrophe preserved


def test_load_dotenv_missing_file_is_a_noop(tmp_path):
    load_dotenv(str(tmp_path / "does-not-exist.env"))  # must not raise
