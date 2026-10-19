#!/usr/bin/env python3
"""CLI helper for spec-review, pre-spec, and specification storage operations."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import error, parse, request


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_CONFIG_PATH = ".agent-library.yaml"
DEFAULT_SDD_ROOT = Path("docs") / "sdd"
DEFAULT_VERSIONING_FILE = DEFAULT_SDD_ROOT / "versioning.md"
TELEMETRY_USER_ID_ENV = "TELEMETRY_USER_ID"
FEATURE_SLUG_PATTERN = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?Feature slug:\s*`?([^`\r\n]+?)`?\s*$"
)
VERSION_PATTERN = re.compile(
    r"(?im)^\s*#\s*WERSJA\s+([0-9]+(?:\.[0-9]+){0,3})\s*$"
)
REMOTE_VERSION_FILE_PATTERN = re.compile(
    r"^specification-([0-9]+(?:\.[0-9]+){0,3})\.md$",
    re.IGNORECASE,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and update pre-spec/spec-review workflows and archived spec versions."
    )
    parser.add_argument("--bearer-token", help="Bearer token. Falls back to PLEO_SPEC_WORKFLOW_BEARER_TOKEN.")
    parser.add_argument("--basic-user", help="Basic auth username. Falls back to PLEO_SPEC_WORKFLOW_BASIC_USER.")
    parser.add_argument("--basic-password", help="Basic auth password. Falls back to PLEO_SPEC_WORKFLOW_BASIC_PASSWORD.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Compare local specs with archived versions in storage.")
    status_parser.add_argument("--project-slug", help="Project slug/folder used in storage. Defaults to .agent-library.yaml projectSlug.")
    status_parser.add_argument(
        "--versioning-file",
        default=str(DEFAULT_VERSIONING_FILE),
        help="Path to docs/sdd/versioning.md with 'featureSlug: version' entries.",
    )

    bootstrap_parser = subparsers.add_parser(
        "bootstrap-storage",
        help="Upload current local specification files and story files into storage for all features from versioning.md.",
    )
    bootstrap_parser.add_argument("--project-slug", help="Project slug/folder used in storage. Defaults to .agent-library.yaml projectSlug.")
    bootstrap_parser.add_argument(
        "--versioning-file",
        default=str(DEFAULT_VERSIONING_FILE),
        help="Path to docs/sdd/versioning.md with 'featureSlug: version' entries.",
    )
    bootstrap_parser.add_argument(
        "--feature-slug",
        help="Optional single feature slug to archive without scanning the whole versioning file.",
    )
    bootstrap_parser.add_argument(
        "--expected-version",
        help="Optional version override for --feature-slug. Skips lookup in versioning.md when provided.",
    )
    bootstrap_mode_group = bootstrap_parser.add_mutually_exclusive_group()
    bootstrap_mode_group.add_argument(
        "--specification-only",
        action="store_true",
        help="Archive only specification.md/spec.md for the selected --feature-slug.",
    )
    bootstrap_mode_group.add_argument(
        "--include-stories",
        action="store_true",
        help="Also archive local story-*.md files for the selected --feature-slug.",
    )
    bootstrap_parser.add_argument(
        "--confirm-upload",
        action="store_true",
        help="Required safety switch for direct storage upload.",
    )

    get_parser = subparsers.add_parser("get", help="Download the current workflow file by Jira key.")
    get_parser.add_argument("--jira-key", required=True, help="Jira key of the active spec-review workflow.")
    get_parser.add_argument("--output", required=True, help="Destination file path or directory.")
    get_parser.add_argument(
        "--confirm-local-write",
        action="store_true",
        help="Required safety switch for writing into the final local spec path.",
    )

    workflow_info_parser = subparsers.add_parser(
        "workflow-info", help="Read workflow metadata, including documentType, without downloading or writing files."
    )
    workflow_info_parser.add_argument("--jira-key", required=True, help="Jira key of the spec-review workflow.")

    workflow_pull_parser = subparsers.add_parser(
        "workflow-pull",
        help="Download currentFile for typed workflows; optionally fetch affected main specs. Legacy untyped workflows may also fetch sourceFile.",
    )
    workflow_pull_parser.add_argument("--jira-key", required=True, help="Jira key of the active spec-review workflow.")
    workflow_pull_parser.add_argument(
        "--output-dir",
        help="Optional directory for downloaded workflow files. Defaults to canonical docs/sdd paths when omitted.",
    )
    workflow_pull_parser.add_argument(
        "--with-affected",
        action="store_true",
        help="Also pull affectedSpecifications to the latest archived version when available.",
    )
    workflow_pull_parser.add_argument(
        "--confirm-local-write",
        action="store_true",
        help="Required safety switch for overwriting local files or writing into canonical spec paths.",
    )

    spec_task_context_parser = subparsers.add_parser(
        "spec-task-context",
        help="Fetch context for a [SPEC] Jira task created from an approved story workflow.",
    )
    spec_task_context_parser.add_argument("--jira-key", required=True, help="Jira key of the [SPEC] task.")

    prespec_context_parser = subparsers.add_parser(
        "prespec-context",
        help="Fetch Jira context and the current pre-spec workflow state by Jira key.",
    )
    prespec_context_parser.add_argument("--jira-key", required=True, help="Jira key used by the pre-spec workflow.")
    prespec_context_parser.add_argument(
        "--include-outdated",
        action="store_true",
        help="Include questions invalidated by current code. Intended only for continuing a pre-spec audit.",
    )

    prespec_start_parser = subparsers.add_parser(
        "prespec-start",
        help="Start or resume a pre-spec workflow from a locally prepared structured payload.",
    )
    prespec_start_parser.add_argument("--jira-key", required=True, help="Jira key used by the pre-spec workflow.")
    prespec_start_parser.add_argument(
        "--project-slug",
        help="Origin project slug. Defaults to .agent-library.yaml projectSlug.",
    )
    prespec_start_parser.add_argument(
        "--payload-file",
        required=True,
        help="JSON file containing questions, analysisLimitations and analyzedRepositories.",
    )
    prespec_start_parser.add_argument(
        "--confirm-start",
        action="store_true",
        help="Required safety switch after the user approves the local question preview.",
    )

    pull_storage_parser = subparsers.add_parser(
        "pull-storage",
        help="Download a concrete archived spec file from storage by path.",
    )
    pull_storage_parser.add_argument("--path", required=True, help="Storage path from /api/spec-review/storage/tree.")
    pull_storage_parser.add_argument("--output", required=True, help="Destination file path or directory.")
    pull_storage_parser.add_argument(
        "--versioning-file",
        default=str(DEFAULT_VERSIONING_FILE),
        help="Version registry updated when --output is the canonical specification.md/spec.md path.",
    )
    pull_storage_parser.add_argument(
        "--confirm-local-write",
        action="store_true",
        help="Required safety switch for overwriting local files.",
    )

    publish_parser = subparsers.add_parser("publish", help="Publish exactly one explicitly typed workflow document.")
    add_publish_like_arguments(publish_parser, confirm_flag="--confirm-publish")

    update_parser = subparsers.add_parser("update", help="Replace exactly one document in an active workflow, preserving its type.")
    add_publish_like_arguments(update_parser, confirm_flag="--confirm-update")

    return parser


def add_publish_like_arguments(parser: argparse.ArgumentParser, *, confirm_flag: str) -> None:
    parser.add_argument("--jira-key", required=True, help="Workflow Jira key.")
    parser.add_argument("--project-slug", help="Project slug for publish/update. Defaults to .agent-library.yaml projectSlug.")
    parser.add_argument("--document-type", required=True, choices=("SPECIFICATION", "STORY"),
                        help="Explicit document type, independent of profile, filename and reviewer roles.")
    parser.add_argument("--specification-file", help="Path to local specification.md.")
    parser.add_argument("--story-file", help="Path to the story document; do not also pass specification-file.")
    parser.add_argument(
        "--affected-specifications-file",
        help="Optional JSON file with affectedSpecifications payload.",
    )
    parser.add_argument(
        confirm_flag,
        action="store_true",
        help="Required safety switch for remote workflow changes.",
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        base_url = resolve_base_url()
        headers = build_auth_headers(args)

        if args.command == "status":
            result = inspect_status(
                base_url=base_url,
                project_slug=resolve_project_slug(args.project_slug),
                versioning_file=Path(args.versioning_file).expanduser(),
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "bootstrap-storage":
            result = bootstrap_storage(
                base_url=base_url,
                project_slug=resolve_project_slug(args.project_slug),
                versioning_file=Path(args.versioning_file).expanduser(),
                feature_slug=args.feature_slug,
                expected_version=args.expected_version,
                specification_only=args.specification_only,
                include_stories=args.include_stories,
                confirm_upload=args.confirm_upload,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "get":
            result = download_current_spec(
                base_url=base_url,
                jira_key=args.jira_key,
                output_arg=args.output,
                confirm_local_write=args.confirm_local_write,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "pull-storage":
            result = download_storage_file(
                base_url=base_url,
                storage_path=args.path,
                output_arg=args.output,
                versioning_file=Path(args.versioning_file).expanduser(),
                confirm_local_write=args.confirm_local_write,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "workflow-info":
            result = fetch_workflow_files_metadata(
                base_url=base_url,
                jira_key=normalize_jira_key(args.jira_key),
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "workflow-pull":
            result = download_workflow_bundle(
                base_url=base_url,
                jira_key=args.jira_key,
                output_dir_arg=args.output_dir,
                with_affected=args.with_affected,
                confirm_local_write=args.confirm_local_write,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "spec-task-context":
            result = fetch_spec_task_context(
                base_url=base_url,
                jira_key=args.jira_key,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "prespec-context":
            result = fetch_prespec_context(
                base_url=base_url,
                jira_key=args.jira_key,
                include_outdated=args.include_outdated,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "prespec-start":
            result = start_prespec(
                base_url=base_url,
                jira_key=args.jira_key,
                project_slug=resolve_project_slug(args.project_slug),
                payload_file=args.payload_file,
                confirm_start=args.confirm_start,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "publish":
            result = publish_spec(
                base_url=base_url,
                jira_key=args.jira_key,
                project_slug=resolve_project_slug(args.project_slug),
                specification_file=args.specification_file,
                story_file=args.story_file,
                affected_specifications_file=args.affected_specifications_file,
                document_type=args.document_type,
                confirm_remote=args.confirm_publish,
                headers=headers,
                timeout=args.timeout,
            )
        elif args.command == "update":
            result = update_current_spec(
                base_url=base_url,
                jira_key=args.jira_key,
                project_slug=resolve_project_slug(args.project_slug),
                specification_file=args.specification_file,
                story_file=args.story_file,
                affected_specifications_file=args.affected_specifications_file,
                document_type=args.document_type,
                confirm_remote=args.confirm_update,
                headers=headers,
                timeout=args.timeout,
            )
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SkillError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


def resolve_base_url() -> str:
    base_url = read_library_base_url(Path(DEFAULT_CONFIG_PATH))
    if not base_url or not base_url.strip():
        raise SkillError("Missing base URL. Set libraryBaseUrl in .agent-library.yaml.")
    return base_url.rstrip("/")


def resolve_project_slug(cli_value: Optional[str]) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()
    project_slug = read_config_value(Path(DEFAULT_CONFIG_PATH), "projectSlug")
    if not project_slug:
        raise SkillError("Missing projectSlug. Pass --project-slug or set projectSlug in .agent-library.yaml.")
    return project_slug.strip()


def read_library_base_url(config_path: Path) -> Optional[str]:
    return read_config_value(config_path, "libraryBaseUrl")


def read_config_value(config_path: Path, key: str) -> Optional[str]:
    if not config_path.is_file():
        return None

    try:
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(rf"{re.escape(key)}\s*:\s*(.+)", line)
            if not match:
                continue
            value = match.group(1).strip()
            if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
                value = value[1:-1]
            return value or None
    except OSError as exc:
        raise SkillError(f"Failed to read {config_path}: {exc}") from exc

    return None


def build_auth_headers(args: argparse.Namespace) -> Dict[str, str]:
    bearer_token = args.bearer_token or os.getenv("PLEO_SPEC_WORKFLOW_BEARER_TOKEN")
    basic_user = args.basic_user or os.getenv("PLEO_SPEC_WORKFLOW_BASIC_USER")
    basic_password = args.basic_password or os.getenv("PLEO_SPEC_WORKFLOW_BASIC_PASSWORD")

    headers: Dict[str, str] = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
        return headers

    if basic_user or basic_password:
        if not basic_user or not basic_password:
            raise SkillError("Both basic auth username and password are required.")
        token = base64.b64encode(f"{basic_user}:{basic_password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"

    return headers


def required_library_user_id() -> str:
    value = os.getenv(TELEMETRY_USER_ID_ENV)
    if value is None or not value.strip():
        raise SkillError("Missing TELEMETRY_USER_ID. PleoAI requests must include libraryUserId.")
    return value.strip()


def inspect_status(
    *,
    base_url: str,
    project_slug: str,
    versioning_file: Path,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    if not versioning_file.is_file():
        raise SkillError(f"versioning.md does not exist: {versioning_file}")

    local_specs = read_versioning_file(versioning_file)
    remote_tree = fetch_storage_tree(base_url=base_url, project_slug=project_slug, headers=headers, timeout=timeout)
    remote_versions = extract_remote_versions(remote_tree)
    local_versions = {spec.feature_slug: spec.version for spec in local_specs}
    sdd_root = versioning_file.resolve().parent
    local_files = {
        feature_slug: find_local_specification_path(sdd_root, feature_slug)
        for feature_slug in set(local_versions) | set(remote_versions)
    }

    statuses = []
    outdated = []
    for spec in local_specs:
        remote_info = remote_versions.get(spec.feature_slug)
        local_file = local_files.get(spec.feature_slug)
        local_present = local_file is not None
        latest_remote_version = remote_info.version if remote_info else None
        latest_remote_path = remote_info.path if remote_info else None
        up_to_date = local_present and (
            latest_remote_version is None or compare_versions(spec.version, latest_remote_version) >= 0
        )
        entry = {
            "featureSlug": spec.feature_slug,
            "path": str(spec.path),
            "localFilePath": str(local_file) if local_file is not None else None,
            "localPresent": local_present,
            "localVersion": spec.version,
            "latestRemoteVersion": latest_remote_version,
            "latestRemotePath": latest_remote_path,
            "upToDate": up_to_date,
        }
        statuses.append(entry)
        if local_present and latest_remote_version is not None \
                and compare_versions(spec.version, latest_remote_version) < 0:
            outdated.append(entry)

    remote_specs = []
    missing_local_specs = []
    for feature_slug, remote_info in sorted(remote_versions.items()):
        local_version = local_versions.get(feature_slug)
        local_file = local_files.get(feature_slug)
        local_present = local_file is not None
        up_to_date = local_present and local_version is not None \
            and compare_versions(local_version, remote_info.version) >= 0
        entry = {
            "featureSlug": feature_slug,
            "localFilePath": str(local_file) if local_file is not None else None,
            "localVersion": local_version,
            "latestRemoteVersion": remote_info.version,
            "latestRemotePath": remote_info.path,
            "localPresent": local_present,
            "upToDate": up_to_date,
        }
        remote_specs.append(entry)
        if not local_present:
            missing_local_specs.append(entry)

    specs_to_pull = [entry for entry in remote_specs if not entry["upToDate"]]

    return {
        "ok": True,
        "projectSlug": project_slug,
        "versioningFile": str(versioning_file),
        "specs": statuses,
        "outdatedSpecs": outdated,
        "remoteSpecs": remote_specs,
        "missingLocalSpecs": missing_local_specs,
        "specsToPull": specs_to_pull,
    }


def bootstrap_storage(
    *,
    base_url: str,
    project_slug: str,
    versioning_file: Path,
    feature_slug: Optional[str],
    expected_version: Optional[str],
    specification_only: bool,
    include_stories: bool,
    confirm_upload: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    ensure_remote_confirmed(confirm_upload, "--confirm-upload")
    selected_feature_slug = normalize_optional_feature_slug(feature_slug)
    local_specs = resolve_bootstrap_specs(
        versioning_file=versioning_file,
        feature_slug=selected_feature_slug,
        expected_version=expected_version,
    )
    remote_tree = fetch_storage_tree(base_url=base_url, project_slug=project_slug, headers=headers, timeout=timeout)
    remote_versions = extract_remote_versions(remote_tree)
    include_story_files = should_include_story_files(
        feature_slug=selected_feature_slug,
        specification_only=specification_only,
        include_stories=include_stories,
    )
    resolved_sdd_root = DEFAULT_SDD_ROOT.resolve()

    uploaded = []
    skipped = []
    for spec in local_specs:
        remote_info = remote_versions.get(spec.feature_slug)
        if remote_info is not None and compare_versions(spec.version, remote_info.version) <= 0:
            skipped.append({
                "featureSlug": spec.feature_slug,
                "localVersion": spec.version,
                "latestRemoteVersion": remote_info.version,
                "reason": "remote version is same or newer",
            })
            continue

        specification_path = resolve_local_specification_path(resolved_sdd_root, spec.feature_slug)
        story_paths = resolve_story_paths(resolved_sdd_root, spec.feature_slug) if include_story_files else []
        response = upload_storage_bundle(
            base_url=base_url,
            project_slug=project_slug,
            feature_slug=spec.feature_slug,
            specification_version=spec.version,
            specification_path=specification_path,
            story_paths=story_paths,
            headers=headers,
            timeout=timeout,
        )
        uploaded.append(response)

    return {
        "ok": True,
        "projectSlug": project_slug,
        "versioningFile": str(versioning_file),
        "sddRoot": str(resolved_sdd_root),
        "featureSlug": selected_feature_slug,
        "includeStories": include_story_files,
        "uploaded": uploaded,
        "skipped": skipped,
    }


def download_current_spec(
    *,
    base_url: str,
    jira_key: str,
    output_arg: str,
    confirm_local_write: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    normalized_jira_key = normalize_jira_key(jira_key)
    response = send_request(
        method="GET",
        url=with_library_user_id(build_current_spec_url(base_url, normalized_jira_key)),
        headers=headers,
        timeout=timeout,
    )

    filename = resolve_download_filename(response.headers, normalized_jira_key)
    output_path = resolve_output_path(output_arg, filename)
    feature_slug = extract_feature_slug(response.body)
    writes_to_canonical_spec_path = is_path_within(output_path, DEFAULT_SDD_ROOT)
    ensure_local_write_confirmed(
        output_path=output_path,
        relocated_to_feature_slug=writes_to_canonical_spec_path,
        confirm_local_write=confirm_local_write,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.body)

    return {
        "ok": True,
        "jiraKey": normalized_jira_key,
        "status": response.status,
        "contentType": response.headers.get("Content-Type"),
        "fileName": filename,
        "featureSlug": feature_slug,
        "relocatedToFeatureSlugPath": False,
        "confirmedLocalWrite": confirm_local_write,
        "savedTo": str(output_path),
        "sizeBytes": len(response.body),
    }


def download_workflow_bundle(
    *,
    base_url: str,
    jira_key: str,
    output_dir_arg: Optional[str],
    with_affected: bool,
    confirm_local_write: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    normalized_jira_key = normalize_jira_key(jira_key)
    metadata = fetch_workflow_files_metadata(
        base_url=base_url,
        jira_key=normalized_jira_key,
        headers=headers,
        timeout=timeout,
    )

    tester_workflow = bool(metadata.get("testerWorkflow"))
    document_type = metadata.get("documentType")
    if document_type not in {None, "SPECIFICATION", "STORY"}:
        raise SkillError("Unknown workflow documentType; refusing to choose a local destination.")
    main_specification = document_type == "SPECIFICATION" if document_type else tester_workflow
    current_file = require_workflow_file_metadata(metadata, "currentFile")
    current_response = send_request(
        method="GET",
        url=with_library_user_id(build_current_spec_url(base_url, normalized_jira_key)),
        headers=headers,
        timeout=timeout,
    )

    current_filename = resolve_download_filename(current_response.headers, current_file["fileName"])
    feature_slug = extract_feature_slug(current_response.body)
    current_output_path = resolve_workflow_output_path(
        output_dir_arg=output_dir_arg,
        feature_slug=feature_slug,
        filename=current_filename,
        main_specification_file=main_specification,
    )

    if document_type is not None or tester_workflow:
        saved_files = [save_downloaded_workflow_file(
            body=current_response.body,
            output_path=current_output_path,
            role=current_file["role"],
            filename=current_filename,
            slack_file_id=current_file["slackFileId"],
            confirm_local_write=confirm_local_write,
            relocated_to_feature_slug=output_dir_arg is None and feature_slug is not None,
        )]
    else:
        source_file = require_workflow_file_metadata(metadata, "sourceFile")
        source_response = send_request(
            method="GET",
            url=with_library_user_id(build_source_spec_url(base_url, normalized_jira_key)),
            headers=headers,
            timeout=timeout,
        )
        source_filename = resolve_download_filename(source_response.headers, source_file["fileName"])
        feature_slug = feature_slug or extract_feature_slug(source_response.body)
        source_output_path = resolve_workflow_output_path(
            output_dir_arg=output_dir_arg,
            feature_slug=feature_slug,
            filename=source_filename,
            main_specification_file=True,
        )
        current_output_path = resolve_workflow_output_path(
            output_dir_arg=output_dir_arg,
            feature_slug=feature_slug,
            filename=current_filename,
            main_specification_file=False,
        )

        if source_output_path.resolve() == current_output_path.resolve():
            saved_files = [save_downloaded_workflow_file(
                body=current_response.body,
                output_path=current_output_path,
                role=current_file["role"],
                filename=current_filename,
                slack_file_id=current_file["slackFileId"],
                confirm_local_write=confirm_local_write,
                relocated_to_feature_slug=output_dir_arg is None and feature_slug is not None,
            )]
        else:
            saved_files = [
                save_downloaded_workflow_file(
                    body=source_response.body,
                    output_path=source_output_path,
                    role=source_file["role"],
                    filename=source_filename,
                    slack_file_id=source_file["slackFileId"],
                    confirm_local_write=confirm_local_write,
                    relocated_to_feature_slug=output_dir_arg is None and feature_slug is not None,
                ),
                save_downloaded_workflow_file(
                    body=current_response.body,
                    output_path=current_output_path,
                    role=current_file["role"],
                    filename=current_filename,
                    slack_file_id=current_file["slackFileId"],
                    confirm_local_write=confirm_local_write,
                    relocated_to_feature_slug=output_dir_arg is None and feature_slug is not None,
                ),
            ]

    affected_result = {
        "enabled": with_affected,
        "updated": [],
        "skipped": [],
    }
    if with_affected:
        if main_specification:
            affected_result = {
                "enabled": True,
                "updated": [],
                "skipped": [
                    {
                        "reason": "affectedSpecifications are not pulled for main specification workflow",
                    }
                ],
            }
        else:
            affected_result = pull_affected_specifications(
                base_url=base_url,
                workflow_metadata=metadata,
                confirm_local_write=confirm_local_write,
                headers=headers,
                timeout=timeout,
            )

    return {
        "ok": True,
        "jiraKey": normalized_jira_key,
        "projectSlug": metadata.get("projectSlug"),
        "workflowStatus": metadata.get("workflowStatus"),
        "testerWorkflow": tester_workflow,
        "documentType": document_type,
        "featureSlug": feature_slug,
        "files": saved_files,
        "affectedSpecifications": affected_result,
    }


def save_downloaded_workflow_file(
    *,
    body: bytes,
    output_path: Path,
    role: str,
    filename: str,
    slack_file_id: str,
    confirm_local_write: bool,
    relocated_to_feature_slug: bool,
) -> Dict[str, object]:
    ensure_local_write_confirmed(
        output_path=output_path,
        relocated_to_feature_slug=relocated_to_feature_slug,
        confirm_local_write=confirm_local_write,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(body)
    return {
        "role": role,
        "fileName": filename,
        "savedTo": str(output_path),
        "slackFileId": slack_file_id,
        "sizeBytes": len(body),
    }


def fetch_workflow_files_metadata(
    *,
    base_url: str,
    jira_key: str,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    response = send_request(
        method="GET",
        url=with_library_user_id(build_workflow_files_url(base_url, jira_key)),
        headers=headers,
        timeout=timeout,
    )
    data = parse_json_body(response.body)
    if not isinstance(data, dict):
        raise SkillError("Unexpected response from workflow files endpoint.")
    return data


def require_workflow_file_metadata(workflow_metadata: Dict[str, object], field_name: str) -> Dict[str, str]:
    value = workflow_metadata.get(field_name)
    if not isinstance(value, dict):
        raise SkillError(f"Workflow metadata is missing '{field_name}'.")
    slack_file_id = value.get("slackFileId")
    file_name = value.get("fileName")
    if not isinstance(slack_file_id, str) or not slack_file_id.strip():
        raise SkillError(f"Workflow metadata is missing {field_name}.slackFileId.")
    if not isinstance(file_name, str) or not file_name.strip():
        raise SkillError(f"Workflow metadata is missing {field_name}.fileName.")
    return {
        "role": str(value.get("role") or field_name),
        "slackFileId": slack_file_id,
        "fileName": file_name,
    }


def resolve_workflow_output_path(
    *,
    output_dir_arg: Optional[str],
    feature_slug: Optional[str],
    filename: str,
    main_specification_file: bool,
) -> Path:
    if output_dir_arg:
        return Path(output_dir_arg).expanduser() / filename
    if not feature_slug:
        return Path(filename)

    feature_dir = DEFAULT_SDD_ROOT / feature_slug
    if main_specification_file:
        specification_path = feature_dir / "specification.md"
        if specification_path.is_file():
            return specification_path
        spec_path = feature_dir / "spec.md"
        if spec_path.is_file():
            return spec_path
        return specification_path
    return feature_dir / "task" / filename


def pull_affected_specifications(
    *,
    base_url: str,
    workflow_metadata: Dict[str, object],
    confirm_local_write: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    affected = workflow_metadata.get("affectedSpecifications")
    if not isinstance(affected, list) or not affected:
        return {
            "enabled": True,
            "updated": [],
            "skipped": [],
        }

    local_project_slug = resolve_project_slug(None)
    versioning_path = Path(DEFAULT_VERSIONING_FILE)
    local_versions = read_versioning_file(versioning_path) if versioning_path.is_file() else []
    local_version_map = {spec.feature_slug: spec.version for spec in local_versions}
    tree_by_project: Dict[str, Dict[str, object]] = {}
    updated = []
    skipped = []

    for item in affected:
        if not isinstance(item, dict):
            skipped.append({"reason": "invalid affected specification entry", "entry": item})
            continue

        project_slug = str(item.get("projectSlug") or "").strip()
        feature_slug = str(item.get("featureSlug") or "").strip()
        display_name = str(item.get("displayName") or "").strip() or None
        label = display_name or f"{project_slug}/{feature_slug}"
        if not project_slug or not feature_slug:
            skipped.append({"label": label, "reason": "missing projectSlug or featureSlug"})
            continue
        if project_slug != local_project_slug:
            skipped.append({"label": label, "reason": f"affected spec belongs to different project: {project_slug}"})
            continue

        tree_response = tree_by_project.get(project_slug)
        if tree_response is None:
            tree_response = fetch_storage_tree(
                base_url=base_url,
                project_slug=project_slug,
                headers=headers,
                timeout=timeout,
            )
            tree_by_project[project_slug] = tree_response

        remote_candidate = find_latest_remote_path_for_feature(
            tree_response=tree_response,
            feature_slug=feature_slug,
        )
        if remote_candidate is None:
            skipped.append({"label": label, "reason": "feature was not found in archive"})
            continue
        remote_version, remote_path = remote_candidate

        output_path = resolve_workflow_output_path(
            output_dir_arg=None,
            feature_slug=feature_slug,
            filename="specification.md",
            main_specification_file=True,
        )
        local_version = local_version_map.get(feature_slug)
        if output_path.is_file() and local_version is not None and compare_versions(local_version, remote_version) >= 0:
            skipped.append({
                "label": label,
                "reason": f"local version {local_version} is already up to date",
                "remoteVersion": remote_version,
            })
            continue

        response = send_request(
            method="GET",
            url=with_library_user_id(build_storage_file_url(base_url, remote_path)),
            headers=headers,
            timeout=timeout,
        )
        saved = save_downloaded_workflow_file(
            body=response.body,
            output_path=output_path,
            role="AFFECTED_SPECIFICATION",
            filename=resolve_download_filename(response.headers, Path(remote_path).name),
            slack_file_id="storage:" + remote_path,
            confirm_local_write=confirm_local_write,
            relocated_to_feature_slug=True,
        )
        update_versioning_entry(versioning_path, feature_slug, remote_version)
        local_version_map[feature_slug] = remote_version
        updated.append({
            "label": label,
            "remoteVersion": remote_version,
            "remotePath": remote_path,
            "savedTo": saved["savedTo"],
        })

    return {
        "enabled": True,
        "updated": updated,
        "skipped": skipped,
    }


def find_latest_remote_path_for_feature(
    *,
    tree_response: Dict[str, object],
    feature_slug: str,
) -> Optional[Tuple[str, str]]:
    remote_versions = extract_remote_versions(tree_response)
    remote_info = remote_versions.get(feature_slug)
    if remote_info is None:
        return None
    return remote_info.version, remote_info.path


def storage_path_exists(tree_response: Dict[str, object], expected_path: str) -> bool:
    nodes = tree_response.get("nodes")
    if not isinstance(nodes, list):
        return False
    stack = [node for node in nodes if isinstance(node, dict)]
    while stack:
        node = stack.pop()
        if node.get("path") == expected_path:
            return True
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return False


def update_versioning_entry(versioning_path: Path, feature_slug: str, version: str) -> None:
    lines = []
    replaced = False
    if versioning_path.is_file():
        for raw_line in versioning_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped and not stripped.startswith("#") and ":" in raw_line:
                existing_feature_slug, _existing_version = raw_line.split(":", 1)
                if existing_feature_slug.strip() == feature_slug:
                    lines.append(f"{feature_slug}: {version}")
                    replaced = True
                    continue
            lines.append(raw_line)
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{feature_slug}: {version}")
    versioning_path.parent.mkdir(parents=True, exist_ok=True)
    versioning_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def download_storage_file(
    *,
    base_url: str,
    storage_path: str,
    output_arg: str,
    versioning_file: Path,
    confirm_local_write: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    storage_spec = parse_storage_specification_path(storage_path)
    response = send_request(
        method="GET",
        url=with_library_user_id(build_storage_file_url(base_url, storage_path)),
        headers=headers,
        timeout=timeout,
    )
    filename = resolve_download_filename(response.headers, Path(storage_path).name)
    output_path = resolve_output_path(output_arg, filename)
    versioning_path = versioning_file.resolve()
    sdd_root = versioning_path.parent
    writes_to_sdd_root = is_path_within(output_path, sdd_root)
    updates_versioning = False
    feature_slug = None
    specification_version = None
    if storage_spec is not None:
        feature_slug, specification_version = storage_spec
        canonical_paths = {
            (sdd_root / feature_slug / "specification.md").resolve(),
            (sdd_root / feature_slug / "spec.md").resolve(),
        }
        updates_versioning = output_path.resolve() in canonical_paths
    if writes_to_sdd_root and not updates_versioning:
        if storage_spec is None:
            raise SkillError(
                "Cannot write an archived file into the SDD root because its storage path does not identify "
                "featureSlug and specification version. Use a temporary output path."
            )
        raise SkillError(
            f"Canonical storage pull for '{feature_slug}' must target "
            f"{sdd_root / feature_slug / 'specification.md'} or {sdd_root / feature_slug / 'spec.md'}."
        )
    ensure_local_write_confirmed(
        output_path=output_path,
        relocated_to_feature_slug=writes_to_sdd_root,
        confirm_local_write=confirm_local_write,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.body)
    if updates_versioning:
        update_versioning_entry(versioning_path, feature_slug, specification_version)
    return {
        "ok": True,
        "path": storage_path,
        "status": response.status,
        "savedTo": str(output_path),
        "fileName": filename,
        "sizeBytes": len(response.body),
        "featureSlug": feature_slug,
        "specificationVersion": specification_version,
        "versioningUpdated": updates_versioning,
        "versioningFile": str(versioning_path) if updates_versioning else None,
    }


def parse_storage_specification_path(storage_path: str) -> Optional[Tuple[str, str]]:
    normalized_path = storage_path.replace("\\", "/")
    match = re.search(
        r"(?:^|/)([^/]+)/versions/specification-([0-9]+(?:\.[0-9]+){0,3})\.md$",
        normalized_path,
        re.IGNORECASE,
    )
    if not match:
        return None
    feature_slug = match.group(1)
    version = match.group(2)
    normalize_version_tuple(version)
    return feature_slug, version


def fetch_spec_task_context(
    *,
    base_url: str,
    jira_key: str,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    normalized_jira_key = normalize_jira_key(jira_key)
    response = send_request(
        method="GET",
        url=with_library_user_id(build_spec_task_context_url(base_url, normalized_jira_key)),
        headers=headers,
        timeout=timeout,
    )
    context = parse_json_body(response.body)
    if not isinstance(context, dict):
        raise SkillError("Spec task context endpoint returned an unexpected response.")
    return {
        "ok": True,
        "jiraKey": normalized_jira_key,
        "context": context,
    }


def fetch_prespec_context(
    *,
    base_url: str,
    jira_key: str,
    include_outdated: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    normalized_jira_key = normalize_jira_key(jira_key)
    context_url = build_prespec_context_url(base_url, normalized_jira_key)
    if include_outdated:
        context_url = f"{context_url}?includeOutdated=true"
    response = send_request(
        method="GET",
        url=with_library_user_id(context_url),
        headers=headers,
        timeout=timeout,
    )
    context = parse_json_body(response.body)
    if not isinstance(context, dict):
        raise SkillError("Pre-spec context endpoint returned an unexpected response.")
    return {
        "ok": True,
        "jiraKey": normalized_jira_key,
        "context": context,
    }


def start_prespec(
    *,
    base_url: str,
    jira_key: str,
    project_slug: str,
    payload_file: str,
    confirm_start: bool,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    ensure_remote_confirmed(confirm_start, "--confirm-start")
    normalized_jira_key = normalize_jira_key(jira_key)
    payload_data = load_prespec_start_payload(payload_file)
    payload_data.update({
        "jiraKey": normalized_jira_key,
        "projectSlug": project_slug,
        "libraryUserId": required_library_user_id(),
    })
    request_headers = dict(headers)
    request_headers["Content-Type"] = "application/json; charset=utf-8"
    request_headers["Accept"] = "application/json"
    response = send_request(
        method="POST",
        url=build_prespec_start_url(base_url),
        headers=request_headers,
        body=json.dumps(payload_data, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    result = parse_json_body(response.body)
    if not isinstance(result, dict):
        raise SkillError("Pre-spec start endpoint returned an unexpected response.")
    return {
        "ok": True,
        **result,
    }


def load_prespec_start_payload(file_arg: str) -> Dict[str, object]:
    path = Path(file_arg).expanduser().resolve()
    if not path.is_file():
        raise SkillError(f"Pre-spec payload file does not exist: {path}")
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillError(f"Invalid pre-spec JSON in {path}: {exc}") from exc
    if not isinstance(raw_payload, dict):
        raise SkillError("Pre-spec payload must be a JSON object.")

    allowed_fields = {
        "questions",
        "analysisLimitations",
        "analyzedRepositories",
        "astreaConversationManaged",
        "astreaConversationCompleted",
    }
    unexpected_fields = sorted(set(raw_payload) - allowed_fields)
    if unexpected_fields:
        raise SkillError(
            "Pre-spec payload contains unsupported fields: " + ", ".join(unexpected_fields)
        )

    questions = raw_payload.get("questions")
    if not isinstance(questions, list):
        raise SkillError("Pre-spec payload field 'questions' must be an array.")
    normalized_questions = []
    seen_question_ids = set()
    astrea_conversation_managed = raw_payload.get("astreaConversationManaged", False)
    astrea_conversation_completed = raw_payload.get("astreaConversationCompleted", False)
    if not isinstance(astrea_conversation_managed, bool):
        raise SkillError("astreaConversationManaged must be a boolean.")
    if not isinstance(astrea_conversation_completed, bool):
        raise SkillError("astreaConversationCompleted must be a boolean.")
    if astrea_conversation_completed and not astrea_conversation_managed:
        raise SkillError("astreaConversationCompleted requires astreaConversationManaged=true.")
    allowed_question_fields = {
        "id",
        "category",
        "question",
        "suggestedAnswer",
        "rationale",
        "finalAnswer",
        "answerType",
        "parentQuestionId",
        "revalidationNote",
        "answeredBySlackUserId",
    }
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            raise SkillError(f"questions[{index}] must be an object.")
        unexpected_question_fields = sorted(set(item) - allowed_question_fields)
        if unexpected_question_fields:
            raise SkillError(
                f"questions[{index}] contains unsupported fields: "
                + ", ".join(unexpected_question_fields)
            )
        normalized_question = {
            field: require_non_empty_string(item.get(field), f"questions[{index}].{field}")
            for field in ("id", "category", "question", "rationale")
        }
        question_id = normalized_question["id"]
        normalized_question_id = question_id.casefold()
        if normalized_question_id in seen_question_ids:
            raise SkillError(f"Duplicate pre-spec question id: {question_id}")
        seen_question_ids.add(normalized_question_id)
        suggested_answer = item.get("suggestedAnswer")
        if suggested_answer is not None:
            normalized_question["suggestedAnswer"] = require_non_empty_string(
                suggested_answer,
                f"questions[{index}].suggestedAnswer",
            )
        final_answer = item.get("finalAnswer")
        answer_type = item.get("answerType")
        if astrea_conversation_completed:
            normalized_question["finalAnswer"] = require_non_empty_string(
                final_answer,
                f"questions[{index}].finalAnswer",
            )
            normalized_answer_type = require_non_empty_string(
                answer_type,
                f"questions[{index}].answerType",
            ).upper()
            if normalized_answer_type not in {"TEXT", "SUGGESTION", "NOT_APPLICABLE", "OUTDATED"}:
                raise SkillError(
                    f"questions[{index}].answerType must be TEXT, SUGGESTION, NOT_APPLICABLE or OUTDATED."
                )
            normalized_question["answerType"] = normalized_answer_type
            if normalized_answer_type != "OUTDATED" and item.get("answeredBySlackUserId") is None:
                raise SkillError(
                    f"questions[{index}].answeredBySlackUserId is required for participant answers."
                )
        elif final_answer is not None or answer_type is not None:
            raise SkillError(
                "Completed answers require astreaConversationCompleted=true."
            )
        for optional_field in ("parentQuestionId", "revalidationNote", "answeredBySlackUserId"):
            optional_value = item.get(optional_field)
            if optional_value is not None:
                normalized_question[optional_field] = require_non_empty_string(
                    optional_value,
                    f"questions[{index}].{optional_field}",
                )
        if normalized_question.get("answerType") == "OUTDATED" \
                and "revalidationNote" not in normalized_question:
            raise SkillError(
                f"questions[{index}].revalidationNote is required for OUTDATED questions."
            )
        normalized_questions.append(normalized_question)

    for index, question in enumerate(normalized_questions):
        parent_question_id = question.get("parentQuestionId")
        if parent_question_id is None:
            continue
        if parent_question_id.casefold() == question["id"].casefold() \
                or parent_question_id.casefold() not in seen_question_ids:
            raise SkillError(
                f"questions[{index}].parentQuestionId must reference another question from the payload."
            )

    analysis_limitations = normalize_string_array(
        raw_payload.get("analysisLimitations", []),
        "analysisLimitations",
    )
    analyzed_repositories = normalize_string_array(
        raw_payload.get("analyzedRepositories", []),
        "analyzedRepositories",
    )
    reject_local_paths(analysis_limitations, "analysisLimitations")
    reject_local_paths(analyzed_repositories, "analyzedRepositories")

    return {
        "questions": normalized_questions,
        "analysisLimitations": analysis_limitations,
        "analyzedRepositories": analyzed_repositories,
        "astreaConversationManaged": astrea_conversation_managed,
        "astreaConversationCompleted": astrea_conversation_completed,
    }


def require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillError(f"{field_name} must be a non-empty string.")
    return value.strip()


def normalize_string_array(value: object, field_name: str) -> List[str]:
    if not isinstance(value, list):
        raise SkillError(f"Pre-spec payload field '{field_name}' must be an array.")
    return [
        require_non_empty_string(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    ]


def reject_local_paths(values: List[str], field_name: str) -> None:
    path_patterns = (
        re.compile(r"\bfile:", re.IGNORECASE),
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(?:[\\/]|[^\s])"),
        re.compile(r"\\"),
        re.compile(r"(?<!\S)(?:~[\\/]|\.\.?[\\/]|/\S)"),
    )
    for index, value in enumerate(values):
        if any(pattern.search(value) for pattern in path_patterns):
            raise SkillError(
                f"{field_name}[{index}] must not contain a local filesystem path."
            )


def publish_spec(
    *,
    base_url: str,
    jira_key: str,
    project_slug: str,
    specification_file: str,
    story_file: str,
    affected_specifications_file: Optional[str],
    confirm_remote: bool,
    headers: Dict[str, str],
    timeout: int,
    document_type: str,
) -> Dict[str, object]:
    ensure_remote_confirmed(confirm_remote, "--confirm-publish")
    spec_path, story_path = validate_spec_files(
        specification_file,
        story_file,
        specification_required=False,
        story_required=False,
        require_any=True,
    )
    affected_payload = load_affected_specifications_payload(affected_specifications_file)

    payload, content_type = build_publish_multipart_payload(
        jira_key=normalize_jira_key(jira_key),
        project_slug=project_slug,
        specification_path=spec_path,
        story_path=story_path,
        affected_specifications_payload=affected_payload,
        document_type=document_type,
    )
    request_headers = dict(headers)
    request_headers["Content-Type"] = content_type
    request_headers["Accept"] = "application/json"

    response = send_request(
        method="POST",
        url=f"{base_url}/integrations/spec-review/publish",
        headers=request_headers,
        body=payload,
        timeout=timeout,
    )
    return {
        "ok": True,
        "jiraKey": normalize_jira_key(jira_key),
        "projectSlug": project_slug,
        "status": response.status,
        "response": parse_json_body(response.body),
    }


def update_current_spec(
    *,
    base_url: str,
    jira_key: str,
    project_slug: str,
    specification_file: str,
    story_file: str,
    affected_specifications_file: Optional[str],
    confirm_remote: bool,
    headers: Dict[str, str],
    timeout: int,
    document_type: str,
) -> Dict[str, object]:
    ensure_remote_confirmed(confirm_remote, "--confirm-update")
    spec_path, story_path = validate_spec_files(
        specification_file,
        story_file,
        specification_required=False,
        story_required=False,
        require_any=True,
    )
    affected_payload = load_affected_specifications_payload(affected_specifications_file)
    normalized_jira_key = normalize_jira_key(jira_key)

    payload, content_type = build_publish_multipart_payload(
        jira_key=normalized_jira_key,
        project_slug=project_slug,
        specification_path=spec_path,
        story_path=story_path,
        affected_specifications_payload=affected_payload,
        document_type=document_type,
        include_jira_field=False,
    )
    request_headers = dict(headers)
    request_headers["Content-Type"] = content_type
    request_headers["Accept"] = "application/json"

    response = send_request(
        method="PUT",
        url=build_current_spec_url(base_url, normalized_jira_key),
        headers=request_headers,
        body=payload,
        timeout=timeout,
    )
    return {
        "ok": True,
        "jiraKey": normalized_jira_key,
        "projectSlug": project_slug,
        "status": response.status,
        "response": parse_json_body(response.body),
    }


def validate_spec_files(
    specification_file: Optional[str],
    story_file: Optional[str],
    *,
    specification_required: bool,
    story_required: bool,
    require_any: bool,
) -> Tuple[Optional[Path], Optional[Path]]:
    spec_path = validate_markdown_file(specification_file, "specificationFile", required=specification_required)
    story_path = validate_markdown_file(story_file, "storyFile", required=story_required)
    if require_any and (spec_path is None) == (story_path is None):
        raise SkillError("Provide exactly one of --specification-file or --story-file.")
    for document_path in (spec_path, story_path):
        if document_path is not None and extract_spec_version(document_path.read_text(encoding="utf-8")) is None:
            raise SkillError(f"Missing '# WERSJA x.y.z' in {document_path}")
    return spec_path, story_path


def validate_markdown_file(file_arg: Optional[str], field_name: str, *, required: bool) -> Optional[Path]:
    if not file_arg:
        if required:
            raise SkillError(f"Missing {field_name}.")
        return None
    file_path = Path(file_arg).expanduser().resolve()
    if not file_path.is_file():
        raise SkillError(f"{field_name} does not exist: {file_path}")
    if file_path.suffix.lower() not in {".md", ".markdown"}:
        raise SkillError(f"{field_name} must point to .md or .markdown file: {file_path}")
    return file_path


def load_affected_specifications_payload(file_arg: Optional[str]) -> Optional[str]:
    if not file_arg:
        return None
    path = Path(file_arg).expanduser().resolve()
    if not path.is_file():
        raise SkillError(f"affectedSpecifications file does not exist: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SkillError(f"Invalid affectedSpecifications JSON in {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise SkillError("affectedSpecifications JSON must be an array.")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise SkillError(f"affectedSpecifications[{index}] must be an object.")
        if "expectedVersion" in item:
            raise SkillError(f"affectedSpecifications[{index}] must not include expectedVersion.")
    return json.dumps(payload, ensure_ascii=False)


def build_publish_multipart_payload(
    *,
    jira_key: str,
    project_slug: str,
    specification_path: Optional[Path],
    story_path: Optional[Path],
    affected_specifications_payload: Optional[str],
    document_type: str,
    include_jira_field: bool = True,
) -> Tuple[bytes, str]:
    if document_type not in {"SPECIFICATION", "STORY"}:
        raise SkillError("documentType must be SPECIFICATION or STORY.")
    if (specification_path is None) == (story_path is None):
        raise SkillError("Provide exactly one of --specification-file or --story-file.")
    if document_type == "SPECIFICATION" and (
        specification_path is None or specification_path.name.lower().startswith("story-")
    ):
        raise SkillError("SPECIFICATION requires specificationFile and cannot upload a story file.")
    boundary = f"----pleo-spec-workflow-{uuid.uuid4().hex}"
    line_break = b"\r\n"
    parts: List[bytes] = []

    parts.extend(build_text_part(boundary, "documentType", document_type))
    if include_jira_field:
        parts.extend(build_text_part(boundary, "jiraKey", jira_key))
    parts.extend(build_text_part(boundary, "projectSlug", project_slug))
    parts.extend(build_text_part(boundary, "libraryUserId", required_library_user_id()))
    if specification_path is not None:
        parts.extend(build_file_part(boundary, "specificationFile", specification_path))
    if story_path is not None:
        parts.extend(build_file_part(boundary, "storyFile", story_path))
    if affected_specifications_payload is not None:
        parts.extend(build_text_part(boundary, "affectedSpecifications", affected_specifications_payload))

    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")
    return line_break.join(parts), f"multipart/form-data; boundary={boundary}"


def build_storage_bootstrap_payload(
    *,
    project_slug: str,
    feature_slug: str,
    specification_version: str,
    specification_path: Path,
    story_paths: Sequence[Path],
) -> Tuple[bytes, str]:
    boundary = f"----pleo-spec-storage-{uuid.uuid4().hex}"
    line_break = b"\r\n"
    parts: List[bytes] = []
    parts.extend(build_text_part(boundary, "projectSlug", project_slug))
    parts.extend(build_text_part(boundary, "featureSlug", feature_slug))
    parts.extend(build_text_part(boundary, "specificationVersion", specification_version))
    parts.extend(build_text_part(boundary, "libraryUserId", required_library_user_id()))
    parts.extend(build_file_part(boundary, "specificationFile", specification_path))
    for story_path in story_paths:
        parts.extend(build_file_part(boundary, "storyFiles", story_path))
    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")
    return line_break.join(parts), f"multipart/form-data; boundary={boundary}"


def build_file_part(boundary: str, field_name: str, file_path: Path) -> List[bytes]:
    media_type = mimetypes.guess_type(file_path.name)[0] or "text/markdown"
    return [
        f"--{boundary}".encode("utf-8"),
        f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"'.encode("utf-8"),
        f"Content-Type: {media_type}".encode("utf-8"),
        b"",
        file_path.read_bytes(),
    ]


def build_text_part(boundary: str, field_name: str, value: str) -> List[bytes]:
    return [
        f"--{boundary}".encode("utf-8"),
        f'Content-Disposition: form-data; name="{field_name}"'.encode("utf-8"),
        b"",
        value.encode("utf-8"),
    ]


def fetch_storage_tree(
    *,
    base_url: str,
    project_slug: str,
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    response = send_request(
        method="GET",
        url=with_library_user_id(f"{base_url}/api/spec-review/storage/tree?project={parse.quote(project_slug, safe='')}"),
        headers=headers,
        timeout=timeout,
    )
    data = parse_json_body(response.body)
    if not isinstance(data, dict):
        raise SkillError("Unexpected response from storage tree endpoint.")
    return data


def upload_storage_bundle(
    *,
    base_url: str,
    project_slug: str,
    feature_slug: str,
    specification_version: str,
    specification_path: Path,
    story_paths: Sequence[Path],
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, object]:
    payload, content_type = build_storage_bootstrap_payload(
        project_slug=project_slug,
        feature_slug=feature_slug,
        specification_version=specification_version,
        specification_path=specification_path,
        story_paths=story_paths,
    )
    request_headers = dict(headers)
    request_headers["Content-Type"] = content_type
    request_headers["Accept"] = "application/json"
    response = send_request(
        method="POST",
        url=f"{base_url}/api/spec-review/storage/upload",
        headers=request_headers,
        body=payload,
        timeout=timeout,
    )
    return {
        "featureSlug": feature_slug,
        "specificationVersion": specification_version,
        "specificationFile": str(specification_path),
        "storyFiles": [str(path) for path in story_paths],
        "response": parse_json_body(response.body),
    }
    

def resolve_local_specification_path(sdd_root: Path, feature_slug: str) -> Path:
    specification_path = find_local_specification_path(sdd_root, feature_slug)
    if specification_path is not None:
        return specification_path
    raise SkillError(f"Missing specification file for feature '{feature_slug}' in {sdd_root / feature_slug}")


def find_local_specification_path(sdd_root: Path, feature_slug: str) -> Optional[Path]:
    feature_dir = sdd_root / feature_slug
    candidates = [feature_dir / "specification.md", feature_dir / "spec.md"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_story_paths(sdd_root: Path, feature_slug: str) -> List[Path]:
    feature_dir = sdd_root / feature_slug
    candidates = sorted(feature_dir.rglob("story-*.md"))
    return [candidate.resolve() for candidate in candidates if candidate.is_file()]


def resolve_bootstrap_specs(
    *,
    versioning_file: Path,
    feature_slug: Optional[str],
    expected_version: Optional[str],
) -> List["LocalSpec"]:
    if expected_version and feature_slug is None:
        raise SkillError("--expected-version requires --feature-slug.")

    if feature_slug is not None and expected_version:
        normalize_version_tuple(expected_version)
        return [LocalSpec(path=Path("<cli>"), feature_slug=feature_slug, version=expected_version)]

    if not versioning_file.is_file():
        if feature_slug is not None:
            raise SkillError(
                f"versioning.md does not exist: {versioning_file}. "
                "Pass --expected-version to archive a single feature without versioning.md."
            )
        raise SkillError(f"versioning.md does not exist: {versioning_file}")

    local_specs = read_versioning_file(versioning_file)
    if feature_slug is None:
        return local_specs

    matching_specs = [spec for spec in local_specs if spec.feature_slug == feature_slug]
    if not matching_specs:
        raise SkillError(
            f"Feature '{feature_slug}' not found in {versioning_file}. "
            "Pass --expected-version to archive it explicitly."
        )
    return matching_specs


def normalize_optional_feature_slug(feature_slug: Optional[str]) -> Optional[str]:
    if feature_slug is None:
        return None
    normalized = feature_slug.strip()
    if not normalized:
        raise SkillError("--feature-slug cannot be empty.")
    return normalized


def should_include_story_files(
    *,
    feature_slug: Optional[str],
    specification_only: bool,
    include_stories: bool,
) -> bool:
    if (specification_only or include_stories) and feature_slug is None:
        raise SkillError("--specification-only and --include-stories require --feature-slug.")
    if feature_slug is None:
        return True
    if specification_only:
        return False
    return include_stories


def read_versioning_file(versioning_file: Path) -> List["LocalSpec"]:
    specs: List[LocalSpec] = []
    for index, raw_line in enumerate(versioning_file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise SkillError(f"Invalid versioning entry at {versioning_file}:{index}. Expected 'featureSlug: version'.")
        feature_slug, version = line.split(":", 1)
        feature_slug = feature_slug.strip()
        version = version.strip()
        if not feature_slug or not version:
            raise SkillError(f"Invalid versioning entry at {versioning_file}:{index}. Expected 'featureSlug: version'.")
        normalize_version_tuple(version)
        specs.append(LocalSpec(path=versioning_file.resolve(), feature_slug=feature_slug, version=version))
    return specs


def extract_remote_versions(tree_response: Dict[str, object]) -> Dict[str, "RemoteSpec"]:
    result: Dict[str, RemoteSpec] = {}
    for project_node in tree_response.get("nodes", []):
        for feature_node in get_children(project_node):
            feature_slug = feature_node.get("label")
            if not isinstance(feature_slug, str) or not feature_slug:
                continue
            remote_spec = find_latest_remote_version(feature_node)
            if remote_spec is not None:
                result[feature_slug] = remote_spec
    return result


def find_latest_remote_version(feature_node: Dict[str, object]) -> Optional["RemoteSpec"]:
    versions_node = None
    for child in get_children(feature_node):
        if child.get("label") == "versions":
            versions_node = child
            break
    if versions_node is None:
        return None

    best_version: Optional[str] = None
    best_path: Optional[str] = None
    for child in get_children(versions_node):
        label = child.get("label")
        path = child.get("path")
        if not isinstance(label, str) or not isinstance(path, str):
            continue
        match = REMOTE_VERSION_FILE_PATTERN.match(label)
        if not match:
            continue
        version = match.group(1)
        if best_version is None or compare_versions(version, best_version) > 0:
            best_version = version
            best_path = path
    if best_version is None or best_path is None:
        return None
    return RemoteSpec(version=best_version, path=best_path)


def get_children(node: object) -> Sequence[Dict[str, object]]:
    if not isinstance(node, dict):
        return []
    children = node.get("children")
    if not isinstance(children, list):
        return []
    return [child for child in children if isinstance(child, dict)]


def compare_versions(left: str, right: str) -> int:
    left_tuple = normalize_version_tuple(left)
    right_tuple = normalize_version_tuple(right)
    if left_tuple < right_tuple:
        return -1
    if left_tuple > right_tuple:
        return 1
    return 0


def normalize_version_tuple(version: str) -> Tuple[int, ...]:
    parts = [int(part) for part in version.strip().split(".") if part != ""]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def build_current_spec_url(base_url: str, jira_key: str) -> str:
    return f"{base_url}/integrations/spec-review/{parse.quote(jira_key, safe='')}/current-spec"


def build_source_spec_url(base_url: str, jira_key: str) -> str:
    return f"{base_url}/integrations/spec-review/{parse.quote(jira_key, safe='')}/source-spec"


def build_workflow_files_url(base_url: str, jira_key: str) -> str:
    return f"{base_url}/integrations/spec-review/{parse.quote(jira_key, safe='')}/workflow-files"


def build_spec_task_context_url(base_url: str, jira_key: str) -> str:
    return f"{base_url}/integrations/spec-review/spec-task/{parse.quote(jira_key, safe='')}/context"


def build_prespec_context_url(base_url: str, jira_key: str) -> str:
    return f"{base_url}/integrations/prespec/{parse.quote(jira_key, safe='')}/context"


def build_prespec_start_url(base_url: str) -> str:
    return f"{base_url}/integrations/prespec/start"


def build_storage_file_url(base_url: str, storage_path: str) -> str:
    return f"{base_url}/api/spec-review/storage/file?path={parse.quote(storage_path, safe='')}"


def with_library_user_id(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}libraryUserId={parse.quote(required_library_user_id(), safe='')}"


def normalize_jira_key(jira_key: str) -> str:
    if jira_key is None:
        raise SkillError("Missing jira key.")
    normalized = jira_key.strip().upper()
    if not normalized:
        raise SkillError("Missing jira key.")
    return normalized


def resolve_download_filename(headers, fallback_name: str) -> str:
    content_disposition = headers.get("Content-Disposition", "")
    match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
    if match:
        return parse.unquote(match.group(1))

    match = re.search(r'filename="?([^";]+)"?', content_disposition, re.IGNORECASE)
    if match:
        return match.group(1)

    return fallback_name


def resolve_output_path(output_arg: str, filename: str) -> Path:
    output_path = Path(output_arg).expanduser()
    if output_arg.endswith(("\\", "/")) or (output_path.exists() and output_path.is_dir()):
        return output_path / filename
    return output_path


def ensure_local_write_confirmed(
    *,
    output_path: Path,
    relocated_to_feature_slug: bool,
    confirm_local_write: bool,
) -> None:
    if output_path.exists() and output_path.is_dir():
        raise SkillError(f"Output path resolves to a directory, expected a file path: {output_path}")
    requires_confirmation = relocated_to_feature_slug or output_path.exists()
    if requires_confirmation and not confirm_local_write:
        reason = "overwrite existing file" if output_path.exists() else "write into canonical local spec path"
        raise SkillError(f"Refusing to {reason} without --confirm-local-write: {output_path}")


def ensure_remote_confirmed(confirm_remote: bool, flag_name: str) -> None:
    if not confirm_remote:
        raise SkillError(f"Refusing remote workflow change without {flag_name}.")


def extract_feature_slug(body: bytes) -> Optional[str]:
    return extract_feature_slug_from_text(body.decode("utf-8", errors="replace"))


def extract_feature_slug_from_text(content: str) -> Optional[str]:
    match = FEATURE_SLUG_PATTERN.search(content)
    if not match:
        return None
    feature_slug = match.group(1).strip()
    return feature_slug or None


def extract_spec_version(content: str) -> Optional[str]:
    match = VERSION_PATTERN.search(content)
    if not match:
        return None
    return match.group(1).strip()


def is_path_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def parse_json_body(body: bytes) -> object:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillError(f"Expected JSON response but received invalid payload: {exc}") from exc


def send_request(
    *,
    method: str,
    url: str,
    headers: Dict[str, str],
    timeout: int,
    body: Optional[bytes] = None,
) -> "HttpResponse":
    req = request.Request(url=url, data=body, method=method, headers=dict(headers))
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status=resp.getcode(), headers=resp.headers, body=resp.read())
    except error.HTTPError as exc:
        response_body = exc.read()
        detail = decode_error_body(response_body)
        raise SkillError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except error.URLError as exc:
        raise SkillError(f"Network error for {url}: {exc.reason}") from exc


def decode_error_body(body: bytes) -> str:
    if not body:
        return "empty response"
    try:
        parsed = json.loads(body.decode("utf-8"))
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        return body.decode("utf-8", errors="replace").strip() or "unreadable response"


@dataclass(frozen=True)
class LocalSpec:
    path: Path
    feature_slug: str
    version: str


@dataclass(frozen=True)
class RemoteSpec:
    version: str
    path: str


class HttpResponse:
    def __init__(self, *, status: int, headers, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body


class SkillError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
