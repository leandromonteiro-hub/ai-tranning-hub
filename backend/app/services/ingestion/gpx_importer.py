"""GPX importer using gpxpy. GPX has no power; HR/cadence via extensions."""
from __future__ import annotations

import io
from datetime import timezone

import gpxpy

from app.core.logging import get_logger
from app.services.ingestion.normalizer import NormalizedActivity

log = get_logger(__name__)


def parse_gpx(data: bytes) -> list[NormalizedActivity]:
    gpx = gpxpy.parse(io.BytesIO(data))
    points = [p for track in gpx.tracks for seg in track.segments for p in seg.points]
    if not points:
        return []

    started_at = points[0].time
    if started_at is None:
        return []
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    duration_s = None
    if points[-1].time and points[0].time:
        duration_s = int((points[-1].time - points[0].time).total_seconds())

    distance_m = gpx.length_3d() or gpx.length_2d()
    uphill, _ = gpx.get_uphill_downhill()
    altitude = [p.elevation for p in points if p.elevation is not None]

    act = NormalizedActivity(
        started_at=started_at,
        name=gpx.tracks[0].name if gpx.tracks else None,
        duration_s=duration_s,
        distance_m=float(distance_m) if distance_m else None,
        elevation_gain_m=float(uphill) if uphill else None,
        altitude_stream=[float(a) for a in altitude],
    )
    log.info("gpx_parsed", extra={"points": len(points)})
    return [act]
