# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pre-start validation (F-001, findings #11): errors are returned before `running`."""

import base64
import os
import shutil
import subprocess  # nosec B404: fixed argv, no shell, used only for `git ls-remote`
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.workflows.registry import get_process
from dexterhouse.apps.workflows.roles import installed_roles, process_roles
from dexterhouse.common import crypto

MODEL_PROFILES = frozenset({"strong", "balanced", "fast", "embed"})
LS_REMOTE_TIMEOUT_S = 20

RepoChecker = Callable[[str, str | None], str | None]


def git_ls_remote(url: str, token: str | None) -> str | None:
    """`git ls-remote` with the token sent as an HTTP header via env (not visible in argv)."""
    git = shutil.which("git")
    if git is None:
        return "git is not available to check the repository"
    env = {"PATH": os.environ.get("PATH", ""), "GIT_TERMINAL_PROMPT": "0", "HOME": "/nonexistent"}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env |= {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
        }
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603: argv list, https URL validated
            [git, "ls-remote", "--heads", "--", url],
            env=env,
            capture_output=True,
            timeout=LS_REMOTE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "the repository did not answer in time"
    return None if result.returncode == 0 else "cannot read the repository with the given token"


def _roles_without_package(roles: set[str], organization_id: Any = None) -> list[str]:
    """Roles that cannot run, when the configured runner needs agent packages."""
    from dexterhouse.apps.agents.services.roster import installed_package_roles

    runner = import_string(settings.WORKFLOWS_TURN_RUNNER)
    if not getattr(runner, "requires_packages", False):
        return []
    return sorted(roles - installed_package_roles(organization_id))


def validate_for_start(project: Project) -> list[dict[str, str]]:
    """Return `[{field, message}]`; empty means the project can start."""
    errors: list[dict[str, str]] = []
    installed = get_process(project.process_name, project.organization_id)
    if installed is None or installed.version != project.process_version:
        errors.append(
            {
                "field": "process",
                "message": f"process {project.process_name}@{project.process_version} "
                "is not installed",
            }
        )
    else:
        roles = process_roles(installed.process)
        missing = sorted(roles - installed_roles(project.organization_id))
        if missing:
            errors.append(
                {"field": "process", "message": f"agent roles not installed: {', '.join(missing)}"}
            )
        without = _roles_without_package(process_roles(installed.process), project.organization_id)
        if without:
            errors.append(
                {
                    "field": "process",
                    "message": f"no agent package for role(s): {', '.join(without)}",
                }
            )
        if "stack" in installed.requirements and not project.stack:
            phases = ", ".join(installed.requirements["stack"])
            errors.append(
                {"field": "stack", "message": f"required by phase(s) {phases} of the process"}
            )
    if project.budget <= 0:
        errors.append({"field": "budget", "message": "must be greater than 0"})
    unknown = sorted(set(project.model_profile_overrides or {}) - MODEL_PROFILES)
    if unknown:
        errors.append(
            {
                "field": "model_profile_overrides",
                "message": f"unknown profile(s): {', '.join(unknown)}",
            }
        )
    if project.remote_repo_url:
        token = crypto.decrypt(project.remote_token) if project.remote_token else None
        checker: RepoChecker = import_string(settings.WORKFLOWS_REPO_CHECKER)
        problem = checker(project.remote_repo_url, token)
        if problem:
            errors.append({"field": "remote_repo_url", "message": problem})
    return errors
