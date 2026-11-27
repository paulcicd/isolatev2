#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Session details and replay helpers for Isolate audit logs."""

import codecs
import json
import os
import re

from isolate_history import _load_events, _row_from_events


# The wrapper prefixes every PTY read with a timestamp. A read does not have to
# end with a newline, so the next timestamp can immediately follow its payload.
TIMESTAMP_RE = re.compile(rb"(?<![0-9.])([0-9]{4,12}\.[0-9]{6})\r?\n")
EPOCH_TIMESTAMP_RE = re.compile(rb"([1-9][0-9]{9}\.[0-9]{6})\r?\n")
MAX_TIMESTAMP_BYTES = len(b"000000000000.000000\r\n")
MAX_TIMESTAMP_GAP_SECONDS = 7 * 24 * 60 * 60
TERMINAL_CONTROL_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)"
    r"|\x1b[P^_X][^\x1b]*(?:\x1b\\|$)"
    r"|\x1b\[(?P<parameters>[0-?]*)[ -/]*(?P<action>[@-~])"
    r"|\x1b\[[0-?]*[ -/]*$"
    r"|\x1b[NO][0-~]"
    r"|\x1b[ -/]*[0-~]"
    r"|\x08 \x08"
    r"|[\x00-\x08\x0a-\x1f\x7f-\x9f]"
)


def readable_terminal_text(text):
    """Return a best-effort view of terminal lines with basic in-line edits."""
    text = str(text or "")
    lines = []
    line = []
    column = 0
    start = 0
    for match in TERMINAL_CONTROL_RE.finditer(text):
        printed = text[start:match.start()]
        line[column:column + len(printed)] = printed
        column += len(printed)
        start = match.end()
        control = match.group()
        if control == "\n":
            lines.append("".join(line))
            line.clear()
            column = 0
        elif control == "\r":
            column = 0
        elif control == "\b":
            column = max(0, column - 1)
        elif control == "\b \b":
            column = max(0, column - 1)
            if column == len(line) - 1:
                line.pop()
            elif column < len(line):
                line[column] = " "
        else:
            action = match.group("action")
            parameters = match.group("parameters")
            if action == "K":
                if parameters in ("", "0"):
                    del line[column:]
                elif parameters == "2":
                    line.clear()
                    column = 0
            elif action in ("C", "D", "G") and (not parameters or parameters.isdecimal()):
                count = max(1, int(parameters[:9] or 1))
                if action == "C":
                    column = min(len(line), column + count)
                elif action == "D":
                    column = max(0, column - count)
                else:
                    column = min(len(line), count - 1)
    line[column:column + len(text) - start] = text[start:]
    lines.append("".join(line))
    return "\n".join(lines)


def _iter_session_files(base_path):
    for current_root, _, files in os.walk(base_path):
        if "session.jsonl" in files:
            yield os.path.join(current_root, "session.jsonl")


def _event_matches(event, connection_id):
    value = str(connection_id)
    return value in (
        str(event.get("connection_id") or ""),
        str(event.get("session_id") or ""),
    )


def find_session(base_path, connection_id, archive_config=None, state_client=None, authorize_archive=None):
    if (archive_config or {}).get("recordings", {}).get("enabled"):
        from isolate_recordings import capture_root, RecordingNotFound
        private_root = capture_root(archive_config)
        private = _find_local_session(private_root, connection_id)
        if private is not None:
            return private
        try:
            return find_archived_session(archive_config, connection_id, state_client=state_client, authorize=authorize_archive)
        except RecordingNotFound:
            # Only an absent authority pointer permits legacy fallback. An S3
            # outage, corrupt evidence or denied access must never downgrade.
            if os.path.realpath(private_root) == os.path.realpath(base_path):
                return None
    return _find_local_session(base_path, connection_id)


def _find_local_session(base_path, connection_id):
    matched_events = []
    matched_paths = []
    for path in _iter_session_files(base_path):
        events = _load_events(path)
        selected = [event for event in events if _event_matches(event, connection_id)]
        if selected:
            matched_events.extend(selected)
            matched_paths.append((path, any(event.get("raw_log_path") for event in selected)))
    if not matched_events:
        return None
    matched_events.sort(key=lambda event: float(event.get("ts") or 0))
    preferred_path = next((path for path, has_raw in matched_paths if has_raw), matched_paths[0][0])
    return build_session_details(preferred_path, matched_events)


def find_archived_session(config, connection_id, state_client=None, authorize=None):
    """Authorize signed metadata before fetching any remote recording contents.

    Callers must supply their existing project/ownership permission check. There
    is deliberately no implicit 'authenticated user may download everything'.
    """
    from isolate_recordings import RecordingArchive, RecordingError, RecordingIntegrityError
    archive = RecordingArchive(config, state_client=state_client)
    description = archive.describe(connection_id)
    if authorize is None or authorize(description["metadata"]) is False:
        raise RecordingError("archived recording permission check is required")
    local = archive.materialize(connection_id, expected_revision=description["revision"])
    session_path = local.get("session_path")
    if not session_path:
        raise RecordingIntegrityError("archived session metadata is missing")
    events = [event for event in _load_events(session_path) if _event_matches(event, connection_id)]
    if not events:
        raise RecordingIntegrityError("archived events do not match the recording identity")
    details = build_session_details(session_path, events)
    details.update(raw_log_path=local.get("raw_log_path"), raw_meta_path=local.get("raw_meta_path"),
                   archive_complete=local["complete"], archive_revision=description["revision"],
                   archive_updated_at=description["updated_at"])
    details["summary"]["raw_log_path"] = local.get("raw_log_path")
    return details


def build_session_details(session_path, events):
    row = _row_from_events(events) or {}
    user_log_dir = os.path.dirname(os.path.dirname(session_path))
    raw_log_path = available_raw_log_path(row.get("raw_log_path"), user_log_dir)
    raw_meta_path = raw_log_path + ".meta" if raw_log_path else None
    if raw_meta_path and not os.path.exists(raw_meta_path):
        raw_meta_path = None
    return {
        "session_path": session_path,
        "session_dir": os.path.dirname(session_path),
        "summary": row,
        "events": events,
        "raw_log_path": raw_log_path,
        "raw_meta_path": raw_meta_path,
    }


def available_raw_log_path(candidate, user_log_dir):
    """Return the path to a recorded file confined to its owner's log directory."""
    if not candidate:
        return None
    try:
        user_log_dir = os.path.realpath(user_log_dir)
        path = os.path.realpath(str(candidate))
        if os.path.commonpath([user_log_dir, path]) != user_log_dir:
            return None
    except (OSError, ValueError):
        return None
    if not path.endswith(".log") or not os.path.isfile(path):
        return None
    return path


def _timestamp_markers(data, beginning):
    epoch_header = EPOCH_TIMESTAMP_RE.match(beginning)
    if epoch_header is None:
        for match in TIMESTAMP_RE.finditer(data):
            yield float(match.group(1)), match.start(), match.end()
        return

    # A ten-digit header establishes the width used by modern captures. When
    # a read ended in a digit, the next header starts inside that digit run.
    # Keep dates far outside the capture timeline as text. The permissive
    # window accommodates long legacy sessions and clock corrections. This
    # format cannot distinguish a nearby printed timestamp from a header.
    previous = float(epoch_header.group(1))
    for match in EPOCH_TIMESTAMP_RE.finditer(data):
        timestamp = float(match.group(1))
        if abs(timestamp - previous) > MAX_TIMESTAMP_GAP_SECONDS:
            continue
        previous = timestamp
        yield timestamp, match.start(), match.end()


def parse_raw_replay(raw_log_path, max_bytes=None, tail=False):
    empty = {"duration": 0, "chunks": [], "plain": "", "readable": "", "truncated": False}
    if not raw_log_path:
        return dict(empty, error="raw log not found")
    try:
        with open(raw_log_path, "rb") as raw_f:
            maximum = int(max_bytes or 0)
            offset = 0
            header = b""
            if tail and maximum > 0:
                offset = max(0, os.fstat(raw_f.fileno()).st_size - maximum)
                if offset:
                    header = raw_f.read(MAX_TIMESTAMP_BYTES)
                    raw_f.seek(offset)
            data = raw_f.read(maximum) if maximum > 0 else raw_f.read()
            remaining = maximum > 0 and os.fstat(raw_f.fileno()).st_size > offset + len(data)
            # Inspect just enough extra bytes to recognize a header split at
            # the limit without returning output from beyond it.
            lookahead = raw_f.read(MAX_TIMESTAMP_BYTES) if remaining else b""
            truncated = bool(offset or remaining)
    except FileNotFoundError:
        return dict(empty, error="raw log not found")
    except OSError as exc:
        return dict(empty, error=str(exc))

    captured = data + lookahead
    matches = _timestamp_markers(captured, header if offset else captured)
    first = next(matches, None)
    if first is None or first[1] >= len(data):
        text = data.decode("utf-8", errors="replace")
        return dict(
            empty,
            plain=text,
            readable=readable_terminal_text(text),
            truncated=truncated,
            error="raw log does not contain replay timestamps",
        )

    chunks = []
    first_ts, _, start = first
    if start > len(data):
        return dict(empty, truncated=truncated, error=None)
    timestamp = first_ts
    last = len(data)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    for next_ts, end, next_start in matches:
        if end >= len(data):
            break
        if next_start > len(data):
            last = end
            break
        chunks.append({"t": round(timestamp - first_ts, 6), "data": decoder.decode(data[start:end])})
        timestamp, start = next_ts, next_start
    chunks.append({"t": round(timestamp - first_ts, 6), "data": decoder.decode(data[start:last], final=True)})
    plain = "".join(chunk["data"] for chunk in chunks)
    return {
        "duration": chunks[-1]["t"],
        "chunks": chunks,
        "plain": plain,
        "readable": readable_terminal_text(plain),
        "truncated": truncated,
        "error": None,
    }


def events_json(events):
    return json.dumps(events, indent=2, sort_keys=True)


def tail_raw_text(raw_log_path, max_bytes=262144):
    if not raw_log_path or not os.path.isfile(raw_log_path):
        return {"text": "", "bytes": 0, "truncated": False, "error": "raw log not found"}
    maximum = max(1, int(max_bytes))
    try:
        size = os.path.getsize(raw_log_path)
        with open(raw_log_path, "rb") as raw_f:
            if size > maximum:
                raw_f.seek(size - maximum)
            data = raw_f.read(maximum)
    except OSError as exc:
        return {"text": "", "bytes": 0, "truncated": False, "error": str(exc)}
    return {
        "text": data.decode("utf-8", errors="replace"),
        "bytes": len(data),
        "truncated": size > maximum,
        "error": None,
    }
