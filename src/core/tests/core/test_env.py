# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from dexterhouse.settings.env import Env, read_secret_file


def test_read_secret_file(tmp_path: Path):
    secret = tmp_path / "key"
    secret.write_text("abc\n")
    assert read_secret_file(str(secret)) == "abc"
    assert read_secret_file(str(tmp_path / "missing")) == ""
    assert read_secret_file("") == ""


def test_secret_key_prefers_env(tmp_path: Path):
    secret = tmp_path / "key"
    secret.write_text("from-file")
    assert Env(SECRET_KEY="from-env", SECRET_KEY_FILE=str(secret)).secret_key() == "from-env"
    assert Env(SECRET_KEY="", SECRET_KEY_FILE=str(secret)).secret_key() == "from-file"


def test_database_url_takes_password_from_file(tmp_path: Path):
    secret = tmp_path / "pg"
    secret.write_text("p@ss/w")
    quoted = "p%40ss%2Fw"
    env = Env(DATABASE_URL="postgres://dh@db:5432/dh", DATABASE_PASSWORD_FILE=str(secret))
    assert env.database_url() == f"postgres://dh:{quoted}@db:5432/dh"
    no_port = Env(DATABASE_URL="postgres://dh@db/dh", DATABASE_PASSWORD_FILE=str(secret))
    assert no_port.database_url() == f"postgres://dh:{quoted}@db/dh"
    inline = "postgres://dh:x@db/dh"  # pragma: allowlist secret
    explicit = Env(DATABASE_URL=inline, DATABASE_PASSWORD_FILE=str(secret))
    assert explicit.database_url() == inline
    assert Env(DATABASE_URL="postgres://dh@db/dh").database_url() == "postgres://dh@db/dh"


def test_split():
    assert Env.split(" a, b ,,c") == ["a", "b", "c"]
