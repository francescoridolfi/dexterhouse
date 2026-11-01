# SPDX-License-Identifier: AGPL-3.0-or-later
import socket
import subprocess
from pathlib import Path

import pytest

from dexterhouse_runner.workspace_mcp import files, gitops, shell
from dexterhouse_runner.workspace_mcp.base import OUTPUT_LIMIT, Config, ToolFailure


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def test_exec_output_env_and_cwd(cfg: Config, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DH_SECRET_INTERNAL", "hidden")
    files.write(cfg, "sub/f.txt", "")
    result = shell.run(
        cfg, "pwd; echo $CI; echo ${DH_SECRET_INTERNAL:-none}", cwd="sub", env={"CI": "1"}
    )
    lines = result["stdout"].splitlines()
    assert lines[0].endswith("/sub")
    assert lines[1:] == ["1", "none"]
    assert result["exit_code"] == 0
    assert result["truncated"] is False
    assert shell.run(cfg, "exit 3")["exit_code"] == 3
    with pytest.raises(ToolFailure) as exc:
        shell.run(cfg, "true", env={"AWS_SECRET": "x"})
    assert exc.value.code == "args_policy"
    with pytest.raises(ToolFailure):
        shell.run(cfg, "  ")
    with pytest.raises(ToolFailure):
        shell.run(cfg, "true", cwd="nope")


def test_exec_truncates_and_times_out(cfg: Config):
    big = shell.run(cfg, f"head -c {OUTPUT_LIMIT + 100} /dev/zero | tr '\\0' a")
    assert big["truncated"]
    assert len(big["stdout"]) == OUTPUT_LIMIT
    assert len(big["full_output"]) > OUTPUT_LIMIT
    with pytest.raises(ToolFailure) as exc:
        shell.run(cfg, "sleep 5", timeout_s=0.2)
    assert exc.value.code == "timeout"
    assert exc.value.data["exit_code"] != 0


def test_exec_background_job_does_not_hang(cfg: Config):
    result = shell.run(cfg, "(sleep 3 &) ; echo done", timeout_s=2)
    assert result["stdout"].strip() == "done"


def test_exec_file_size_limit_is_quota_exceeded(repo: Path):
    small = Config(root=repo, quota_bytes=1024 * 1024)
    with pytest.raises(ToolFailure) as exc:
        shell.run(small, "head -c 3000000 /dev/zero > big.bin")
    assert exc.value.code == "quota_exceeded"


def test_exec_usage_over_quota(repo: Path):
    small = Config(root=repo, quota_bytes=200 * 1024)
    with pytest.raises(ToolFailure) as exc:
        shell.run(small, "for i in 1 2 3; do head -c 150000 /dev/zero > f$i; done")
    assert exc.value.code == "quota_exceeded"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("== 3 passed, 1 failed, 2 skipped in 0.1s ==", (3, 1, 2)),
        ("== 1 failed, 2 error in 1s", (0, 3, 0)),
        ("Tests:       1 failed, 1 skipped, 4 passed, 6 total", (4, 1, 1)),
        ("--- PASS: TestA\n--- FAIL: TestB\n--- SKIP: TestC\n", (1, 1, 1)),
        ("nothing", (0, 0, 0)),
    ],
)
def test_summarize(output: str, expected: tuple[int, int, int]):
    s = shell.summarize(output)
    assert (s["passed"], s["failed"], s["skipped"]) == expected


def test_narrow_test_command(cfg: Config):
    assert shell.narrow_test_command(cfg, "all", None) == cfg.test_command
    pytest_cfg = Config(root=cfg.root, test_command="uv run pytest -q")
    assert (
        shell.narrow_test_command(pytest_cfg, "path", "tests/a.py")
        == "uv run pytest -q 'tests/a.py'"
    )
    npm = Config(root=cfg.root, test_command="npm test")
    assert shell.narrow_test_command(npm, "path", "src/a.test.ts") == "npm test -- 'src/a.test.ts'"
    go = Config(root=cfg.root, test_command="go test ./...")
    assert shell.narrow_test_command(go, "path", "pkg") == "go test ./pkg/..."
    with pytest.raises(ToolFailure):
        shell.narrow_test_command(Config(root=cfg.root), "all", None)


def test_run_tests(cfg: Config):
    result = shell.run_tests(cfg)
    assert result["ok"]
    assert result["summary"]["passed"] == 1
    assert result["full_output"].startswith("$ python3")
    failing = Config(root=cfg.root, test_command="echo '1 failed'; exit 1")
    assert shell.run_tests(failing)["ok"] is False
    slow = Config(root=cfg.root, test_command="sleep 3")
    assert shell.run_tests(slow, timeout_s=0.2)["timed_out"] is True
    with pytest.raises(ToolFailure):
        shell.run_tests(cfg, scope="bad")


def test_services_and_open_port(repo: Path):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        cfg = Config(
            root=repo,
            services=[
                {"name": "redis", "host": "127.0.0.1", "port": port},
                {"name": "postgres", "host": "127.0.0.1", "port": 1},
            ],
        )
        states = {s["name"]: s["status"] for s in shell.services(cfg)["services"]}
    assert states == {"redis": "up", "postgres": "down"}
    assert shell.open_port(cfg, 8000)["url"] == "http://127.0.0.1:8000"
    with pytest.raises(ToolFailure):
        shell.open_port(cfg, 80)


@pytest.fixture
def no_scan(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    found: dict[str, int] = {}
    monkeypatch.setattr(gitops, "scan_secrets", lambda cfg, files: dict(found))
    return found


def test_commit_rules(cfg: Config, no_scan: dict[str, int]):
    files.write(cfg, "a.py", "x = 1\n")
    with pytest.raises(ToolFailure) as exc:
        gitops.commit(cfg, "feat: on main", all=True)
    assert exc.value.code == "protected_branch"
    git(cfg.root, "checkout", "-q", "-b", "task/T-01")
    with pytest.raises(ToolFailure) as exc:
        gitops.commit(cfg, "added stuff", all=True)
    assert exc.value.code == "args_policy"
    with pytest.raises(ToolFailure, match="trailers"):
        gitops.commit(cfg, "feat: x\n\nCo-authored-by: someone <a@b.c>", all=True)
    with pytest.raises(ToolFailure, match="nothing staged"):
        gitops.commit(cfg, "feat: x")
    no_scan["a.py"] = 1
    with pytest.raises(ToolFailure) as exc:
        gitops.commit(cfg, "feat(T-01): add a", all=True)
    assert exc.value.code == "secrets_blocked"
    assert exc.value.data == {"files": ["a.py"], "count": 1}
    assert git(cfg.root, "log", "--format=%s").splitlines() == ["chore: initial commit"]
    no_scan.clear()
    done = gitops.commit(cfg, "feat(T-01): add a", all=True, author="Developer")
    assert done["files_changed"] == 1
    assert done["branch"] == "task/T-01"
    author, committer = git(cfg.root, "log", "-1", "--format=%an <%ae>|%cn").strip().split("|")
    assert author == "Developer (DexterHouse) <agents@dexterhouse.dev>"
    assert committer == "DexterHouse"


def test_lint_is_reported_not_blocking(repo: Path, no_scan: dict[str, int]):
    cfg = Config(root=repo, lint_command="echo 'E501 too long'; exit 1")
    git(repo, "checkout", "-q", "-b", "task/T-02")
    files.write(cfg, "b.py", "y = 2\n")
    gitops.add(cfg, ["b.py"])
    result = gitops.commit(cfg, "fix(T-02): add b")
    assert result["lint"]["exit_code"] == 1
    assert "E501" in result["lint"]["output"]


def test_status_diff_log_show_checkout_stash(cfg: Config, no_scan: dict[str, int]):
    git(cfg.root, "checkout", "-q", "-b", "task/T-03")
    files.write(cfg, "c.txt", "one\n")
    assert gitops.status(cfg)["files"] == [{"status": "??", "path": "c.txt"}]
    gitops.commit(cfg, "feat(T-03): c", all=True)
    assert gitops.status(cfg)["clean"]
    diff = gitops.diff(cfg)
    assert "+one" in diff["diff"]
    assert not diff["truncated"]
    assert "c.txt" in gitops.diff(cfg, stat_only=True)["diff"]
    assert "c.txt" in gitops.diff(cfg, path="c.txt")["diff"]
    files.write(cfg, "c.txt", "two\n")
    assert "+two" in gitops.diff(cfg, base="HEAD", head="WORKTREE")["diff"]
    log = gitops.log(cfg, max=5)["commits"]
    assert [c["message"] for c in log] == ["feat(T-03): c", "chore: initial commit"]
    assert gitops.log(cfg, path="c.txt")["commits"][0]["message"] == "feat(T-03): c"
    assert gitops.show(cfg, "HEAD", "c.txt")["content"] == "one\n"
    assert "feat(T-03)" in gitops.show(cfg, "HEAD")["content"]
    with pytest.raises(ToolFailure):
        gitops.show(cfg, "--output=/tmp/x")
    gitops.checkout_file(cfg, "c.txt")
    assert (cfg.root / "c.txt").read_text() == "one\n"
    files.write(cfg, "d.txt", "tmp\n")
    assert gitops.stash(cfg)["stashed"] is True
    assert not (cfg.root / "d.txt").exists()
    gitops.stash_pop(cfg)
    assert (cfg.root / "d.txt").exists()
    with pytest.raises(ToolFailure):
        gitops.add(cfg, [])
    with pytest.raises(ToolFailure):
        gitops.checkout_file(cfg, "c.txt", ref="--evil")
    with pytest.raises(ToolFailure):
        gitops.git(cfg, "checkout", "no-such-branch")
