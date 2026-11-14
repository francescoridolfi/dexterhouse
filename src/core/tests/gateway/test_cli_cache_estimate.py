# SPDX-License-Identifier: AGPL-3.0-or-later
"""The block transcript writes each step once instead of rewriting the whole conversation."""

from tests.gateway.cli_cache_estimate import Shape, estimate


def test_cache_writes_grow_by_the_new_step_only():
    shape = Shape(steps=18)
    result = estimate(shape)
    before, _ = result["before"]
    after, after_reads = result["after"]
    step = shape.call + shape.result
    assert all(w >= shape.context for w in before)  # every call rewrites the conversation
    assert after[0] >= shape.context
    assert all(w <= step * 1.1 for w in after[1:])  # then only the new step is written
    assert sum(after) * 10 < sum(before)
    assert after_reads[-1] >= shape.context + (shape.steps - 2) * step * 0.9
