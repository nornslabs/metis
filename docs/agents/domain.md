# Domain Docs

Engineering skills should read the repo's domain documentation before exploring code:

- Read the root `GLOSSARY.md`, or `GLOSSARY-MAP.md` if present and the relevant context glossary it points to.
- Read relevant architecture decision records (ADRs) in `docs/adr/` before changing the area they cover.

This is a single-context repo. Keep one glossary at the root and repo-wide ADRs in `docs/adr/`. These files can be created lazily when a domain term or architecture decision needs to be recorded.

Use glossary terms consistently. If a needed concept is missing, call out the gap rather than inventing a competing term. If a change conflicts with an ADR, surface the conflict explicitly.
