"""Drafts and immutable publications for the operational runbook catalogue."""

import json
import re
import time

from redis.exceptions import WatchError

from isolate_runbooks import (
    BUILTIN_RUNBOOKS,
    CUSTOM_PARAMETER_NAME,
    CUSTOM_PARAMETER_TOKEN,
    MAX_CUSTOM_INTEGER,
    MIN_CUSTOM_INTEGER,
    RunbookError,
    _definition_hash,
    _normalize_custom_parameter,
    _render_definition,
)


CUSTOM_RUNBOOK_PREFIX = "runbook_custom_"
_MAX_VERSIONS = 32
_RUNBOOK_ID = re.compile(r"[a-z][a-z0-9-]{0,63}")
_EXECUTABLE = re.compile(r"/[A-Za-z0-9_.+/-]+")
_STRING_PATTERN = re.compile(r"\^?\[[A-Za-z0-9_.:@/-]+\](?:[+?*]|\{[0-9]{1,3}(?:,[0-9]{0,3})?\})?\$?")
_SHELLS = {"sh", "bash", "dash", "ash", "zsh", "ksh", "fish", "csh", "tcsh"}
_INTERPRETERS = re.compile(r"(?:python|perl|ruby|php|lua|node|awk|sed)(?:[0-9.]+)?")
_WRAPPERS = {"env", "busybox", "sudo", "doas", "eval", "xargs", "find"}


class RunbookConflict(RunbookError):
    """The runbook changed after the editor was opened."""


def _valid_id(runbook_id):
    return (isinstance(runbook_id, str) and bool(_RUNBOOK_ID.fullmatch(runbook_id))
            and runbook_id not in BUILTIN_RUNBOOKS)


def _key(runbook_id):
    if not _valid_id(runbook_id):
        raise RunbookError("invalid or reserved runbook ID")
    return CUSTOM_RUNBOOK_PREFIX + runbook_id


def _integer(value, description, minimum, maximum):
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,10}", value):
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise RunbookError("{} must be an integer between {} and {}".format(description, minimum, maximum))
    return value


def _text(value, description, maximum, *, required=False):
    if not isinstance(value, str) or "\x00" in value or len(value) > maximum or (required and not value.strip()):
        raise RunbookError("{} must be text of {} to {} characters".format(description, 1 if required else 0, maximum))
    return value.strip()


def _parameter_specs(supplied):
    if not isinstance(supplied, dict) or len(supplied) > 24:
        raise RunbookError("parameters must be an object with at most 24 entries")
    definitions = {}
    for name, raw in supplied.items():
        if not isinstance(name, str) or not re.fullmatch(CUSTOM_PARAMETER_NAME, name) or not isinstance(raw, dict):
            raise RunbookError("invalid parameter definition")
        kind = raw.get("type")
        if kind not in ("string", "integer"):
            raise RunbookError("parameter {} must have type string or integer".format(name))
        allowed_fields = {"type", "required", "default"} | ({"minimum", "maximum"} if kind == "integer" else {"pattern"})
        required = raw.get("required", False)
        if set(raw) - allowed_fields or type(required) is not bool:
            raise RunbookError("invalid fields for parameter {}".format(name))
        specification = {"type": kind, "required": required}
        if kind == "integer":
            for field in ("minimum", "maximum"):
                if field in raw:
                    specification[field] = _integer(raw[field], field + " for " + name, MIN_CUSTOM_INTEGER, MAX_CUSTOM_INTEGER)
            if specification.get("minimum", MIN_CUSTOM_INTEGER) > specification.get("maximum", MAX_CUSTOM_INTEGER):
                raise RunbookError("parameter {} minimum exceeds maximum".format(name))
        elif "pattern" in raw:
            pattern = raw["pattern"]
            # One character class and one optional quantifier keep validation bounded.
            if not isinstance(pattern, str) or len(pattern) > 120 or not _STRING_PATTERN.fullmatch(pattern):
                raise RunbookError("parameter {} pattern must be a single character class with an optional quantifier".format(name))
            try:
                re.compile(pattern)
            except re.error as exc:
                raise RunbookError("parameter {} has an invalid pattern".format(name)) from exc
            specification["pattern"] = pattern
        if "default" in raw:
            default = _normalize_custom_parameter(name, raw["default"], specification)
            specification["default"] = int(default) if kind == "integer" else default
        definitions[name] = specification
    return definitions


def _validate_command_parameters(command, dynamic_indexes):
    if not dynamic_indexes:
        return
    filename = command[0].rsplit("/", 1)[-1]
    first_parameter = dynamic_indexes[0]
    if filename in _SHELLS and command[1] == "-c":
        # sh -c script name [arguments...] keeps the script and $0 constant.
        allowed = first_parameter >= 4
    elif filename in _SHELLS or _INTERPRETERS.fullmatch(filename):
        allowed = first_parameter >= 2 and _EXECUTABLE.fullmatch(command[1])
    else:
        allowed = filename not in _WRAPPERS
    if not allowed:
        raise RunbookError("command parameters must be arguments to a fixed script or executable")


def validate_custom_definition(definition):
    fields = {"title", "description", "class", "commands", "parameters", "default_timeout"}
    if not isinstance(definition, dict) or set(definition) - fields:
        raise RunbookError("invalid fields in runbook definition")
    if definition.get("class", "operational") != "operational":
        raise RunbookError("custom runbooks must be operational")
    title = _text(definition.get("title"), "title", 120, required=True)
    description = _text(definition.get("description", ""), "description", 1000)
    timeout = _integer(definition.get("default_timeout", 60), "default timeout", 1, 86400)
    parameters = _parameter_specs(definition.get("parameters", {}))
    commands = definition.get("commands")
    if not isinstance(commands, list) or not 1 <= len(commands) <= 16:
        raise RunbookError("provide between 1 and 16 commands")
    argv = []
    for command in commands:
        if not isinstance(command, list) or not 1 <= len(command) <= 32:
            raise RunbookError("each command must be an array of 1 to 32 strings")
        if any(not isinstance(argument, str) or len(argument) > 4096 or "\x00" in argument for argument in command):
            raise RunbookError("command arguments must be text of at most 4096 characters")
        executable = command[0]
        if not _EXECUTABLE.fullmatch(executable) or executable.endswith("/"):
            raise RunbookError("command must use a fixed absolute executable path")
        dynamic_indexes = []
        for index, argument in enumerate(command[1:], start=1):
            placeholder = CUSTOM_PARAMETER_TOKEN.fullmatch(argument)
            if placeholder:
                if placeholder.group(1) not in parameters:
                    raise RunbookError("unknown command parameter {}".format(placeholder.group(1)))
                dynamic_indexes.append(index)
            elif any(match.group(1) in parameters for match in CUSTOM_PARAMETER_TOKEN.finditer(argument)):
                raise RunbookError("a command parameter must occupy a whole argument")
        _validate_command_parameters(command, dynamic_indexes)
        argv.append(list(command))
    normalized = {"title": title, "description": description, "class": "operational",
                  "commands": argv, "parameters": parameters, "default_timeout": timeout}
    try:
        size = len(json.dumps(normalized, ensure_ascii=False).encode("utf-8"))
    except UnicodeError as exc:
        raise RunbookError("runbook definition must contain valid UTF-8 text") from exc
    if size > 16384:
        raise RunbookError("runbook definition exceeds 16 KiB")
    return normalized


def preview_runbook_draft(definition, parameters=None):
    return _render_definition(validate_custom_definition(definition), parameters, custom=True)


def _decode_record(raw, runbook_id):
    if raw is None:
        return None
    try:
        record = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise RunbookError("stored runbook record is invalid") from exc
    if (not isinstance(record, dict) or record.get("id") != runbook_id
            or type(record.get("revision")) is not int or not isinstance(record.get("versions"), list)):
        raise RunbookError("stored runbook record is invalid")
    return record


def get_custom_runbook(store, runbook_id):
    return _decode_record(store.get(_key(runbook_id)), runbook_id)


def list_custom_runbooks(store):
    records = {}
    for key in store.scan_iter(match=CUSTOM_RUNBOOK_PREFIX + "*"):
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        runbook_id = key.removeprefix(CUSTOM_RUNBOOK_PREFIX)
        if _valid_id(runbook_id):
            record = _decode_record(store.get(key), runbook_id)
            if record is not None:
                records[runbook_id] = record
    return [records[runbook_id] for runbook_id in sorted(records)]


def _published(record, definition_sha256=None):
    if record is None:
        return None
    version = next((item for item in record["versions"] if (
        item["definition_sha256"] == definition_sha256 if definition_sha256 is not None
        else item["version"] == record["active_version"])), None)
    if version is None or "retired_at" in version:
        return None
    digest = _release_digest(record["id"], version["version"], version["definition"])
    if digest != version["definition_sha256"]:
        raise RunbookError("published runbook definition failed its integrity check")
    definition = validate_custom_definition(version["definition"])
    return dict(definition, id=record["id"], source="custom", version=version["version"], definition_sha256=digest)


def get_published_runbook(store, runbook_id, *, definition_sha256=None):
    if not _valid_id(runbook_id):
        return None
    return _published(get_custom_runbook(store, runbook_id), definition_sha256)


def list_published_runbooks(store):
    return [published for record in list_custom_runbooks(store) if (published := _published(record)) is not None]


def _release_digest(runbook_id, version, definition):
    return _definition_hash({"id": runbook_id, "version": version, "definition": definition})


def _update(store, runbook_id, actor, expected_revision, change, *, allow_create=False):
    key = _key(runbook_id)
    actor = _text(actor, "actor", 256, required=True)
    expected_revision = _integer(expected_revision, "expected revision", 0, MAX_CUSTOM_INTEGER)
    try:
        with store.pipeline() as pipeline:
            pipeline.watch(key)
            record = _decode_record(pipeline.get(key), runbook_id)
            if record is None:
                if not allow_create:
                    raise RunbookError("custom runbook was not found")
                record = {"id": runbook_id, "revision": 0, "draft": None, "active_version": None, "versions": []}
            if record["revision"] != expected_revision:
                raise RunbookConflict("runbook changed since it was opened")
            now = int(time.time())
            change(record, actor, now)
            record.update(revision=record["revision"] + 1, updated_by=actor, updated_at=now)
            pipeline.multi()
            pipeline.set(key, json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            pipeline.execute()
    except WatchError as exc:
        raise RunbookConflict("runbook changed since it was opened") from exc
    return record


def save_runbook_draft(store, runbook_id, definition, *, actor, expected_revision=0):
    draft = validate_custom_definition(definition)

    def save(record, author, now):
        record.update(draft=draft, draft_updated_by=author, draft_updated_at=now)

    return _update(store, runbook_id, actor, expected_revision, save, allow_create=True)


def publish_runbook(store, runbook_id, *, actor, expected_revision):
    def publish(record, author, now):
        if record["draft"] is None:
            raise RunbookError("save a draft before publishing")
        if len(record["versions"]) >= _MAX_VERSIONS:
            raise RunbookError("runbook has reached its limit of 32 published versions")
        definition = validate_custom_definition(record["draft"])
        version = len(record["versions"]) + 1
        record["versions"].append({"version": version, "definition": definition,
                                   "definition_sha256": _release_digest(runbook_id, version, definition),
                                   "published_at": now, "published_by": author})
        record.update(draft=None, active_version=version)

    return _update(store, runbook_id, actor, expected_revision, publish)


def retire_runbook(store, runbook_id, *, actor, expected_revision, version=None):
    if version is not None:
        version = _integer(version, "version", 1, _MAX_VERSIONS)

    def retire(record, author, now):
        target = version if version is not None else record["active_version"]
        publication = next((item for item in record["versions"] if item["version"] == target), None)
        if publication is None or "retired_at" in publication:
            raise RunbookError("published runbook version is not active")
        publication.update(retired_at=now, retired_by=author)
        if record["active_version"] == target:
            record["active_version"] = None

    return _update(store, runbook_id, actor, expected_revision, retire)
