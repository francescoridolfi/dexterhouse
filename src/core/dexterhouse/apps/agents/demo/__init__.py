# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic answers of the gateway's `fake` provider for the built-in agents.

Set `GATEWAY_FAKE_RESPONDER = "dexterhouse.apps.agents.demo.respond"` and give the
organization `fake` model profiles to run whole projects without any LLM: CI end-to-end
tests, the brief samples suite and demos. Behaviour is scripted by `AGENTS_DEMO_SCRIPT`
(see :mod:`dexterhouse.apps.agents.demo.responder`).
"""

from dexterhouse.apps.agents.demo.responder import respond

__all__ = ["respond"]
