from __future__ import annotations

import math


def downsample(values: list[float | None] | None, n: int) -> list[float | None]:
    """Reduz a série a no máximo ``n`` pontos pela média de cada bucket.

    None/vazio → []. Série menor/igual a n → cópia. Bucket sem números → None."""
    if not values:
        return []
    if len(values) <= n or n <= 0:
        return list(values)
    size = len(values) / n
    out: list[float | None] = []
    for i in range(n):
        lo = math.floor(i * size)
        hi = math.floor((i + 1) * size) if i < n - 1 else len(values)
        nums = [v for v in values[lo:hi] if v is not None]
        out.append(round(sum(nums) / len(nums), 2) if nums else None)
    return out
