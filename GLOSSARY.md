# Glossary

Shared language for Metis. Terms only; no implementation details.

**Soul**
The written persona of Metis: how it greets people, how it asks questions, and the tone it keeps. One soul is shared by every specialist.
_Avoid_: personality prompt, system voice

**Gate**
A check that must pass before a specialist may take a costly or user-visible action. A gate either lets the action through or rejects it with a reason.
_Avoid_: guardrail, filter, validator

**Input gate**
A gate that decides whether an action is worth taking at all (for example, asking a question or running a search).

**Output gate**
A gate that decides whether something a specialist produced is good enough to keep or show (for example, a question's tone and options, or a piece of advice).

**Skipped item**
An action a gate rejected for good, after the specialist had its chances to revise. A skipped item is a valid outcome, not a failure of the run.
_Avoid_: dropped, failed

**HLD**
The high-level design of a software idea: the MVP broken into components, the build language, and how the components fit together. A blueprint of what is built and why, never the implementation. Non-software ideas have none.
_Avoid_: architecture doc, tech spec

**Issue brief**
A Linear issue's description when it holds everything needed to build the task: goal, context, requirements, what not to do, acceptance criteria, and a link to the HLD component. A developer only needs the issue number.
_Avoid_: ticket text, issue body
