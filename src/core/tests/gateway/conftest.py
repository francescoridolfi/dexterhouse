# SPDX-License-Identifier: AGPL-3.0-or-later
from collections.abc import Callable

import pytest

from dexterhouse.apps.gateway.messages import CompletionRequest, Message, TextPart


@pytest.fixture
def make_request() -> Callable[..., CompletionRequest]:
    def build(text: str = "hello") -> CompletionRequest:
        return CompletionRequest(
            messages=[
                Message(
                    role="system", parts=[TextPart(text="You are an agent.")], cache_breakpoint=True
                ),
                Message(role="user", parts=[TextPart(text=text)]),
            ],
            profile="fast",
            model="fake-model",
            max_tokens=100,
        )

    return build
