from __future__ import annotations

import threading
from collections import defaultdict


_LOCK = threading.Lock()
_COUNTERS: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_HISTOGRAMS: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(
    lambda: [0.0] * 8
)
_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, float("inf"))


def _label_key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return tuple()
    return tuple(sorted((k, str(v)) for k, v in labels.items()))


def inc_counter(name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
    key = (name, _label_key(labels))
    with _LOCK:
        _COUNTERS[key] += value


def observe_histogram(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    key = (name, _label_key(labels))
    with _LOCK:
        buckets = _HISTOGRAMS[key]
        for idx, bound in enumerate(_BUCKETS):
            if value <= bound:
                buckets[idx] += 1
                break


def render_prometheus() -> str:
    lines: list[str] = []
    with _LOCK:
        for (name, labels), count in sorted(_COUNTERS.items()):
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f"{name}{{{label_str}}} {count}" if label_str else f"{name} {count}")

        for (name, labels), buckets in sorted(_HISTOGRAMS.items()):
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            for idx, bound in enumerate(_BUCKETS):
                le = "+Inf" if bound == float("inf") else str(bound)
                base = f'le="{le}"'
                full = f"{base},{label_str}" if label_str else base
                lines.append(f'{name}_bucket{{{full}}} {buckets[idx]}')
    return "\n".join(lines) + ("\n" if lines else "")
