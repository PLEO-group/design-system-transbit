#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_PATTERN = re.compile(r"(?im)^#\s*WERSJA\s+(\d+\.\d+\.\d+)\s*$")
INSTRUCTION_TYPES = ("AGENTS", "CLAUDE", "GEMINI")
TRANSIENT_HTTP_STATUS_CODES = {502, 503, 504}
MAX_TRANSIENT_RETRIES = 2


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    base_url: str
    project_slug: str
    path_by_type: dict[str, Path]
    library_user_id: str


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root(Path(args.repo_root) if args.repo_root else Path(__file__).resolve())
        config = load_config(repo_root)
        selected_types = normalize_types(args.type)
        if args.command == "check":
            result = check_instructions(config, selected_types)
        elif args.command == "pull":
            result = pull_instructions(config, selected_types)
        elif args.command == "publish":
            result = publish_instructions(config, selected_types)
        else:
            raise ScriptError(f"Nieznana komenda: {args.command}")
    except ScriptError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronizuje AGENTS.md, CLAUDE.md i GEMINI.md z biblioteką."
    )
    parser.add_argument("--repo-root", help="Ścieżka do katalogu repo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Porównaj lokalne pliki z biblioteką.")
    check_parser.add_argument("--type", action="append", choices=INSTRUCTION_TYPES, help="Typ instrukcji.")

    pull_parser = subparsers.add_parser("pull", help="Pobierz wskazane instrukcje z biblioteki.")
    pull_parser.add_argument("--type", action="append", choices=INSTRUCTION_TYPES, required=True, help="Typ instrukcji.")

    publish_parser = subparsers.add_parser("publish", help="Opublikuj wskazane instrukcje do biblioteki.")
    publish_parser.add_argument("--type", action="append", choices=INSTRUCTION_TYPES, required=True, help="Typ instrukcji.")

    return parser


def check_instructions(config: Config, selected_types: list[str]) -> dict[str, Any]:
    remote_by_type = fetch_remote_instructions(config)
    results = [build_instruction_status(config, remote_by_type, instruction_type) for instruction_type in selected_types]
    return {
        "projectSlug": config.project_slug,
        "results": results,
    }


def pull_instructions(config: Config, selected_types: list[str]) -> dict[str, Any]:
    remote_by_type = fetch_remote_instructions(config)
    results: list[dict[str, Any]] = []
    for instruction_type in selected_types:
        remote = remote_by_type.get(instruction_type)
        if remote is None:
            raise ScriptError(f"Biblioteka PLEO nie zwróciła wpisu dla typu {instruction_type}.")
        content = remote["content"]
        remote_version = extract_version(content, f"remote {instruction_type}")
        target_path = config.path_by_type[instruction_type]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        results.append(
            {
                "type": instruction_type,
                "path": str(target_path),
                "remoteVersion": remote_version,
                "changed": True,
            }
        )

    return {
        "projectSlug": config.project_slug,
        "results": results,
    }


def publish_instructions(config: Config, selected_types: list[str]) -> dict[str, Any]:
    remote_by_type = fetch_remote_instructions(config)
    results: list[dict[str, Any]] = []
    for instruction_type in selected_types:
        local_path = config.path_by_type[instruction_type]
        if not local_path.is_file():
            raise ScriptError(f"Brakuje lokalnego pliku dla {instruction_type}: {local_path}")
        content = local_path.read_text(encoding="utf-8")
        declared_version = extract_version(content, str(local_path))
        remote = remote_by_type.get(instruction_type)
        if remote is not None:
            remote_content = remote["content"]
            remote_version = extract_version(remote_content, f"remote {instruction_type}")
            version_cmp = compare_semver(declared_version, remote_version)
            if version_cmp < 0:
                raise ScriptError(
                    f"Biblioteka PLEO ma nowszą wersję {instruction_type}: "
                    f"{declared_version} -> {remote_version}. Najpierw pobierz nowszą wersję."
                )
            if version_cmp == 0 and sha256_hex(content) != sha256_hex(remote_content):
                raise ScriptError(
                    f"Lokalna instrukcja {instruction_type} ma zmienioną treść bez podbicia # WERSJA "
                    f"({declared_version}). Podbij wersję przed publikacją."
                )
        result = request_json(
            config,
            "POST",
            "/library/projects/agent-instructions/remote/upsert",
            body={
                "projectSlug": config.project_slug,
                "type": instruction_type,
                "content": content,
                "libraryUserId": config.library_user_id,
            },
        )
        results.append(
            {
                "type": instruction_type,
                "path": str(local_path),
                "contentVersion": declared_version,
                "libraryVersion": result["version"],
                "updatedAt": result["updatedAt"],
            }
        )

    return {
        "projectSlug": config.project_slug,
        "results": results,
    }


def build_instruction_status(
    config: Config,
    remote_by_type: dict[str, dict[str, Any]],
    instruction_type: str,
) -> dict[str, Any]:
    local_path = config.path_by_type[instruction_type]
    local_exists = local_path.is_file()
    local_content = local_path.read_text(encoding="utf-8") if local_exists else None
    local_version = extract_version(local_content, str(local_path)) if local_content is not None else None
    remote = remote_by_type.get(instruction_type)
    remote_content = remote["content"] if remote is not None else None
    remote_version = extract_version(remote_content, f"remote {instruction_type}") if remote_content is not None else None
    local_hash = sha256_hex(local_content) if local_content is not None else None
    remote_hash = sha256_hex(remote_content) if remote_content is not None else None
    content_equal = local_hash is not None and remote_hash is not None and local_hash == remote_hash
    same_version_different_content = (
        local_version is not None
        and remote_version is not None
        and compare_semver(local_version, remote_version) == 0
        and not content_equal
    )
    update_available = False
    missing_locally = False
    needs_publish = False
    publish_blocked = False
    publish_block_reason = None
    if remote_version is not None:
        if local_version is None:
            update_available = True
            missing_locally = True
        else:
            version_cmp = compare_semver(remote_version, local_version)
            update_available = version_cmp > 0
            needs_publish = version_cmp < 0
            publish_blocked = same_version_different_content
            if publish_blocked:
                publish_block_reason = "same_version_different_content"

    return {
        "type": instruction_type,
        "path": str(local_path),
        "localExists": local_exists,
        "localVersion": local_version,
        "localSha256": local_hash,
        "remotePresent": remote is not None,
        "remoteVersion": remote_version,
        "remoteSha256": remote_hash,
        "contentEqual": content_equal,
        "sameVersionDifferentContent": same_version_different_content,
        "missingLocally": missing_locally,
        "updateAvailable": update_available,
        "needsPublish": needs_publish,
        "publishBlocked": publish_blocked,
        "publishBlockReason": publish_block_reason,
    }


def fetch_remote_instructions(config: Config) -> dict[str, dict[str, Any]]:
    response = request_json(
        config,
        "GET",
        "/library/projects/agent-instructions",
        query={"projectSlug": config.project_slug, "libraryUserId": config.library_user_id},
    )
    remote_by_type: dict[str, dict[str, Any]] = {}
    for item in response:
        remote_by_type[item["type"]] = item
    return remote_by_type


def normalize_types(values: list[str] | None) -> list[str]:
    if not values:
        return list(INSTRUCTION_TYPES)
    return values


def extract_version(content: str, label: str) -> str:
    match = VERSION_PATTERN.search(content)
    if not match:
        raise ScriptError(f"Brakuje nagłówka # WERSJA w {label}.")
    return match.group(1)


def load_config(repo_root: Path) -> Config:
    raw_config = parse_simple_yaml(repo_root / ".agent-library.yaml")
    base_url = expect_string(raw_config, "libraryBaseUrl").rstrip("/")
    project_slug = expect_string(raw_config, "projectSlug")
    paths = expect_dict(raw_config, "paths")

    path_by_type = {
        "AGENTS": repo_root / expect_string(paths, "agents"),
        "CLAUDE": repo_root / expect_string(paths, "claude"),
        "GEMINI": repo_root / expect_string(paths, "gemini"),
    }

    return Config(
        base_url=base_url,
        project_slug=project_slug,
        library_user_id=load_required_library_user_id(),
        path_by_type=path_by_type,
    )


def request_json(
    config: Config,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = config.base_url + path
    if query:
        url += "?" + urllib.parse.urlencode(query)

    headers = {"Accept": "application/json"}

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_transient_error: str | None = None
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                response_bytes = response.read()
            break
        except urllib.error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            message = f"HTTP {exc.code} dla {path}: {extract_error_message(response_text)}"
            if exc.code in TRANSIENT_HTTP_STATUS_CODES and attempt < MAX_TRANSIENT_RETRIES:
                last_transient_error = message
                time.sleep(2**attempt)
                continue
            if last_transient_error is not None:
                message += f". Poprzedni błąd transient: {last_transient_error}"
            raise ScriptError(message) from exc
        except urllib.error.URLError as exc:
            raise ScriptError(f"Nie udało się połączyć z biblioteką: {exc.reason}") from exc
    else:
        raise ScriptError(f"Nie udało się połączyć z biblioteką po retry dla {path}.")

    if not response_bytes:
        return None
    return json.loads(response_bytes.decode("utf-8"))


def load_required_library_user_id() -> str:
    value = os.environ.get("TELEMETRY_USER_ID")
    if value is None or not value.strip():
        raise ScriptError("Brakuje TELEMETRY_USER_ID. Biblioteka wymaga przekazywania libraryUserId.")
    return value.strip()


def extract_error_message(payload: str) -> str:
    payload = payload.strip()
    if not payload:
        return "brak treści błędu"
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


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compare_semver(left: str, right: str) -> int:
    left_parts = parse_semver(left)
    right_parts = parse_semver(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ScriptError(f"Nieprawidlowa wersja semver: {value}")
    return tuple(int(part) for part in match.groups())


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


def expect_dict(values: dict[str, Any], key: str) -> dict[str, Any]:
    value = values.get(key)
    if not isinstance(value, dict):
        raise ScriptError(f"Brakuje sekcji {key} w .agent-library.yaml")
    return value


def expect_string(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ScriptError(f"Brakuje pola {key} w .agent-library.yaml")
    return value.strip()


def find_repo_root(start_path: Path) -> Path:
    current = start_path if start_path.is_dir() else start_path.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".agent-library.yaml").is_file():
            return candidate
    raise ScriptError("Nie znaleziono .agent-library.yaml")


if __name__ == "__main__":
    raise SystemExit(main())
