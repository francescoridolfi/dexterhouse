# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from dexterhouse_runner import __version__
from dexterhouse_runner.cli import main


@pytest.mark.parametrize(("argv", "code", "out"), [([], 0, "ok"), (["version"], 0, __version__)])
def test_known_commands(capsys: pytest.CaptureFixture[str], argv: list[str], code: int, out: str):
    assert main(argv) == code
    assert capsys.readouterr().out.strip() == out


def test_unknown_command(capsys: pytest.CaptureFixture[str]):
    assert main(["explode"]) == 2
    assert "unknown command" in capsys.readouterr().err
