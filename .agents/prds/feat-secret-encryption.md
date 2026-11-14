# PRD: feat-secret-encryption

Linear: SHIP-215 · https://linear.app/heimdallabs/issue/SHIP-215/09-envelope-encryption-for-secrets

## Problem / Goal

Workspaces will bring their own LLM, Exa and MCP credentials (BYO). `architecture.md` says these are stored encrypted and never returned or logged, but nothing can encrypt them today. `ENCRYPTION_MASTER_KEY` is already loaded and validated (32 bytes, base64) in `core/config.py`, yet no code uses it. If provider keys were stored now, a database leak would leak every key.

Goal: a small `core/crypto.py` that seals a secret with envelope encryption (AES-256-GCM), binds it to its workspace, carries a master-key version for later rotation, and masks secrets for display. This unblocks SHIP-217 (provider keys and settings API) and SHIP-231 (MCP connections).

## User stories

1. As a workspace owner, I want my LLM and Exa keys encrypted at rest, so that a database leak does not leak my keys.
2. As a workspace owner, I want my MCP OAuth tokens encrypted at rest, so that a leaked backup cannot be used against my Linear or Notion.
3. As a workspace owner, I want to see a masked form of my key (e.g. `sk-…a1b2`), so that I can tell which key is saved without it being shown.
4. As a workspace owner, I want a secret from my workspace to be unusable in another workspace, so that a row copied across tenants cannot be decrypted there.
5. As a service author (provider keys, MCP), I want `encrypt(plaintext, aad) -> SealedSecret`, so that I can store a secret without touching cipher details.
6. As a service author, I want `decrypt(sealed, aad) -> str`, so that I can use a stored secret right before calling the provider.
7. As a service author, I want `SealedSecret` to have exactly the fields I store (`ciphertext`, `nonce`, `wrapped_key`, `key_version`), so that my table columns map one to one.
8. As a service author, I want decrypting with the wrong workspace, a tampered field or an unknown key version to raise one clear domain error, so that I never get garbage plaintext and can handle the failure in one place.
9. As a service author, I want `mask(secret)` in the same module, so that every API shows secrets the same way.
10. As an operator, I want each secret sealed with its own random data key, so that one compromised data key exposes one secret, not all.
11. As an operator, I want every sealed secret to record the master-key version, so that the master key can be rotated later (decrypt with old, re-encrypt with new) without guessing which key sealed which row.
12. As an operator, I want the master key read only from `ENCRYPTION_MASTER_KEY` via `core/config.py`, so that there is one source of configuration and no key in code.
13. As an operator, I want no plaintext secret, data key or master key in logs or error messages, so that logs are safe to ship.
14. As a security reviewer, I want only the `cryptography` library used, so that no hand-rolled crypto exists.
15. As a security reviewer, I want a fresh random nonce for every encryption, so that AES-GCM nonces are never reused under one key.
16. As a developer, I want `SealedSecret` immutable, so that a sealed value cannot be half-changed in memory.
17. As a developer, I want the crypto errors in the error catalog, so that an API that hits one returns RFC 7807 without leaking detail.

## Requirements

1. Add `cryptography` to `server/pyproject.toml` dependencies via `uv add cryptography` (updates `uv.lock` through the package manager).
2. `server/metis/core/crypto.py` (new):
   - `SealedSecret`: frozen Pydantic v2 model with `ciphertext: bytes`, `nonce: bytes`, `wrapped_key: bytes`, `key_version: int`.
   - `encrypt(plaintext: str, aad: str | UUID) -> SealedSecret`: generate a random 32-byte data key and a random 12-byte nonce; encrypt the UTF-8 plaintext with AES-256-GCM under the data key with `aad` as associated data; wrap the data key with AES-256-GCM under the current master key (its own random nonce, stored as part of `wrapped_key`) with `aad` and `key_version` as associated data; return the sealed value with the current `key_version`.
   - `decrypt(sealed: SealedSecret, aad: str | UUID) -> str`: look up the master key for `sealed.key_version`, unwrap the data key, decrypt, return the plaintext.
   - `aad` is the `workspace_id`; callers pass it, `core/crypto.py` does not know about workspaces beyond encoding it as bytes consistently (a `UUID` and its string form give the same bytes).
   - `mask(secret: str) -> str`: first 3 characters + `…` + last 4 when the secret is at least 12 characters long (e.g. `sk-…a1b2`); otherwise `…••••` (nothing revealed). The minimum length and visible counts are named constants.
3. Key versions: a keyring maps `key_version` to master key. For now it holds one entry, version `1` → `ENCRYPTION_MASTER_KEY` (base64-decoded, from `get_settings()`). `CURRENT_KEY_VERSION` is a named constant. Adding a version later must need no change to stored rows or to `encrypt`/`decrypt` signatures.
4. Errors: add `SecretDecryptError` (code `crypto.decrypt_failed`, HTTP 422, user-facing message asking to re-enter the key) to `core/errors.py` and the error catalog. It is raised for a wrong `aad`, any tampered field, a malformed field and an unknown `key_version`. Its message never contains plaintext, key material or ciphertext. `encrypt` with an empty plaintext raises `InvalidInputError`.
5. Logging: `core/crypto.py` logs nothing that contains plaintext or key material. The existing `_redact_secrets` processor in `core/logging.py` stays the safety net.
6. Named constants for key and nonce sizes; no magic numbers.
7. Docs sync: in `.agents/ctx/server-context.md`, add a short "Secrets" line under the config/security section (envelope encryption, AES-256-GCM, `workspace_id` as AAD, `key_version`, `mask`) and `SecretDecryptError` to the Errors table.

## Out of scope

- KMS integration.
- The rotation job (re-encrypting rows under a new master key) and any second master-key env var.
- Tables or columns that store `SealedSecret` (SHIP-217 provider keys, SHIP-231 MCP connections).
- API endpoints that accept or show keys.
- Changes to log redaction in `core/logging.py`.

## Touches

`server/metis/core/crypto.py` (new), `server/metis/core/errors.py`, `server/tests/core/test_crypto.py` (new), `server/pyproject.toml`, `server/uv.lock` (via `uv add`), `.agents/ctx/server-context.md`.

## Dependencies

- SHIP-206 Core infrastructure (Done in Linear; delivered as `chore-core-config`, `chore-core-errors`, `feat-global-logger`, all `done`).

Blocks: SHIP-217 (provider keys and settings API), SHIP-231 (MCP connections).

## Test seam

One seam, the highest available: the public `encrypt` / `decrypt` / `mask` functions of `core/crypto.py`. Pure functions, no DB or Redis. Tests assert only what a caller sees: the returned plaintext, the raised error type and code, and the masked string. No assertions on internal helpers, wire layout of `wrapped_key`, or cipher calls. Master keys come from settings built in the test (as `tests/core/test_config.py` does), never from a real secret. Prior art: `tests/core/test_ids.py` (pure-function tests), `tests/core/test_errors.py` (error code assertions).

Planned tests:

- Round trip: `decrypt(encrypt(s, ws), ws) == s`, including a non-ASCII secret.
- Two encryptions of the same secret differ (fresh data key and nonce).
- Tampering with `ciphertext`, `nonce` or `wrapped_key` (flip one byte) raises `SecretDecryptError`.
- Decrypting with a different `workspace_id` raises `SecretDecryptError`.
- An unknown `key_version` raises `SecretDecryptError`.
- A secret sealed under one master key fails under another master key.
- `encrypt("")` raises `InvalidInputError`.
- `mask` of a long secret is first 3 + `…` + last 4 and reveals no other characters; a secret shorter than 12 reveals nothing.
- A failed decrypt maps to HTTP 422 with code `crypto.decrypt_failed`.
- Error messages from failed decrypts do not contain the plaintext.

## Acceptance criteria

- [x] All tests pass; the library is `cryptography` only.
- [x] Round trip works; tampered ciphertext fails; wrong `workspace_id` fails.
- [x] Masked value shows only the last 4 characters of the secret.
- [x] `key_version` is stored and checked so the master key can rotate later.
- [x] No plaintext secret appears in logs (covered by log redaction from core infra; `core/crypto.py` logs no secret material).
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.
- [x] `server-context.md` documents the secrets convention and `SecretDecryptError`.

## Open questions

None. Resolved 2026-11-14:

- `mask` format: first 3 + `…` + last 4 for secrets ≥ 12 chars; shorter secrets reveal nothing.
- `SecretDecryptError` maps to HTTP 422 and asks the user to re-enter the key.
- Test seam: only the public `encrypt` / `decrypt` / `mask` functions.

## Status

done
