"""Dual UTC + America/New_York timezone formatting for iBitLabs user-facing output.

Use this for any text Bonny will read directly: CLI prints, ntfy/iMessage push bodies,
log lines she scans, Moltbook post bodies. Backend audit JSONL / DB / SQLite timestamps
stay UTC and do NOT call this — use plain `datetime.now(timezone.utc).isoformat()`.

EDT/EST switches automatically via zoneinfo("America/New_York"). %Z renders "EDT" in summer
(DST) and "EST" in winter.

Public HTML embedding: emit `format_html_time(dt, mode=...)` then include `/tz.js` on the page.
JS will overwrite the textContent with the viewer's locale on page load.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def format_utc_edt(
    dt: datetime | None = None,
    *,
    with_date: bool = True,
    sep: str = " | ",
) -> str:
    """Return e.g. '2026-05-14 20:10 UTC | 16:10 EDT'.

    with_date=False drops the date, giving '20:10 UTC | 16:10 EDT'.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    dt = _ensure_aware(dt)
    utc = dt.astimezone(timezone.utc)
    ny = dt.astimezone(NY)
    tz_label = ny.strftime("%Z")  # EDT / EST
    if with_date:
        return f"{utc.strftime('%Y-%m-%d %H:%M')} UTC{sep}{ny.strftime('%H:%M')} {tz_label}"
    return f"{utc.strftime('%H:%M')} UTC{sep}{ny.strftime('%H:%M')} {tz_label}"


def format_utc_edt_full(dt: datetime | None = None) -> str:
    """Return e.g. '2026-05-14 20:10:42 UTC | 16:10:42 EDT' (full HMS for forensic lines)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    dt = _ensure_aware(dt)
    utc = dt.astimezone(timezone.utc)
    ny = dt.astimezone(NY)
    return f"{utc.strftime('%Y-%m-%d %H:%M:%S')} UTC | {ny.strftime('%H:%M:%S')} {ny.strftime('%Z')}"


def format_html_time(
    dt: datetime | None = None,
    *,
    mode: str = "dual",
    fallback_utc: bool = True,
) -> str:
    """Return `<time datetime="ISO8601Z" data-tz="MODE">UTC-fallback</time>` for public HTML.

    The fallback text shown before tz.js runs is UTC by convention (matches what build_report
    used to bake). After tz.js runs in the browser, the text is replaced with viewer-local.

    mode: 'dual' | 'date-local' | 'time-local' | 'local'
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    dt = _ensure_aware(dt)
    utc = dt.astimezone(timezone.utc)
    iso = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not fallback_utc:
        fallback = ""
    elif mode == "date-local":
        fallback = utc.strftime("%Y-%m-%d")
    elif mode == "time-local":
        fallback = utc.strftime("%H:%M UTC")
    elif mode == "local":
        fallback = utc.strftime("%Y-%m-%d %H:%M UTC")
    else:  # dual (default)
        fallback = utc.strftime("%Y-%m-%d %H:%M UTC")
    return f'<time datetime="{iso}" data-tz="{mode}">{fallback}</time>'


def now_dual() -> str:
    """Shortcut: dual-formatted current time."""
    return format_utc_edt()


if __name__ == "__main__":
    import sys
    now = datetime.now(timezone.utc)
    print("now (dual):       ", format_utc_edt(now))
    print("now (dual no-date):", format_utc_edt(now, with_date=False))
    print("now (full):       ", format_utc_edt_full(now))
    print("html (dual):      ", format_html_time(now, mode="dual"))
    print("html (date-local):", format_html_time(now, mode="date-local"))
    print("html (time-local):", format_html_time(now, mode="time-local"))
    print("html (local):     ", format_html_time(now, mode="local"))
    sys.exit(0)
