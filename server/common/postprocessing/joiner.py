"""Streaming join of independently sampled channels into aligned rows.

A step needing several channels (two ADC electrodes and a temperature) gets
them in separate packets, possibly out of order when a device delivers its
history in a batch. Each sample of the step's base channel (its first input)
waits until every other input has a sample within the tolerance, then becomes
one row. Rows are never built from a stale value.

Channels may be skewed against each other by any amount, but each channel's
own samples are assumed to arrive in time order. That is what lets a base
sample be dropped once a partner channel has moved past it without a match,
and a partner sample be dropped once no current or future base sample can use
it.

State is a plain JSON-serialisable dict so it can live in Flink keyed state:
    {"buffers": {channel: [[time, value], ...]}, "pending": [[time, value], ...],
     "base_latest": time | None}
"""
from bisect import bisect_left, insort

# Bounds state when one channel is far ahead of, or far denser than, the others.
MAX_BUFFERED_SAMPLES = 1024


def new_state() -> dict:
    return {"buffers": {}, "pending": [], "base_latest": None}


def _nearest(series: list, time: float, tolerance: float):
    """The value nearest to `time` within the tolerance, else None."""
    if not series:
        return None
    index = bisect_left(series, [time])
    best = None
    for candidate in series[max(0, index - 1): index + 1]:
        distance = abs(candidate[0] - time)
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, candidate[1])
    return None if best is None else best[1]


class StepJoin:
    """Joins one step's input channels, reading and mutating `state` in place."""

    def __init__(self, base: str, others: tuple[str, ...], tolerance: float, state: dict):
        self.base = base
        self.others = tuple(c for c in others if c != base)
        self.tolerance = float(tolerance)
        self.state = state

    def add(self, channel: str, time: float, value: float) -> list[dict]:
        """Take one sample and return the rows it completes, oldest first.

        Each row is {"time": base time, <channel>: value, ...}.
        """
        if channel != self.base and channel not in self.others:
            return []
        if channel == self.base:
            insort(self.state["pending"], [time, value])
            latest = self.state.get("base_latest")
            self.state["base_latest"] = time if latest is None else max(latest, time)
        else:
            insort(self.state["buffers"].setdefault(channel, []), [time, value])
        rows = self._complete()
        self._prune()
        return rows

    def _complete(self) -> list[dict]:
        rows, still_pending = [], []
        for time, value in self.state["pending"]:
            row = {"time": time, self.base: value}
            for other in self.others:
                partner = _nearest(self.state["buffers"].get(other, []), time, self.tolerance)
                if partner is None:
                    row = None
                    break
                row[other] = partner
            if row is None:
                still_pending.append([time, value])
            else:
                rows.append(row)
        self.state["pending"] = still_pending
        return rows

    def _prune(self) -> None:
        buffers = self.state["buffers"]
        tolerance = self.tolerance

        def moved_past(time: float) -> bool:
            """A partner channel went beyond `time` without a sample near it."""
            return any(
                buffers.get(c)
                and buffers[c][-1][0] > time + tolerance
                and _nearest(buffers[c], time, tolerance) is None
                for c in self.others
            )

        pending = [p for p in self.state["pending"] if not moved_past(p[0])]
        self.state["pending"] = pending[-MAX_BUFFERED_SAMPLES:]

        base_latest = self.state.get("base_latest")
        if base_latest is None:
            floor = None
        else:
            floor = min([base_latest] + [p[0] for p in self.state["pending"]]) - tolerance
        for channel, series in buffers.items():
            kept = series if floor is None else [s for s in series if s[0] >= floor]
            buffers[channel] = kept[-MAX_BUFFERED_SAMPLES:]
