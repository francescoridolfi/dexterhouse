# dexterhouse-runner

The only DexterHouse service with access to the Docker socket. It creates workspace containers,
runs MCP workspace tools inside them and never holds secrets or writes events (ADR-0006, ADR-0016).
It does not import the core: it talks to it through Celery messages whose payloads live in
`dexterhouse-schema`. Skeleton only until the runner epic.
