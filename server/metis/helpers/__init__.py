"""Generic helpers: stateless code with no business rules and no knowledge of a
particular vendor, module or request. Any layer may import them.

Infrastructure with state or config (DB, jobs, events, auth, crypto, logging,
errors, config) lives in ``core``; vendor wrappers live in ``adapters``.
"""
