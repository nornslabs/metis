# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- Keep one feature per directory: `.scratch/<feature-slug>/`.
- Store a feature spec at `.scratch/<feature-slug>/spec.md`.
- Store each implementation ticket in its own file at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Record triage state in a `Status:` line near the top of each issue file, using the role strings in `triage-labels.md`.
- Append comments and conversation history under a `## Comments` heading at the bottom of the file.

## Skill operations

- **Publish an issue or spec:** create a file under `.scratch/<feature-slug>/`, creating the directory if needed.
- **Fetch a ticket:** read the referenced path. The user will normally provide a path or issue number.

## Wayfinding operations

- **Map:** use `.scratch/<effort>/map.md` for Notes, Decisions-so-far, and Fog.
- **Child ticket:** create one file per ticket at `.scratch/<effort>/issues/<NN>-<slug>.md`, numbered from `01`. Include a `Type:` line (`research`, `prototype`, `grilling`, or `task`) and a `Status:` line (`claimed` or `resolved`).
- **Blocking:** record `Blocked by: NN, NN` near the top. A ticket is unblocked when all referenced files have `Status: resolved`.
- **Frontier:** scan the effort's issue files for open, unblocked, unclaimed tickets; choose the first by number.
- **Claim:** set `Status: claimed` and save before starting work.
- **Resolve:** add the answer under `## Answer`, set `Status: resolved`, then add a context pointer to the map's Decisions-so-far.
