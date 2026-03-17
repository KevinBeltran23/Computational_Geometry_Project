from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import List, Sequence

from .types import Point


@dataclass
class _Node:
    idx: int
    point: Point
    prev: int
    nxt: int
    alive: bool = True
    version: int = 0


def _triangle_area2(a: Point, b: Point, c: Point) -> float:
    # Twice signed area magnitude; monotonic with area, cheaper than 0.5 factor.
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def simplify_vw_to_count(points: Sequence[Point], target_count: int) -> List[Point]:
    n = len(points)
    if n <= target_count:
        return list(points)
    if n <= 2:
        return list(points)

    nodes: List[_Node] = []
    for i, p in enumerate(points):
        nodes.append(
            _Node(
                idx=i,
                point=p,
                prev=i - 1 if i > 0 else -1,
                nxt=i + 1 if i < n - 1 else -1,
            )
        )

    heap: List[tuple[float, int, int]] = []  # (effective area, idx, version)

    def push(i: int) -> None:
        if i <= 0 or i >= n - 1:
            return
        nd = nodes[i]
        if not nd.alive:
            return
        if nd.prev == -1 or nd.nxt == -1:
            return
        a = nodes[nd.prev].point
        b = nd.point
        c = nodes[nd.nxt].point
        area2 = _triangle_area2(a, b, c)
        heapq.heappush(heap, (area2, i, nd.version))

    for i in range(1, n - 1):
        push(i)

    alive_count = n
    while alive_count > target_count and heap:
        _, i, ver = heapq.heappop(heap)
        nd = nodes[i]
        if not nd.alive or nd.version != ver:
            continue

        # remove nd
        nd.alive = False
        alive_count -= 1
        p = nd.prev
        q = nd.nxt
        if p != -1:
            nodes[p].nxt = q
            nodes[p].version += 1
            push(p)
        if q != -1:
            nodes[q].prev = p
            nodes[q].version += 1
            push(q)

    out = [nd.point for nd in nodes if nd.alive]
    if len(out) < 2:
        return [points[0], points[-1]]
    return out
