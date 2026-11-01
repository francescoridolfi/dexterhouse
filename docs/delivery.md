# Delivering releases

After the release gate DexterHouse pushes the project's `main` to your repository
(`Project.remote_repo_url`). It never force-pushes and never pushes from inside a workspace:
the runner redeems the token once, through a grant that lives 60 seconds, and gives it to git
only for that push.

| `delivery_mode` | What happens |
|---|---|
| `pull_request` (default) | push to `dexterhouse/release-<n>` and open a pull request (GitHub) or merge request (GitLab) towards `main`; without the right token scope the branch is pushed and you open the request yourself |
| `push_main` | push to `main` as a fast-forward; refused when `main` is protected or has commits the release lacks |

Token scopes:

- GitHub: a classic token with `repo`, or a fine-grained token with `Contents: read and write`
  and `Pull requests: read and write` on the repository.
- GitLab: a project or personal access token with `api` (`write_repository` alone pushes the
  branch but cannot open the merge request).

The outcome is the event `release.delivered` (with the pull request URL when one was opened)
or `release.failed` with `auth`, `protected_branch`, `conflict` or `network`.
