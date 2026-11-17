"""Analog-launch forecaster for a game's Twitch viewers over its release day.

Given the hour-1 print of a launch, every past launch in the case's `comparables` votes on how the next 23 hourly
counts relate to its own hour 1 (a log ratio). Launches of a similar audience size weigh more, and each hour's five
quantiles are weighted empirical quantiles of those log ratios.
"""

import math
from datetime import datetime, timezone
from functools import lru_cache

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)

# Chosen by leave-one-out over the comparables: the kernel width, in ln-viewers, of how far a past launch's hour 1
# may sit from the target's and still count. Wider kernels let tiny launches that exploded later inflate the tails.
SIZE_BANDWIDTH = 1.2
# A console-only launch (no PC version) follows the same release-day rhythm as GTA VI, which is console-only too:
# its curve counts this many times as much as a PC-or-mixed launch's of the same size.
CONSOLE_ONLY_BONUS = 4.0
# Fewest analogues an hour needs before its own spread is trusted.
MIN_POINTS = 4
# Hours of a comparable's release day (of 23) it must cover to be used at all.
MIN_COVERED_HOURS = 8


@lru_cache(maxsize=None)
def to_epoch(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def hour1_print(case):
    known = case["known"]
    row = known[0] if isinstance(known, list) else known
    return max(float(row["viewers"]), 1.0)


def curve_by_offset(hourly, day_start):
    """Map whole hours since day_start to viewers for a list of {from, viewers} points."""
    t0 = to_epoch(day_start)
    out = {}
    for point in hourly:
        out[int(round((to_epoch(point["from"]) - t0) / 3600.0))] = float(point["viewers"])
    return out


def weighted_quantile(pairs, tau):
    """Quantile of (value, weight) pairs by interpolating the weighted empirical CDF at midpoints."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if len(pairs) == 1:
        return pairs[0][0]
    cum = 0.0
    mids = []
    for _, weight in pairs:
        mids.append((cum + weight / 2.0) / total)
        cum += weight
    if tau <= mids[0]:
        return pairs[0][0]
    if tau >= mids[-1]:
        return pairs[-1][0]
    for i in range(1, len(pairs)):
        if tau <= mids[i]:
            span = mids[i] - mids[i - 1]
            frac = (tau - mids[i - 1]) / span if span > 0 else 0.0
            return pairs[i - 1][0] + frac * (pairs[i][0] - pairs[i - 1][0])
    return pairs[-1][0]


def is_console_only(comp):
    """True when the comparable's platform list names no PC, Steam or Stadia version."""
    tokens = str(comp.get("platforms", "")).lower().replace("/", ",").split(",")
    return bool(tokens) and not any(t.strip().startswith(("pc", "steam", "stadia")) for t in tokens)


def analogues(case, p1):
    """Yield (offset curve, own hour 1, weight) per comparable that has enough of its release day."""
    lp = math.log(p1)
    for comp in case.get("comparables") or []:
        curve = curve_by_offset(comp["hourly"], comp["day_start"])
        if 0 not in curve:
            continue
        if sum(1 for h in range(1, 24) if h in curve) < MIN_COVERED_HOURS:
            continue
        own1 = max(curve[0], 1.0)
        gap = (math.log(own1) - lp) / SIZE_BANDWIDTH
        weight = math.exp(-0.5 * gap * gap)
        if is_console_only(comp):
            weight *= CONSOLE_ONLY_BONUS
        yield curve, own1, weight


def forecast(case):
    p1 = hour1_print(case)
    pool = list(analogues(case, p1))
    rows = []
    for hour in range(2, 25):
        pairs = []
        for curve, own1, weight in pool:
            if hour - 1 in curve:
                pairs.append((math.log(max(curve[hour - 1], 1.0) / own1), weight + 1e-9))
        if len(pairs) < MIN_POINTS:
            pairs = [(0.0, 1.0), (-0.3, 1.0), (0.3, 1.0)]
        quants = [p1 * math.exp(weighted_quantile(pairs, tau)) for tau in LEVELS]
        for i in range(1, len(quants)):
            quants[i] = max(quants[i], quants[i - 1])
        rows.append({"hour": hour, "q": [round(max(v, 0.01), 2) for v in quants]})
    return {"hours": rows}
