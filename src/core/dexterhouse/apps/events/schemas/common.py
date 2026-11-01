# SPDX-License-Identifier: AGPL-3.0-or-later
"""Value objects shared by several event payloads."""

import uuid

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactRef(_Strict):
    id: uuid.UUID
    kind: str
    version: int


class PackageRef(_Strict):
    """A package (or process) pinned to a semver version."""

    name: str
    version: str
