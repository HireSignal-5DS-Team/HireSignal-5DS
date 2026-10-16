"""Small statistics helpers (no scipy)."""
import math


def wilson(k, n, z=1.96):
    """Wilson score 95 % interval of a proportion k/n; None when n == 0."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def pct(xs, q):
    """Nearest-rank percentile; None for an empty list."""
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(q / 100 * len(s)) - 1))]


def exact_binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial test (sign / McNemar on discordant pairs)."""
    if n == 0:
        return 1.0
    probs = [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(x for x in probs if x <= probs[k] * (1 + 1e-9)))
