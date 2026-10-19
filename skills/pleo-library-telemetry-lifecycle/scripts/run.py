#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_API_PATH = "/api/agent-telemetry/events"
PLEO_LIBRARY_PREFIX = "pleo-library-"
TELEMETRY_USER_ID_ENV = "TELEMETRY_USER_ID"
SUPPORTED_COMMANDS = ("start", "progress", "finish", "interrupt")
DEFAULT_STAGE_BY_COMMAND = {
    "start": "started",
    "progress": "in_progress",
    "finish": "completed",
    "interrupt": "interrupted",
}
DEFAULT_STATUS_BY_COMMAND = {
    "interrupt": "cancelled",
}
ALLOWED_STATUS_BY_COMMAND = {
    "start": {None},
    "progress": {None},
    "finish": {"success", "error"},
    "interrupt": {"cancelled", "error"},
}


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    api_path: str
    source: str
    timeout_seconds: float
    retries: int
    retry_delay_seconds: float
    dry_run: bool
    allow_pleo_library_skill: bool


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        normalize_args(args)
        config = build_config(args)
        payload = build_payload(config, args)
        send_event(config, payload)
    except ScriptError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send lifecycle telemetry events for skills to an external API."
    )
    parser.add_argument(
        "command",
        help="Lifecycle command: start, progress, finish, interrupt.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Calling agent/source, for example codex, claude, gemini.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--project-slug")
    parser.add_argument("--stage")
    parser.add_argument("--message")
    parser.add_argument("--status")
    parser.add_argument(
        "--details-json",
        help="Optional JSON object with additional fields, for example '{\"phase\":\"analysis\"}'.",
    )
    parser.add_argument(
        "--created-at",
        help="Optional ISO-8601 timestamp to use instead of current UTC time.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-pleo-library-skill",
        action="store_true",
        help="Deprecated compatibility flag. Standard telemetry does not report pleo-library-* skills.",
    )
    return parser


def normalize_args(args: argparse.Namespace) -> None:
    args.command = normalize_command(args.command)
    args.source = normalize_required_text(args.source, "--source")
    args.run_id = normalize_required_text(args.run_id, "--run-id")
    args.skill = normalize_required_text(args.skill, "--skill")
    args.project_slug = normalize_optional_text(args.project_slug)
    args.message = normalize_optional_text(args.message)
    args.stage = normalize_optional_text(args.stage) or DEFAULT_STAGE_BY_COMMAND[args.command]
    args.status = normalize_status(args.command, args.status)
    args.created_at = parse_created_at(args.created_at)


def normalize_command(raw_command: str) -> str:
    command = normalize_optional_text(raw_command)
    if command is None:
        raise ScriptError("Command is required.")
    normalized = command.lower()
    if normalized == "heartbeat":
        raise ScriptError(
            "Command heartbeat was removed. Send progress only when the work actually changes stage; otherwise omit it."
        )
    if normalized not in SUPPORTED_COMMANDS:
        supported = ", ".join(SUPPORTED_COMMANDS)
        raise ScriptError(f"Unsupported command: {raw_command}. Supported commands: {supported}.")
    return normalized


def normalize_status(command: str, raw_status: str | None) -> str | None:
    normalized = normalize_optional_text(raw_status)
    if normalized is None:
        if command == "finish":
            raise ScriptError("finish wymaga jawnego --status success albo --status error.")
        return DEFAULT_STATUS_BY_COMMAND.get(command)
    normalized = normalized.lower()
    if normalized not in ALLOWED_STATUS_BY_COMMAND[command]:
        allowed = sorted(status for status in ALLOWED_STATUS_BY_COMMAND[command] if status is not None)
        if allowed:
            raise ScriptError(f"--status={normalized} is not valid for {command}. Allowed values: {', '.join(allowed)}.")
        raise ScriptError(f"--status is not supported for {command}.")
    return normalized


def parse_created_at(value: str | None) -> str:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return utc_now_iso()
    try:
        parsed = dt.datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScriptError("--created-at must be a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_config(args: argparse.Namespace) -> ClientConfig:
    if args.retries < 0:
        raise ScriptError("--retries must be >= 0.")
    if args.retry_delay_seconds < 0:
        raise ScriptError("--retry-delay-seconds must be >= 0.")
    if args.timeout_seconds <= 0:
        raise ScriptError("--timeout-seconds must be > 0.")

    return ClientConfig(
        base_url=load_library_base_url(),
        api_path=DEFAULT_API_PATH,
        source=args.source,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        retry_delay_seconds=args.retry_delay_seconds,
        dry_run=bool(args.dry_run),
        allow_pleo_library_skill=bool(args.allow_pleo_library_skill),
    )


def build_payload(config: ClientConfig, args: argparse.Namespace) -> dict[str, Any]:
    validate_tracked_skill_name(args.skill, config.allow_pleo_library_skill)
    details = parse_optional_json_object(args.details_json)
    library_user_id = load_required_library_user_id()
    payload: dict[str, Any] = {
        "eventType": args.command,
        "runId": args.run_id,
        "skillName": args.skill,
        "projectSlug": args.project_slug,
        "telemetryUserId": library_user_id,
        "libraryUserId": library_user_id,
        "stage": args.stage,
        "message": args.message,
        "status": args.status,
        "source": config.source,
        "createdAt": args.created_at,
    }
    if details is not None:
        payload["details"] = details
    clean_payload(payload)
    return payload


def send_event(config: ClientConfig, payload: dict[str, Any]) -> None:
    if config.dry_run:
        print(json.dumps(payload, ensure_ascii=False))
        return

    url = config.base_url + config.api_path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    attempts = config.retries + 1
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                response.read()
            return
        except urllib.error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            if should_retry_http(exc.code) and attempt < attempts:
                time.sleep(config.retry_delay_seconds)
                continue
            raise ScriptError(f"HTTP {exc.code} for {url}: {extract_error_message(response_text)}") from exc
        except urllib.error.URLError as exc:
            if attempt < attempts:
                time.sleep(config.retry_delay_seconds)
                continue
            raise ScriptError(f"Connection error for {url}: {exc.reason}") from exc


def validate_tracked_skill_name(skill_name: str, allow_pleo_library_skill: bool) -> None:
    normalized_skill_name = normalize_optional_text(skill_name)
    if normalized_skill_name is None:
        raise ScriptError("--skill must not be blank.")
    if normalized_skill_name.lower().startswith(PLEO_LIBRARY_PREFIX):
        raise ScriptError(
            "Telemetry nie raportuje skilli pleo-library-*. "
            "Użyj telemetryki tylko dla skilla docelowego spoza prefiksu pleo-library-."
        )


def should_retry_http(code: int) -> bool:
    return 500 <= code <= 599 or code == 429


def parse_optional_json_object(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ScriptError(f"--details-json is not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ScriptError("--details-json must be a JSON object.")
    return parsed


def extract_error_message(payload: str) -> str:
    payload = payload.strip()
    if not payload:
        return "empty error response"
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(parsed, dict):
        for key in ("message", "error", "detail"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return payload


def clean_payload(payload: dict[str, Any]) -> None:
    keys_to_remove = [key for key, value in payload.items() if value is None]
    for key in keys_to_remove:
        payload.pop(key, None)


def load_optional_telemetry_user_id() -> str | None:
    value = os.environ.get(TELEMETRY_USER_ID_ENV)
    return normalize_optional_text(value)


def load_required_library_user_id() -> str:
    value = load_optional_telemetry_user_id()
    if value is None:
        raise ScriptError("Brakuje TELEMETRY_USER_ID. PleoAI wymaga przekazywania libraryUserId.")
    return value


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_library_base_url() -> str:
    repo_root = find_repo_root(Path(__file__).resolve())
    config = parse_simple_yaml(repo_root / ".agent-library.yaml")
    value = config.get("libraryBaseUrl")
    if not isinstance(value, str) or not value.strip():
        raise ScriptError("Brakuje libraryBaseUrl w .agent-library.yaml.")
    return value.strip().rstrip("/")


def find_repo_root(start_path: Path) -> Path:
    current = start_path if start_path.is_dir() else start_path.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".agent-library.yaml").is_file():
            return candidate
    raise ScriptError("Nie znaleziono .agent-library.yaml.")


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ScriptError(f"Brakuje pliku konfiguracyjnego: {path}")

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        key, separator, value = stripped.partition(":")
        if not separator:
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        key = key.strip()
        value = value.strip()
        if not value:
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
        else:
            current[key] = parse_yaml_scalar(value)
    return root


def parse_yaml_scalar(value: str) -> Any:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.isdigit():
        return int(value)
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_required_text(value: str | None, field_name: str) -> str:
    normalized = normalize_optional_text(value)
    if normalized is None:
        raise ScriptError(f"{field_name} must not be blank.")
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
