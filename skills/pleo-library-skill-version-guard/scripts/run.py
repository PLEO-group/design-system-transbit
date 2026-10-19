#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FRONTMATTER_FIELD_PATTERN = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
PARENT_PATH_PATTERN = re.compile(r"(^|/)\.\.(/|$)")
WINDOWS_INVALID_PATH_CHARACTER_PATTERN = re.compile(r'[<>:"|?*\x00-\x1f]')
WINDOWS_RESERVED_NAME_PATTERN = re.compile(
    r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$"
)
REQUEST_TIMEOUT_SECONDS = 5
TEXT_SUFFIXES = {".md", ".txt", ".yml", ".yaml", ".json", ".xml", ".java", ".js", ".ts", ".tsx", ".jsx", ".py", ".sh", ".properties", ".toml", ".ini", ".cfg", ".csv", ".sql", ".svg", ".html", ".css", ".rst", ".jsonl", ".ndjson", ".ps1"}


class ScriptError(RuntimeError):
    pass


class HttpScriptError(ScriptError):
    def __init__(self, status_code: int, path: str, response_text: str):
        self.status_code = status_code
        self.path = path
        self.response_text = response_text
        super().__init__(f"HTTP {status_code} dla {path}: {extract_error_message(response_text)}")


@dataclass(frozen=True)
class Config:
    repo_root: Path
    base_url: str
    project_slug: str | None
    skills_dir: Path
    library_user_id: str
    runtime_managed_skills: bool = False
    skill_snapshot_dir: Path | None = None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = resolve_repo_root(args.repo_root)
        config = load_config(repo_root)
        check = check_skill(config, args.skill)
        local_state = inspect_local_skill_state(config, args.skill)

        if args.command == "check" and check["needsPull"]:
            if local_state["clean"]:
                pull_result = pull_skill(config, args.skill)
                result = check_skill(config, args.skill)
                result["autoPull"] = {
                    "attempted": True,
                    "completed": True,
                    "pullResult": pull_result,
                }
            else:
                result = check
                result["autoPull"] = {
                    "attempted": False,
                    "completed": False,
                    "blockedReason": "local_changes",
                }
        elif args.command == "pull":
            if not local_state["clean"]:
                raise ScriptError(
                    f"Nie można zaktualizować skilla {args.skill}: jego katalog zawiera lokalne zmiany."
                )
            result = pull_skill(config, args.skill)
            result["autoPull"] = {"attempted": False, "completed": False}
        else:
            result = check
            result["autoPull"] = {
                "attempted": False,
                "completed": False,
                "blockedReason": None,
            }

        result["guardMode"] = "target-only"
        result["localStateBeforeUpdate"] = local_state
        target_updated = bool(
            result.get("changed")
            or result.get("autoPull", {}).get("pullResult", {}).get("changed")
        )
        result["projectSkillStateSync"] = sync_project_manifest_and_update_outdated(
            config,
            force=target_updated,
        )
    except ScriptError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sprawdza lub pobiera najnowszą wersję lokalnego skilla z biblioteki."
    )
    parser.add_argument("--repo-root", help="Ścieżka do katalogu repo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Sprawdz status wersji skilla.")
    check_parser.add_argument("--skill", required=True, help="Nazwa skilla z katalogu skills/.")

    pull_parser = subparsers.add_parser("pull", help="Pobierz i nadpisz lokalny katalog skilla.")
    pull_parser.add_argument("--skill", required=True, help="Nazwa skilla z katalogu skills/.")

    return parser


def check_skill(config: Config, skill_name: str) -> dict[str, Any]:
    skill_dir = resolve_skill_dir(config.skills_dir, skill_name)
    local_version = extract_version(skill_dir / "SKILL.md")
    latest = request_json(
        config,
        "GET",
        f"/skills/remote/{urllib.parse.quote(skill_name)}/latest",
        query=remote_project_query(config, {"currentVersion": local_version}),
        allow_status={404},
    )
    if latest is None:
        return {
            "skillName": skill_name,
            "localVersion": local_version,
            "remoteFound": False,
            "upToDate": True,
            "versionRelation": "missing_remote",
            "needsPull": False,
            "needsPublish": True,
        }
    latest_result = expect_json_object(latest, "odpowiedź latest skilla")
    latest_version = expect_semver_field(latest_result, "latestVersion", "odpowiedź latest skilla")
    version_cmp = compare_semver(local_version, latest_version)
    if version_cmp > 0:
        version_relation = "local_newer"
    elif version_cmp < 0:
        version_relation = "remote_newer"
    else:
        version_relation = "same"

    return {
        "skillName": skill_name,
        "localVersion": local_version,
        "remoteFound": True,
        "latestVersion": latest_version,
        "upToDate": version_cmp >= 0,
        "versionRelation": version_relation,
        "needsPull": version_cmp < 0,
        "needsPublish": version_cmp > 0,
    }


def inspect_local_skill_state(config: Config, skill_name: str) -> dict[str, Any]:
    skill_dir = resolve_skill_dir(config.skills_dir, skill_name)
    if config.runtime_managed_skills:
        return {"clean": True, "changes": [], "managedByRuntime": True}
    try:
        relative_skill_dir = skill_dir.resolve().relative_to(config.repo_root.resolve())
    except ValueError as exception:
        raise ScriptError(f"Katalog skilla znajduje się poza repozytorium: {skill_dir}") from exception

    try:
        completed = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                relative_skill_dir.as_posix(),
            ],
            cwd=config.repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exception:
        raise ScriptError(f"Nie udało się uruchomić Git podczas kontroli skilla: {exception}") from exception

    if completed.returncode != 0:
        error = completed.stderr.strip() or "nieznany błąd Git"
        raise ScriptError(f"Nie udało się sprawdzić lokalnych zmian skilla: {error}")

    changes = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        "clean": not changes,
        "changes": changes,
    }


def pull_skill(config: Config, skill_name: str) -> dict[str, Any]:
    skill_dir = resolve_skill_dir(config.skills_dir, skill_name)
    local_version = extract_version(skill_dir / "SKILL.md")
    result = expect_json_object(
        request_json(
            config,
            "POST",
            f"/skills/remote/{urllib.parse.quote(skill_name)}/pull",
            body=remote_project_query(config, {"currentVersion": local_version}),
        ),
        "odpowiedź pull skilla",
    )
    update_available = expect_boolean_field(result, "updateAvailable", "odpowiedź pull skilla")
    latest_version = expect_semver_field(result, "latestVersion", "odpowiedź pull skilla")

    if not update_available:
        return {
            "skillName": skill_name,
            "localVersion": local_version,
            "latestVersion": latest_version,
            "changed": False,
            "writtenFiles": [],
            "removedFiles": [],
            "updateStrategy": "none",
        }

    if not inspect_local_skill_state(config, skill_name)["clean"]:
        raise ScriptError(
            f"Przerwano aktualizację skilla {skill_name}: jego katalog zmienił się po rozpoczęciu checku."
        )

    written_files, removed_files, update_strategy, changed = rewrite_skill_directory(
        skill_dir,
        expect_json_array(result.get("files"), "pliki odpowiedzi pull skilla"),
        expected_version=latest_version,
    )
    snapshot_path = None
    snapshot_error = None
    try:
        snapshot_path = snapshot_skill_update(config, skill_name, latest_version)
    except Exception as exception:
        # Snapshot jest wyłącznie artefaktem późniejszej publikacji. Jego zapis nie może
        # unieważnić poprawnie zakończonej aktualizacji współdzielonego skilla.
        snapshot_error = str(exception)
    return {
        "skillName": skill_name,
        "localVersion": local_version,
        "latestVersion": latest_version,
        "changed": changed,
        "writtenFiles": written_files,
        "removedFiles": removed_files,
        "updateStrategy": update_strategy,
        "snapshotPath": str(snapshot_path) if snapshot_path is not None else None,
        "snapshotStatus": "FAILED" if snapshot_error else ("SAVED" if snapshot_path is not None else "SKIPPED"),
        "snapshotError": snapshot_error,
    }


def sync_project_manifest_and_update_outdated(config: Config, *, force: bool = False) -> dict[str, Any]:
    if not config.project_slug:
        return {"enabled": False, "reason": "missing_project_slug"}

    invalid_local_skills: list[dict[str, str]] = []
    installed_skills = collect_local_installed_skills(
        config,
        invalid_skills=invalid_local_skills,
    )
    status = project_skill_state_status(config)
    if (
        not force
        and status.get("freshToday") is True
        and status.get("installedSkillCount") == len(installed_skills)
    ):
        return {
            "enabled": True,
            "skipped": True,
            "reason": "manifest_verified_today",
            "projectSlug": config.project_slug,
            "installedSkillCount": len(installed_skills),
            "status": status,
            "invalidLocalSkills": invalid_local_skills,
            "outdatedDetected": [],
            "autoUpdatedSkills": [],
            "blockedSkills": [],
            "finalOutdatedInstalledProjectSkills": [],
        }

    detected: dict[str, dict[str, Any]] = {}
    updated: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    handled: set[str] = set()
    max_attempts = max(1, len(installed_skills) + 1)

    for _ in range(max_attempts):
        try:
            manifest = sync_project_manifest_once(config, installed_skills=installed_skills)
            candidates = expect_json_array(
                manifest.get("outdatedInstalledProjectSkills", []),
                "outdatedInstalledProjectSkills synchronizacji manifestu",
            )
        except HttpScriptError as exception:
            conflict = parse_downgrade_conflict(exception)
            if conflict is None:
                raise
            manifest = {"enabled": False, "syncConflict": conflict}
            candidates = [conflict]

        pending = []
        for candidate in candidates:
            item = expect_json_object(candidate, "wpis nieaktualnego skilla")
            skill_name = item.get("skillName")
            if not isinstance(skill_name, str) or not skill_name.strip():
                raise ScriptError("Wpis nieaktualnego skilla nie zawiera skillName")
            normalized_name = normalize_skill_name(skill_name.strip())
            detected[normalized_name] = item
            if normalized_name not in handled:
                pending.append(normalized_name)

        if not pending:
            return {
                "enabled": True,
                "projectSlug": config.project_slug,
                "invalidLocalSkills": invalid_local_skills,
                "outdatedDetected": list(detected.values()),
                "autoUpdatedSkills": updated,
                "blockedSkills": blocked,
                "finalOutdatedInstalledProjectSkills": candidates,
                "manifest": manifest,
            }

        changed_any = False
        for skill_name in pending:
            handled.add(skill_name)
            outcome = auto_update_outdated_skill(config, skill_name)
            if outcome["status"] == "updated":
                updated.append(outcome)
                changed_any = True
            else:
                blocked.append(outcome)

        if not changed_any:
            return {
                "enabled": True,
                "projectSlug": config.project_slug,
                "invalidLocalSkills": invalid_local_skills,
                "outdatedDetected": list(detected.values()),
                "autoUpdatedSkills": updated,
                "blockedSkills": blocked,
                "finalOutdatedInstalledProjectSkills": candidates,
                "manifest": manifest,
            }

        invalid_local_skills = []
        installed_skills = collect_local_installed_skills(
            config,
            invalid_skills=invalid_local_skills,
        )

    raise ScriptError("Nie udało się ustabilizować manifestu po automatycznych aktualizacjach skilli")


def project_skill_state_status(config: Config) -> dict[str, Any]:
    return expect_json_object(
        request_json(
            config,
            "GET",
            "/skills/remote/project-skill-state/status",
            query={
                "projectSlug": config.project_slug,
                "libraryUserId": config.library_user_id,
            },
        ),
        "status manifestu projektu",
    )


def auto_update_outdated_skill(config: Config, skill_name: str) -> dict[str, Any]:
    try:
        local_state = inspect_local_skill_state(config, skill_name)
        if not local_state["clean"]:
            return {
                "skillName": skill_name,
                "status": "blocked",
                "reason": "local_changes",
                "localState": local_state,
            }

        check = check_skill(config, skill_name)
        if not check["needsPull"]:
            return {
                "skillName": skill_name,
                "status": "skipped",
                "reason": "already_current",
                "check": check,
            }

        return {
            "skillName": skill_name,
            "status": "updated",
            "check": check,
            "pullResult": pull_skill(config, skill_name),
        }
    except ScriptError as exception:
        return {
            "skillName": skill_name,
            "status": "blocked",
            "reason": "update_error",
            "error": str(exception),
        }


def sync_project_manifest_once(
    config: Config,
    *,
    installed_skills: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return expect_json_object(
        request_json(
            config,
            "POST",
            "/skills/remote/project-skill-state/sync",
            body={
                "projectSlug": config.project_slug,
                "libraryUserId": config.library_user_id,
                "installedSkills": (
                    installed_skills
                    if installed_skills is not None
                    else collect_local_installed_skills(config)
                ),
            },
        ),
        "odpowiedź synchronizacji manifestu projektu",
    )


def collect_local_installed_skills(
    config: Config,
    *,
    invalid_skills: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    installed = []
    for skill_dir in sorted(config.skills_dir.iterdir(), key=lambda path: path.name.lower()):
        skill_md = skill_dir / "SKILL.md"
        if skill_dir.is_dir() and not skill_dir.name.startswith(".") and skill_md.is_file():
            try:
                installed_version = extract_version(skill_md)
            except ScriptError as exception:
                if invalid_skills is not None:
                    invalid_skills.append({
                        "skillName": skill_dir.name,
                        "reason": "invalid_skill_metadata",
                        "error": str(exception),
                    })
                continue
            installed.append({
                "skillName": skill_dir.name,
                "installedVersion": installed_version,
            })
    return installed


def parse_downgrade_conflict(exception: HttpScriptError) -> dict[str, Any] | None:
    if exception.status_code != 409 or exception.path != "/skills/remote/project-skill-state/sync":
        return None
    try:
        payload = json.loads(exception.response_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("reasonCode") != "DOWNGRADE_ATTEMPT":
        return None
    skill_name = payload.get("skillName")
    if not isinstance(skill_name, str) or not skill_name.strip():
        return None
    return {
        "skillName": skill_name.strip(),
        "installedVersion": payload.get("incomingVersion"),
        "latestVersion": payload.get("storedVersion"),
        "reasonCode": "DOWNGRADE_ATTEMPT",
    }


def rewrite_skill_directory(
    skill_dir: Path,
    files: list[dict[str, Any]],
    *,
    expected_version: str,
) -> tuple[list[str], list[str], str, bool]:
    if not isinstance(files, list) or not files:
        raise ScriptError("Payload aktualizacji skilla nie zawiera plików")
    if not isinstance(expected_version, str):
        raise ScriptError("Payload aktualizacji skilla nie zawiera poprawnej latestVersion")
    parse_semver(expected_version)

    normalized_files: list[tuple[str, bytes]] = []
    expected_paths_by_portable_name: dict[str, str] = {}
    for file_payload in files:
        if not isinstance(file_payload, dict):
            raise ScriptError("Nieprawidłowy wpis pliku w payloadzie")
        raw_path = file_payload.get("relativePath")
        encoded_content = file_payload.get("contentBase64")
        if not isinstance(raw_path, str) or not isinstance(encoded_content, str):
            raise ScriptError("Plik w payloadzie wymaga tekstowych relativePath i contentBase64")

        relative_path = normalize_relative_path(raw_path)
        if is_python_cache(relative_path):
            continue
        portable_name = unicodedata.normalize("NFC", relative_path).casefold()
        previous_path = expected_paths_by_portable_name.get(portable_name)
        if previous_path is not None:
            raise ScriptError(
                f"Duplikat lub nieprzenośna kolizja pliku w payloadzie: {previous_path} / {relative_path}"
            )
        expected_paths_by_portable_name[portable_name] = relative_path
        content = decode_file_content(relative_path, encoded_content)
        validate_text_encoding(relative_path, file_payload.get("mimeType"), content)
        normalized_files.append((relative_path, content))

    expected_paths = set(expected_paths_by_portable_name.values())
    if "SKILL.md" not in expected_paths:
        raise ScriptError("Payload aktualizacji skilla nie zawiera kanonicznego pliku SKILL.md")

    current_skill_md = skill_dir / "SKILL.md"
    if current_skill_md.is_file():
        current_version = extract_version(current_skill_md)
        if compare_semver(current_version, expected_version) >= 0:
            return [], [], "already-current", False
    written_files = [relative_path for relative_path, _ in normalized_files]
    removed_files = collect_removed_files(skill_dir, expected_paths)
    staged_skill_dir = stage_skill_directory(skill_dir, normalized_files)
    try:
        validate_staged_skill_directory(staged_skill_dir, skill_dir.name, expected_version)
        update_strategy = swap_in_staged_skill_directory(skill_dir, staged_skill_dir)
    except Exception:
        if staged_skill_dir.exists():
            shutil.rmtree(staged_skill_dir, ignore_errors=True)
        raise
    return written_files, removed_files, update_strategy, True


def snapshot_skill_update(config: Config, skill_name: str, expected_version: str) -> Path | None:
    snapshot_root = config.skill_snapshot_dir
    if snapshot_root is None:
        return None
    skill_dir = resolve_skill_dir(config.skills_dir, skill_name)
    installed_version = extract_version(skill_dir / "SKILL.md")
    if compare_semver(installed_version, expected_version) < 0:
        raise ScriptError(
            f"Nie można zapisać snapshotu skilla {skill_name}: zainstalowana wersja {installed_version} "
            f"jest starsza od oczekiwanej wersji aktualizacji {expected_version}."
        )
    snapshot_root.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{skill_name}.snapshot-", dir=str(snapshot_root)))
    target = snapshot_root / skill_name
    backup = snapshot_root / f".{skill_name}.backup-{uuid.uuid4().hex}"
    try:
        shutil.copytree(skill_dir, staged, dirs_exist_ok=True)
        ensure_directory_contains_no_symlinks(staged)
        if target.exists():
            target.rename(backup)
        staged.rename(target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    return target


def decode_file_content(relative_path: str, encoded_content: str) -> bytes:
    try:
        return base64.b64decode(encoded_content, validate=True)
    except (binascii.Error, ValueError) as exception:
        raise ScriptError(f"Nieprawidłowy Base64 dla pliku: {relative_path}") from exception


def is_python_cache(relative_path: str) -> bool:
    parts = relative_path.replace("\\", "/").lower().split("/")
    return "__pycache__" in parts or parts[-1].endswith((".pyc", ".pyo"))


def validate_text_encoding(relative_path: str, mime_type: str | None, content: bytes) -> None:
    lower_path = relative_path.lower()
    lower_mime = (mime_type or "").lower()
    if not (Path(lower_path).suffix in TEXT_SUFFIXES or lower_path.endswith(".gitignore")
            or lower_mime.startswith("text/") or any(kind in lower_mime for kind in ("json", "xml", "yaml", "javascript"))):
        return
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise ScriptError(f"Plik tekstowy musi być zapisany w UTF-8: {relative_path}") from exception
    if "\x00" in text:
        raise ScriptError(f"Plik tekstowy zawiera bajt NUL: {relative_path}")


def validate_staged_skill_directory(staged_skill_dir: Path, expected_name: str, expected_version: str) -> None:
    skill_md_path = staged_skill_dir / "SKILL.md"
    try:
        skill_md_content = skill_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exception:
        raise ScriptError(f"Nie udało się odczytać SKILL.md ze stagingu: {skill_md_path}") from exception
    actual_name = extract_frontmatter_field(skill_md_content, "name")
    if actual_name != expected_name:
        raise ScriptError(
            f"Nazwa skilla w SKILL.md nie odpowiada katalogowi docelowemu: "
            f"expected={expected_name}; actual={actual_name or 'missing'}"
        )
    actual_version = extract_version(skill_md_path)
    if compare_semver(actual_version, expected_version) != 0:
        raise ScriptError(
            f"Wersja skilla w SKILL.md nie odpowiada latestVersion payloadu: "
            f"expected={expected_version}; actual={actual_version}"
        )


def collect_removed_files(skill_dir: Path, expected_paths: set[str]) -> list[str]:
    removed_files: list[str] = []
    if not skill_dir.exists():
        return removed_files

    for existing_file in skill_dir.rglob("*"):
        if not existing_file.is_file():
            continue
        relative_path = existing_file.relative_to(skill_dir).as_posix()
        if relative_path not in expected_paths:
            removed_files.append(relative_path)
    removed_files.sort()
    return removed_files


def stage_skill_directory(skill_dir: Path, normalized_files: list[tuple[str, bytes]]) -> Path:
    skill_dir.parent.mkdir(parents=True, exist_ok=True)
    staged_dir = Path(tempfile.mkdtemp(prefix=f".{skill_dir.name}.tmp-", dir=str(skill_dir.parent)))
    try:
        for relative_path, content in normalized_files:
            target_path = staged_dir / Path(relative_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            ensure_resolved_path_within_directory(staged_dir, target_path.parent)
            target_path.write_bytes(content)
    except Exception:
        shutil.rmtree(staged_dir, ignore_errors=True)
        raise
    return staged_dir


def swap_in_staged_skill_directory(skill_dir: Path, staged_skill_dir: Path) -> str:
    backup_dir: Path | None = None
    update_completed = False
    try:
        if skill_dir.exists():
            backup_dir = skill_dir.parent / f".{skill_dir.name}.bak-{uuid.uuid4().hex}"
            try:
                skill_dir.rename(backup_dir)
            except OSError as atomic_error:
                update_strategy = replace_locked_skill_directory_in_place(skill_dir, staged_skill_dir, atomic_error)
                update_completed = True
                return update_strategy
        try:
            staged_skill_dir.rename(skill_dir)
            update_completed = True
            return "atomic"
        except OSError as atomic_error:
            if backup_dir is None or not backup_dir.exists() or skill_dir.exists():
                raise
            update_strategy = replace_skill_directory_in_place(
                skill_dir, staged_skill_dir, backup_dir, atomic_error
            )
            update_completed = True
            return update_strategy
    except ScriptError:
        if staged_skill_dir.exists():
            shutil.rmtree(staged_skill_dir, ignore_errors=True)
        raise
    except Exception as exc:
        if backup_dir is not None and backup_dir.exists() and not skill_dir.exists():
            backup_dir.rename(skill_dir)
        if staged_skill_dir.exists():
            shutil.rmtree(staged_skill_dir, ignore_errors=True)
        raise ScriptError(f"Nie udało się atomowo zaktualizować katalogu skilla: {skill_dir}") from exc
    finally:
        if update_completed and backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def replace_locked_skill_directory_in_place(
    skill_dir: Path,
    staged_skill_dir: Path,
    atomic_error: OSError,
) -> str:
    ensure_directory_contains_no_symlinks(skill_dir)
    rollback_dir = skill_dir.parent / f".{skill_dir.name}.rollback-{uuid.uuid4().hex}"
    rollback_ready = False
    cleanup_rollback = False
    try:
        shutil.copytree(skill_dir, rollback_dir)
        rollback_ready = True
        synchronize_skill_directory(staged_skill_dir, skill_dir)
        verify_skill_directory(staged_skill_dir, skill_dir)
        shutil.rmtree(staged_skill_dir)
        cleanup_rollback = True
        return "verified_in_place_fallback"
    except Exception as fallback_error:
        if not rollback_ready:
            cleanup_rollback = True
            raise ScriptError(
                "Nie udało się utworzyć kopii rollbackowej zablokowanego katalogu skilla; "
                f"katalog źródłowy pozostał bez zmian: {skill_dir}; atomic={atomic_error}; "
                f"fallback={fallback_error}; rollback=not_created"
            ) from fallback_error
        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            synchronize_skill_directory(rollback_dir, skill_dir)
            verify_skill_directory(rollback_dir, skill_dir)
            cleanup_rollback = True
        except Exception as rollback_error:
            raise ScriptError(
                "Nie udało się zaktualizować zablokowanego katalogu skilla ani odtworzyć kopii zapasowej: "
                f"{skill_dir}; atomic={atomic_error}; fallback={fallback_error}; rollback={rollback_error}; "
                f"recoveryCopy={rollback_dir}"
            ) from rollback_error
        raise ScriptError(
            "Nie udało się zaktualizować zablokowanego katalogu skilla przez zweryfikowany fallback: "
            f"{skill_dir}; atomic={atomic_error}; fallback={fallback_error}"
        ) from fallback_error
    finally:
        if cleanup_rollback and rollback_dir.exists():
            shutil.rmtree(rollback_dir, ignore_errors=True)


def replace_skill_directory_in_place(
    skill_dir: Path,
    staged_skill_dir: Path,
    backup_dir: Path,
    atomic_error: OSError,
) -> str:
    rollback_dir = skill_dir.parent / f".{skill_dir.name}.rollback-{uuid.uuid4().hex}"
    cleanup_rollback = False
    try:
        ensure_directory_contains_no_symlinks(backup_dir)
        shutil.copytree(backup_dir, rollback_dir)
        backup_dir.rename(skill_dir)
        synchronize_skill_directory(staged_skill_dir, skill_dir)
        verify_skill_directory(staged_skill_dir, skill_dir)
        shutil.rmtree(staged_skill_dir)
        cleanup_rollback = True
        return "verified_in_place_fallback"
    except Exception as fallback_error:
        try:
            if not skill_dir.exists() and backup_dir.exists():
                backup_dir.rename(skill_dir)
            elif rollback_dir.exists():
                skill_dir.mkdir(parents=True, exist_ok=True)
                synchronize_skill_directory(rollback_dir, skill_dir)
                verify_skill_directory(rollback_dir, skill_dir)
            cleanup_rollback = True
        except Exception as rollback_error:
            raise ScriptError(
                "Nie udało się zaktualizować katalogu skilla ani odtworzyć kopii zapasowej: "
                f"{skill_dir}; atomic={atomic_error}; fallback={fallback_error}; rollback={rollback_error}; "
                f"backup={backup_dir}; recoveryCopy={rollback_dir}"
            ) from rollback_error
        raise ScriptError(
            "Nie udało się zaktualizować katalogu skilla przez zweryfikowany fallback: "
            f"{skill_dir}; atomic={atomic_error}; fallback={fallback_error}"
        ) from fallback_error
    finally:
        if cleanup_rollback and rollback_dir.exists():
            shutil.rmtree(rollback_dir, ignore_errors=True)


def synchronize_skill_directory(source_dir: Path, target_dir: Path) -> None:
    ensure_directory_contains_no_symlinks(source_dir)
    ensure_directory_contains_no_symlinks(target_dir)
    expected_files = {
        source_file.relative_to(source_dir).as_posix()
        for source_file in source_dir.rglob("*")
        if source_file.is_file()
    }
    target_dir.mkdir(parents=True, exist_ok=True)

    for relative_path in sorted(expected_files):
        source_file = source_dir / Path(relative_path)
        target_file = target_dir / Path(relative_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        ensure_resolved_path_within_directory(target_dir, target_file.parent)
        temporary_file = target_file.parent / f".{target_file.name}.tmp-{uuid.uuid4().hex}"
        try:
            shutil.copy2(source_file, temporary_file)
            temporary_file.replace(target_file)
        finally:
            temporary_file.unlink(missing_ok=True)

    for existing_file in list(target_dir.rglob("*")):
        if not existing_file.is_file():
            continue
        relative_path = existing_file.relative_to(target_dir).as_posix()
        if relative_path not in expected_files:
            existing_file.unlink()

    cleanup_empty_directories(target_dir)


def verify_skill_directory(source_dir: Path, target_dir: Path) -> None:
    ensure_directory_contains_no_symlinks(source_dir)
    ensure_directory_contains_no_symlinks(target_dir)
    source_files = {
        source_file.relative_to(source_dir).as_posix(): source_file
        for source_file in source_dir.rglob("*")
        if source_file.is_file()
    }
    target_files = {
        target_file.relative_to(target_dir).as_posix(): target_file
        for target_file in target_dir.rglob("*")
        if target_file.is_file()
    }
    if source_files.keys() != target_files.keys():
        raise ScriptError(f"Weryfikacja listy plików po aktualizacji nie powiodła się: {target_dir}")

    for relative_path, source_file in source_files.items():
        if source_file.read_bytes() != target_files[relative_path].read_bytes():
            raise ScriptError(f"Weryfikacja zawartości pliku po aktualizacji nie powiodła się: {relative_path}")


def ensure_directory_contains_no_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise ScriptError(f"Katalog skilla nie może być symlinkiem podczas fallbacku: {root}")
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ScriptError(f"Fallback aktualizacji nie obsługuje symlinków w katalogu skilla: {path}")
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError as exception:
            raise ScriptError(
                f"Fallback aktualizacji wykrył ścieżkę wychodzącą poza katalog skilla: {path}"
            ) from exception


def ensure_resolved_path_within_directory(root: Path, candidate: Path) -> None:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exception:
        raise ScriptError(f"Ścieżka docelowa wychodzi poza katalog skilla: {candidate}") from exception


def cleanup_empty_directories(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    directories.sort(key=lambda path: len(path.parts), reverse=True)
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            continue


def load_config(repo_root: Path) -> Config:
    raw_config = parse_simple_yaml(repo_root / ".agent-library.yaml")
    base_url = expect_string(raw_config, "libraryBaseUrl").rstrip("/")
    project_slug = raw_config.get("projectSlug")
    raw_runtime_workspace = os.environ.get("PLEO_ASTREA_WORKSPACE_ROOT")
    runtime_workspace = (
        Path(raw_runtime_workspace).resolve()
        if raw_runtime_workspace
        else None
    )
    is_runtime_workspace = runtime_workspace == repo_root.resolve()
    paths = raw_config.get("paths")
    if isinstance(paths, dict):
        skills_dir = repo_root / expect_string(paths, "skillsDir")
    elif is_runtime_workspace:
        skills_dir = repo_root / "skills"
    else:
        raise ScriptError("Brakuje sekcji paths w .agent-library.yaml")
    runtime_managed_skills = raw_config.get("runtimeManagedSkills") is True or is_runtime_workspace
    if runtime_managed_skills and is_runtime_workspace:
        skills_dir = materialize_runtime_skill_overlay(repo_root, skills_dir)
    raw_snapshot_dir = os.environ.get("PLEO_ASTREA_SKILL_SNAPSHOT_DIR")
    return Config(
        repo_root=repo_root,
        base_url=base_url,
        project_slug=project_slug.strip() if isinstance(project_slug, str) and project_slug.strip() else None,
        skills_dir=skills_dir,
        library_user_id=load_required_library_user_id(),
        runtime_managed_skills=runtime_managed_skills,
        skill_snapshot_dir=Path(raw_snapshot_dir).resolve() if raw_snapshot_dir else None,
    )


def materialize_runtime_skill_overlay(workspace_root: Path, configured_skills_dir: Path) -> Path:
    local_skills_dir = workspace_root / "skills"
    if local_skills_dir.is_dir() and not local_skills_dir.is_symlink():
        return local_skills_dir

    if local_skills_dir.is_symlink():
        source_skills_dir = local_skills_dir.resolve()
    else:
        source_skills_dir = configured_skills_dir.resolve()
    if not source_skills_dir.is_dir():
        raise ScriptError(
            f"Nie można przygotować task-localnych skilli Astrei: brak katalogu źródłowego {source_skills_dir}"
        )

    staged_skills_dir = workspace_root / f".skills-overlay-{uuid.uuid4().hex}"
    previous_skills_link = workspace_root / f".skills-shared-link-{uuid.uuid4().hex}"
    overlay_installed = False
    try:
        shutil.copytree(
            source_skills_dir,
            staged_skills_dir,
            symlinks=False,
            ignore=shutil.ignore_patterns(
                ".*.update.lock",
                ".*.tmp-*",
                ".*.bak-*",
                ".*.rollback-*",
            ),
        )
        if not any(
            candidate.is_dir() and (candidate / "SKILL.md").is_file()
            for candidate in staged_skills_dir.iterdir()
        ):
            raise ScriptError(
                f"Katalog źródłowy {source_skills_dir} nie zawiera żadnego poprawnego skilla"
            )
        ensure_directory_contains_no_symlinks(staged_skills_dir)

        if local_skills_dir.is_symlink():
            local_skills_dir.rename(previous_skills_link)
        elif local_skills_dir.exists():
            raise ScriptError(
                f"Ścieżka task-localnych skilli nie jest katalogiem ani symlinkiem: {local_skills_dir}"
            )
        staged_skills_dir.rename(local_skills_dir)
        overlay_installed = True
    except Exception:
        if staged_skills_dir.exists():
            shutil.rmtree(staged_skills_dir, ignore_errors=True)
        if previous_skills_link.is_symlink() and not local_skills_dir.exists():
            previous_skills_link.rename(local_skills_dir)
        raise
    finally:
        if overlay_installed and previous_skills_link.is_symlink():
            previous_skills_link.unlink()
    return local_skills_dir


def resolve_repo_root(explicit_repo_root: str | None) -> Path:
    if explicit_repo_root:
        return find_repo_root(Path(explicit_repo_root))
    workspace_root = os.environ.get("PLEO_ASTREA_WORKSPACE_ROOT")
    if workspace_root:
        return find_repo_root(Path(workspace_root))
    try:
        return find_repo_root(Path.cwd())
    except ScriptError:
        return find_repo_root(Path(__file__).resolve())


def request_json(
    config: Config,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    allow_status: set[int] | None = None,
) -> Any:
    url = config.base_url + path
    if query:
        url += "?" + urllib.parse.urlencode(query)

    headers = {"Accept": "application/json"}

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response_bytes = response.read()
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        if allow_status and exc.code in allow_status:
            return None
        raise HttpScriptError(exc.code, path, response_text) from exc
    except urllib.error.URLError as exc:
        raise ScriptError(f"Nie udało się połączyć z biblioteką: {exc.reason}") from exc

    if not response_bytes:
        return None
    try:
        return json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exception:
        raise ScriptError(f"Biblioteka zwróciła nieprawidłowy JSON dla {path}") from exception


def expect_json_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScriptError(f"{context} musi być obiektem JSON")
    return value


def expect_json_array(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ScriptError(f"{context} musi być tablicą JSON")
    return value


def expect_boolean_field(value: dict[str, Any], field_name: str, context: str) -> bool:
    field_value = value.get(field_name)
    if not isinstance(field_value, bool):
        raise ScriptError(f"{context} wymaga boolean {field_name}")
    return field_value


def expect_semver_field(value: dict[str, Any], field_name: str, context: str) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str):
        raise ScriptError(f"{context} wymaga tekstowego {field_name}")
    parse_semver(field_value)
    return field_value


def extract_error_message(payload: str) -> str:
    payload = payload.strip()
    if not payload:
        return "brak treści błędu"
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(parsed, dict):
        for key in ("message", "reason", "detail", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return payload


def resolve_skill_dir(skills_dir: Path, skill_name: str) -> Path:
    normalized_skill_name = normalize_skill_name(skill_name)
    skill_dir = skills_dir / normalized_skill_name
    if not skill_dir.is_dir():
        raise ScriptError(f"Nie znaleziono katalogu skilla: {skill_dir}")
    return skill_dir


def normalize_skill_name(skill_name: str) -> str:
    if not isinstance(skill_name, str):
        raise ScriptError("Nazwa skilla musi być tekstem")
    normalized_name = normalize_relative_path(skill_name)
    if "/" in normalized_name or normalized_name.startswith(".") or normalized_name != skill_name:
        raise ScriptError(f"Nieprawidłowa nazwa skilla: {skill_name!r}")
    return normalized_name


def extract_version(skill_md_path: Path) -> str:
    if not skill_md_path.is_file():
        raise ScriptError(f"Brakuje pliku SKILL.md: {skill_md_path}")
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exception:
        raise ScriptError(f"Nie udało się odczytać SKILL.md jako UTF-8: {skill_md_path}") from exception
    frontmatter_version = extract_frontmatter_field(content, "version")
    if frontmatter_version is None:
        raise ScriptError(f"Brakuje frontmatter version w {skill_md_path}")
    parse_semver(frontmatter_version)
    return frontmatter_version


def extract_frontmatter_field(content: str, field_name: str) -> str | None:
    frontmatter_match = FRONTMATTER_PATTERN.match(content)
    if not frontmatter_match:
        return None
    for match in FRONTMATTER_FIELD_PATTERN.finditer(frontmatter_match.group(1)):
        if match.group(1).strip().lower() != field_name.lower():
            continue
        value = match.group(2).strip().strip("\"'")
        return value or None
    return None


def normalize_relative_path(raw_path: str) -> str:
    if raw_path != raw_path.strip():
        raise ScriptError(f"Ścieżka nie może zawierać skrajnych białych znaków: {raw_path!r}")
    normalized = raw_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.endswith("/"):
        raise ScriptError("Pusta ścieżka w payloadzie")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or PARENT_PATH_PATTERN.search(normalized)
    ):
        raise ScriptError(f"Nieprawidłowa ścieżka w payloadzie: {raw_path}")
    canonical_path = posix_path.as_posix()
    if canonical_path in ("", "."):
        raise ScriptError(f"Nieprawidłowa ścieżka w payloadzie: {raw_path}")
    for path_segment in posix_path.parts:
        if (
            WINDOWS_INVALID_PATH_CHARACTER_PATTERN.search(path_segment)
            or path_segment.endswith((" ", "."))
            or WINDOWS_RESERVED_NAME_PATTERN.fullmatch(path_segment)
        ):
            raise ScriptError(f"Ścieżka nie jest przenośna na Windows: {raw_path}")
    return canonical_path


def compare_semver(left: str, right: str) -> int:
    left_parts = parse_semver(left)
    right_parts = parse_semver(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ScriptError(f"Nieprawidłowa wersja semver: {value}")
    return tuple(int(part) for part in match.groups())


def remote_project_query(config: Config, payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["libraryUserId"] = config.library_user_id
    if config.project_slug:
        enriched["projectSlug"] = config.project_slug
    return enriched


def load_required_library_user_id() -> str:
    value = os.environ.get("TELEMETRY_USER_ID")
    if value is None or not value.strip():
        raise ScriptError("Brakuje TELEMETRY_USER_ID. Biblioteka wymaga przekazywania libraryUserId.")
    return value.strip()


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
