from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

from .types import Point


def path_length(points: Sequence[Point]) -> float:
    return sum(math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]) for i in range(1, len(points)))


def point_to_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return math.hypot(px - qx, py - qy)


def max_perpendicular_error(original: Sequence[Point], simplified: Sequence[Point]) -> float:
    if len(original) <= 1 or len(simplified) <= 1:
        return 0.0

    segs = list(zip(simplified[:-1], simplified[1:]))
    max_err = 0.0
    for p in original:
        d = min(point_to_segment_distance(p, a, b) for a, b in segs)
        if d > max_err:
            max_err = d
    return max_err


def directed_hausdorff(a: Sequence[Point], b: Sequence[Point]) -> float:
    # Discrete directed Hausdorff distance over vertex sets.
    if not a or not b:
        return 0.0
    best = 0.0
    for p in a:
        d = min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in b)
        if d > best:
            best = d
    return best


def symmetric_hausdorff(a: Sequence[Point], b: Sequence[Point]) -> float:
    return max(directed_hausdorff(a, b), directed_hausdorff(b, a))


def compression_ratio(original_n: int, simplified_n: int) -> float:
    if original_n <= 0:
        return 0.0
    return 1.0 - (simplified_n / original_n)


def bbox_diag(points: Sequence[Point]) -> float:
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))
