# software-house-default

The default DexterHouse process: the brief goes through analysis, architecture and planning,
each closed by an approval gate; tasks are implemented one at a time by a developer, a
reviewer and a tester (at most 3 iterations, then escalation); the release is integration
tested, smoke tested and delivered after the `approve_release` gate; a retrospective closes
the project.

In `autonomous` mode approval gates are auto-approved (and recorded) unless the project marks
them `always_required`; the analyst writes assumptions instead of asking questions.
