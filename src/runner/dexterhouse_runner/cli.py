# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-runner`: `worker` (the Celery worker), `health`, `version`."""

import sys

from dexterhouse_runner import __version__


def health() -> int:
    """Healthy when the Docker daemon and the broker answer (compose healthcheck)."""
    import docker
    import redis

    from dexterhouse_runner.config import get_settings

    try:
        docker.from_env(timeout=5).ping()
        redis.Redis.from_url(get_settings().REDIS_URL, socket_timeout=5).ping()
    except Exception as exc:
        sys.stderr.write(f"unhealthy: {exc}\n")
        return 1
    sys.stdout.write("ok\n")
    return 0


def worker(extra: list[str]) -> int:
    from dexterhouse_runner.config import get_settings
    from dexterhouse_runner.tasks import app

    settings = get_settings()
    argv = [
        "worker",
        "-Q",
        "runner",
        "-P",
        "threads",
        "-c",
        str(settings.RUNNER_CONCURRENCY),
        "-n",
        f"runner@{settings.RUNNER_ID}",
        "-l",
        "info",
        *extra,
    ]
    app.worker_main(argv)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "health"
    if command == "version":
        sys.stdout.write(f"{__version__}\n")
        return 0
    if command == "health":
        return health()
    if command == "worker":
        return worker(args[1:])
    sys.stderr.write(f"unknown command: {command}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
