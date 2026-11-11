# Metis

## Overview

Metis is an agentic planning app for solo hackers and startup founders. It turns a raw idea (software or not) into a researched, scored and buildable plan: it interviews the user on why the idea matters, finds real competitors and market facts, scores the idea on a fixed rubric with explanations, and turns a confirmed spec into an HLD, phases and Linear issues with dependencies. Low-scoring ideas get advice instead of a plan. Built as an educational hackathon project (2 people, ~30 hours). Free, bring your own keys.

## Goals

1. Go from idea to a sourced score and a Linear-ready plan in one session.
2. Make every score explainable: per-parameter reason, evidence links, confidence.
3. Keep scores live: rescore when the market changes and suggest improvements.
4. Stay pluggable: LLMs, research sources, inputs and integrations swap by config.

## Core User Flow

1. User signs in and adds their OpenAI-compatible LLM key and Exa key.
2. User submits an idea.
3. Metis runs an adaptive interview (why needed, why it works, who pays, feasibility).
4. Metis researches competitors and market facts via Exa, with sources.
5. Metis scores the idea out of 100 with reasons; below 55 it switches to adviser mode (gaps, pivots, revise and rescore).
6. User edits and confirms the generated spec.
7. For software ideas, Metis drafts an HLD and saves it to Notion.
8. Metis splits the spec into phases (user can edit) and phases into tasks with dependencies and point estimates.
9. User approves the export; Metis creates a Linear project (one per idea), milestones per phase, and issues with blocked-by links.
10. Afterwards, market watch rescans, rescores, suggests changes, and rebalances Linear on approval.

## Features

### Discovery and Scoring

- Adaptive interview that skips what user memory already knows.
- Exa research with sourced competitors; shared competitor knowledge base.
- Fixed rubric: Problem severity 25%, Uniqueness 25%, Market demand 15%, Value 15%, Feasibility 10%, Timing 10%.
- Bands: 75+ build it, 55–74 promising, below 55 adviser mode.
- Live scores: weekly market watch (per-idea toggle; if off, prompt to rescan on return), score history, change suggestions, in-app alerts.

### Planning and Export

- Editable, versioned spec; HLD to Notion for software ideas.
- User-configurable phases; tasks with dependencies, labels and Fibonacci points.
- Linear export via MCP: one team per workspace (user picks or creates), one project per idea.
- Rebalance: create new issues, update needed ones, cancel unfinished ones no longer needed, keep done ones.

### Platform

- Multi-user workspaces; BYO keys, encrypted.
- Learning agent: per-user memory, shared market KB, score calibration over time.
- Public shareable score cards.

## Scope

### In Scope (hackathon MVP)

- Web app, multi-user auth, BYO keys.
- Interview → Exa research → score with explanations → adviser mode.
- Editable spec, generated phases and tasks, Linear export via MCP.
- Manual "re-check market" rescore; Markdown export.

### Out of Scope (for now)

- HLD to Notion, rebalance, scheduled market watch, learning agent (next phases).
- Other inputs (CLI, Slack/Discord bot, Metis as an MCP server).
- Other integrations (GitHub Issues, Jira), extra research sources, native non-OpenAI adapters.
- Email/Slack alerts, leaderboard, paid plans or hosted keys.

## Success Criteria

1. A signed-in user can save BYO keys and submit an idea.
2. The interview adapts to answers and ends when evidence is enough.
3. Research returns competitors with source links.
4. The score shows all 6 parameters with reason, evidence and confidence; below 55 shows advice.
5. The user can edit and confirm the spec, and edit phases.
6. Export creates a Linear project, milestones and issues with correct blocked-by links, and re-running it creates no duplicates.
7. A run survives a worker restart and resumes from its last step.
