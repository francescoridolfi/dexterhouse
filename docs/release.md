# Releasing DexterHouse

For maintainers. One version covers the whole product: the Python packages, the images and
`DH_VERSION`. Pushing a `vX.Y.Z` tag runs `.github/workflows/release.yml`.

## One-time setup

Done once, before the first release, by the repository owner.

1. **Protect `main`** (*Settings → Rules → Rulesets*): pull request required, no force
   push, no deletion, required checks `pre-commit`, `test`, `test-slow (brief-samples)`,
   `test-slow (e2e-builtin)`, `test-slow (runtime)`, `test-slow (runner)`, `security`,
   `frontend`, `images`.
2. **Private vulnerability reporting** on (*Settings → Code security*), and a working
   `security@dexterhouse.dev` mailbox ([SECURITY.md](../SECURITY.md)).
3. **CLA**: legal review of [CLA.md](../CLA.md), then install the CLA Assistant app (or an
   equivalent check) so first-time contributors sign it in their pull request.
4. **PyPI trusted publishing** for `dexterhouse-schema`:
   - on <https://pypi.org/manage/account/publishing/> add a *pending publisher*: project
     `dexterhouse-schema`, owner `francescoridolfi`, repository `dexterhouse`, workflow
     `release.yml`, environment `pypi`;
   - in the repository create the environment `pypi` (optionally with required reviewers)
     and the repository variable `PYPI_PUBLISH=true`.
   Until `PYPI_PUBLISH` is `true` the `pypi` job is skipped and the release goes on without
   it.
5. **The registry repository**: create `francescoridolfi/dexterhouse-registry` from the
   prepared local checkout following its `SETUP.md` (variables `DH_SCHEMA_REF`,
   `CORE_LATEST`, the deploy key, the ruleset). After the first PyPI release switch its
   workflows from `uvx --from git+…` to `uvx dexterhouse-schema==X.Y.Z`.
6. **GHCR visibility**: after the first release, make the packages `dexterhouse-core`,
   `-runner`, `-frontend` and `-workspace` public (*Packages → Package settings → Change
   visibility*) and link them to the repository. New GHCR packages start private, so
   `docker compose pull` fails for everyone else until then.

## Each release

1. `main` is green and the milestone is closed. Check that nothing in `.trivyignore` is
   past its review date.
2. Preview the version and the changelog:

   ```bash
   uvx --from commitizen cz bump --dry-run          # next version from the commits
   uvx --from commitizen cz bump --dry-run 1.0.0    # or an explicit version
   ```

3. Bump on a release branch (`main` is protected, and the `no-commit-to-branch` hook
   refuses commits on it). commitizen updates every version file, `.env.example`,
   `compose.yaml`, `uv.lock` and `CHANGELOG.md`, commits and tags locally:

   ```bash
   git fetch origin && git switch -c release/1.0.0 origin/main
   uvx --from commitizen cz bump 1.0.0
   git push -u origin release/1.0.0          # the branch only, not the tag yet
   gh pr create --fill --base main
   ```

   When CI is green, squash-merge the pull request, then tag the merge commit on `main`
   and push the tag (this starts the release):

   ```bash
   git switch main && git pull
   git tag -d v1.0.0 && git tag v1.0.0
   git push origin v1.0.0
   ```

4. Watch the **Release** workflow: version check, six images built, scanned with Trivy and
   pushed (`core`, `runner`, `frontend` as `X.Y.Z`, `X.Y`, `latest`; `workspace` as
   `python|node|full` and `-X.Y.Z`), `dexterhouse-schema` on PyPI, then the GitHub Release
   with the changelog section and the image digests. A pre-release tag (`v1.1.0-rc.1`)
   moves no `latest` or flavour tag and is marked pre-release.
5. Verify on a clean machine, following [install.md](install.md) with the published images:

   ```bash
   git clone https://github.com/francescoridolfi/dexterhouse.git && cd dexterhouse
   git checkout v1.0.0 && cp .env.example .env
   docker compose pull && docker compose up -d --wait
   ```

   Run a demo project (fake provider) to completion, then the manual security checks of
   [security.md](security.md#security-tests).
6. Announce: the GitHub Release (edit the notes if needed), Discussions, and the project
   site once it exists.

## If a release fails

- Version check failed: the tag does not match the files; delete the tag (`git push
  --delete origin vX.Y.Z`), fix, bump again.
- Trivy failed: update the base image pin (Dependabot usually has a pull request) or, if
  the finding does not apply, add it to `.trivyignore` with a reason and a review date;
  then delete and re-push the tag. Nothing was pushed to GHCR for the failing image.
- PyPI failed: rerun the job; a version already on PyPI cannot be uploaded twice.

## Weekly image rebuild

`images-weekly.yml` runs every Monday at 03:00 UTC (and by hand from *Actions*): it
rebuilds the three workspace images from the latest base images of the same lines, scans
them and pushes `:<flavour>` and `:<flavour>-YYYY.MM.DD`. Core, runner and frontend images
change only with a release; security fixes in their dependencies ship as patch releases.
