"""TCX importer using lxml. Reads Trackpoints (HR, cadence, watts ext, altitude)."""
from __future__ import annotations

from datetime import datetime, timezone

from lxml import etree

from app.core.logging import get_logger
from app.services.ingestion.normalizer import NormalizedActivity

log = get_logger(__name__)

_NS = {
    "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ext": "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
}


def _findall(node, path: str):
    return node.findall(path, namespaces=_NS)


def parse_tcx(data: bytes) -> list[NormalizedActivity]:
    root = etree.fromstring(data)
    trackpoints = _findall(root, ".//tcx:Trackpoint")
    if not trackpoints:
        return []

    power: list[float] = []
    hr: list[float] = []
    cadence: list[float] = []
    altitude: list[float] = []
    times: list[datetime] = []

    for tp in trackpoints:
        t = tp.find("tcx:Time", namespaces=_NS)
        if t is not None and t.text:
            try:
                times.append(datetime.fromisoformat(t.text.replace("Z", "+00:00")))
            except ValueError:
                pass
        hr_node = tp.find("tcx:HeartRateBpm/tcx:Value", namespaces=_NS)
        if hr_node is not None and hr_node.text:
            hr.append(float(hr_node.text))
        alt_node = tp.find("tcx:AltitudeMeters", namespaces=_NS)
        if alt_node is not None and alt_node.text:
            altitude.append(float(alt_node.text))
        watts = tp.find(".//ext:Watts", namespaces=_NS)
        if watts is not None and watts.text:
            power.append(float(watts.text))
        cad = tp.find(".//ext:RunCadence", namespaces=_NS)
        if cad is not None and cad.text:
            cadence.append(float(cad.text))

    if not times:
        return []
    started_at = times[0]
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    duration_s = int((times[-1] - times[0]).total_seconds()) if len(times) > 1 else None

    act = NormalizedActivity(
        started_at=started_at,
        duration_s=duration_s,
        avg_power=sum(power) / len(power) if power else None,
        avg_hr=sum(hr) / len(hr) if hr else None,
        max_hr=max(hr) if hr else None,
        power_stream=power,
        hr_stream=hr,
        cadence_stream=cadence,
        altitude_stream=altitude,
    )
    log.info("tcx_parsed", extra={"trackpoints": len(trackpoints)})
    return [act]
