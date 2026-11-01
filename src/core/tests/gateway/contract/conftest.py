# SPDX-License-Identifier: AGPL-3.0-or-later
"""Harness of the provider contract suite: recorded responses, never the network.

HTTP providers get an `httpx2.Client` whose transport replays the cassette body (the
provider's own wire format: SSE, NDJSON); `anthropic-cli` runs a fake `claude` executable
that prints the recorded stream-json and saves what it was given (argv, stdin, MCP config).
See `cassettes/README.md` for the format and how to re-record against real providers.
"""

import json
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import pytest

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.messages import CompletionRequest, Message, TextPart, ToolSpec
from dexterhouse.apps.gateway.providers import Provider, ProviderConfig, get_provider

CASSETTES = Path(__file__).parent / "cassettes"
HTTP_PROVIDERS = ("anthropic", "openai", "openai-compatible", "ollama")
ALL_PROVIDERS = (*HTTP_PROVIDERS, "anthropic-cli")
SEARCH = ToolSpec(
    name="memory.search",
    description="Search the project memory",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
        "required": ["query"],
    },
)

FAKE_CLAUDE = """#!{python}
import json, os, sys
if "--version" in sys.argv:
    print(os.environ.get("FAKE_CLAUDE_VERSION", "2.1.278 (Claude Code)"))
    sys.exit(0)
argv = sys.argv[1:]
record = {{"argv": argv, "stdin": sys.stdin.read(), "cwd": os.getcwd()}}
record["home"] = os.environ.get("HOME")
record["system"] = open(argv[argv.index("--system-prompt-file") + 1]).read()
if "--mcp-config" in argv:
    record["mcp"] = json.load(open(argv[argv.index("--mcp-config") + 1]))
    bridge_env = record["mcp"]["mcpServers"]["dexterhouse"]["env"]
    record["tools_raw"] = open(bridge_env["DH_BRIDGE_TOOLS"]).read()
json.dump(record, open(os.environ["FAKE_CLAUDE_RECORD"], "w"))
if os.environ.get("FAKE_CLAUDE_SLEEP"):
    import time
    time.sleep(float(os.environ["FAKE_CLAUDE_SLEEP"]))
for line in json.load(open(os.environ["FAKE_CLAUDE_CASSETTE"]))["stdout"]:
    print(line, flush=True)
"""


def load(provider: str, scenario: str) -> dict[str, Any]:
    return json.loads((CASSETTES / provider / f"{scenario}.json").read_text(encoding="utf-8"))


def scenarios(provider: str, *, errors: bool) -> list[str]:
    names = sorted(p.stem for p in (CASSETTES / provider).glob("*.json"))
    return [n for n in names if ("error" in load(provider, n)["expect"]) == errors]


@dataclass
class Recorder:
    """What the provider sent: HTTP JSON bodies, or the fake CLI's record."""

    bodies: list[dict[str, Any]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    cli_record: Path | None = None

    @property
    def cli(self) -> dict[str, Any]:
        assert self.cli_record is not None
        return json.loads(self.cli_record.read_text(encoding="utf-8"))


def replay_client(cassette: dict[str, Any], recorder: Recorder) -> httpx2.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        recorder.bodies.append(json.loads(request.content or b"{}"))
        recorder.urls.append(str(request.url))
        body = "\n".join(cassette["body"]) + "\n"
        return httpx2.Response(
            cassette["status"], headers=cassette["headers"], content=body.encode()
        )

    return httpx2.Client(transport=httpx2.MockTransport(handler), base_url="http://provider.test")


def make_request(model: str, extra: list[Message] | None = None) -> CompletionRequest:
    return CompletionRequest(
        messages=[
            Message(
                role="system", parts=[TextPart(text="You are the Analyst.")], cache_breakpoint=True
            ),
            Message(role="user", parts=[TextPart(text="Summarise the brief.")]),
            *(extra or []),
        ],
        tools=[SEARCH],
        profile="balanced",
        model=model,
        max_tokens=512,
        metadata={"agent_turn_id": "0195f3b0-0000-7000-8000-000000000001"},
    )


Build = Callable[..., tuple[Provider, Recorder, dict[str, Any]]]


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake `claude` on CLAUDE_CLI_PATH; returns the record file it writes."""
    script = tmp_path / "claude"
    script.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    record = tmp_path / "record.json"
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    get_gateway_env.cache_clear()
    yield record
    get_gateway_env.cache_clear()


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_claude: Path) -> Build:
    def make(
        provider: str, scenario: str, **options: Any
    ) -> tuple[Provider, Recorder, dict[str, Any]]:
        cassette = load(provider, scenario)
        recorder = Recorder()
        if provider == "anthropic-cli":
            monkeypatch.setenv(
                "FAKE_CLAUDE_CASSETTE", str(CASSETTES / provider / f"{scenario}.json")
            )
            recorder.cli_record = fake_claude
            return get_provider(provider, ProviderConfig(options=options)), recorder, cassette
        config = ProviderConfig(
            api_key="sk-test",  # pragma: allowlist secret
            base_url="http://provider.test/v1" if provider == "openai-compatible" else "",
            http_client=replay_client(cassette, recorder),
            options=options,
        )
        return get_provider(provider, config), recorder, cassette

    return make
