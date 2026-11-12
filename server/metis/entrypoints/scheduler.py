"""Scheduler process entrypoint.

The scheduler only enqueues jobs (market-watch ticks, nightly maintenance).
Until the real scheduler loop lands it blocks on an event so the process stays
up instead of crashing.
"""

from __future__ import annotations

import asyncio


async def run() -> None:
    """Run the scheduler loop forever.

    The real implementation enqueues ``run_graph`` watch jobs and maintenance
    jobs on a cron schedule. Until then we block on an event so the process
    stays alive.
    """
    await asyncio.Event().wait()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()