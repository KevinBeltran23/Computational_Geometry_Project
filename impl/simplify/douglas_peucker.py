from __future__ import annotations

from typing import List, Sequence

from .geometry import bbox_diag, point_to_segment_distance
from .types import Point


def _dp(points: Sequence[Point], epsilon: float) -> List[Point]:
    n = len(points)
    if n <= 2:
        return list(points)

    keep = [False] * n
    keep[0] = True
    keep[-1] = True

    stack: List[tuple[int, int]] = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        a = points[i0]
        b = points[i1]

        max_dist = -1.0
        split = -1
        for i in range(i0 + 1, i1):
            d = point_to_segment_distance(points[i], a, b)
            if d > max_dist:
                max_dist = d
                split = i

        if max_dist > epsilon and split != -1:
            keep[split] = True
            stack.append((i0, split))
            stack.append((split, i1))

    return [p for p, k in zip(points, keep) if k]


def simplify_dp_to_count(points: Sequence[Point], target_count: int, steps: int = 30) -> List[Point]:
    if len(points) <= target_count:
        return list(points)

    lo = 0.0
    hi = max(bbox_diag(points), 1e-12)

    best = list(points)
    best_delta = abs(len(best) - target_count)

    for _ in range(steps):
        mid = (lo + hi) / 2.0
        candidate = _dp(points, mid)
        delta = abs(len(candidate) - target_count)
        if delta < best_delta or (delta == best_delta and len(candidate) < len(best)):
            best = candidate
            best_delta = delta

        if len(candidate) > target_count:
            lo = mid
        else:
            hi = mid

    return best
