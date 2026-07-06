"""Garmin's ORIGINAL activity download is a ZIP wrapping the .fit file
(verified against a real account, 2026-07-06: header ``PK\\x03\\x04``).
``_extract_fit_from_original`` must unwrap it so ``import_file`` receives raw
FIT bytes — the ingestion parsers pick the parser by filename extension and
would fail on zip bytes.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from app.services.garmin.client import GarminSyncError, _extract_fit_from_original

FIT_BYTES = b"\x0e\x10\x98\x00\x1b\x00\x00\x00.FITxxxx-fake-fit-payload"


def _zip_with(*members: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def test_unwraps_fit_from_original_zip():
    data = _zip_with(("23489425927_ACTIVITY.fit", FIT_BYTES))
    assert _extract_fit_from_original(data) == FIT_BYTES


def test_picks_fit_member_case_insensitively_among_others():
    data = _zip_with(("readme.txt", b"hi"), ("A.FIT", FIT_BYTES))
    assert _extract_fit_from_original(data) == FIT_BYTES


def test_non_zip_bytes_pass_through_unchanged():
    assert _extract_fit_from_original(FIT_BYTES) == FIT_BYTES


def test_zip_without_fit_member_raises_sync_error():
    data = _zip_with(("activity.gpx", b"<gpx/>"))
    with pytest.raises(GarminSyncError):
        _extract_fit_from_original(data)
