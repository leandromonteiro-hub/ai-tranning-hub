"""Deterministic analysis of a structured workout: duration, IF, TSS, description.

These are estimates derived purely from the planned structure (durations + power
targets as %FTP), independent of the athlete's absolute FTP. Used to (a) populate
``estimated_tss`` and (b) build a human-readable breakdown — including rest times,
Intensity Factor and TSS — that the athlete uses to gauge the session.

IF is approximated with the same fourth-power weighting used for Normalized Power:
    IF ≈ ( Σ frac_i^4 · t_i / Σ t_i ) ^ (1/4)
TSS follows the standard definition: TSS = hours · IF² · 100.
"""
from __future__ import annotations

from collections.abc import Iterator

from app.services.workout.model import Repeat, Step, StructuredWorkout, Target

# Assumed easy-spin intensity for an "open"/free segment (no explicit target).
_OPEN_NOMINAL = 0.45


def _frac(t: Target) -> float:
    """Representative power as a fraction of FTP (midpoint of the target range)."""
    if t.type != "power_pct_ftp" or t.low is None:
        return _OPEN_NOMINAL
    high = t.high if t.high is not None else t.low
    return (t.low + high) / 2


def _leaves(workout: StructuredWorkout) -> Iterator[Step]:
    """Flatten elements into the actual sequence of executed steps."""
    for el in workout.elements:
        if isinstance(el, Repeat):
            for _ in range(el.count):
                yield from el.steps
        else:
            yield el


def total_duration_s(workout: StructuredWorkout) -> int:
    return sum(s.duration_s for s in _leaves(workout))


def intensity_factor(workout: StructuredWorkout) -> float:
    total = total_duration_s(workout)
    if total <= 0:
        return 0.0
    acc = sum((_frac(s.target) ** 4) * s.duration_s for s in _leaves(workout))
    return round((acc / total) ** 0.25, 2)


def estimated_tss(workout: StructuredWorkout) -> float:
    total = total_duration_s(workout)
    if_ = intensity_factor(workout)
    return round((total / 3600) * (if_ ** 2) * 100)


def _pct(t: Target) -> str:
    if t.type != "power_pct_ftp" or t.low is None:
        return "livre"
    if t.high is None or t.high == t.low:
        return f"{round(t.low * 100)}% FTP"
    return f"{round(t.low * 100)}-{round(t.high * 100)}% FTP"


def _mins(seconds: int) -> str:
    return f"{round(seconds / 60)}min"


_LABEL = {
    "warmup": "Aquecimento",
    "cooldown": "Volta à calma",
    "active": "Bloco",
    "rest": "Descanso",
}


def describe(workout: StructuredWorkout) -> str:
    """Human-readable breakdown with rest times, total duration, IF and TSS."""
    total = total_duration_s(workout)
    if_ = intensity_factor(workout)
    tss = estimated_tss(workout)
    lines = [f"{workout.name} — total {total // 60}min · IF {if_:.2f} · TSS ~{int(tss)}"]
    for el in workout.elements:
        if isinstance(el, Repeat) and len(el.steps) == 2:
            on, off = el.steps
            lines.append(
                f"- {el.count}× ({_mins(on.duration_s)} @ {_pct(on.target)}"
                f" + {_mins(off.duration_s)} descanso @ {_pct(off.target)})"
            )
        elif isinstance(el, Repeat):
            lines.append(f"- {el.count}× bloco:")
            for s in el.steps:
                lines.append(f"    · {_mins(s.duration_s)} @ {_pct(s.target)}")
        else:
            lines.append(f"- {_LABEL.get(el.intensity, 'Bloco')}: {_mins(el.duration_s)} @ {_pct(el.target)}")
    return "\n".join(lines)
