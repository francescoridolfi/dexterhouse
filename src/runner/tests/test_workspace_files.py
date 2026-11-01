# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from dexterhouse_runner.workspace_mcp import files
from dexterhouse_runner.workspace_mcp.base import (
    OUTPUT_LIMIT,
    Config,
    ToolFailure,
    clip,
    human,
    parse_size,
    resolve,
    usage_bytes,
)


@pytest.mark.parametrize("path", ["../x", "/etc/passwd", "a/../../b", "", "a\x00b"])
def test_escape_is_refused(cfg: Config, path: str):
    with pytest.raises(ToolFailure) as exc:
        resolve(cfg.root, path)
    assert exc.value.code == "workspace_escape"


def test_symlink_out_and_git_writes_are_refused(cfg: Config, tmp_path: Path):
    (cfg.root / "out").symlink_to(tmp_path)
    for path, write in (("out/secret", False), (".git/config", True), ("out", False)):
        with pytest.raises(ToolFailure) as exc:
            resolve(cfg.root, path, write=write)
        assert exc.value.code == "workspace_escape"
    assert resolve(cfg.root, ".git/config") == (cfg.root / ".git/config").resolve()


def test_write_read_edit_move_delete(cfg: Config):
    assert files.write(cfg, "src/app.py", "a = 1\nb = 2\n") == {
        "path": "src/app.py",
        "bytes": 12,
        "created": True,
    }
    assert files.write(cfg, "src/app.py", "a = 1\nb = 2\n")["created"] is False
    read = files.read(cfg, "src/app.py", start_line=2)
    assert read["content"] == "b = 2\n"
    assert read["total_lines"] == 2
    assert files.edit(cfg, "src/app.py", "b = 2", "b = 3")["replaced"] == 1
    with pytest.raises(ToolFailure, match="occurs 1 times"):
        files.edit(cfg, "src/app.py", "a", "c", occurrences=2)
    with pytest.raises(ToolFailure, match="not found"):
        files.edit(cfg, "src/app.py", "zzz", "c")
    assert files.move(cfg, "src/app.py", "src/main.py") == {
        "from": "src/app.py",
        "to": "src/main.py",
    }
    with pytest.raises(ToolFailure) as exc:
        files.move(cfg, "src/missing.py", "x.py")
    assert exc.value.code == "not_found"
    files.write(cfg, "x.py", "")
    with pytest.raises(ToolFailure) as exc:
        files.move(cfg, "src/main.py", "x.py")
    assert exc.value.code == "conflict"
    assert files.delete(cfg, "src")["deleted"] is True
    assert files.delete(cfg, "src")["deleted"] is False
    with pytest.raises(ToolFailure):
        files.delete(cfg, ".")
    with pytest.raises(ToolFailure):
        files.read(cfg, "missing.txt")
    with pytest.raises(ToolFailure):
        files.write(cfg, "nodir/x", "", create_dirs=False)


def test_read_binary_and_large(cfg: Config):
    (cfg.root / "bin").write_bytes(b"\x00\x01")
    assert files.read(cfg, "bin")["encoding"] == "binary"
    files.write(cfg, "big.txt", "x" * (OUTPUT_LIMIT + 10))
    result = files.read(cfg, "big.txt")
    assert result["truncated"]
    assert "hint" in result
    assert len(result["content"]) == OUTPUT_LIMIT


def test_list_ignores_and_sizes(cfg: Config):
    files.write(cfg, "src/pkg/mod.py", "x" * 2048)
    files.write(cfg, "node_modules/lib/index.js", "")
    files.write(cfg, ".env", "A=1")
    tree = files.list_tree(cfg, depth=3)
    assert "src/" in tree["tree"]
    assert "mod.py (2.0 KB)" in tree["tree"]
    assert "node_modules" not in tree["tree"]
    assert ".git" not in tree["tree"]
    assert ".env" not in tree["tree"]
    assert ".env" in files.list_tree(cfg, include_hidden=True)["tree"]
    with pytest.raises(ToolFailure):
        files.list_tree(cfg, "src/pkg/mod.py")


def test_search(cfg: Config):
    files.write(cfg, "a.py", "def handler():\n    return 1\n")
    files.write(cfg, "b.txt", "handler here\n")
    found = files.search(cfg, r"handler", glob="*.py")
    assert [m["file"] for m in found["matches"]] == ["a.py"]
    assert found["matches"][0]["context"][0] == "def handler():"
    assert files.search(cfg, "handler", max_results=1)["truncated"] is True
    with pytest.raises(ToolFailure):
        files.search(cfg, "(")


def test_quota_on_write(repo: Path):
    small = Config(root=repo, quota_bytes=64 * 1024)
    with pytest.raises(ToolFailure) as exc:
        files.write(small, "big.bin", "x" * (200 * 1024))
    assert exc.value.code == "quota_exceeded"
    assert not (repo / "big.bin").exists()


def test_helpers():
    assert parse_size("5G") == 5 * 1024**3
    assert parse_size("512m") == 512 * 1024**2
    assert parse_size("100") == 100
    assert clip("abc", 2) == ("ab", True)
    assert human(10) == "10 B"
    assert human(2048) == "2.0 KB"
    assert ToolFailure("x", "y", a=1).as_dict() == {"error": {"code": "x", "detail": "y"}, "a": 1}


def test_config_from_env(tmp_path: Path):
    cfg = Config.from_env(
        {
            "DH_WORKSPACE_ROOT": str(tmp_path),
            "DH_WORKSPACE_QUOTA": "1G",
            "DH_STACK_ENV_KEYS": "APP_ENV,DEBUG",
            "DH_SERVICES": '[{"name": "redis"}]',
        }
    )
    assert cfg.root == tmp_path
    assert cfg.quota_bytes == 1024**3
    assert cfg.stack_env_keys == {"APP_ENV", "DEBUG"}
    assert cfg.services == [{"name": "redis"}]
    assert usage_bytes(tmp_path / "missing") == 0
