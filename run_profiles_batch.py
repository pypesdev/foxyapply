#!/usr/bin/env python3
"""Batch runner to apply for jobs with all configured HiringFunnel profiles.

This script loads profiles from ~/.hiringfunnel/profiles.json and sequentially runs
EasyApplyBot for each one until either the desired number of successful
applications has been submitted or a per-profile timeout is reached.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import os
import sys
import threading
import time
import uuid as _uuid
from typing import Dict, List, Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

_PYPES_BASE_URL = os.environ.get("PYPES_BASE_URL", "https://api.pypes.dev")
_CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
_PYPES_JOB_EVENTS = {"job_applied", "job_failed", "daily_limit_reached", "consecutive_failures_exceeded"}


def _pypes_post(path: str, payload: dict) -> None:
    if not _CLIENT_SECRET or not _requests:
        return
    try:
        _requests.post(
            f"{_PYPES_BASE_URL}{path}",
            json=payload,
            headers={"X-Pypes-Secret": _CLIENT_SECRET},
            timeout=5,
        )
    except Exception:
        pass


import easyapplybot as bot_module
from easyapplybot import ProfileConfig, _run_bot
from profiles import load_profiles


def run_profile(
    name: str,
    raw_profile: Dict,
    target: int,
    timeout_minutes: Optional[int] = None,
) -> Dict:
    """Run a single profile until `target` applications or timeout.

    Returns a dictionary with execution stats and status info.
    """
    stats = {
        "profile": name,
        "applied": 0,
        "failed": 0,
        "seen": 0,
        "errors": [],
        "status": "starting",
        "target_met": False,
        "duration_s": 0.0,
    }

    timeout_seconds = timeout_minutes * 60 if timeout_minutes else None
    done = threading.Event()
    session_id = str(_uuid.uuid4())
    start = time.time()

    try:
        config = ProfileConfig(**raw_profile)
    except Exception as exc:  # pragma: no cover - validation errors are rare
        stats["status"] = f"config_error: {exc}"
        return stats

    def on_event(event_type: str, payload: Dict) -> None:
        if event_type == "job_applied":
            stats["applied"] += 1
            print(
                f"[{name}] Applied job #{stats['applied']}: {payload.get('title', 'Unknown')} @ {payload.get('company', 'Unknown')}",
                flush=True,
            )
        elif event_type == "job_failed":
            stats["failed"] += 1
            print(
                f"[{name}] Failed to submit: {payload.get('title', 'Unknown')} ({payload.get('error', 'reason unknown')})",
                flush=True,
            )
        elif event_type == "progress":
            stats["applied"] = max(stats["applied"], payload.get("applied", 0))
            stats["failed"] = max(stats["failed"], payload.get("failed", 0))
            stats["seen"] = max(stats["seen"], payload.get("total_seen", 0))
        elif event_type == "error":
            message = payload.get("message")
            if message:
                stats["errors"].append(message)
                print(f"[{name}] Error: {message}", flush=True)
        elif event_type == "bot_stopped":
            stats["status"] = payload.get("reason", "stopped")
            done.set()
            print(f"[{name}] Bot stopped: {stats['status']}", flush=True)

        if target and stats["applied"] >= target and not stats["target_met"]:
            stats["target_met"] = True
            print(f"[{name}] Target of {target} applications reached. Stopping bot...", flush=True)
            if bot_module._bot is not None:
                bot_module._bot.stop()

        now = _datetime.datetime.now(_datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if event_type in _PYPES_JOB_EVENTS:
            _pypes_post("/client/job-event", {
                "profile": name,
                "event": event_type,
                "occurred_at": now,
                **payload,
            })
        elif event_type == "bot_started":
            _pypes_post("/client/bot-run", {
                "profile": name,
                "run_id": session_id,
                "event": "started",
                "occurred_at": now,
            })
        elif event_type == "bot_stopped":
            _pypes_post("/client/bot-run", {
                "profile": name,
                "run_id": session_id,
                "event": "stopped",
                "reason": payload.get("reason", ""),
                "applied": stats["applied"],
                "failed": stats["failed"],
                "seen": stats["seen"],
                "occurred_at": now,
            })

    thread = threading.Thread(target=_run_bot, args=(config, on_event), daemon=True)
    thread.start()

    while thread.is_alive():
        if done.wait(timeout=5):
            break
        if timeout_seconds and (time.time() - start) > timeout_seconds:
            stats["status"] = f"timeout_after_{timeout_minutes}m"
            if bot_module._bot is not None:
                bot_module._bot.stop()
            done.wait(timeout=30)
            break

    thread.join(timeout=30)
    stats["duration_s"] = time.time() - start
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Batch-run HiringFunnel profiles")
    parser.add_argument(
        "--profiles",
        help="Comma-separated list of profile names. Default: all",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=25,
        help="Target number of successful applications per profile",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=120,
        help="Maximum minutes to spend per profile (0 = unlimited)",
    )

    args = parser.parse_args(argv)

    all_profiles = load_profiles()
    if not all_profiles:
        print("No profiles found in ~/.hiringfunnel/profiles.json", file=sys.stderr)
        return 1

    selected: Dict[str, Dict]
    if args.profiles:
        requested = {name.strip() for name in args.profiles.split(",") if name.strip()}
        missing = requested - set(all_profiles.keys())
        if missing:
            print(f"Unknown profiles requested: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        selected = {name: all_profiles[name] for name in requested}
    else:
        selected = all_profiles

    print(
        f"Running {len(selected)} profile(s) with target={args.target} and timeout={args.timeout_minutes}m each...",
        flush=True,
    )

    results = []
    for name, profile in selected.items():
        print(f"\n=== {name} ===", flush=True)
        result = run_profile(name, profile, args.target, args.timeout_minutes or None)
        print(
            f"Status: {result['status']}; applied={result['applied']} failed={result['failed']} "
            f"seen={result['seen']} duration={result['duration_s']:.1f}s",
            flush=True,
        )
        if result["errors"]:
            print("  Errors:")
            for err in result["errors"]:
                print(f"    - {err}")
        results.append(result)

    print("\nSummary:")
    for res in results:
        print(
            f"- {res['profile']}: applied={res['applied']} target_met={res['target_met']} status={res['status']} duration={res['duration_s'] / 60:.1f}m"
        )

    unmet = [r for r in results if not r.get("target_met")]
    return 0 if not unmet else 2


if __name__ == "__main__":
    raise SystemExit(main())
