"""Metrics derived from raw samples at ingest time.

- Aerobic decoupling (Pw:Hr / Pa:Hr drift): compares the efficiency factor
  (speed-per-heartbeat, grade-adjusted when available) of the first and
  second half of a run. Positive % = drifting (second half less efficient).
- Power-duration curve: best average power over standard durations. Works
  for running power today and lights up for cycling if a power meter shows up.
"""

PDC_DURATIONS_S = [5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600]

MIN_DECOUPLING_DURATION_S = 20 * 60


def aerobic_decoupling_pct(samples: list[dict]) -> float | None:
    moving = [
        s for s in samples
        if (s.get("hr") or 0) > 90 and ((s.get("gas_ms") or s.get("speed_ms")) or 0) > 0.5
    ]
    if len(moving) < 60:
        return None
    total = moving[-1]["elapsed_s"] - moving[0]["elapsed_s"]
    if total < MIN_DECOUPLING_DURATION_S:
        return None
    midpoint = moving[0]["elapsed_s"] + total / 2
    first = [s for s in moving if s["elapsed_s"] <= midpoint]
    second = [s for s in moving if s["elapsed_s"] > midpoint]
    if len(first) < 30 or len(second) < 30:
        return None

    def efficiency(chunk: list[dict]) -> float | None:
        speeds = [(s.get("gas_ms") or s.get("speed_ms")) for s in chunk]
        hrs = [s["hr"] for s in chunk]
        mean_hr = sum(hrs) / len(hrs)
        return (sum(speeds) / len(speeds)) / mean_hr if mean_hr else None

    ef1, ef2 = efficiency(first), efficiency(second)
    if not ef1 or not ef2:
        return None
    return round((ef1 - ef2) / ef1 * 100.0, 2)


def power_curve(samples: list[dict]) -> list[tuple[int, float]]:
    """Best average power per duration from irregular (1-3 s) samples.

    Resamples onto a 1 s grid holding the last value (smart recording keeps
    values constant between samples), then takes max rolling means.
    """
    pts = sorted(
        (int(s["elapsed_s"]), s["power_w"])
        for s in samples
        if s.get("power_w") is not None and s.get("elapsed_s") is not None
    )
    if len(pts) < 30:
        return []
    end = pts[-1][0]
    grid = [0.0] * (end + 1)
    j = 0
    current = pts[0][1]
    for t in range(end + 1):
        while j < len(pts) and pts[j][0] <= t:
            current = pts[j][1]
            j += 1
        grid[t] = current

    prefix = [0.0]
    for v in grid:
        prefix.append(prefix[-1] + v)

    curve = []
    for dur in PDC_DURATIONS_S:
        if dur > len(grid):
            break
        best = max(prefix[i + dur] - prefix[i] for i in range(len(grid) - dur + 1)) / dur
        curve.append((dur, round(best, 1)))
    return curve
