#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_PATTERN = re.compile(r"(?im)^#\s*WERSJA\s+(\d+\.\d+\.\d+)\s*$")
TITLE_PATTERN = re.compile(r"(?m)^#\s*Instrukcje\s+\S+\s+dla\s+(.+?)\s*$")
SKILLS_SECTION_PATTERN = re.compile(r"(?ms)^## Skille\s*\n.*?(?=^##\s|\Z)")
INSTRUCTIONS_BLOCK_PATTERN = re.compile(r"(?s)(<INSTRUCTIONS>\s*)(.*?)(\s*</INSTRUCTIONS>)")
FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FRONTMATTER_FIELD_PATTERN = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
PARENT_PATH_PATTERN = re.compile(r"(^|/)\.\.(/|$)")
TEXT_SUFFIXES = {".md", ".txt", ".yml", ".yaml", ".json", ".xml", ".java", ".js", ".ts", ".tsx", ".jsx", ".py", ".sh", ".properties", ".toml", ".ini", ".cfg", ".csv", ".sql", ".svg", ".html", ".css", ".rst", ".jsonl", ".ndjson", ".ps1"}

INSTRUCTION_TYPES = ("AGENTS", "CLAUDE", "GEMINI")
INSTRUCTION_FILENAMES = {
    "AGENTS": "AGENTS.md",
    "CLAUDE": "CLAUDE.md",
    "GEMINI": "GEMINI.md",
}

USAGE_RULES = (
    "Uruchom skill, gdy zadanie wyraźnie pasuje do jego opisu.",
    "`pleo-library-skill-version-guard` wykonuje target-only check wskazanego skilla i lekki check statusu manifestu; pełny sync robi tylko dla manifestu niezweryfikowanego dzisiaj, zmiany liczby skilli albo po aktualizacji targetu.",
    "Wszystkie wykryte nieaktualne skille z czystymi katalogami Git aktualizuje automatycznie bez pytania użytkownika; lokalne zmiany blokują pull danego skilla.",
    "Nie raportuj telemetrycznie samego `pleo-library-skill-version-guard`, bo to infrastrukturalny check aktualności skilli.",
    "Przed użyciem lokalnych skilli uruchom `pleo-library-skill-version-guard`, jeśli chcesz potwierdzić aktualność skilli w repo.",
    "Po routingu `pleo-library-prompt-model-triage` kontynuuj bez pytania, jeśli rekomendowany reasoning to `medium` albo niżej; jeśli reasoning jest wyższy niż `medium`, zatrzymaj się i czekaj na jasne potwierdzenie użytkownika przed dalszą pracą.",
    "Nie raportuj telemetrycznie żadnych skilli `pleo-library-*`, w tym `pleo-library-prompt-model-triage`, `pleo-library-shared-skill-sync`, `pleo-library-skill-version-guard` i `pleo-library-telemetry-lifecycle`.",
    "Jeśli triage wskazuje `pleo-library-shared-skill-sync`, wykonaj go bez telemetryki.",
    "Dla skilli docelowych spoza `pleo-library-*` wyślij `start`, wysyłaj `progress` tylko przy realnej zmianie etapu, a na końcu `finish` albo `interrupt`.",
    "Pełny audyt wersji wszystkich skilli albo synchronizację całego stanu projektu wykonuj tylko na jawne polecenie użytkownika.",
    "Jeśli zadanie dotyczy dodania nowego skilla do biblioteki albo publikacji zmian lokalnego skilla do biblioteki, użyj `pleo-library-skill-publisher`.",
    "Jeśli zadanie zmodyfikowało lokalny skill w `skills/**` albo lokalny plik `AGENTS.md`, `CLAUDE.md` lub `GEMINI.md`, na końcu sprawdź, czy wersja w zmienionym pliku została świadomie podbita; jeśli nie, przypomnij o podbiciu frontmatter `version`.",
    "Przy refaktorze, tłumaczeniu albo porządkowaniu skilla nie wolno usuwać informacji merytorycznych. Można przenosić szczegóły do `references/`, ale triggery, zasady, przykłady, edge case'y i default prompty muszą pozostać dostępne.",
    "Jeśli zadanie zmodyfikowało lokalny skill w `skills/**` albo lokalny plik `AGENTS.md`, `CLAUDE.md` lub `GEMINI.md`, na końcu zawsze zapytaj użytkownika, czy opublikować zmiany do biblioteki.",
    "Jeśli pasuje kilka skilli, użyj minimalnego zestawu i podaj kolejność.",
    "Otwieraj tylko pliki potrzebne do bieżącej zmiany; unikaj ładowania niepowiązanych modułów.",
    "Preferuj rozszerzanie istniejących wzorców projektu zamiast wymyślania nowych.",
    "Jeśli skillu nie da się zastosować wprost, napisz krótko dlaczego i przejdź do najlepszego sensownego obejścia.",
)


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    repo_root: Path
    base_url: str
    project_slug: str | None
    skills_dir: Path
    path_by_type: dict[str, Path]
    library_user_id: str


@dataclass(frozen=True)
class RemoteSkill:
    id: int
    name: str
    category: str | None
    tags: list[str]
    latest_version: str | None


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    skill_md_path: Path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root(Path(args.repo_root) if args.repo_root else Path(__file__).resolve())
        config = load_config(repo_root)
        if args.command == "check":
            result = check_shared_skills(config, args.category, args.tag or [])
        elif args.command == "categories":
            result = {
                "projectSlug": config.project_slug,
                "availableCategories": fetch_shared_skill_categories(config),
            }
        elif args.command == "pull":
            result = pull_shared_skills(
                config,
                requested_skills=args.skill or [],
                category=args.category,
                tags=args.tag or [],
            )
        else:
            raise ScriptError(f"Nieznana komenda: {args.command}")
    except ScriptError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sprawdza i pobiera brakujące shared skille z biblioteki."
    )
    parser.add_argument("--repo-root", help="Ścieżka do katalogu repo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Sprawdź brakujące shared skille.")
    check_parser.add_argument("--category", help="Kategoria shared skilli do sprawdzenia.")
    check_parser.add_argument("--tag", action="append", help="Tag shared skilli do sprawdzenia.")

    subparsers.add_parser("categories", help="Pobierz listę dostępnych kategorii shared skilli.")

    pull_parser = subparsers.add_parser("pull", help="Pobierz wskazane brakujące shared skille.")
    pull_parser.add_argument("--skill", action="append", help="Nazwa shared skilla do pobrania.")
    pull_parser.add_argument("--category", help="Kategoria shared skilli do pobrania.")
    pull_parser.add_argument("--tag", action="append", help="Tag shared skilli do pobrania.")

    return parser


def check_shared_skills(config: Config, category: str | None, tags: list[str]) -> dict[str, Any]:
    normalized_category = first_non_blank(category)
    normalized_tags = normalize_tag_filters(tags)
    remote_skills = fetch_shared_skills(
        config,
        normalized_category if normalized_category else None,
        normalized_tags,
    )
    local_versions = collect_local_skill_versions(config.skills_dir)
    results = []
    missing_skills = []
    local_newer_than_remote = []
    remote_newer_than_local = []
    same_version = []

    for remote_skill in remote_skills:
        local_version = local_versions.get(remote_skill.name.lower())
        missing = local_version is None
        version_state = "missing_locally" if missing else "unknown"
        needs_pull = False
        needs_publish = False
        if not missing and local_version is not None and remote_skill.latest_version is not None:
            version_cmp = compare_semver(local_version, remote_skill.latest_version)
            if version_cmp > 0:
                version_state = "local_newer"
                needs_publish = True
            elif version_cmp < 0:
                version_state = "remote_newer"
                needs_pull = True
            else:
                version_state = "same"
        if missing:
            missing_skills.append(remote_skill.name)
        item = {
            "skillName": remote_skill.name,
            "category": remote_skill.category,
            "tags": remote_skill.tags,
            "latestVersion": remote_skill.latest_version,
            "localExists": not missing,
            "localVersion": local_version,
            "missingLocally": missing,
            "pullable": remote_skill.latest_version is not None,
            "versionState": version_state,
            "needsPull": needs_pull,
            "needsPublish": needs_publish,
        }
        if version_state == "local_newer":
            local_newer_than_remote.append(item)
        elif version_state == "remote_newer":
            remote_newer_than_local.append(item)
        elif version_state == "same":
            same_version.append(item)
        results.append(item)

    return {
        "projectSlug": config.project_slug,
        "skillsDir": str(config.skills_dir),
        "availableCategories": [],
        "availableCategoriesFetched": False,
        "categoryDiscovery": {
            "attempted": False,
            "reason": "not_required_for_check",
            "command": "categories",
        },
        "selectedCategory": normalized_category,
        "selectedTags": normalized_tags,
        "remoteSharedCount": len(remote_skills),
        "missingSharedSkills": missing_skills,
        "versionSummary": {
            "missingLocally": len(missing_skills),
            "localNewerThanRemote": len(local_newer_than_remote),
            "remoteNewerThanLocal": len(remote_newer_than_local),
            "sameVersion": len(same_version),
        },
        "localNewerThanRemote": local_newer_than_remote,
        "remoteNewerThanLocal": remote_newer_than_local,
        "bulkPullRequiresExplicitUserRequest": True,
        "results": results,
    }


def pull_shared_skills(
    config: Config,
    *,
    requested_skills: list[str],
    category: str | None,
    tags: list[str],
) -> dict[str, Any]:
    if not requested_skills:
        raise ScriptError(
            "Podaj co najmniej jedno --skill. Najpierw użyj `check`, pokaż użytkownikowi brakujące shared skille i pobierz tylko wybrane pozycje."
        )

    normalized_category = first_non_blank(category)
    normalized_tags = normalize_tag_filters(tags)
    remote_skills = fetch_shared_skills(
        config,
        normalized_category if normalized_category else None,
        normalized_tags,
    )
    local_versions = collect_local_skill_versions(config.skills_dir)

    resolution = resolve_requested_skills(requested_skills, remote_skills)
    target_skills = resolution.pop("_targetSkills")
    unresolved_skills = resolution["unresolvedSkills"]
    if not target_skills:
        details = ", ".join(item["requestedName"] for item in unresolved_skills) or "brak poprawnych nazw"
        raise ScriptError(
            "Nie znaleziono żadnego jednoznacznego shared skilla do pobrania. "
            f"Pozycje nierozwiązane: {details}."
        )

    changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for remote_skill in target_skills:
        normalized = remote_skill.name.lower()
        if normalized in local_versions:
            skipped.append(
                {
                    "skillName": remote_skill.name,
                    "category": remote_skill.category,
                    "tags": remote_skill.tags,
                    "reason": "already_present",
                    "localVersion": local_versions[normalized],
                }
            )
            continue
        if remote_skill.latest_version is None:
            skipped.append(
                {
                    "skillName": remote_skill.name,
                    "category": remote_skill.category,
                    "tags": remote_skill.tags,
                    "reason": "no_published_version",
                }
            )
            continue

        result = request_json(
            config,
            "POST",
            f"/skills/remote/{urllib.parse.quote(remote_skill.name)}/pull",
            body={
                "currentVersion": "0.0.0",
                "projectSlug": config.project_slug,
                "libraryUserId": config.library_user_id,
            },
        )
        if not result["updateAvailable"]:
            skipped.append(
                {
                    "skillName": remote_skill.name,
                    "reason": "remote_pull_returned_no_update",
                    "latestVersion": result["latestVersion"],
                }
            )
            continue

        written_files = write_new_skill_directory(config.skills_dir, remote_skill.name, result["files"])
        changes.append(
            {
                "skillName": remote_skill.name,
                "category": remote_skill.category,
                "tags": remote_skill.tags,
                "latestVersion": result["latestVersion"],
                "writtenFiles": written_files,
            }
        )

    instruction_changes = refresh_instruction_files(config) if changes else []

    return {
        "projectSlug": config.project_slug,
        "selectedCategory": normalized_category,
        "selectedTags": normalized_tags,
        "bulkPullRequiresExplicitUserRequest": True,
        "requestedSkillResolution": resolution,
        "addedSkills": changes,
        "skippedSkills": skipped,
        "instructionChanges": instruction_changes,
    }


def resolve_requested_skills(requested_skills: list[str], remote_skills: list[RemoteSkill]) -> dict[str, Any]:
    remote_by_name = {skill.name.lower(): skill for skill in remote_skills}
    resolved: list[RemoteSkill] = []
    resolved_items: list[dict[str, Any]] = []
    unresolved_items: list[dict[str, Any]] = []
    seen_requests: set[str] = set()
    seen_resolved: set[str] = set()

    for raw_name in requested_skills:
        requested_name = raw_name.strip()
        normalized_request = requested_name.lower()
        if not normalized_request or normalized_request in seen_requests:
            continue
        seen_requests.add(normalized_request)

        exact_match = remote_by_name.get(normalized_request)
        if exact_match is not None:
            resolved_skill = exact_match
            match_type = "exact"
        else:
            candidates = find_alias_candidates(requested_name, remote_skills)
            if len(candidates) != 1:
                unresolved_items.append(
                    {
                        "requestedName": requested_name,
                        "reason": "not_found" if not candidates else "ambiguous_alias",
                        "candidates": [candidate.name for candidate in candidates],
                    }
                )
                continue
            resolved_skill = candidates[0]
            match_type = "alias"

        resolved_key = resolved_skill.name.lower()
        resolved_items.append(
            {
                "requestedName": requested_name,
                "skillName": resolved_skill.name,
                "matchType": match_type,
            }
        )
        if resolved_key in seen_resolved:
            continue
        seen_resolved.add(resolved_key)
        resolved.append(resolved_skill)

    return {
        "_targetSkills": resolved,
        "resolved": resolved_items,
        "unresolvedSkills": unresolved_items,
    }


def find_alias_candidates(requested_name: str, remote_skills: list[RemoteSkill]) -> list[RemoteSkill]:
    compact_request = compact_skill_name(requested_name)
    if not compact_request:
        return []
    exact_compact = [skill for skill in remote_skills if compact_skill_name(skill.name) == compact_request]
    if exact_compact:
        return exact_compact
    return [skill for skill in remote_skills if compact_skill_name(skill.name).endswith(compact_request)]


def compact_skill_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def fetch_shared_skill_categories(config: Config) -> list[str]:
    response = request_json(
        config,
        "GET",
        "/skills/remote/shared/categories",
        query={"libraryUserId": config.library_user_id},
    )
    return [item for item in response if isinstance(item, str) and item.strip()]


def fetch_shared_skills(config: Config, category: str | None, tags: list[str]) -> list[RemoteSkill]:
    query: dict[str, Any] = {"libraryUserId": config.library_user_id}
    if category:
        query["category"] = category
    if tags:
        query["tags"] = tags
    response = request_json(config, "GET", "/skills/remote/shared", query=query)
    skills = []
    for item in response:
        skills.append(
            RemoteSkill(
                id=item["id"],
                name=item["name"],
                category=item.get("category"),
                tags=normalize_remote_tags(item.get("tags")),
                latest_version=item.get("latestVersion"),
            )
        )
    return sorted(skills, key=lambda skill: skill.name.lower())


def normalize_tag_filters(tags: list[str] | None) -> list[str]:
    if not tags:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized_tag = first_non_blank(tag)
        if normalized_tag is None:
            continue
        lowered = normalized_tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(normalized_tag)
    return normalized


def normalize_remote_tags(raw_tags: Any) -> list[str]:
    if not isinstance(raw_tags, list):
        return []
    return [tag.strip() for tag in raw_tags if isinstance(tag, str) and tag.strip()]


def compare_semver(left: str, right: str) -> int:
    left_parts = parse_semver(left)
    right_parts = parse_semver(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ScriptError(f"Nieprawidłowa wersja semver: {value}")
    return tuple(int(part) for part in match.groups())


def collect_local_skill_versions(skills_dir: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    if not skills_dir.is_dir():
        return versions
    for path in sorted(skills_dir.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_dir():
            continue
        skill_md = path / "SKILL.md"
        if not skill_md.is_file():
            continue
        versions[path.name.lower()] = extract_version(skill_md)
    return versions


def write_new_skill_directory(skills_dir: Path, skill_name: str, files: list[dict[str, Any]]) -> list[str]:
    target_dir = skills_dir / skill_name
    if target_dir.exists():
        raise ScriptError(f"Skill {skill_name} już istnieje lokalnie: {target_dir}")

    normalized_files: list[tuple[str, bytes]] = []
    for file_payload in files:
        relative_path = normalize_relative_path(file_payload["relativePath"])
        if is_python_cache(relative_path):
            continue
        content = base64.b64decode(file_payload["contentBase64"])
        validate_text_encoding(relative_path, file_payload.get("mimeType"), content)
        normalized_files.append((relative_path, content))
    if "SKILL.md" not in {path for path, _ in normalized_files}:
        raise ScriptError(f"Brakuje pliku SKILL.md w paczce skilla {skill_name}")

    written_files: list[str] = []
    for relative_path, content in normalized_files:
        target_path = target_dir / Path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        written_files.append(relative_path)
    return written_files


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


def refresh_instruction_files(config: Config) -> list[dict[str, Any]]:
    skills = inspect_skills(config.skills_dir)
    source_content = load_best_instruction_source(config)
    project_label = resolve_project_label(config)
    changes: list[dict[str, Any]] = []

    for instruction_type in INSTRUCTION_TYPES:
        path = config.path_by_type[instruction_type]
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
        skills_section = render_skills_section(skills, relative_to=path.parent)
        updated = ensure_instruction_support(
            instruction_type=instruction_type,
            current_content=existing,
            source_content=source_content,
            project_label=project_label,
            skills_section=skills_section,
        )
        if existing == updated:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        changes.append(
            {
                "type": instruction_type,
                "path": str(path),
                "action": "create" if existing is None else "update",
            }
        )

    return changes


def inspect_skills(skills_dir: Path) -> list[SkillEntry]:
    skills: list[SkillEntry] = []
    if not skills_dir.is_dir():
        return skills

    for child in sorted(skills_dir.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        content = skill_md.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)
        name = frontmatter.get("name", child.name).strip() or child.name
        description = normalize_whitespace(frontmatter.get("description", "Brak opisu w frontmatter SKILL.md"))
        skills.append(SkillEntry(name=name, description=description, skill_md_path=skill_md))

    return skills


def render_skills_section(skills: list[SkillEntry], *, relative_to: Path) -> str:
    lines = [
        "## Skille",
        "Skill to lokalny zestaw instrukcji zapisany w pliku `SKILL.md`.",
        "",
        "### Dostępne skille",
    ]

    if skills:
        for skill in skills:
            path = relative_instruction_path(relative_to, skill.skill_md_path)
            lines.append(f"- {skill.name}: {skill.description} (file: {path})")
    else:
        lines.append("- Brak lokalnych skilli w katalogu `skills/`.")

    lines.append("")
    lines.append("### Jak używać skilli")
    for rule in USAGE_RULES:
        lines.append(f"- {rule}")
    return "\n".join(lines)


def relative_instruction_path(base_dir: Path, target_path: Path) -> str:
    try:
        relative_path = os.path.relpath(target_path.resolve(), start=base_dir.resolve())
    except ValueError as exc:
        raise ScriptError(
            f"Nie da się wyznaczyć względnej ścieżki z {base_dir} do {target_path}."
        ) from exc
    return Path(relative_path).as_posix()


def ensure_instruction_support(
    *,
    instruction_type: str,
    current_content: str | None,
    source_content: str | None,
    project_label: str,
    skills_section: str,
) -> str:
    if current_content is None:
        base_content = create_instruction_template(instruction_type, project_label)
        if source_content is not None:
            base_content = retitle_instruction(source_content, instruction_type, project_label)
    else:
        base_content = current_content

    newline = detect_newline(base_content)
    normalized = retitle_instruction(base_content, instruction_type, project_label)
    normalized = upsert_skills_section(normalized, skills_section, newline)
    return normalized


def load_best_instruction_source(config: Config) -> str | None:
    for instruction_type in INSTRUCTION_TYPES:
        path = config.path_by_type[instruction_type]
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def retitle_instruction(content: str, instruction_type: str, project_label: str) -> str:
    title = f"# Instrukcje {INSTRUCTION_FILENAMES[instruction_type]} dla {project_label}"
    if TITLE_PATTERN.search(content):
        return TITLE_PATTERN.sub(title, content, count=1)

    newline = detect_newline(content)
    if content.startswith("# WERSJA"):
        parts = content.splitlines()
        if len(parts) >= 2:
            rebuilt = [parts[0], "", title]
            tail = parts[1:]
            while tail and not tail[0].strip():
                tail = tail[1:]
            rebuilt.extend(tail)
            return newline.join(rebuilt)
    return content.rstrip() + newline + newline + title + newline


def upsert_skills_section(content: str, skills_section: str, newline: str) -> str:
    rendered_section = skills_section.replace("\n", newline)
    match = INSTRUCTIONS_BLOCK_PATTERN.search(content)
    if match:
        body = match.group(2).strip()
        if SKILLS_SECTION_PATTERN.search(body):
            updated_body = SKILLS_SECTION_PATTERN.sub(rendered_section, body, count=1)
        else:
            updated_body = body + (newline + newline if body else "") + rendered_section
        rebuilt_block = match.group(1) + updated_body + match.group(3)
        return content[:match.start()] + rebuilt_block + content[match.end():]

    if SKILLS_SECTION_PATTERN.search(content):
        return SKILLS_SECTION_PATTERN.sub(rendered_section, content, count=1)

    suffix = "" if content.endswith(newline) else newline
    return (
        content.rstrip()
        + suffix
        + newline
        + "<INSTRUCTIONS>"
        + newline
        + rendered_section
        + newline
        + "</INSTRUCTIONS>"
        + newline
    )


def create_instruction_template(instruction_type: str, project_label: str) -> str:
    return "\n".join(
        [
            "# WERSJA 1.0.0",
            "",
            f"# Instrukcje {INSTRUCTION_FILENAMES[instruction_type]} dla {project_label}",
            "",
            "<INSTRUCTIONS>",
            "</INSTRUCTIONS>",
            "",
        ]
    )


def detect_newline(content: str) -> str:
    return "\r\n" if "\r\n" in content else "\n"


def parse_frontmatter(content: str) -> dict[str, str]:
    match = FRONTMATTER_PATTERN.match(content.lstrip("\ufeff"))
    if not match:
        return {}
    values: dict[str, str] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line or line.startswith("#"):
            index += 1
            continue
        key, separator, value = line.partition(":")
        if not separator:
            index += 1
            continue
        normalized_value = value.strip()
        if normalized_value.startswith((">", "|")):
            block_lines: list[str] = []
            parent_indent = len(raw_line) - len(raw_line.lstrip(" "))
            index += 1
            while index < len(lines):
                nested_raw_line = lines[index]
                nested_line = nested_raw_line.strip()
                nested_indent = len(nested_raw_line) - len(nested_raw_line.lstrip(" "))
                if nested_line and nested_indent <= parent_indent:
                    break
                block_lines.append(nested_raw_line.lstrip())
                index += 1
            values[key.strip()] = "\n".join(block_lines).strip()
            continue
        values[key.strip()] = normalized_value.strip("'\"")
        index += 1
    return values


def extract_version(skill_md_path: Path) -> str:
    if not skill_md_path.is_file():
        raise ScriptError(f"Brakuje pliku SKILL.md: {skill_md_path}")
    content = skill_md_path.read_text(encoding="utf-8")
    frontmatter_version = extract_frontmatter_field(content, "version")
    if frontmatter_version is not None:
        return frontmatter_version
    match = VERSION_PATTERN.search(content)
    if not match:
        raise ScriptError(f"Brakuje frontmatter version w {skill_md_path}")
    return match.group(1)


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
    normalized = raw_path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        raise ScriptError("Pusta ścieżka w payloadzie")
    if normalized.startswith("/") or PARENT_PATH_PATTERN.search(normalized):
        raise ScriptError(f"Nieprawidłowa ścieżka w payloadzie: {raw_path}")
    return normalized


def load_config(repo_root: Path) -> Config:
    raw_config = parse_simple_yaml(repo_root / ".agent-library.yaml")
    base_url = expect_string(raw_config, "libraryBaseUrl").rstrip("/")
    project_slug = raw_config.get("projectSlug") if isinstance(raw_config.get("projectSlug"), str) else None
    paths = expect_dict(raw_config, "paths")
    return Config(
        repo_root=repo_root,
        base_url=base_url,
        project_slug=project_slug.strip() if project_slug else None,
        skills_dir=repo_root / expect_string(paths, "skillsDir"),
        path_by_type={
            "AGENTS": repo_root / expect_string(paths, "agents"),
            "CLAUDE": repo_root / expect_string(paths, "claude"),
            "GEMINI": repo_root / expect_string(paths, "gemini"),
        },
        library_user_id=load_required_library_user_id(),
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
        query = {key: value for key, value in query.items() if value is not None}
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)

    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            response_bytes = response.read()
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise ScriptError(f"HTTP {exc.code} dla {path}: {extract_error_message(response_text)}") from exc
    except urllib.error.URLError as exc:
        raise ScriptError(f"Nie udało się połączyć z biblioteką: {exc.reason}") from exc

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


def resolve_project_label(config: Config) -> str:
    if config.project_slug and "/" in config.project_slug:
        return config.project_slug.split("/")[-1]
    if config.project_slug:
        return config.project_slug
    return config.repo_root.name


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def first_non_blank(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip():
            return value.strip()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
