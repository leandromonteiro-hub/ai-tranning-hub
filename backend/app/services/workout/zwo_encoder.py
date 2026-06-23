"""Encode a StructuredWorkout as Zwift workout (.zwo) XML.

.zwo is the format TrainingPeaks accepts for importing planned structured
workouts into the Workout Library (verified 2026-06-23). Power targets are
fractions of FTP, applied by the importing platform — so the athlete's FTP is
NOT embedded here. Unlike the FIT encoder, repeats map to native ``IntervalsT``
elements (no flattening), which preserves the "3×" grouping on import.

Mapping from the canonical model:
  - warmup Step           -> <Warmup Duration PowerLow PowerHigh>  (ramp)
  - cooldown Step         -> <Cooldown Duration PowerLow PowerHigh> (ramp), or
                             <FreeRide Duration> when the target is open
  - active/rest Step      -> <SteadyState Duration Power>  (single midpoint)
  - open Step (any)       -> <FreeRide Duration>
  - Repeat([on, off])     -> <IntervalsT Repeat OnDuration OffDuration OnPower OffPower>
  - Repeat (other shapes) -> expanded into repeated per-step elements
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from app.services.workout import analysis
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _mid(t: Target) -> float | None:
    """Single representative power (fraction of FTP) for a target, or None if open."""
    if t.type != "power_pct_ftp" or t.low is None:
        return None
    high = t.high if t.high is not None else t.low
    return round((t.low + high) / 2, 3)


def _fmt(x: float) -> str:
    return f"{x:g}"


def _step_xml(step: Step) -> str:
    """Render a single (non-repeat) step."""
    d = step.duration_s
    if step.target.type == "open" or step.target.low is None:
        return f'    <FreeRide Duration="{d}"/>'
    if step.intensity in ("warmup", "cooldown"):
        tag = "Warmup" if step.intensity == "warmup" else "Cooldown"
        low = step.target.low
        high = step.target.high if step.target.high is not None else low
        return f'    <{tag} Duration="{d}" PowerLow="{_fmt(low)}" PowerHigh="{_fmt(high)}"/>'
    return f'    <SteadyState Duration="{d}" Power="{_fmt(_mid(step.target))}"/>'


def encode_zwo(workout: StructuredWorkout) -> str:
    lines = [
        "<workout_file>",
        "  <author>Athlete AI Training Hub</author>",
        f"  <name>{escape(workout.name)}</name>",
        # The breakdown (rest times, total duration, IF, TSS) shows in TrainingPeaks.
        f"  <description>{escape(analysis.describe(workout))}</description>",
        "  <sportType>bike</sportType>",
        "  <workout>",
    ]
    for el in workout.elements:
        if isinstance(el, Repeat) and len(el.steps) == 2:
            on, off = el.steps
            lines.append(
                f'    <IntervalsT Repeat="{el.count}" '
                f'OnDuration="{on.duration_s}" OffDuration="{off.duration_s}" '
                f'OnPower="{_fmt(_mid(on.target))}" OffPower="{_fmt(_mid(off.target))}"/>'
            )
        elif isinstance(el, Repeat):
            # Uncommon shape: expand into repeated per-step elements.
            for _ in range(el.count):
                for s in el.steps:
                    lines.append(_step_xml(s))
        else:
            lines.append(_step_xml(el))
    lines += ["  </workout>", "</workout_file>", ""]
    return "\n".join(lines)
