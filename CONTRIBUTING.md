# Contributing

## Commit Convention
This project follows [Conventional Commits](https://www.conventionalcommits.org/):
- `feat: ...` — new feature
- `fix: ...` — bug fix
- `docs: ...` — documentation only
- `chore: ...` — tooling, config, non-code changes
- `test: ...` — adding/updating tests
- `refactor: ...` — code change that neither fixes a bug nor adds a feature

Commit messages explain *why*, not just what.

## Branch Naming
- `feat/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`
- `docs/<short-description>`

## Pull Request Process
1. Create an issue describing the work.
2. Branch off `main`.
3. Commit in small, atomic units.
4. Open a PR referencing the issue (`Closes #N`).
5. Self-review the diff with inline comments before merging.
6. Merge once CI is green.

## Bootstrapping Note
`main` was created from `chore/repo-hygiene` at its initial commit, since a
branch must exist before protection rules can be applied. No commit has been
pushed directly to `main`; all subsequent changes merge via reviewed PR.

Branch protection is configured via GitHub Ruleset but is not enforced by
GitHub on private repositories under a free personal account. It becomes
GitHub-enforced once the repository is made public prior to submission.
Until then, the PR-only workflow is maintained manually.