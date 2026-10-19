#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
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

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LEGACY_VERSION_PATTERN = re.compile(r"(?im)^#\s*WERSJA\s+\d+\.\d+\.\d+\s*$")
LEGACY_AUTHOR_PATTERN = re.compile(r"(?im)^#\s*AUTOR\s+[^\r\n]+?\s*$")
FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FRONTMATTER_FIELD_PATTERN = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
FRONTMATTER_LIST_ITEM_PATTERN = re.compile(r"(?m)^\s*-\s*(.*?)\s*$")
PLEO_LIBRARY_SKILL_PREFIX = "pleo-library-"
TRANSIENT_HTTP_STATUS_CODES = {502, 503, 504}
MAX_TRANSIENT_RETRIES = 2
TEXT_SUFFIXES = {".md", ".txt", ".yml", ".yaml", ".json", ".xml", ".java", ".js", ".ts", ".tsx", ".jsx", ".py", ".sh", ".properties", ".toml", ".ini", ".cfg", ".csv", ".sql", ".svg", ".html", ".css", ".rst", ".jsonl", ".ndjson", ".ps1"}


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    base_url: str
    project_slug: str | None
    skills_dir: Path
    default_scope: str | None
    library_user_id: str


@dataclass(frozen=True)
class LocalFile:
    relative_path: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class LocalSkill:
    name: str
    declared_version: str
    declared_author: str
    category: str | None
    tags: list[str]
    scope: str | None
    files: list[LocalFile]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root(Path(args.repo_root) if args.repo_root else Path(__file__).resolve())
        config = load_config(repo_root)
        if args.command == "publish":
            result = publish_skill(
                config=config,
                skill_name=args.skill,
                category=args.category,
                scope=args.scope,
                project_slug=args.project_slug,
                changelog_md=read_optional_text(args.changelog_file),
            )
        elif args.command == "publish-all":
            result = publish_all(
                config=config,
                shared_prefixes=args.shared_skill_prefix or [],
                changelog_md=read_optional_text(args.changelog_file),
            )
        elif args.command in {"audit", "publish-audit"}:
            result = audit_publication_state(
                config=config,
                excluded_skills=args.exclude_skill or [],
            )
        elif args.command == "migrate-project-to-shared":
            result = migrate_project_to_shared(
                config=config,
                skill_name=args.skill,
                category=args.category,
                project_slug=args.project_slug,
                changelog_md=read_optional_text(args.changelog_file),
            )
        elif args.command == "categories":
            result = {
                "availableCategories": fetch_shared_skill_categories(config),
            }
        elif args.command == "rename":
            result = rename_skill(config, args.skill, args.new_skill_name, args.project_slug)
        elif args.command == "delete":
            result = delete_skill(config, args.skill, args.project_slug)
        else:
            raise ScriptError(f"Nieznana komenda: {args.command}")
    except ScriptError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publikuje lokalny skill lub wszystkie skille z repo do biblioteki."
    )
    parser.add_argument("--repo-root", help="Ścieżka do katalogu repo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish_parser = subparsers.add_parser("publish", help="Opublikuj pojedynczy skill.")
    publish_parser.add_argument("--skill", required=True, help="Nazwa katalogu skilla.")
    publish_parser.add_argument("--category", help="Kategoria dla nowego skilla SHARED.")
    publish_parser.add_argument("--scope", choices=["SHARED", "PROJECT"], help="Scope skilla.")
    publish_parser.add_argument(
        "--project-slug",
        help="Slug projektu dla skilla PROJECT albo slug repo wydawcy dla skilli pleo-library-*.",
    )
    publish_parser.add_argument("--changelog-file", help="Plik z changelogiem markdown.")

    publish_all_parser = subparsers.add_parser("publish-all", help="Opublikuj wszystkie katalogi z skills/.")
    publish_all_parser.add_argument(
        "--shared-skill-prefix",
        action="append",
        help="Kazdy skill z takim prefiksem zostanie opublikowany jako SHARED.",
    )
    publish_all_parser.add_argument("--changelog-file", help="Plik z changelogiem markdown.")

    for audit_command in ("audit", "publish-audit"):
        audit_parser = subparsers.add_parser(audit_command, help="Porównaj lokalne skille z biblioteką bez zapisu.")
        audit_parser.add_argument(
            "--exclude-skill",
            action="append",
            help="Nazwa lokalnego skilla do pominięcia w audycie. Można podać wiele razy.",
        )

    migrate_parser = subparsers.add_parser(
        "migrate-project-to-shared",
        help="Przenieś skill z wpisu PROJECT na SHARED: usuń wpis projektowy i opublikuj SHARED.",
    )
    migrate_parser.add_argument("--skill", required=True, help="Nazwa katalogu skilla.")
    migrate_parser.add_argument("--category", required=True, help="Kategoria docelowa SHARED.")
    migrate_parser.add_argument("--project-slug", help="Slug projektu źródłowego. Domyślnie z .agent-library.yaml.")
    migrate_parser.add_argument("--changelog-file", help="Plik z changelogiem markdown.")

    subparsers.add_parser("categories", help="Pobierz listę dostępnych kategorii shared skilli.")

    rename_parser = subparsers.add_parser("rename", help="Zmien nazwe skilla w bibliotece.")
    rename_parser.add_argument("--skill", required=True, help="Aktualna nazwa skilla.")
    rename_parser.add_argument("--new-skill-name", required=True, help="Nowa nazwa skilla.")
    rename_parser.add_argument("--project-slug", help="Slug projektu dla skilla PROJECT albo repo wydawcy.")

    delete_parser = subparsers.add_parser("delete", help="Usun skill z biblioteki.")
    delete_parser.add_argument("--skill", required=True, help="Nazwa skilla do usuniecia.")
    delete_parser.add_argument("--project-slug", help="Slug projektu dla skilla PROJECT albo repo wydawcy.")

    return parser


def publish_all(config: Config, shared_prefixes: list[str], changelog_md: str | None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for skill_dir in sorted(path for path in config.skills_dir.iterdir() if path.is_dir()):
        local_skill = load_local_skill(config.skills_dir, skill_dir.name)
        scope = local_skill.scope or ("SHARED" if any(skill_dir.name.startswith(prefix) for prefix in shared_prefixes)
                                      else config.default_scope)
        project_slug = config.project_slug if scope == "PROJECT" else None
        results.append(
            publish_skill(
                config=config,
                skill_name=skill_dir.name,
                category=None,
                scope=scope,
                project_slug=project_slug,
                changelog_md=changelog_md,
            )
        )

    return {
        "action": "publish-all",
        "skillCount": len(results),
        "results": results,
    }


def audit_publication_state(config: Config, excluded_skills: list[str]) -> dict[str, Any]:
    excluded = {skill.strip().lower() for skill in excluded_skills if skill.strip()}
    shared_by_name = fetch_shared_skill_index(config)
    results: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    local_newer: list[dict[str, Any]] = []
    remote_newer: list[dict[str, Any]] = []
    same_version: list[dict[str, Any]] = []
    publish_blocked: list[dict[str, Any]] = []
    publish_requires_library_permission: list[dict[str, Any]] = []

    for skill_dir in sorted(path for path in config.skills_dir.iterdir() if path.is_dir()):
        if skill_dir.name.lower() in excluded:
            continue
        local_skill = load_local_skill(config.skills_dir, skill_dir.name)
        target_scope = local_skill.scope or config.default_scope
        remote_project_slug = (config.project_slug if target_scope == "PROJECT"
                               or is_reserved_library_skill_name(local_skill.name) else None)
        remote_latest = request_json(
            config,
            "GET",
            f"/skills/remote/{urllib.parse.quote(local_skill.name)}/latest",
            query=build_remote_project_query(remote_project_slug, {"currentVersion": local_skill.declared_version}),
            allow_status={404},
        )
        shared_meta = shared_by_name.get(local_skill.name.lower())
        remote_scope = "SHARED" if shared_meta is not None else (target_scope if remote_latest is not None else None)
        if remote_latest is None and target_scope == "SHARED" and config.project_slug is not None and shared_meta is None:
            project_match = request_json(
                config,
                "GET",
                f"/skills/remote/{urllib.parse.quote(local_skill.name)}/latest",
                query=build_remote_project_query(config.project_slug),
                allow_status={404},
            )
            if project_match is not None:
                remote_scope = "PROJECT"
        remote_category = shared_meta.get("category") if shared_meta else None
        requires_library_permission = is_reserved_library_skill_name(local_skill.name)
        item = {
            "skillName": local_skill.name,
            "localVersion": local_skill.declared_version,
            "remoteFound": remote_latest is not None,
            "latestVersion": remote_latest.get("latestVersion") if remote_latest else None,
            "remoteScope": remote_scope,
            "remoteCategory": remote_category,
            "versionRelation": "missing_remote",
            "needsPublish": False,
            "needsPull": False,
            "requiresLibraryPermission": requires_library_permission,
            "publishRisk": None,
            "publishBlockedReason": None,
        }
        if remote_latest is None:
            item["needsPublish"] = True
            if requires_library_permission:
                item["publishRisk"] = "reserved_prefix_requires_library_permissions"
                publish_requires_library_permission.append(item)
            missing.append(item)
        else:
            version_cmp = compare_semver(local_skill.declared_version, remote_latest["latestVersion"])
            if version_cmp > 0:
                item["versionRelation"] = "local_newer"
                item["needsPublish"] = True
                if requires_library_permission:
                    item["publishRisk"] = "reserved_prefix_requires_library_permissions"
                    publish_requires_library_permission.append(item)
                local_newer.append(item)
            elif version_cmp < 0:
                item["versionRelation"] = "remote_newer"
                item["needsPull"] = True
                remote_newer.append(item)
            else:
                item["versionRelation"] = "same"
                same_version.append(item)
                remote_version = fetch_remote_version(config, local_skill.name, remote_latest["latestVersion"], remote_project_slug)
                if not has_same_payload(local_skill.files, remote_version["files"]):
                    item["needsPublish"] = True
                    item["publishBlockedReason"] = "same_version_different_payload"
        if target_scope not in {"SHARED", "PROJECT"}:
            item["publishBlockedReason"] = "missing_or_invalid_scope"
        elif target_scope == "PROJECT" and config.project_slug is None:
            item["publishBlockedReason"] = "missing_project_slug"
        elif remote_scope is not None and remote_scope != target_scope:
            item["publishBlockedReason"] = "scope_conflict"
        elif remote_latest is None and target_scope == "SHARED" and local_skill.category is None:
            item["publishBlockedReason"] = "missing_shared_category"
        elif item["needsPull"]:
            item["publishBlockedReason"] = "remote_newer"
        if item["publishBlockedReason"] is not None:
            publish_blocked.append(item)
        results.append(item)

    return {
        "action": "audit",
        "skillsDir": str(config.skills_dir),
        "projectSlug": config.project_slug,
        "excludedSkills": sorted(excluded),
        "summary": {
            "checked": len(results),
            "missing": len(missing),
            "localNewerThanRemote": len(local_newer),
            "remoteNewerThanLocal": len(remote_newer),
            "sameVersion": len(same_version),
            "publishBlocked": len(publish_blocked),
            "publishRequiresLibraryPermission": len(publish_requires_library_permission),
        },
        "missing": missing,
        "localNewerThanRemote": local_newer,
        "remoteNewerThanLocal": remote_newer,
        "sameVersion": same_version,
        "publishBlocked": publish_blocked,
        "publishRequiresLibraryPermission": publish_requires_library_permission,
        "results": results,
    }


def migrate_project_to_shared(
    *,
    config: Config,
    skill_name: str,
    category: str,
    project_slug: str | None,
    changelog_md: str | None,
) -> dict[str, Any]:
    resolved_project_slug = first_non_blank(project_slug, config.project_slug)
    if resolved_project_slug is None:
        raise ScriptError(f"Migracja PROJECT -> SHARED dla {skill_name} wymaga projectSlug.")

    local_skill = load_local_skill(config.skills_dir, skill_name)
    if local_skill.scope != "SHARED":
        raise ScriptError(f"Migracja {skill_name} wymaga scope: SHARED w lokalnym SKILL.md przed usunięciem PROJECT.")
    if first_non_blank(category) is None:
        raise ScriptError(f"Migracja {skill_name} wymaga kategorii SHARED przed usunięciem PROJECT.")
    source = request_json(
        config,
        "GET",
        f"/skills/remote/{urllib.parse.quote(skill_name)}/latest",
        query=build_remote_project_query(resolved_project_slug),
        allow_status={404},
    )
    if source is None:
        raise ScriptError(f"Nie znaleziono źródłowego skilla PROJECT {skill_name} w {resolved_project_slug}; niczego nie usunięto.")

    delete_result = delete_project_skill_if_exists(config, skill_name, resolved_project_slug)
    try:
        publish_result = publish_skill(
            config=config,
            skill_name=skill_name,
            category=category,
            scope="SHARED",
            project_slug=None,
            changelog_md=changelog_md,
        )
    except ScriptError as exception:
        raise ScriptError(
            f"Publikacja SHARED nie powiodła się po próbie usunięcia PROJECT {skill_name}. "
            f"Wpis źródłowy mógł już zostać usunięty. "
            f"deleteProjectResult={json.dumps(delete_result, ensure_ascii=False)}; przyczyna: {exception}"
        ) from exception
    return {
        "action": "MIGRATED_PROJECT_TO_SHARED",
        "skillName": skill_name,
        "sourceProjectSlug": resolved_project_slug,
        "targetScope": "SHARED",
        "targetCategory": category,
        "deleteProjectResult": delete_result,
        "publishResult": publish_result,
    }


def publish_skill(
    *,
    config: Config,
    skill_name: str,
    category: str | None,
    scope: str | None,
    project_slug: str | None,
    changelog_md: str | None,
) -> dict[str, Any]:
    local_skill = load_local_skill(config.skills_dir, skill_name)
    scope, project_slug = resolve_target(config, skill_name, first_non_blank(scope, local_skill.scope), project_slug)
    normalized_category = first_non_blank(category, local_skill.category)
    remote_query = build_remote_project_query(project_slug, {"currentVersion": local_skill.declared_version})
    remote_latest = request_json(
        config,
        "GET",
        f"/skills/remote/{urllib.parse.quote(skill_name)}/latest",
        query=remote_query,
        allow_status={404},
    )

    if scope == "SHARED" and remote_latest is None and normalized_category is None:
        available_categories = fetch_shared_skill_categories(config)
        if available_categories:
            raise ScriptError(
                "Nowy skill SHARED wymaga --category. Dostępne kategorie: "
                + ", ".join(available_categories)
            )
        raise ScriptError("Nowy skill SHARED wymaga --category.")

    if remote_latest is not None:
        latest_version = remote_latest["latestVersion"]
        version_cmp = compare_semver(local_skill.declared_version, latest_version)
        if version_cmp < 0:
            raise ScriptError(
                f"Biblioteka PLEO ma nowszą wersję skilla {skill_name}: "
                f"{local_skill.declared_version} -> {latest_version}. Najpierw pobierz nowszą wersję."
            )

        remote_version = fetch_remote_version(config, skill_name, latest_version, project_slug)
        if has_same_payload(local_skill.files, remote_version["files"]):
            if version_cmp == 0:
                return {
                    "skillName": skill_name,
                    "category": normalized_category,
                    "scope": scope,
                    "projectSlug": project_slug,
                    "version": latest_version,
                    "action": "NO_CHANGE",
                    "changed": False,
                }
            raise ScriptError(
                f"Payload skilla {skill_name} nie zmienił się, więc frontmatter version musi pozostać {latest_version}."
            )
        if version_cmp == 0:
            raise ScriptError(
                f"Lokalny skill {skill_name} ma zmieniony payload bez podbicia frontmatter version "
                f"({local_skill.declared_version})."
            )

    payload = {
        "skillName": local_skill.name,
        "category": normalized_category,
        "tags": local_skill.tags,
        "scope": scope,
        "projectSlug": project_slug,
        "changelogMd": changelog_md,
        "libraryUserId": config.library_user_id,
        "files": [
            {
                "relativePath": file.relative_path,
                "mimeType": file.mime_type,
                "contentBase64": base64.b64encode(file.content).decode("ascii"),
            }
            for file in local_skill.files
        ],
    }
    result = request_json(config, "POST", "/skills/remote/upsert", body=payload)
    return {
        "skillName": result["skillName"],
        "category": normalized_category,
        "scope": scope,
        "projectSlug": project_slug,
        "version": result["version"],
        "action": result["action"],
        "changed": bool(result["changed"]),
    }


def rename_skill(config: Config, skill_name: str, new_skill_name: str, project_slug: str | None) -> dict[str, Any]:
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", skill_name)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", new_skill_name)
            or skill_name.lower() == new_skill_name.lower()):
        raise ScriptError("Nowa nazwa skilla musi być innym, bezpiecznym segmentem katalogu.")
    resolved_project_slug = resolve_remote_skill_project_slug(config, skill_name, project_slug)
    local_skill = load_local_skill(config.skills_dir, skill_name)
    if local_skill.scope not in {"PROJECT", "SHARED"}:
        raise ScriptError(f"Rename skilla {skill_name} wymaga jawnego scope w lokalnym SKILL.md.")
    if local_skill.scope == "PROJECT" and resolved_project_slug is None:
        raise ScriptError(f"Rename skilla PROJECT {skill_name} wymaga jawnego --project-slug.")
    if local_skill.scope == "SHARED" and resolved_project_slug is not None and not is_reserved_library_skill_name(skill_name):
        raise ScriptError(f"Rename zwykłego skilla SHARED {skill_name} nie może zawierać --project-slug.")
    source_dir = config.skills_dir / skill_name
    target_dir = config.skills_dir / new_skill_name
    if source_dir.is_symlink() or target_dir.exists():
        raise ScriptError(f"Nie można bezpiecznie zmienić lokalnego katalogu {source_dir} na {target_dir}.")
    source_md = source_dir / "SKILL.md"
    original_bytes = source_md.read_bytes()
    original_text = original_bytes.decode("utf-8")
    frontmatter = FRONTMATTER_PATTERN.match(original_text)
    if frontmatter is None or first_frontmatter_value(parse_frontmatter(original_text), "name") != skill_name:
        raise ScriptError(f"SKILL.md musi deklarować name: {skill_name} przed rename.")
    major, minor, patch = parse_semver(local_skill.declared_version)
    next_version = f"{major}.{minor}.{patch + 1}"
    updated_frontmatter, name_count = re.subn(r"(?m)^name:[^\r\n]*", f"name: {new_skill_name}", frontmatter.group(1), count=1)
    updated_frontmatter, version_count = re.subn(r"(?m)^version:[^\r\n]*", f"version: {next_version}", updated_frontmatter, count=1)
    if name_count != 1 or version_count != 1:
        raise ScriptError("SKILL.md wymaga pól name i version w frontmatter przed rename.")
    updated_bytes = (original_text[:frontmatter.start(1)] + updated_frontmatter
                     + original_text[frontmatter.end(1):]).encode("utf-8")
    remote_latest = request_json(
        config, "GET", f"/skills/remote/{urllib.parse.quote(skill_name)}/latest",
        query=build_remote_project_query(resolved_project_slug), allow_status={404},
    )
    if remote_latest is None:
        raise ScriptError(f"Nie znaleziono zdalnego skilla {skill_name}; lokalny katalog pozostaje bez zmian.")
    if compare_semver(local_skill.declared_version, remote_latest["latestVersion"]) < 0:
        raise ScriptError(f"Biblioteka ma nowszą wersję {skill_name}; pobierz ją przed rename.")

    try:
        source_dir.rename(target_dir)
        (target_dir / "SKILL.md").write_bytes(updated_bytes)
    except OSError as exception:
        if target_dir.exists() and not source_dir.exists():
            target_dir.rename(source_dir)
            (source_dir / "SKILL.md").write_bytes(original_bytes)
        raise ScriptError(f"Nie udało się przygotować lokalnego rename: {exception}") from exception
    try:
        result = request_json(
            config,
            "POST",
            f"/skills/remote/{urllib.parse.quote(skill_name)}/rename",
            body={
                "newSkillName": new_skill_name,
                "projectSlug": resolved_project_slug,
                "libraryUserId": config.library_user_id,
            },
        )
    except ScriptError:
        target_dir.rename(source_dir)
        (source_dir / "SKILL.md").write_bytes(original_bytes)
        raise
    try:
        publication = publish_skill(config=config, skill_name=new_skill_name, category=local_skill.category,
                                    scope=local_skill.scope, project_slug=resolved_project_slug, changelog_md=None)
    except ScriptError as exception:
        raise ScriptError(
            f"Zdalny i lokalny rename {skill_name} -> {new_skill_name} powiódł się, "
            f"ale publikacja wersji {next_version} nie: {exception}. "
            "Lokalny katalog i wpis zdalny mają nową nazwę; ponów publish po naprawie błędu."
        ) from exception
    return {
        "action": "RENAMED",
        "previousSkillName": skill_name,
        "skillName": result["name"],
        "scope": result["scope"],
        "localDirectory": str(target_dir),
        "version": next_version,
        "publishResult": publication,
    }


def delete_skill(config: Config, skill_name: str, project_slug: str | None) -> dict[str, Any]:
    resolved_project_slug = resolve_remote_skill_project_slug(config, skill_name, project_slug)
    result = request_json(
        config,
        "POST",
        f"/skills/remote/{urllib.parse.quote(skill_name)}/delete",
        body={
            "projectSlug": resolved_project_slug,
            "libraryUserId": config.library_user_id,
        },
    )
    return {
        "action": result["action"],
        "skillName": result["skillName"],
        "skillId": result["skillId"],
    }


def delete_project_skill_if_exists(config: Config, skill_name: str, project_slug: str) -> dict[str, Any]:
    result = request_json(
        config,
        "POST",
        f"/skills/remote/{urllib.parse.quote(skill_name)}/delete",
        body={
            "projectSlug": project_slug,
            "libraryUserId": config.library_user_id,
        },
        allow_status={404},
    )
    if result is None:
        return {
            "action": "NOT_FOUND",
            "skillName": skill_name,
            "projectSlug": project_slug,
        }
    return {
        "action": result["action"],
        "skillName": result["skillName"],
        "skillId": result["skillId"],
        "projectSlug": project_slug,
    }


def fetch_shared_skill_categories(config: Config) -> list[str]:
    response = request_json(
        config,
        "GET",
        "/skills/remote/shared/categories",
        query={"libraryUserId": config.library_user_id},
    )
    return [item for item in response if isinstance(item, str) and item.strip()]


def fetch_shared_skill_index(config: Config) -> dict[str, dict[str, Any]]:
    response = request_json(
        config,
        "GET",
        "/skills/remote/shared",
        query={"libraryUserId": config.library_user_id},
    )
    index: dict[str, dict[str, Any]] = {}
    for item in response:
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            index[name.strip().lower()] = item
    return index


def fetch_remote_version(
    config: Config,
    skill_name: str,
    version: str,
    project_slug: str | None,
) -> dict[str, Any]:
    return request_json(
        config,
        "GET",
        f"/skills/remote/{urllib.parse.quote(skill_name)}/versions/{urllib.parse.quote(version)}",
        query=build_remote_project_query(project_slug),
    )


def has_same_payload(local_files: list[LocalFile], remote_files: list[dict[str, Any]]) -> bool:
    local_by_path = {file.relative_path.lower(): sha256_hex(file.content) for file in local_files}
    remote_by_path = {
        normalize_relative_path(file["relativePath"]).lower(): sha256_hex(base64.b64decode(file["contentBase64"]))
        for file in remote_files
    }
    return local_by_path == remote_by_path


def is_python_cache(relative_path: str) -> bool:
    parts = relative_path.replace("\\", "/").lower().split("/")
    return "__pycache__" in parts or parts[-1].endswith((".pyc", ".pyo"))


def validate_text_encoding(relative_path: str, mime_type: str, content: bytes) -> None:
    lower_path = relative_path.lower()
    lower_mime = mime_type.lower()
    if not (Path(lower_path).suffix in TEXT_SUFFIXES or lower_path.endswith(".gitignore")
            or lower_mime.startswith("text/") or any(kind in lower_mime for kind in ("json", "xml", "yaml", "javascript"))):
        return
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise ScriptError(f"Plik tekstowy musi być zapisany w UTF-8: {relative_path}") from exception
    if "\x00" in text:
        raise ScriptError(f"Plik tekstowy zawiera bajt NUL: {relative_path}")


def load_local_skill(skills_dir: Path, skill_name: str) -> LocalSkill:
    skill_dir = skills_dir / skill_name
    if not skill_dir.is_dir():
        raise ScriptError(f"Nie znaleziono katalogu skilla: {skill_dir}")

    files: list[LocalFile] = []
    for file_path in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
        relative_path = file_path.relative_to(skill_dir).as_posix()
        if is_python_cache(relative_path):
            continue
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()
        validate_text_encoding(relative_path, mime_type, content)
        files.append(LocalFile(relative_path=relative_path, mime_type=mime_type, content=content))

    skill_md = next((file for file in files if file.relative_path == "SKILL.md"), None)
    if skill_md is None:
        raise ScriptError(f"Brakuje pliku SKILL.md w {skill_dir}")

    body = skill_md.content.decode("utf-8")
    ensure_new_skill_format(body, skill_name)
    declared_version = extract_version(body, skill_name)
    declared_author = extract_author(body, skill_name)
    frontmatter = parse_frontmatter(body)
    return LocalSkill(
        name=skill_name,
        declared_version=declared_version,
        declared_author=declared_author,
        category=first_non_blank(first_frontmatter_value(frontmatter, "category")),
        tags=normalize_tags(frontmatter.get("tags")),
        scope=normalize_scope(first_frontmatter_value(frontmatter, "scope")),
        files=files,
    )


def extract_version(skill_md_body: str, skill_name: str) -> str:
    frontmatter_version = first_frontmatter_value(parse_frontmatter(skill_md_body), "version")
    if frontmatter_version is not None:
        return frontmatter_version
    raise ScriptError(f"Skill {skill_name} nie ma frontmatter version x.y.z w SKILL.md.")


def extract_author(skill_md_body: str, skill_name: str) -> str:
    frontmatter_author = first_frontmatter_value(parse_frontmatter(skill_md_body), "author")
    if frontmatter_author is not None:
        author = frontmatter_author
        if not EMAIL_PATTERN.match(author):
            raise ScriptError(f"Skill {skill_name} ma nieprawidłowy email w frontmatter author.")
        return author
    raise ScriptError(f"Skill {skill_name} nie ma frontmatter author email w SKILL.md.")


def ensure_new_skill_format(skill_md_body: str, skill_name: str) -> None:
    if LEGACY_VERSION_PATTERN.search(skill_md_body) or LEGACY_AUTHOR_PATTERN.search(skill_md_body):
        raise ScriptError(
            f"Skill {skill_name} używa starego formatu # WERSJA/# AUTOR. "
            "Przerób SKILL.md na nowy frontmatter: version, author, scope i tags. "
            "Pole category stosuj tylko dla scope SHARED."
        )


def parse_frontmatter(content: str) -> dict[str, list[str]]:
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}
    result: dict[str, list[str]] = {}
    current_list_key: str | None = None
    for line in match.group(1).splitlines():
        field_match = FRONTMATTER_FIELD_PATTERN.match(line)
        if field_match:
            key = field_match.group(1).strip().lower()
            value = strip_yaml_quotes(field_match.group(2).strip())
            current_list_key = key if value == "" else None
            result[key] = parse_frontmatter_value(value) if value else []
            continue
        if current_list_key:
            item_match = FRONTMATTER_LIST_ITEM_PATTERN.match(line)
            if item_match:
                result.setdefault(current_list_key, []).append(strip_yaml_quotes(item_match.group(1).strip()))
    return result


def parse_frontmatter_value(value: str) -> list[str]:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [strip_yaml_quotes(item.strip()) for item in inner.split(",") if item.strip()]
    return [value]


def first_frontmatter_value(frontmatter: dict[str, list[str]], key: str) -> str | None:
    values = frontmatter.get(key.lower()) or []
    return first_non_blank(*values)


def normalize_tags(tags: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        value = first_non_blank(tag)
        if value is None or value.lower() in seen:
            continue
        seen.add(value.lower())
        normalized.append(value)
    return normalized


def normalize_scope(scope: str | None) -> str | None:
    value = first_non_blank(scope)
    if value is None:
        return None
    normalized = value.upper()
    if normalized not in {"SHARED", "PROJECT"}:
        raise ScriptError(f"Nieprawidłowy frontmatter scope: {scope}")
    return normalized


def strip_yaml_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

def resolve_target(
    config: Config,
    skill_name: str,
    scope: str | None,
    project_slug: str | None,
) -> tuple[str, str | None]:
    resolved_scope = scope or config.default_scope
    if not resolved_scope:
        raise ScriptError(f"Brak scope dla skilla {skill_name}. Podaj --scope lub defaultScope w .agent-library.yaml.")

    # Wymuszaj scope SHARED dla skilli z prefiksem pleo-library-*
    if is_reserved_library_skill_name(skill_name) and resolved_scope != "SHARED":
        raise ScriptError(
            f"Skill {skill_name} z prefiksem {PLEO_LIBRARY_SKILL_PREFIX} może być publikowany tylko jako SHARED, "
            f"nie jako {resolved_scope}."
        )

    normalized_project_slug = first_non_blank(project_slug)
    required_repo_project_slug = required_library_repo_project_slug(config, skill_name)
    if (
        required_repo_project_slug is not None
        and normalized_project_slug is not None
        and normalized_project_slug.lower() != required_repo_project_slug.lower()
    ):
        raise ScriptError(
            f"Skill {skill_name} z prefiksem {PLEO_LIBRARY_SKILL_PREFIX} może być publikowany tylko z projectSlug "
            f"{required_repo_project_slug}."
        )
    if resolved_scope == "SHARED":
        if normalized_project_slug is not None and required_repo_project_slug is None:
            raise ScriptError("Skill SHARED nie może mieć projectSlug.")
        return resolved_scope, required_repo_project_slug

    if required_repo_project_slug is not None:
        return resolved_scope, required_repo_project_slug

    resolved_project_slug = first_non_blank(normalized_project_slug, config.project_slug)
    if resolved_project_slug is None:
        raise ScriptError(f"Skill PROJECT {skill_name} wymaga projectSlug.")
    return resolved_scope, resolved_project_slug


def required_library_repo_project_slug(config: Config, skill_name: str) -> str | None:
    if not is_reserved_library_skill_name(skill_name):
        return None
    if config.project_slug is None:
        raise ScriptError(
            f"Skill {skill_name} z prefiksem {PLEO_LIBRARY_SKILL_PREFIX} wymaga projectSlug w .agent-library.yaml."
        )
    return config.project_slug


def resolve_remote_skill_project_slug(config: Config, skill_name: str, project_slug: str | None) -> str | None:
    normalized_project_slug = first_non_blank(project_slug)
    required_repo_project_slug = required_library_repo_project_slug(config, skill_name)
    if (
        required_repo_project_slug is not None
        and normalized_project_slug is not None
        and normalized_project_slug.lower() != required_repo_project_slug.lower()
    ):
        raise ScriptError(
            f"Skill {skill_name} z prefiksem {PLEO_LIBRARY_SKILL_PREFIX} może być publikowany tylko z projectSlug "
            f"{required_repo_project_slug}."
        )
    return required_repo_project_slug or normalized_project_slug


def is_reserved_library_skill_name(skill_name: str) -> bool:
    return skill_name.lower().startswith(PLEO_LIBRARY_SKILL_PREFIX)


def load_config(repo_root: Path) -> Config:
    raw_config = parse_simple_yaml(repo_root / ".agent-library.yaml")
    base_url = expect_string(raw_config, "libraryBaseUrl").rstrip("/")
    project_slug_raw = raw_config.get("projectSlug")
    paths = expect_dict(raw_config, "paths")
    publish = raw_config.get("publish") if isinstance(raw_config.get("publish"), dict) else {}
    default_scope = publish.get("defaultScope")
    if default_scope is not None and default_scope not in {"SHARED", "PROJECT"}:
        raise ScriptError("publish.defaultScope musi byc SHARED albo PROJECT.")
    return Config(
        base_url=base_url,
        project_slug=project_slug_raw.strip() if isinstance(project_slug_raw, str) and project_slug_raw.strip() else None,
        skills_dir=repo_root / expect_string(paths, "skillsDir"),
        default_scope=default_scope,
        library_user_id=load_required_library_user_id(),
    )


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
        query = {key: value for key, value in query.items() if value is not None}
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
            if allow_status and exc.code in allow_status:
                return None
            if exc.code in TRANSIENT_HTTP_STATUS_CODES and attempt < MAX_TRANSIENT_RETRIES:
                last_transient_error = format_http_error(exc.code, path, response_text)
                time.sleep(2**attempt)
                continue
            message = format_http_error(exc.code, path, response_text)
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


def format_http_error(status_code: int, path: str, payload: str) -> str:
    message = extract_error_message(payload)
    details = f"HTTP {status_code} dla {path}: {message}"
    stripped_payload = payload.strip()
    if stripped_payload and stripped_payload != message:
        details += f". Odpowiedź backendu: {stripped_payload}"
    if status_code == 400 and "upsert" in path:
        details += (
            ". Wskazówka: endpoint upsert może odrzucać kategorię przy scope PROJECT "
            "albo payload niezgodny z regułami backendu."
        )
    if status_code == 403 and "upsert" in path:
        details += (
            ". Wskazówka: publikacja może wymagać uprawnień do danego scope, kategorii "
            "albo prefiksu zastrzeżonego `pleo-library-`."
        )
    if status_code == 409:
        details += (
            ". Wskazówka: sprawdź, czy skill nie istnieje już pod innym scope; "
            "dla migracji PROJECT -> SHARED użyj komendy `migrate-project-to-shared`."
        )
    return details


def normalize_relative_path(raw_path: str) -> str:
    normalized = raw_path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/") or "/../" in f"/{normalized}/":
        raise ScriptError(f"Nieprawidłowa ścieżka pliku: {raw_path}")
    return normalized


def compare_semver(left: str, right: str) -> int:
    left_parts = parse_semver(left)
    right_parts = parse_semver(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ScriptError(f"Nieprawidlowa wersja semver: {value}")
    return tuple(int(part) for part in match.groups())


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_optional_text(path: str | None) -> str | None:
    if path is None:
        return None
    return Path(path).read_text(encoding="utf-8")


def build_remote_project_query(project_slug: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(extra or {})
    payload["libraryUserId"] = load_required_library_user_id()
    if project_slug:
        payload["projectSlug"] = project_slug
    return payload


def load_required_library_user_id() -> str:
    value = os.environ.get("TELEMETRY_USER_ID")
    if value is None or not value.strip():
        raise ScriptError("Brakuje TELEMETRY_USER_ID. Biblioteka wymaga przekazywania libraryUserId.")
    return value.strip()


def first_non_blank(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip():
            return value.strip()
    return None


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
