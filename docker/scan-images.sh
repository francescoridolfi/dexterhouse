#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Scan built images with Trivy (T9): fail on CRITICAL vulnerabilities that have a fix,
# except those listed in .trivyignore. Usage: docker/scan-images.sh IMAGE [IMAGE...]
# TRIVY_VERSION overrides the pinned scanner; TRIVY_REPORT_DIR keeps one table per image.
set -euo pipefail

TRIVY_IMAGE="aquasec/trivy:${TRIVY_VERSION:-0.76.1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORTS="${TRIVY_REPORT_DIR:-}"
status=0

for image in "$@"; do
  echo "::group::trivy ${image}"
  args=(image --quiet --scanners vuln --ignore-unfixed --ignorefile /src/.trivyignore)
  if [[ -n "$REPORTS" ]]; then
    mkdir -p "$REPORTS"
    name="$(echo "$image" | tr '/:@' '___')"
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$ROOT:/src:ro" \
      -v trivy-cache:/root/.cache "$TRIVY_IMAGE" "${args[@]}" --severity HIGH,CRITICAL \
      --format table "$image" > "$REPORTS/$name.txt" || true
  fi
  if ! docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$ROOT:/src:ro" \
    -v trivy-cache:/root/.cache "$TRIVY_IMAGE" "${args[@]}" --severity CRITICAL \
    --exit-code 1 "$image"; then
    echo "::error::${image}: CRITICAL vulnerabilities with a fix (see the table above)"
    status=1
  fi
  echo "::endgroup::"
done
exit "$status"
