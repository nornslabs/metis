# Pull Request

## Summary

<!-- One paragraph: what this PR does and why. -->

## Linear

Closes linear issue: `SHIP-XXXX` — https://linear.app/heimdallabs/issue/SHIP-XXXX

<!-- Linear closes the linked issue when this PR is merged. Any of these
     keywords work: `Closes`, `Fixes`, `Resolves`, `Relates to`.
     If there is no Linear issue yet, create one first and replace this line. -->

## Spec

PRD: `.agents/prds/<type>-<name>.md`

<!-- The PRD this PR implements. One PRD = one PR = one branch.
     Branch name must match the PRD: <type>/<kebab-name> -->

## Scope

- **Touches:** (folders / modules)
- **Out of scope:** (what this PR deliberately does not do)

## Before merging

- [ ] Acceptance criteria in the PRD pass end to end.
- [ ] No invariant in `.agents/ctx/architecture.md` is violated.
- [ ] Server: `uv run ruff check .`, `uv run mypy`, `uv run pytest` pass.
- [ ] Web: `npm run lint`, `npm run typecheck`, `npm run build` pass.
- [ ] Docker images build (`server`, `web`).
- [ ] `.agents/progress-tracker.md` is updated (PRD status `done`, row marked).
- [ ] Matching `.agents/ctx/*.md` synced if architecture / enums / conventions changed.
- [ ] Conventional commit message, e.g. `feat(auth): add workspace RLS (SHIP-2XXX)`.

## Notes

<!-- Anything a reviewer should know: trade-offs, known limitations, follow-ups. -->