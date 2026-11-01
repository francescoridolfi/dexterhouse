# SPDX-License-Identifier: AGPL-3.0-or-later
import base64
from pathlib import Path

from dexterhouse.tools.init_secrets import init_secrets, main


def test_creates_missing_and_keeps_existing(tmp_path: Path):
    target = tmp_path / "secrets"
    assert sorted(init_secrets(target)) == ["fernet_key", "pg_password", "runner_key", "secret_key"]
    key = (target / "fernet_key").read_text()
    assert len(base64.urlsafe_b64decode(key)) == 32
    assert len((target / "runner_key").read_text()) == 64
    assert init_secrets(target) == []
    assert (target / "fernet_key").read_text() == key


def test_main(tmp_path: Path, capsys):
    assert main([str(tmp_path)]) == 0
    assert "secret_key" in capsys.readouterr().out
    assert main([]) == 2
