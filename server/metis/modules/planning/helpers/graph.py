"""Graph checks on task links: which nodes sit on a cycle."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable


def nodes_on_cycles[K: Hashable](nodes: Iterable[K], edges: Iterable[tuple[K, K]]) -> list[K]:
    """The nodes on a cycle, or between cycles; ``[]`` when the graph has none.

    ``edges`` are ``(from, to)`` pairs. The graph is trimmed from both ends (Kahn's sort from
    the sources, then from the sinks), so tasks that merely wait on a loop are not reported.
    Nodes come back in the order given.
    """
    ordered = list(nodes)
    remaining = set(ordered)
    pairs = [(a, b) for a, b in edges if a in remaining and b in remaining]
    for direction in (0, 1):
        remaining = _trim(remaining, pairs, direction)
        pairs = [(a, b) for a, b in pairs if a in remaining and b in remaining]
    return [node for node in ordered if node in remaining]


def _trim[K: Hashable](nodes: set[K], pairs: list[tuple[K, K]], direction: int) -> set[K]:
    """Drop nodes with no incoming edges (direction 0) or no outgoing ones (direction 1)."""
    waiting: dict[K, int] = {node: 0 for node in nodes}
    next_nodes: dict[K, list[K]] = defaultdict(list)
    for pair in pairs:
        source, target = pair[direction], pair[1 - direction]
        waiting[target] += 1
        next_nodes[source].append(target)
    queue = deque(node for node, count in waiting.items() if count == 0)
    removed: set[K] = set()
    while queue:
        node = queue.popleft()
        removed.add(node)
        for target in next_nodes[node]:
            waiting[target] -= 1
            if waiting[target] == 0:
                queue.append(target)
    return nodes - removed
