#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Typed diagnostic and operational runbooks."""

import copy
import hashlib
import json
import re
import shlex


class RunbookError(ValueError):
    pass


SERVICE_PATTERN = r"^[A-Za-z0-9@_.:-]{1,128}$"
CUSTOM_PARAMETER_NAME = r"[A-Za-z][A-Za-z0-9_]{0,47}"
CUSTOM_PARAMETER_TOKEN = re.compile(r"\{(" + CUSTOM_PARAMETER_NAME + r")\}")
CUSTOM_STRING_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}")
MIN_CUSTOM_INTEGER = -(2 ** 31)
MAX_CUSTOM_INTEGER = 2 ** 31 - 1


BUILTIN_RUNBOOKS = {
    "uptime": {
        "title": "System uptime and load",
        "class": "read_only",
        "description": "Show uptime and load averages.",
        "commands": [["/usr/bin/uptime"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "disk-usage": {
        "title": "Filesystem usage",
        "class": "read_only",
        "description": "Show filesystem type and human-readable space usage.",
        "commands": [["/usr/bin/df", "-hT"]],
        "parameters": {},
        "default_timeout": 60,
    },
    "inode-usage": {
        "title": "Filesystem inode usage",
        "class": "read_only",
        "description": "Show inode consumption for mounted filesystems.",
        "commands": [["/usr/bin/df", "-ih"]],
        "parameters": {},
        "default_timeout": 60,
    },
    "memory": {
        "title": "Memory usage",
        "class": "read_only",
        "description": "Show memory and swap usage in MiB.",
        "commands": [["/usr/bin/free", "-m"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "cpu-processes": {
        "title": "Top CPU processes",
        "class": "read_only",
        "description": "Show a bounded snapshot of processes sorted by CPU usage.",
        "commands": [["/usr/bin/ps", "-eo", "pid,ppid,user,stat,%cpu,%mem,etime,comm", "--sort=-%cpu"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "memory-processes": {
        "title": "Top memory processes",
        "class": "read_only",
        "description": "Show a bounded snapshot of processes sorted by memory usage.",
        "commands": [["/usr/bin/ps", "-eo", "pid,ppid,user,stat,%cpu,%mem,rss,etime,comm", "--sort=-%mem"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "top-snapshot": {
        "title": "Top snapshot",
        "class": "read_only",
        "description": "Capture one non-interactive top snapshot.",
        "commands": [["/usr/bin/top", "-b", "-n", "1", "-w", "160"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "atop-snapshot": {
        "title": "Atop snapshot",
        "class": "read_only",
        "description": "Capture one parseable CPU, memory, disk, and network atop sample.",
        "commands": [["/usr/bin/atop", "-P", "CPU,MEM,DSK,NET", "1", "1"]],
        "parameters": {},
        "default_timeout": 45,
    },
    "service-status": {
        "title": "Service status",
        "class": "read_only",
        "description": "Show full systemd status for one validated unit.",
        "commands": [["/usr/bin/systemctl", "--no-pager", "--full", "status", "--", "{service}"]],
        "parameters": {"service": {"type": "string", "pattern": SERVICE_PATTERN, "required": True}},
        "default_timeout": 30,
    },
    "service-active": {
        "title": "Service active state",
        "class": "read_only",
        "description": "Check whether one validated systemd unit is active.",
        "commands": [["/usr/bin/systemctl", "is-active", "--", "{service}"]],
        "parameters": {"service": {"type": "string", "pattern": SERVICE_PATTERN, "required": True}},
        "default_timeout": 30,
    },
    "journal-tail": {
        "title": "Service journal tail",
        "class": "read_only",
        "description": "Show the latest journal entries for one validated systemd unit.",
        "commands": [["/usr/bin/journalctl", "--no-pager", "-u", "{service}", "-n", "{lines}"]],
        "parameters": {
            "service": {"type": "string", "pattern": SERVICE_PATTERN, "required": True},
            "lines": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 200},
        },
        "default_timeout": 60,
    },
    "failed-services": {
        "title": "Failed services",
        "class": "read_only",
        "description": "List failed systemd units.",
        "commands": [["/usr/bin/systemctl", "--no-pager", "--failed"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "listening-sockets": {
        "title": "Listening sockets",
        "class": "read_only",
        "description": "Show listening TCP and UDP sockets and owning processes when permitted.",
        "commands": [["/usr/bin/ss", "-lntup"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "network-addresses": {
        "title": "Network addresses",
        "class": "read_only",
        "description": "Show a compact list of network interfaces and addresses.",
        "commands": [["/usr/sbin/ip", "-brief", "address"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "network-routes": {
        "title": "Network routes",
        "class": "read_only",
        "description": "Show the current network routing table.",
        "commands": [["/usr/sbin/ip", "route", "show"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "service-restart": {
        "title": "Restart service",
        "class": "operational",
        "description": "Restart one validated systemd unit.",
        "commands": [["/usr/bin/systemctl", "restart", "--", "{service}"]],
        "parameters": {"service": {"type": "string", "pattern": SERVICE_PATTERN, "required": True}},
        "default_timeout": 120,
    },
    "dns-cache-flush": {
        "title": "Flush system DNS cache",
        "class": "operational",
        "description": "Flush the systemd-resolved DNS cache.",
        "commands": [["/usr/bin/resolvectl", "flush-caches"]],
        "parameters": {},
        "default_timeout": 30,
    },
    "deploy-diagnostics": {
        "title": "Deployment diagnostics",
        "class": "operational",
        "description": "Collect bounded service, journal, disk, and memory diagnostics after a deployment.",
        "commands": [
            ["/usr/bin/systemctl", "--no-pager", "--full", "status", "--", "{service}"],
            ["/usr/bin/journalctl", "--no-pager", "-u", "{service}", "-n", "{lines}"],
            ["/usr/bin/df", "-hT"],
            ["/usr/bin/free", "-m"],
        ],
        "parameters": {
            "service": {"type": "string", "pattern": SERVICE_PATTERN, "required": True},
            "lines": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 200},
        },
        "default_timeout": 120,
    },
}


def _definition_hash(runbook):
    payload = json.dumps(runbook, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def list_runbooks(config, classes=None, *, store=None):
    disabled = set((config.get("runbooks", {}) or {}).get("disabled") or [])
    selected_classes = set(classes or ("read_only", "operational"))
    rows = []
    for runbook_id, source in BUILTIN_RUNBOOKS.items():
        if runbook_id in disabled or source["class"] not in selected_classes:
            continue
        record = copy.deepcopy(source)
        record.update({"id": runbook_id, "definition_sha256": _definition_hash(source)})
        rows.append(record)
    if store is not None and "operational" in selected_classes:
        from isolate_runbook_catalog import list_published_runbooks

        rows.extend(record for record in list_published_runbooks(store) if record["id"] not in disabled)
    rows.sort(key=lambda item: (item["class"], item["id"]))
    return rows


def get_runbook(config, runbook_id, *, store=None, definition_sha256=None):
    for record in list_runbooks(config):
        if record["id"] == runbook_id:
            if definition_sha256 is None or record["definition_sha256"] == definition_sha256:
                return record
            return None
    if store is not None and isinstance(runbook_id, str) and runbook_id not in BUILTIN_RUNBOOKS:
        if runbook_id in ((config.get("runbooks", {}) or {}).get("disabled") or []):
            return None
        from isolate_runbook_catalog import get_published_runbook

        return get_published_runbook(store, runbook_id, definition_sha256=definition_sha256)
    return None


def _normalize_parameter(name, value, specification):
    value_type = specification.get("type")
    if value_type == "integer":
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise RunbookError("parameter {} must be an integer".format(name)) from exc
        if normalized < int(specification.get("minimum", normalized)):
            raise RunbookError("parameter {} is below the minimum".format(name))
        if normalized > int(specification.get("maximum", normalized)):
            raise RunbookError("parameter {} exceeds the maximum".format(name))
        return str(normalized)
    normalized = str(value or "").strip()
    if not normalized:
        raise RunbookError("parameter {} is required".format(name))
    pattern = specification.get("pattern")
    if pattern and re.fullmatch(pattern, normalized) is None:
        raise RunbookError("parameter {} has an invalid value".format(name))
    return normalized


def _normalize_custom_parameter(name, value, specification):
    if specification["type"] == "integer":
        if type(value) is int:
            valid = MIN_CUSTOM_INTEGER <= value <= MAX_CUSTOM_INTEGER
        else:
            valid = isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,10}", value)
            valid = valid and MIN_CUSTOM_INTEGER <= int(value) <= MAX_CUSTOM_INTEGER
        if not valid:
            raise RunbookError("parameter {} must be a 32-bit integer".format(name))
    elif not isinstance(value, str) or not CUSTOM_STRING_VALUE.fullmatch(value):
        raise RunbookError("parameter {} must be a safe string of 1 to 128 characters".format(name))
    return _normalize_parameter(name, value, specification)


def render_runbook(config, runbook_id, parameters=None, *, store=None, definition_sha256=None):
    runbook = get_runbook(config, str(runbook_id or "").strip(), store=store, definition_sha256=definition_sha256)
    if runbook is None:
        raise RunbookError("runbook is unknown or disabled")
    return _render_definition(runbook, parameters, custom=runbook.get("source") == "custom")


def _render_definition(runbook, parameters, *, custom=False):
    supplied = parameters or {}
    if not isinstance(supplied, dict):
        raise RunbookError("parameters must be an object")
    definitions = runbook.get("parameters") or {}
    unknown = sorted(set(supplied) - set(definitions))
    if unknown:
        raise RunbookError("unknown runbook parameter: {}".format(unknown[0]))
    normalized = {}
    normalize = _normalize_custom_parameter if custom else _normalize_parameter
    for name, specification in definitions.items():
        if name in supplied:
            value = supplied[name]
        elif "default" in specification:
            value = specification["default"]
        elif specification.get("required"):
            raise RunbookError("parameter {} is required".format(name))
        else:
            continue
        normalized[name] = normalize(name, value, specification)

    rendered_commands = []
    for command in runbook.get("commands") or []:
        if not command or not str(command[0]).startswith("/"):
            raise RunbookError("runbook command must use an absolute executable path")
        argv = []
        for token in command:
            rendered = str(token)
            if custom:
                placeholder = CUSTOM_PARAMETER_TOKEN.fullmatch(rendered)
                if placeholder:
                    name = placeholder.group(1)
                    if name not in normalized:
                        raise RunbookError("parameter {} is required".format(name))
                    rendered = normalized[name]
            else:
                for name, value in normalized.items():
                    rendered = rendered.replace("{{{}}}".format(name), value)
                if re.search(r"\{[A-Za-z0-9_]+\}", rendered):
                    raise RunbookError("runbook command contains an unresolved parameter")
            argv.append(rendered)
        rendered_commands.append(" ".join(shlex.quote(token) for token in argv))
    if not rendered_commands:
        raise RunbookError("runbook does not contain commands")
    return {
        "runbook": runbook,
        "parameters": normalized,
        "command": (" && " if custom else "; ").join(rendered_commands),
        "policy_action": "runbook" if runbook["class"] == "read_only" else "operate",
    }
