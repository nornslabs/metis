"""Feature flag adapters: static (environment-driven) providers."""

from metis.adapters.flags.static import StaticProvider, build_flag_provider

__all__ = ["StaticProvider", "build_flag_provider"]
