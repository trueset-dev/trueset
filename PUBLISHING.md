# Publishing trueset

A one-time setup, then every release is: tag → GitHub Release → auto-published to
PyPI. Steps only you can do are marked **(you)**; the rest is already wired.

## 1. Create the GitHub org + repo **(you)**

1. Create an organization: https://github.com/organizations/plan → Free.
   Suggested name: `trueset-dev` or `trueset-io` (bare `trueset` is a dormant org;
   the org name does **not** affect `pip install trueset`).
2. Create an empty repo named `trueset` inside that org (no README/license — this
   repo already has them).

## 2. Push this repo **(you, one command)**

Once the org name is set, the remote is added for you (or run it yourself):

```bash
git remote add origin git@github.com:<ORG>/trueset.git
git push -u origin main
```

CI (`.github/workflows/ci.yml`) runs the 83 tests on every push automatically.

## 3. Set up PyPI Trusted Publishing **(you — no token needed)**

Trusted Publishing lets GitHub Actions publish to PyPI over OIDC, so there is no
long-lived API token to leak.

1. Create a PyPI account: https://pypi.org/account/register/ (enable 2FA).
2. Go to https://pypi.org/manage/account/publishing/ and add a **pending
   publisher** with exactly:
   - **PyPI Project Name:** `trueset`
   - **Owner:** `<ORG>` (your GitHub org)
   - **Repository name:** `trueset`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. (Optional, recommended) In the GitHub repo → Settings → Environments, create an
   environment called `pypi` and add yourself as a required reviewer, so a human
   approves each publish.

> Prefer a token instead? Skip Trusted Publishing, create a PyPI API token, add it
> as the `PYPI_API_TOKEN` repo secret, and give `pypa/gh-action-pypi-publish` a
> `with: password: ${{ secrets.PYPI_API_TOKEN }}`. Trusted Publishing is preferred.

## 4. Cut a release **(you)**

```bash
git tag v0.1.0
git push origin v0.1.0
```

Then on GitHub: Releases → Draft a new release → pick tag `v0.1.0` → Publish.
The `release` workflow builds the sdist + wheel, checks the metadata, and
publishes to PyPI. Within a minute:

```bash
pip install trueset
```

## Releasing later versions

1. Bump `version` in `pyproject.toml` and `__version__` in `src/trueset/__init__.py`.
2. Move the `## [Unreleased]` notes in `CHANGELOG.md` under the new version.
3. Tag `vX.Y.Z`, push the tag, publish the GitHub Release.

## TestPyPI first (optional dry run)

Add a second pending publisher on https://test.pypi.org with the same values, and
temporarily point the publish step at TestPyPI (`with: repository-url:
https://test.pypi.org/legacy/`) to rehearse before the real thing.
