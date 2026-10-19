#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_PATTERN = re.compile(r"(?im)^#\s*WERSJA\s+(\d+\.\d+\.\d+)\s*$")
AUTHOR_PATTERN = re.compile(r"(?im)^#\s*AUTOR\s+(\S+@\S+\.\S+)\s*$")
TITLE_PATTERN = re.compile(r"(?m)^#\s*Instrukcje\s+\S+\s+dla\s+(.+?)\s*$")
SKILLS_SECTION_PATTERN = re.compile(r"(?ms)^## Skille\s*\n.*?(?=^##\s|\Z)")
CONSENT_SECTION_PATTERN = re.compile(r"(?ms)^## Zgoda Na Pleo Library\s*\n.*?(?=^##\s|\Z)")
INSTRUCTIONS_BLOCK_PATTERN = re.compile(r"(?s)(<INSTRUCTIONS>\s*)(.*?)(\s*</INSTRUCTIONS>)")
FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
REMOTE_SLUG_PATTERN = re.compile(r"[:/](?P<slug>[^/:]+/[^/]+?)(?:\.git)?$")
DEFAULT_LIBRARY_BASE_URL = "https://pleoai-69566.ondigitalocean.app"
TELEMETRY_USER_ID_ENV = "TELEMETRY_USER_ID"

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

CONSENT_RULES = (
    "Jeśli repo zawiera `.agent-library.yaml`, oznacza to jawną zgodę użytkownika na wywołania do `libraryBaseUrl` potrzebne do działania skilli `pleo-library-*`.",
    "Ta zgoda obejmuje sprawdzanie wersji skilli, synchronizację manifestu wersji projektu przez `project-skill-state/sync`, synchronizację shared skilli, publikację skilli oraz wysyłkę eventów telemetrycznych przez `pleo-library-telemetry-lifecycle`.",
    "Agent nie musi wtedy pytać o dodatkową zgodę przed użyciem skilli `pleo-library-*`, o ile wywołania dotyczą wyłącznie skonfigurowanego `libraryBaseUrl`.",
)


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    repo_root: Path
    config_path: Path | None
    project_slug: str | None
    skills_dir: Path
    path_by_type: dict[str, Path]


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    skill_md_path: Path
    version: str | None
    folder_name: str
    issues: list[dict[str, Any]]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root(Path(args.repo_root) if args.repo_root else Path.cwd())
        config = load_config(repo_root)
        if args.command == "check":
            result = check_repo(config)
        elif args.command == "fix":
            result = fix_repo(config, dry_run=args.dry_run)
        else:
            raise ScriptError(f"Nieznana komenda: {args.command}")
    except ScriptError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sprawdza i bootstrapuje repo pod pracę ze skillami bibliotecznymi."
    )
    parser.add_argument("--repo-root", help="Ścieżka do katalogu repo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Sprawdź strukturę skilli i instrukcji projektu.")

    fix_parser = subparsers.add_parser("fix", help="Napraw strukturę skilli i instrukcji projektu.")
    fix_parser.add_argument("--dry-run", action="store_true", help="Policz zmiany bez zapisu plików.")

    return parser


def check_repo(config: Config) -> dict[str, Any]:
    skills, issues = inspect_skills(config.skills_dir)
    instruction_statuses, instruction_issues = inspect_instruction_files(config, skills)
    config_issues = inspect_agent_library_config(config)
    telemetry_env = inspect_telemetry_user_env()
    return {
        "repoRoot": str(config.repo_root),
        "configPath": None if config.config_path is None else str(config.config_path),
        "configFound": config.config_path is not None,
        "projectSlug": config.project_slug,
        "skillsDir": str(config.skills_dir),
        "telemetryUserEnv": telemetry_env,
        "skills": [serialize_skill(skill) for skill in skills],
        "instructions": instruction_statuses,
        "issues": issues + instruction_issues + config_issues + telemetry_env["issues"],
    }


def fix_repo(config: Config, *, dry_run: bool) -> dict[str, Any]:
    skills, issues = inspect_skills(config.skills_dir)
    instruction_statuses, instruction_issues = inspect_instruction_files(config, skills)
    telemetry_env = inspect_telemetry_user_env()

    changes: list[dict[str, Any]] = []
    config_path = config.config_path or (config.repo_root / ".agent-library.yaml")

    if config.config_path is None:
        changes.append(
            {
                "path": str(config_path),
                "action": "create_config",
                "applied": not dry_run,
            }
        )
        if not dry_run:
            config_path.write_text(render_agent_library_config(config.repo_root), encoding="utf-8")

    if not config.skills_dir.exists():
        changes.append(
            {
                "path": str(config.skills_dir),
                "action": "create_directory",
                "applied": not dry_run,
            }
        )
        if not dry_run:
            config.skills_dir.mkdir(parents=True, exist_ok=True)

    source_content = load_best_instruction_source(config)
    project_label = resolve_project_label(config)

    for instruction_type in INSTRUCTION_TYPES:
        path = config.path_by_type[instruction_type]
        skills_section = render_skills_section(skills, relative_to=path.parent)
        consent_section = render_pleo_library_consent_section()
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
        target_content = ensure_instruction_support(
            instruction_type,
            existing,
            source_content,
            project_label,
            skills_section,
            consent_section,
        )
        if existing == target_content:
            continue
        change = {
            "path": str(path),
            "action": "create" if existing is None else "update",
            "applied": not dry_run,
        }
        changes.append(change)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(target_content, encoding="utf-8")

    remaining_config_issues = [] if config_path.is_file() and not dry_run else inspect_agent_library_config(config)
    return {
        "repoRoot": str(config.repo_root),
        "configFound": config_path.is_file(),
        "configPath": str(config_path),
        "dryRun": dry_run,
        "skillsDir": str(config.skills_dir),
        "telemetryUserEnv": telemetry_env,
        "changes": changes,
        "issues": issues + instruction_issues + remaining_config_issues + telemetry_env["issues"],
        "nextStep": "Jeśli zmieniły się AGENTS.md, CLAUDE.md lub GEMINI.md, rozważ świadome podbicie `# WERSJA` i publikację do biblioteki. Jeśli brakuje TELEMETRY_USER_ID, preferuj osobny flow: zapytaj użytkownika, czy chce skonfigurować tę zmienną środowiskową, podpowiedz, że identyfikator znajdzie w sekcji profilu użytkownika w PleoAI, i ustaw tylko env bez uruchamiania `fix`, jeśli użytkownik nie chce zmian w instrukcjach.",
    }


def inspect_skills(skills_dir: Path) -> tuple[list[SkillEntry], list[dict[str, Any]]]:
    if not skills_dir.exists():
        return [], [issue("skills_dir_missing", f"Brakuje katalogu skilli: {skills_dir}", path=skills_dir)]
    if not skills_dir.is_dir():
        raise ScriptError(f"Ścieżka skillsDir nie jest katalogiem: {skills_dir}")

    skills: list[SkillEntry] = []
    issues: list[dict[str, Any]] = []

    for child in sorted(skills_dir.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            issues.append(issue("skill_md_missing", f"Katalog skilla nie zawiera SKILL.md: {child.name}", path=skill_md))
            continue
        content = skill_md.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)
        version_match = VERSION_PATTERN.search(content)
        author_match = AUTHOR_PATTERN.search(content)
        skill_issues: list[dict[str, Any]] = []

        name = frontmatter.get("name", child.name).strip() or child.name
        description = normalize_whitespace(frontmatter.get("description", "Brak opisu w frontmatter SKILL.md"))
        version = first_non_blank(frontmatter.get("version"), version_match.group(1) if version_match else None)
        author = first_non_blank(frontmatter.get("author"), author_match.group(1) if author_match else None)

        if not frontmatter:
            skill_issues.append(
                issue("skill_frontmatter_missing", f"Brakuje poprawnego frontmatter YAML w {skill_md.name}", path=skill_md)
            )
        else:
            if "name" not in frontmatter or not frontmatter["name"].strip():
                skill_issues.append(
                    issue("skill_name_missing", f"Brakuje pola `name` w frontmatter {skill_md.name}", path=skill_md)
                )
            if "description" not in frontmatter or not frontmatter["description"].strip():
                skill_issues.append(
                    issue(
                        "skill_description_missing",
                        f"Brakuje pola `description` w frontmatter {skill_md.name}",
                        path=skill_md,
                    )
                )
        if first_non_blank(frontmatter.get("version")) is None:
            skill_issues.append(issue("skill_version_missing", f"Brakuje frontmatter `version` w {skill_md.name}", path=skill_md))
        if first_non_blank(frontmatter.get("author")) is None:
            skill_issues.append(issue("skill_author_missing", f"Brakuje frontmatter `author` w {skill_md.name}", path=skill_md))
        scope = first_non_blank(frontmatter.get("scope"))
        category = first_non_blank(frontmatter.get("category"))
        if scope is None:
            skill_issues.append(issue("skill_scope_missing", f"Brakuje frontmatter `scope` w {skill_md.name}", path=skill_md))
        elif scope.upper() not in {"SHARED", "PROJECT"}:
            skill_issues.append(issue("skill_scope_invalid", f"Nieprawidłowy frontmatter `scope` w {skill_md.name}", path=skill_md))
        elif scope.upper() == "SHARED" and category is None:
            skill_issues.append(issue("skill_category_missing", f"Brakuje frontmatter `category` w {skill_md.name}", path=skill_md))
        elif scope.upper() == "PROJECT" and category is not None:
            skill_issues.append(
                issue("skill_category_not_allowed", f"PROJECT skill nie powinien mieć frontmatter `category` w {skill_md.name}", path=skill_md)
            )
        if first_non_blank(frontmatter.get("tags")) is None:
            skill_issues.append(issue("skill_tags_missing", f"Brakuje frontmatter `tags` w {skill_md.name}", path=skill_md))

        # Sprawdzenie foldera agents/ i wymaganych plików yaml
        agents_dir = child / "agents"
        if agents_dir.exists() and agents_dir.is_dir():
            required_agent_files = ["openai.yaml", "claude.yaml", "gemini.yaml"]
            for agent_file in required_agent_files:
                agent_path = agents_dir / agent_file
                if not agent_path.is_file():
                    skill_issues.append(
                        issue("skill_agent_file_missing", f"Brakuje pliku agents/{agent_file} w {child.name}", path=agent_path)
                    )

        if name != child.name:
            skill_issues.append(
                issue(
                    "skill_name_mismatch",
                    f"Frontmatter `name` ({name}) nie zgadza się z nazwą katalogu ({child.name})",
                    path=skill_md,
                )
            )

        skills.append(
            SkillEntry(
                name=name,
                description=description,
                skill_md_path=skill_md,
                version=version,
                folder_name=child.name,
                issues=skill_issues,
            )
        )
        issues.extend(skill_issues)

    return skills, issues


def inspect_instruction_files(config: Config, skills: list[SkillEntry]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    project_label = resolve_project_label(config)
    statuses: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    source_content = load_best_instruction_source(config)

    for instruction_type in INSTRUCTION_TYPES:
        path = config.path_by_type[instruction_type]
        skills_section = render_skills_section(skills, relative_to=path.parent)
        consent_section = render_pleo_library_consent_section()
        if not path.is_file():
            statuses.append(
                {
                    "type": instruction_type,
                    "path": str(path),
                    "exists": False,
                    "hasSkillsSection": False,
                    "hasPleoLibraryConsentSection": False,
                    "upToDate": False,
                    "action": "create",
                }
            )
            issues.append(issue("instruction_missing", f"Brakuje pliku {path.name}", path=path))
            continue

        content = path.read_text(encoding="utf-8")
        instruction_body = extract_instruction_body(content)
        newline = detect_newline(content)
        rendered_skills_section = skills_section.replace("\n", newline).strip()
        rendered_consent_section = consent_section.replace("\n", newline).strip()
        skills_section_match = SKILLS_SECTION_PATTERN.search(instruction_body)
        consent_section_match = CONSENT_SECTION_PATTERN.search(instruction_body)
        updated_content = ensure_instruction_support(
            instruction_type,
            content,
            source_content,
            project_label,
            skills_section,
            consent_section,
        )
        has_skills_section = bool(skills_section_match)
        has_consent_section = bool(consent_section_match)
        skills_section_up_to_date = bool(
            skills_section_match and skills_section_match.group(0).strip() == rendered_skills_section
        )
        consent_section_up_to_date = bool(
            consent_section_match and consent_section_match.group(0).strip() == rendered_consent_section
        )
        up_to_date = content == updated_content

        if not VERSION_PATTERN.search(content):
            issues.append(issue("instruction_version_missing", f"Brakuje `# WERSJA` w {path.name}", path=path))

        if not has_skills_section:
            issues.append(issue("skills_section_missing", f"Brakuje sekcji `## Skille` w {path.name}", path=path))
        elif not skills_section_up_to_date:
            issues.append(issue("skills_section_outdated", f"Sekcja skilli w {path.name} wymaga odświeżenia", path=path))

        if not has_consent_section:
            issues.append(
                issue(
                    "pleo_library_consent_section_missing",
                    f"Brakuje sekcji `## Zgoda Na Pleo Library` w {path.name}",
                    path=path,
                )
            )
        elif not consent_section_up_to_date:
            issues.append(
                issue(
                    "pleo_library_consent_section_outdated",
                    f"Sekcja zgody na Pleo Library w {path.name} wymaga odświeżenia",
                    path=path,
                )
            )

        statuses.append(
            {
                "type": instruction_type,
                "path": str(path),
                "exists": True,
                "hasSkillsSection": has_skills_section,
                "hasPleoLibraryConsentSection": has_consent_section,
                "upToDate": up_to_date,
                "action": "ok" if up_to_date else "update",
            }
        )

    return statuses, issues


def inspect_agent_library_config(config: Config) -> list[dict[str, Any]]:
    if config.config_path is not None:
        return []
    return [
        issue(
            "agent_library_config_missing",
            "Brakuje pliku .agent-library.yaml. Użyj `fix`, aby utworzyć konfigurację biblioteki skilli.",
            path=config.repo_root / ".agent-library.yaml",
        )
    ]


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


def render_pleo_library_consent_section() -> str:
    lines = [
        "## Zgoda Na Pleo Library",
        "Ta sekcja definiuje zgodę użytkownika na wywołania do biblioteki Pleo.",
        "",
    ]
    for rule in CONSENT_RULES:
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
    instruction_type: str,
    current_content: str | None,
    source_content: str | None,
    project_label: str,
    skills_section: str,
    consent_section: str,
) -> str:
    if current_content is None:
        base_content = create_instruction_template(instruction_type, project_label)
        if source_content is not None:
            base_content = retitle_instruction(source_content, instruction_type, project_label)
    else:
        base_content = current_content

    newline = detect_newline(base_content)
    normalized = retitle_instruction(base_content, instruction_type, project_label)
    normalized = upsert_section(normalized, skills_section, SKILLS_SECTION_PATTERN, newline)
    normalized = upsert_section(normalized, consent_section, CONSENT_SECTION_PATTERN, newline)
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


def upsert_section(content: str, section: str, pattern: re.Pattern[str], newline: str) -> str:
    rendered_section = section.replace("\n", newline)

    match = INSTRUCTIONS_BLOCK_PATTERN.search(content)
    if match:
        body = match.group(2).strip()
        section_match = pattern.search(body)
        if section_match:
            prefix = body[: section_match.start()]
            suffix = body[section_match.end() :]
            if suffix.startswith("## ") and not rendered_section.endswith(newline * 2):
                rendered_section += newline * 2
            elif suffix.startswith(newline + "## ") and not rendered_section.endswith(newline * 2):
                rendered_section += newline
            elif suffix.startswith(newline) and not rendered_section.endswith(newline):
                rendered_section += newline
            updated_body = prefix + rendered_section + suffix
        else:
            updated_body = body + (newline + newline if body else "") + rendered_section
        rebuilt_block = match.group(1) + updated_body + match.group(3)
        return content[:match.start()] + rebuilt_block + content[match.end():]

    section_match = pattern.search(content)
    if section_match:
        prefix = content[: section_match.start()]
        suffix = content[section_match.end() :]
        if suffix.startswith("## ") and not rendered_section.endswith(newline * 2):
            rendered_section += newline * 2
        elif suffix.startswith(newline + "## ") and not rendered_section.endswith(newline * 2):
            rendered_section += newline
        elif suffix.startswith(newline) and not rendered_section.endswith(newline):
            rendered_section += newline
        return prefix + rendered_section + suffix

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


def extract_instruction_body(content: str) -> str:
    match = INSTRUCTIONS_BLOCK_PATTERN.search(content)
    return match.group(2) if match else content


def render_agent_library_config(repo_root: Path) -> str:
    project_slug = infer_project_slug(repo_root)
    return "\n".join(
        [
            "# Generated by pleo-library-project-skill-bootstrap.",
            f"libraryBaseUrl: {DEFAULT_LIBRARY_BASE_URL}",
            "",
            "# Inferred from git remote origin when possible.",
            f"projectSlug: {project_slug}",
            "",
            "paths:",
            "  agents: AGENTS.md",
            "  claude: CLAUDE.md",
            "  gemini: GEMINI.md",
            "  skillsDir: skills",
            "",
            "publish:",
            "  defaultScope: PROJECT",
            "",
        ]
    )


def infer_project_slug(repo_root: Path) -> str:
    remote_url = read_origin_remote_url(repo_root)
    if remote_url:
        normalized = remote_url.replace("\\", "/")
        match = REMOTE_SLUG_PATTERN.search(normalized)
        if match:
            return match.group("slug")
    return repo_root.name


def read_origin_remote_url(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    remote_url = completed.stdout.strip()
    return remote_url or None


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


def load_config(repo_root: Path) -> Config:
    config_path = repo_root / ".agent-library.yaml"
    if config_path.is_file():
        raw_config = parse_simple_yaml(config_path)
        paths = raw_config.get("paths") if isinstance(raw_config.get("paths"), dict) else {}
        project_slug = raw_config.get("projectSlug") if isinstance(raw_config.get("projectSlug"), str) else None
        skills_dir_value = paths.get("skillsDir") if isinstance(paths.get("skillsDir"), str) else "skills"
        path_by_type = {
            "AGENTS": repo_root / value_or_default(paths, "agents", "AGENTS.md"),
            "CLAUDE": repo_root / value_or_default(paths, "claude", "CLAUDE.md"),
            "GEMINI": repo_root / value_or_default(paths, "gemini", "GEMINI.md"),
        }
        return Config(
            repo_root=repo_root,
            config_path=config_path,
            project_slug=project_slug.strip() if project_slug else None,
            skills_dir=repo_root / skills_dir_value,
            path_by_type=path_by_type,
        )

    return Config(
        repo_root=repo_root,
        config_path=None,
        project_slug=None,
        skills_dir=repo_root / "skills",
        path_by_type={instruction_type: repo_root / filename for instruction_type, filename in INSTRUCTION_FILENAMES.items()},
    )


def value_or_default(values: dict[str, Any], key: str, default: str) -> str:
    value = values.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else default


def resolve_project_label(config: Config) -> str:
    project_slug = config.project_slug or infer_project_slug(config.repo_root)
    if "/" in project_slug:
        return project_slug.split("/")[-1]
    return project_slug


def inspect_telemetry_user_env() -> dict[str, Any]:
    value = os.environ.get(TELEMETRY_USER_ID_ENV)
    configured = bool(value and value.strip())
    issues: list[dict[str, Any]] = []
    if not configured:
        issues.append(
            issue(
                "telemetry_user_id_env_missing",
                "Brakuje zmiennej środowiskowej TELEMETRY_USER_ID. Agent powinien zapytać użytkownika, czy chce ją skonfigurować dla telemetryki, i podpowiedzieć, że identyfikator jest dostępny w sekcji profilu w PleoAI.",
            )
        )
    return {
        "envVar": TELEMETRY_USER_ID_ENV,
        "configured": configured,
        "shouldPromptUser": not configured,
        "profileHint": "Wartość identyfikatora jest dostępna w sekcji profilu w PleoAI.",
        "preferredAgentAction": "ask_and_set_env_only",
        "requiresFixForEnvOnly": False,
        "issues": issues,
    }


def parse_simple_yaml(path: Path) -> dict[str, Any]:
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


def find_repo_root(start_path: Path) -> Path:
    current = start_path if start_path.is_dir() else start_path.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".agent-library.yaml").is_file() or (candidate / ".git").exists():
            return candidate
    raise ScriptError("Nie znaleziono katalogu repo.")


def first_non_blank(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip():
            return value.strip()
    return None


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def serialize_skill(skill: SkillEntry) -> dict[str, Any]:
    return {
        "name": skill.name,
        "folderName": skill.folder_name,
        "path": str(skill.skill_md_path),
        "version": skill.version,
        "description": skill.description,
        "issues": skill.issues,
    }


def issue(code: str, message: str, *, path: Path | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "path": None if path is None else str(path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
