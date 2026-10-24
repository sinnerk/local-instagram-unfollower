#!/usr/bin/env python3
"""Compare an Instagram data export's followers and following lists.

This tool is deliberately read-only: it never logs in to Instagram, never talks
to Instagram, and never clicks unfollow. It turns a JSON data export into a
local HTML dashboard for manual review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import webbrowser
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

APP_NAME = "Local Instagram Unfollower"
VERSION = "1.0.0"
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,64}$")


class AuditError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def clean_username(value: Any) -> str | None:
    """Normalize a username or an Instagram profile URL."""
    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    if "instagram.com" in value.lower():
        parsed = urlparse(value if "://" in value else f"https://{value}")
        parts = [part for part in parsed.path.split("/") if part]
        if not parts:
            return None
        # Older mobile links sometimes use /_u/username.
        if parts[0] == "_u" and len(parts) > 1:
            value = unquote(parts[1])
        else:
            value = unquote(parts[0])

    value = value.strip().lstrip("@").strip().rstrip("/")
    if not value or not USERNAME_RE.fullmatch(value):
        return None
    return value


def normalize_timestamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp > 10**12:
        timestamp //= 1000
    if timestamp <= 0:
        return None
    return timestamp


def _profile_url_username(value: Any) -> str | None:
    if not isinstance(value, str) or "instagram.com" not in value.lower():
        return None
    return clean_username(value)


def extract_entries(record: Any) -> list[tuple[str, int | None]]:
    """Pull all username/timestamp candidates out of one export record."""
    found: list[tuple[str, int | None]] = []

    def add(value: Any, timestamp: Any = None) -> None:
        username = clean_username(value)
        if username:
            found.append((username, normalize_timestamp(timestamp)))

    if isinstance(record, str):
        add(record)
        return found

    if not isinstance(record, dict):
        return found

    record_ts = normalize_timestamp(record.get("timestamp"))

    # Most exports keep the username in value/username and the profile URL in
    # href. Some older exports only have a title.
    for key in ("value", "username"):
        if key in record:
            add(record[key], record_ts)

    if "href" in record:
        add(record["href"], record_ts)

    string_list = record.get("string_list_data")
    if isinstance(string_list, list):
        for item in string_list:
            if isinstance(item, dict):
                item_ts = normalize_timestamp(item.get("timestamp")) or record_ts
                for key in ("value", "username"):
                    if key in item:
                        add(item[key], item_ts)
                if "href" in item:
                    add(item["href"], item_ts)
                if "title" in item:
                    add(item["title"], item_ts)
            elif isinstance(item, str):
                add(item, record_ts)

    if not found:
        add(record.get("title"), record_ts)
        add(record.get("href"), record_ts)

    return found


def extract_sections(data: Any) -> list[tuple[str | None, list[Any]]]:
    """Find the follower/following record arrays inside a JSON document."""
    if isinstance(data, list):
        return [(None, data)]

    if not isinstance(data, dict):
        return []

    sections: list[tuple[str | None, list[Any]]] = []
    for key in ("relationships_following", "relationships_followers"):
        value = data.get(key)
        if isinstance(value, list):
            sections.append((key, value))

    if sections:
        return sections

    for key in ("relationships", "data", "items"):
        value = data.get(key)
        if isinstance(value, list):
            sections.append((key, value))
            return sections

    if any(key in data for key in ("string_list_data", "title", "value", "username")):
        return [(None, [data])]

    return []


def kind_from_filename(name: str) -> str | None:
    """Best-effort classification for exports without a relationship key."""
    base = Path(name.replace("\\", "/")).name.lower()
    # "followers_and_following" can contain both; don't guess.
    has_following = "following" in base
    has_followers = "followers" in base
    if has_following and not has_followers:
        return "following"
    if has_followers and not has_following:
        return "followers"
    return None


def remember(
    store: dict[str, dict[str, Any]], username: str, timestamp: int | None
) -> None:
    key = username.casefold()
    existing = store.get(key)
    if existing is None:
        store[key] = {"username": username, "timestamp": timestamp}
        return
    if timestamp and (not existing["timestamp"] or timestamp > existing["timestamp"]):
        existing["timestamp"] = timestamp


def read_json_files(export_path: Path) -> list[tuple[str, Any]]:
    if export_path.is_dir():
        files = sorted(export_path.rglob("*.json"))
        documents: list[tuple[str, Any]] = []
        for path in files:
            try:
                with path.open("r", encoding="utf-8-sig") as handle:
                    documents.append(
                        (path.relative_to(export_path).as_posix(), json.load(handle))
                    )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                print(f"Warning: skipped {path}: {exc}", file=sys.stderr)
        return documents

    if zipfile.is_zipfile(export_path):
        documents = []
        with zipfile.ZipFile(export_path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir() or not info.filename.lower().endswith(".json"):
                    continue
                try:
                    raw = archive.read(info)
                    documents.append(
                        (info.filename, json.loads(raw.decode("utf-8-sig")))
                    )
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    print(f"Warning: skipped {info.filename}: {exc}", file=sys.stderr)
        return documents

    raise AuditError(
        f"{export_path} is not an Instagram export ZIP or a folder containing one."
    )


def load_follow_lists(
    export_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    documents = read_json_files(export_path)
    if not documents:
        raise AuditError(
            "No JSON files were found. Download your Instagram information in JSON "
            "format (not HTML), then try again."
        )

    following: dict[str, dict[str, Any]] = {}
    followers: dict[str, dict[str, Any]] = {}
    kinds_found: set[str] = set()

    for filename, data in documents:
        filename_kind = kind_from_filename(filename)
        for section, records in extract_sections(data):
            if section == "relationships_following":
                kind = "following"
            elif section == "relationships_followers":
                kind = "followers"
            else:
                kind = filename_kind

            if kind not in ("following", "followers"):
                continue

            kinds_found.add(kind)
            target = following if kind == "following" else followers
            for record in records:
                for username, timestamp in extract_entries(record):
                    remember(target, username, timestamp)

    if "following" not in kinds_found or "followers" not in kinds_found:
        present = ", ".join(name for name, _ in documents[:12])
        missing = "following" if "following" not in kinds_found else "followers"
        raise AuditError(
            f"Could not find the {missing} list in the export. Make sure you selected "
            "both Followers and following in JSON format.\n"
            f"JSON files seen: {present or 'none'}"
        )

    return following, followers


# ---------------------------------------------------------------------------
# Report data
# ---------------------------------------------------------------------------


def build_payload(export_path: Path) -> dict[str, Any]:
    following, followers = load_follow_lists(export_path)

    not_following_back = [following[key] for key in following if key not in followers]
    fans = [followers[key] for key in followers if key not in following]
    mutual = [following[key] for key in following if key in followers]

    def sort_key(account: dict[str, Any]) -> str:
        return account["username"].casefold()

    not_following_back.sort(key=sort_key)
    fans.sort(key=sort_key)
    mutual.sort(key=sort_key)

    all_usernames = sorted(set(following) | set(followers))
    fingerprint = hashlib.sha256("\n".join(all_usernames).encode("utf-8")).hexdigest()[
        :16
    ]

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "generated": now,
        "source": export_path.name,
        "fingerprint": fingerprint,
        "counts": {
            "following": len(following),
            "followers": len(followers),
            "notFollowingBack": len(not_following_back),
            "fans": len(fans),
            "mutual": len(mutual),
        },
        "notFollowingBack": not_following_back,
        "fans": fans,
        "mutual": mutual,
    }


# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------


def write_text_list(path: Path, accounts: Iterable[dict[str, Any]]) -> None:
    lines = [account["username"] for account in accounts]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    categories = (
        ("not_following_back", payload["notFollowingBack"]),
        ("fans", payload["fans"]),
        ("mutual", payload["mutual"]),
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("category", "username", "profile_url", "timestamp_utc"))
        for category, accounts in categories:
            for account in accounts:
                timestamp = account.get("timestamp")
                timestamp_iso = (
                    datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                    if timestamp
                    else ""
                )
                writer.writerow(
                    (
                        category,
                        account["username"],
                        f"https://www.instagram.com/{account['username']}/",
                        timestamp_iso,
                    )
                )


def write_report(path: Path, payload: dict[str, Any]) -> None:
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    document = HTML_TEMPLATE.replace("__AUDIT_DATA__", data_json)
    path.write_text(document, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML dashboard
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Local Instagram Unfollower</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #09090d;
    --panel: #111118;
    --panel-2: #171720;
    --line: #282834;
    --line-soft: #20202b;
    --text: #f5f5f8;
    --muted: #9696a8;
    --muted-2: #6e6e80;
    --pink: #e33f9b;
    --orange: #f58a3c;
    --violet: #9a5cff;
    --green: #4ade80;
    --shadow: 0 24px 80px rgba(0, 0, 0, .38);
  }

  * { box-sizing: border-box; }
  [hidden] { display: none !important; }

  html { min-height: 100%; background: var(--bg); }

  body {
    margin: 0;
    min-height: 100vh;
    font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--text);
    background:
      radial-gradient(900px 500px at 12% -10%, rgba(227, 63, 155, .14), transparent 65%),
      radial-gradient(800px 440px at 92% 4%, rgba(154, 92, 255, .12), transparent 64%),
      var(--bg);
    -webkit-font-smoothing: antialiased;
  }

  a { color: inherit; }
  button, input { font: inherit; }
  button { cursor: pointer; }

  .shell {
    width: min(1040px, calc(100% - 40px));
    margin: 0 auto;
    padding: 62px 0 40px;
  }

  .hero { max-width: 680px; }

  .eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 22px;
    color: #d7d7e2;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .16em;
    text-transform: uppercase;
  }

  .brand-mark {
    width: 30px;
    height: 30px;
    border-radius: 10px;
    background: linear-gradient(135deg, #feda75 0%, #fa7e1e 27%, #d62976 58%, #962fbf 80%, #4f5bd5 100%);
    box-shadow: 0 8px 24px rgba(214, 41, 118, .25);
    position: relative;
  }

  .brand-mark::after {
    content: "";
    position: absolute;
    inset: 8px;
    border: 2px solid rgba(255, 255, 255, .9);
    border-radius: 50%;
  }

  h1 {
    margin: 0;
    max-width: 620px;
    font-size: clamp(42px, 7vw, 76px);
    line-height: .98;
    letter-spacing: -.055em;
    font-weight: 780;
  }

  h1 span {
    color: transparent;
    background: linear-gradient(100deg, #ffd18b, #f375b1 45%, #b08bff 90%);
    -webkit-background-clip: text;
    background-clip: text;
  }

  .lede {
    max-width: 570px;
    margin: 22px 0 0;
    color: var(--muted);
    font-size: 16px;
    line-height: 1.65;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 18px;
    margin-top: 20px;
    color: var(--muted-2);
    font-size: 12px;
  }

  .meta strong {
    color: #c9c9d6;
    font-weight: 600;
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 42px 0 14px;
  }

  .stat {
    position: relative;
    overflow: hidden;
    min-height: 106px;
    padding: 18px 20px;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 255, 255, .025), transparent), var(--panel);
  }

  .stat::after {
    content: "";
    position: absolute;
    width: 110px;
    height: 110px;
    right: -44px;
    bottom: -62px;
    border-radius: 50%;
    background: rgba(255, 255, 255, .025);
  }

  .stat-label {
    display: block;
    margin-bottom: 7px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .02em;
  }

  .stat-value {
    font-size: 32px;
    font-weight: 740;
    letter-spacing: -.04em;
    font-variant-numeric: tabular-nums;
  }

  .stat.accent {
    border-color: rgba(227, 63, 155, .34);
    background:
      radial-gradient(160px 100px at 90% 0%, rgba(227, 63, 155, .18), transparent 70%),
      linear-gradient(180deg, rgba(227, 63, 155, .07), transparent),
      var(--panel);
  }

  .stat.accent .stat-value {
    color: #ff9ccc;
  }

  .panel {
    margin-top: 14px;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: rgba(17, 17, 24, .9);
    box-shadow: var(--shadow);
    backdrop-filter: blur(14px);
  }

  .tabs {
    display: flex;
    gap: 4px;
    padding: 14px 16px 0;
    overflow-x: auto;
    border-bottom: 1px solid var(--line-soft);
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar { display: none; }

  .tab {
    flex: 0 0 auto;
    padding: 11px 14px 14px;
    border: 0;
    border-bottom: 2px solid transparent;
    background: transparent;
    color: var(--muted);
    font-size: 13px;
    font-weight: 650;
    white-space: nowrap;
    transition: color .18s ease, border-color .18s ease;
  }

  .tab:hover { color: #dddde7; }

  .tab.is-active {
    color: var(--text);
    border-bottom-color: #ee6bb5;
  }

  .tab-count {
    display: inline-grid;
    min-width: 23px;
    height: 20px;
    margin-left: 6px;
    padding: 0 6px;
    place-items: center;
    border-radius: 999px;
    background: #242430;
    color: #b8b8c8;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }

  .tab.is-active .tab-count {
    background: rgba(227, 63, 155, .17);
    color: #ffacd4;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 16px;
  }

  .search {
    position: relative;
    flex: 1 1 220px;
    min-width: 160px;
  }

  .search svg {
    position: absolute;
    top: 50%;
    left: 13px;
    width: 16px;
    height: 16px;
    transform: translateY(-50%);
    color: var(--muted-2);
    pointer-events: none;
  }

  .search input {
    width: 100%;
    height: 42px;
    padding: 0 14px 0 38px;
    border: 1px solid var(--line);
    border-radius: 12px;
    outline: none;
    background: #0d0d13;
    color: var(--text);
    font-size: 13px;
    transition: border-color .18s ease, box-shadow .18s ease;
  }

  .search input::placeholder { color: #6b6b7d; }

  .search input:focus {
    border-color: rgba(227, 63, 155, .55);
    box-shadow: 0 0 0 3px rgba(227, 63, 155, .1);
  }

  .toggle {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    gap: 8px;
    height: 42px;
    padding: 0 12px;
    border: 1px solid var(--line);
    border-radius: 12px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
  }

  .toggle input {
    width: 15px;
    height: 15px;
    margin: 0;
    accent-color: var(--pink);
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    flex: 0 0 auto;
    height: 42px;
    padding: 0 14px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--panel-2);
    color: #d8d8e4;
    font-size: 12px;
    font-weight: 650;
    white-space: nowrap;
    transition: transform .15s ease, border-color .15s ease, background .15s ease;
  }

  .btn:hover {
    border-color: #3b3b4b;
    background: #1d1d28;
    transform: translateY(-1px);
  }

  .btn:active { transform: translateY(0); }

  .btn.primary {
    border-color: transparent;
    color: #fff;
    background: linear-gradient(110deg, #d92d8f, #9a5cff);
    box-shadow: 0 8px 24px rgba(227, 63, 155, .2);
  }

  .btn.primary:hover {
    background: linear-gradient(110deg, #e5429e, #a66cff);
  }

  .btn:focus-visible,
  .tab:focus-visible,
  .toggle:focus-within {
    outline: 2px solid #e56bb3;
    outline-offset: 2px;
  }

  .progress-wrap {
    margin: 0 16px 15px;
    padding: 13px 14px;
    border: 1px solid var(--line-soft);
    border-radius: 14px;
    background: #0d0d13;
  }

  .progress-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 9px;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
  }

  .progress-top strong {
    color: #e7e7ef;
    font-variant-numeric: tabular-nums;
  }

  .progress-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .reset {
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--muted-2);
    font-size: 11px;
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .reset:hover { color: #d6d6e2; }
  .reset:disabled { opacity: .4; cursor: default; text-decoration: none; }

  .track {
    height: 5px;
    overflow: hidden;
    border-radius: 999px;
    background: #24242f;
  }

  .bar {
    width: 0;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #f58a3c, #e33f9b 55%, #9a5cff);
    transition: width .25s ease;
  }

  .list-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 16px;
    padding: 4px 20px 10px;
  }

  .list-head h2 {
    margin: 0;
    font-size: 13px;
    font-weight: 650;
  }

  .list-head p {
    margin: 0;
    color: var(--muted-2);
    font-size: 11px;
  }

  .list { padding: 0 8px 8px; }

  .account-row {
    display: flex;
    align-items: center;
    gap: 13px;
    min-height: 69px;
    padding: 10px 12px;
    border-radius: 13px;
    transition: background .16s ease, opacity .16s ease;
  }

  .account-row + .account-row { border-top: 1px solid rgba(255, 255, 255, .045); }
  .account-row:hover { background: rgba(255, 255, 255, .025); }
  .account-row.is-handled { opacity: .42; }
  .account-row.is-handled .username { text-decoration: line-through; text-decoration-color: #79798c; }

  .row-check {
    display: grid;
    flex: 0 0 auto;
    width: 22px;
    height: 22px;
    place-items: center;
    cursor: pointer;
  }

  .row-check input {
    width: 16px;
    height: 16px;
    margin: 0;
    accent-color: #d946a0;
    cursor: pointer;
  }

  .avatar {
    display: grid;
    flex: 0 0 auto;
    width: 42px;
    height: 42px;
    place-items: center;
    border: 1px solid rgba(255, 255, 255, .14);
    border-radius: 50%;
    color: #fff;
    font-size: 15px;
    font-weight: 750;
    text-transform: uppercase;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .13);
  }

  .account-main {
    min-width: 0;
    flex: 1 1 auto;
  }

  .username {
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    color: #f0f0f6;
    font-size: 14px;
    font-weight: 650;
    text-decoration: none;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .username:hover { color: #ffacd4; }

  .sub {
    margin-top: 3px;
    overflow: hidden;
    color: var(--muted-2);
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-action {
    flex: 0 0 auto;
    padding: 7px 10px;
    border-radius: 9px;
    color: #d8d8e4;
    font-size: 11px;
    font-weight: 650;
    text-decoration: none;
    transition: color .15s ease, background .15s ease;
  }

  .row-action:hover {
    color: #fff;
    background: rgba(255, 255, 255, .06);
  }

  .empty {
    display: grid;
    min-height: 230px;
    padding: 40px 20px;
    place-items: center;
    text-align: center;
  }

  .empty-icon {
    display: grid;
    width: 58px;
    height: 58px;
    margin: 0 auto 16px;
    place-items: center;
    border: 1px solid var(--line);
    border-radius: 50%;
    background: var(--panel-2);
    color: #f3a8cc;
    font-size: 24px;
  }

  .empty h3 {
    margin: 0 0 7px;
    font-size: 15px;
  }

  .empty p {
    max-width: 360px;
    margin: 0;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.6;
  }

  footer {
    display: flex;
    justify-content: space-between;
    gap: 20px;
    padding: 22px 4px 0;
    color: var(--muted-2);
    font-size: 11px;
    line-height: 1.6;
  }

  footer p { margin: 0; }
  footer .safe { color: #8b8b9d; }

  .toast {
    position: fixed;
    left: 50%;
    bottom: 26px;
    z-index: 20;
    max-width: min(460px, calc(100% - 32px));
    padding: 11px 16px;
    border: 1px solid #363646;
    border-radius: 12px;
    background: #1b1b25;
    color: #f0f0f6;
    box-shadow: 0 14px 50px rgba(0, 0, 0, .45);
    font-size: 12px;
    text-align: center;
    opacity: 0;
    pointer-events: none;
    transform: translate(-50%, 10px);
    transition: opacity .18s ease, transform .18s ease;
  }

  .toast.is-visible {
    opacity: 1;
    transform: translate(-50%, 0);
  }

  @media (max-width: 780px) {
    .shell { width: min(100% - 24px, 1040px); padding-top: 38px; }
    .stats { grid-template-columns: repeat(2, 1fr); margin-top: 30px; }
    .toolbar { flex-wrap: wrap; }
    .search { flex-basis: 100%; }
    .toggle { margin-right: auto; }
    footer { flex-direction: column; gap: 6px; }
  }

  @media (max-width: 480px) {
    .shell { width: calc(100% - 16px); }
    h1 { font-size: 43px; }
    .stat { min-height: 94px; padding: 15px 16px; }
    .stat-value { font-size: 27px; }
    .tabs { padding-left: 8px; padding-right: 8px; }
    .toolbar { padding: 12px; }
    .toolbar .btn { flex: 1 1 auto; }
    .progress-wrap { margin-left: 12px; margin-right: 12px; }
    .list-head { padding-left: 14px; padding-right: 14px; }
    .account-row { gap: 10px; padding-left: 8px; padding-right: 8px; }
    .avatar { width: 38px; height: 38px; }
    .row-action { padding-left: 6px; padding-right: 6px; }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
  }
</style>
</head>
<body>
<main class="shell">
  <header class="hero">
    <div class="eyebrow"><span class="brand-mark" aria-hidden="true"></span> Local Instagram unfollower</div>
    <h1>Who doesn't<br><span>follow you back?</span></h1>
    <p class="lede">A private, offline comparison of your followers and following lists. Nothing is sent to Instagram, and every unfollow stays in your hands.</p>
    <div class="meta">
      <span>Export: <strong id="meta-source"></strong></span>
      <span id="meta-generated"></span>
    </div>
  </header>

  <section class="stats" aria-label="Audit summary">
    <div class="stat">
      <span class="stat-label">Following</span>
      <span class="stat-value" id="stat-following">0</span>
    </div>
    <div class="stat">
      <span class="stat-label">Followers</span>
      <span class="stat-value" id="stat-followers">0</span>
    </div>
    <div class="stat accent">
      <span class="stat-label">Not following back</span>
      <span class="stat-value" id="stat-not-following">0</span>
    </div>
    <div class="stat">
      <span class="stat-label">Fans</span>
      <span class="stat-value" id="stat-fans">0</span>
    </div>
  </section>

  <section class="panel">
    <div class="tabs" role="tablist" aria-label="Account categories">
      <button class="tab is-active" type="button" role="tab" aria-selected="true" data-view="notFollowingBack">
        Not following back <span class="tab-count" id="tab-not-following">0</span>
      </button>
      <button class="tab" type="button" role="tab" aria-selected="false" data-view="fans">
        Fans <span class="tab-count" id="tab-fans">0</span>
      </button>
      <button class="tab" type="button" role="tab" aria-selected="false" data-view="mutual">
        Mutual <span class="tab-count" id="tab-mutual">0</span>
      </button>
    </div>

    <div class="toolbar">
      <label class="search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5"></circle>
          <path d="m16 16 4 4"></path>
        </svg>
        <input id="search" type="search" placeholder="Search accounts" autocomplete="off" spellcheck="false" aria-label="Search accounts">
      </label>
      <label class="toggle">
        <input id="hide-checked" type="checkbox">
        Hide checked
      </label>
      <button class="btn" type="button" id="copy-list">Copy list</button>
      <button class="btn" type="button" id="download-csv">CSV</button>
      <button class="btn primary" type="button" id="open-next">Open next &nearr;</button>
    </div>

    <div class="progress-wrap" id="progress-wrap">
      <div class="progress-top">
        <span>Cleanup progress</span>
        <span class="progress-actions">
          <span><strong id="done-count">0</strong> / <span id="total-count">0</span> checked</span>
          <button class="reset" type="button" id="reset-progress">Reset</button>
        </span>
      </div>
      <div class="track" role="progressbar" aria-label="Cleanup progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="progress-track">
        <div class="bar" id="progress-bar"></div>
      </div>
    </div>

    <div class="list-head">
      <h2 id="list-hint">You follow them. They don't follow you.</h2>
      <p id="visible-count"></p>
    </div>
    <div class="list" id="list"></div>
  </section>

  <footer>
    <p class="safe">Local-only report. No login, no scraping, no automatic actions.</p>
    <p>Unfollow manually and slowly. Rapid bulk actions can trigger Instagram restrictions.</p>
  </footer>
</main>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script type="application/json" id="audit-data">__AUDIT_DATA__</script>
<script>
(() => {
  "use strict";

  const payload = JSON.parse(document.getElementById("audit-data").textContent);
  const views = {
    notFollowingBack: {
      label: "Not following back",
      hint: "You follow them. They don't follow you.",
      emptyTitle: "Everyone follows you back",
      emptyText: "There are no accounts in this category."
    },
    fans: {
      label: "Fans",
      hint: "They follow you. You don't follow them.",
      emptyTitle: "No fans in this export",
      emptyText: "Nobody in your followers list is missing from your following list."
    },
    mutual: {
      label: "Mutual",
      hint: "You follow each other.",
      emptyTitle: "No mutual follows",
      emptyText: "There are no accounts in this category."
    }
  };

  const lists = {
    notFollowingBack: payload.notFollowingBack || [],
    fans: payload.fans || [],
    mutual: payload.mutual || []
  };

  const storageKey = "igAudit.v1." + payload.fingerprint;
  const $ = (id) => document.getElementById(id);
  let activeView = "notFollowingBack";
  let query = "";
  let handled = new Set();

  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (Array.isArray(saved)) handled = new Set(saved);
  } catch (_) {
    // Private browsing or file:// restrictions: tracking still works in memory.
  }

  const keyFor = (account) => account.username.toLocaleLowerCase();
  const profileUrl = (username) => "https://www.instagram.com/" + encodeURIComponent(username) + "/";
  const formatNumber = (value) => Number(value || 0).toLocaleString();

  function formatDate(timestamp) {
    if (!timestamp) return "";
    try {
      return new Date(timestamp * 1000).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric"
      });
    } catch (_) {
      return "";
    }
  }

  function saveHandled() {
    try {
      localStorage.setItem(storageKey, JSON.stringify([...handled]));
    } catch (_) {
      // Keep working without persistence.
    }
  }

  function metaText() {
    $("meta-source").textContent = payload.source || "Instagram export";
    try {
      $("meta-generated").textContent = "Generated " + new Date(payload.generated).toLocaleString();
    } catch (_) {
      $("meta-generated").textContent = "Generated locally";
    }
  }

  function fillStats() {
    $("stat-following").textContent = formatNumber(payload.counts.following);
    $("stat-followers").textContent = formatNumber(payload.counts.followers);
    $("stat-not-following").textContent = formatNumber(payload.counts.notFollowingBack);
    $("stat-fans").textContent = formatNumber(payload.counts.fans);
    $("tab-not-following").textContent = formatNumber(payload.counts.notFollowingBack);
    $("tab-fans").textContent = formatNumber(payload.counts.fans);
    $("tab-mutual").textContent = formatNumber(payload.counts.mutual);
    $("total-count").textContent = formatNumber(lists.notFollowingBack.length);
  }

  function updateProgress() {
    const total = lists.notFollowingBack.length;
    let done = 0;
    for (const account of lists.notFollowingBack) {
      if (handled.has(keyFor(account))) done += 1;
    }
    const percent = total ? Math.round((done / total) * 100) : 0;
    $("done-count").textContent = formatNumber(done);
    $("progress-bar").style.width = percent + "%";
    $("progress-track").setAttribute("aria-valuenow", String(percent));
    $("progress-track").setAttribute("aria-valuetext", done + " of " + total + " checked");
    $("reset-progress").disabled = done === 0;
  }

  function filteredAccounts() {
    let accounts = lists[activeView] || [];
    if (query) {
      const needle = query.toLocaleLowerCase().replace(/^@/, "");
      accounts = accounts.filter((account) => account.username.toLocaleLowerCase().includes(needle));
    }
    if (activeView === "notFollowingBack" && $("hide-checked").checked) {
      accounts = accounts.filter((account) => !handled.has(keyFor(account)));
    }
    return accounts;
  }

  function avatarFor(username) {
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    let hash = 0;
    for (const char of username) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
    const hue = hash % 360;
    avatar.style.background = "linear-gradient(135deg, hsl(" + hue + " 68% 46%), hsl(" + ((hue + 38) % 360) + " 72% 35%))";
    avatar.textContent = username.charAt(0);
    return avatar;
  }

  function subtitleFor(account) {
    if (activeView === "notFollowingBack") {
      const date = formatDate(account.timestamp);
      return date ? "Following since " + date : "Doesn't follow you back";
    }
    if (activeView === "fans") {
      const date = formatDate(account.timestamp);
      return date ? "Follows you since " + date : "Follows you";
    }
    return "You follow each other";
  }

  function makeRow(account) {
    const username = account.username;
    const key = keyFor(account);
    const row = document.createElement("article");
    row.className = "account-row";
    row.dataset.username = username;
    if (handled.has(key)) row.classList.add("is-handled");

    const checkLabel = document.createElement("label");
    checkLabel.className = "row-check";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = handled.has(key);
    checkbox.setAttribute("aria-label", "Mark @" + username + " as handled");
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) handled.add(key);
      else handled.delete(key);
      saveHandled();
      row.classList.toggle("is-handled", checkbox.checked);
      updateProgress();
      if (checkbox.checked && $("hide-checked").checked) {
        row.hidden = true;
        updateVisibleCount();
      }
    });
    checkLabel.appendChild(checkbox);

    const main = document.createElement("div");
    main.className = "account-main";

    const link = document.createElement("a");
    link.className = "username";
    link.href = profileUrl(username);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "@" + username;

    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent = subtitleFor(account);

    main.append(link, sub);

    const action = document.createElement("a");
    action.className = "row-action";
    action.href = profileUrl(username);
    action.target = "_blank";
    action.rel = "noopener noreferrer";
    action.textContent = "Open \u2197";
    action.setAttribute("aria-label", "Open @" + username + " on Instagram");

    row.append(checkLabel, avatarFor(username), main, action);
    return row;
  }

  function makeEmpty() {
    const wrap = document.createElement("div");
    wrap.className = "empty";
    const inner = document.createElement("div");
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "OK";
    const title = document.createElement("h3");
    title.textContent = query ? "No matching accounts" : views[activeView].emptyTitle;
    const text = document.createElement("p");
    text.textContent = query
      ? "Try a different search, or clear the search field."
      : views[activeView].emptyText;
    inner.append(icon, title, text);
    wrap.appendChild(inner);
    return wrap;
  }

  function updateVisibleCount() {
    const visible = document.querySelectorAll("#list .account-row:not([hidden])").length;
    $("visible-count").textContent = formatNumber(visible) + " shown";
  }

  function renderList() {
    const accounts = filteredAccounts();
    const list = $("list");
    const fragment = document.createDocumentFragment();
    for (const account of accounts) fragment.appendChild(makeRow(account));
    list.replaceChildren();
    if (accounts.length) list.appendChild(fragment);
    else list.appendChild(makeEmpty());

    $("list-hint").textContent = views[activeView].hint;
    $("progress-wrap").hidden = activeView !== "notFollowingBack";
    $("hide-checked").closest(".toggle").hidden = activeView !== "notFollowingBack";
    updateVisibleCount();
  }

  function selectView(view) {
    activeView = view;
    document.querySelectorAll(".tab").forEach((tab) => {
      const isActive = tab.dataset.view === view;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", String(isActive));
    });
    renderList();
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      try {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        const copied = document.execCommand("copy");
        area.remove();
        return copied;
      } catch (_) {
        return false;
      }
    }
  }

  let toastTimer = null;
  function toast(message) {
    const element = $("toast");
    element.textContent = message;
    element.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.remove("is-visible"), 3200);
  }

  function downloadCsv() {
    const rows = [["category", "username", "profile_url", "timestamp_utc"]];
    const categories = [
      ["not_following_back", lists.notFollowingBack],
      ["fans", lists.fans],
      ["mutual", lists.mutual]
    ];
    for (const [category, accounts] of categories) {
      for (const account of accounts) {
        const ts = account.timestamp ? new Date(account.timestamp * 1000).toISOString() : "";
        rows.push([category, account.username, profileUrl(account.username), ts]);
      }
    }
    const csv = rows.map((row) => row.map((cell) => '"' + String(cell).replace(/"/g, '""') + '"').join(",")).join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "instagram_audit_accounts.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("CSV downloaded.");
  }

  $("search").addEventListener("input", (event) => {
    query = event.target.value.trim();
    renderList();
  });

  $("hide-checked").addEventListener("change", renderList);

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => selectView(tab.dataset.view));
  });

  $("open-next").addEventListener("click", () => {
    const next = lists.notFollowingBack.find((account) => !handled.has(keyFor(account)));
    if (!next) {
      toast("Everything in the not-following-back list is checked off.");
      return;
    }
    window.open(profileUrl(next.username), "_blank", "noopener,noreferrer");
    toast("Opened @" + next.username + ". Unfollow manually, then check it off.");
  });

  $("copy-list").addEventListener("click", async () => {
    const text = lists.notFollowingBack.map((account) => account.username).join("\n");
    if (!text) {
      toast("The not-following-back list is empty.");
      return;
    }
    const copied = await copyText(text);
    toast(copied
      ? "Copied " + formatNumber(lists.notFollowingBack.length) + " usernames."
      : "Could not copy automatically. Use the CSV instead.");
  });

  $("download-csv").addEventListener("click", downloadCsv);

  $("reset-progress").addEventListener("click", () => {
    if (!handled.size) return;
    if (!confirm("Clear all checked-off accounts?")) return;
    handled.clear();
    saveHandled();
    renderList();
    updateProgress();
    toast("Cleanup progress reset.");
  });

  metaText();
  fillStats();
  updateProgress();
  renderList();
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ig_audit.py",
        description=(
            "Compare followers and following from an Instagram JSON data export. "
            "The generated report is local-only; unfollowing remains manual."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    parser.add_argument(
        "export",
        type=Path,
        help="Path to the Instagram export ZIP or an extracted export folder.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("instagram_audit.html"),
        help="HTML report path (default: instagram_audit.html).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated report in the default browser.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    export_path = args.export.expanduser().resolve()

    if not export_path.exists():
        print(f"Error: {export_path} does not exist.", file=sys.stderr)
        return 1

    try:
        payload = build_payload(export_path)
    except AuditError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path = args.out.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stem = out_path.with_suffix("")
    txt_path = Path(str(stem) + "_not_following_back.txt")
    csv_path = Path(str(stem) + "_accounts.csv")

    write_report(out_path, payload)
    write_text_list(txt_path, payload["notFollowingBack"])
    write_csv(csv_path, payload)

    counts = payload["counts"]
    print(f"{APP_NAME}: {payload['source']}")
    print(f"  Following:              {counts['following']:,}")
    print(f"  Followers:              {counts['followers']:,}")
    print(f"  Not following back:     {counts['notFollowingBack']:,}")
    print(f"  Fans:                   {counts['fans']:,}")
    print(f"  Mutual:                 {counts['mutual']:,}")
    print()
    print(f"Report:      {out_path}")
    print(f"Username list: {txt_path}")
    print(f"CSV:         {csv_path}")

    if args.open:
        webbrowser.open(out_path.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
