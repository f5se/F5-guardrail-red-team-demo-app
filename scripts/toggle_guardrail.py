#!/usr/bin/env python3
"""
Toggle Calypso/F5 project guardrails by package/scanner name.

Modes:
1) package mode (add/remove package to project)
2) scanner-patch mode (PATCH project config.scanners[].enabled)
   - resolves scanner ID by scanner name dynamically
   - optional scanner version pin

Examples:
  # List scanners in a package
  python scripts/toggle_guardrail.py --list --package "Corporate guardrails package"

  # Enable scanner via project PATCH (recommended for packaged scanners)
  python scripts/toggle_guardrail.py --action enable --scanner "Prompt injection guardrail" --mode scanner-patch --version "2026-02"

  # Disable scanner via project PATCH
  python scripts/toggle_guardrail.py --action disable --scanner "Prompt injection guardrail" --mode scanner-patch --version "2026-02"

  # Toggle known Prompt injection guardrail in current project
  python scripts/toggle_guardrail.py --action enable --prompt-injection
  python scripts/toggle_guardrail.py --action disable --prompt-injection
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, Optional

from calypsoai import CalypsoAI

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

PROMPT_INJECTION_SCANNER_ID = "019620d4-e065-7014-8f56-c1002045c205"
PROMPT_INJECTION_DEFAULT_VERSION = "2026-02"


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _match_by_name(items: Iterable, target_name: str, field: str = "name"):
    target = _norm(target_name)
    matched = [it for it in items if _norm(str(getattr(it, field, "") or "")) == target]
    if not matched:
        return None, []
    if len(matched) > 1:
        return None, matched
    return matched[0], []


def _must_env(name: str) -> str:
    val = (os.getenv(name) or "").strip()
    if not val:
        raise SystemExit(f"[ERROR] Missing required env: {name}")
    return val


def _build_client() -> tuple[CalypsoAI, str]:
    if load_dotenv is not None:
        load_dotenv(".env")

    url = _must_env("CALYPSOAI_URL")
    token = _must_env("CALYPSOAI_TOKEN")
    project_id = _must_env("CALYPSOAI_PROJECT_ID")
    return CalypsoAI(url=url, token=token), project_id


def _list_packages(cai: CalypsoAI, project_id: str):
    packages = []
    cursor = None
    while True:
        resp = cai.client.scannerPackages.get(
            cursor=cursor,
            limit=100,
            accessibleToProjectId=project_id,
        )
        packages.extend(resp.packages or [])
        if not getattr(resp, "next", None):
            break
        cursor = resp.next
    return packages


def _print_list(cai: CalypsoAI, project_id: str, package_name: str):
    packages = _list_packages(cai, project_id)
    pkg, dup = _match_by_name(packages, package_name)
    if dup:
        print(f"[ERROR] package name duplicated: {package_name}")
        for p in dup:
            print(f"  - id={p.id} name={p.name}")
        raise SystemExit(2)
    if not pkg:
        print(f"[ERROR] package not found: {package_name}")
        raise SystemExit(2)

    _, scanners = cai.scannerPackages.getWithScanners(pkg.id)
    print(f"package: {pkg.name} ({pkg.id})")
    if not scanners:
        print("  (no scanners)")
        return
    for s in scanners:
        print(f"  - {s.name} ({s.id})")


def _print_packages(cai: CalypsoAI, project_id: str):
    packages = _list_packages(cai, project_id)
    if not packages:
        print("[INFO] no accessible packages for current project")
        return
    for p in packages:
        print(f"- {p.name} ({p.id})")


def _list_scanners(cai: CalypsoAI, *, search: Optional[str] = None, include_packages: bool = True):
    scanners = []
    cursor = None
    while True:
        resp = cai.client.scanners.get(
            cursor=cursor,
            limit=100,
            search=search,
            includePackages=include_packages,
        )
        scanners.extend(resp.scanners or [])
        if not getattr(resp, "next", None):
            break
        cursor = resp.next
    return scanners


def _resolve_scanner_by_name(cai: CalypsoAI, scanner_name: str):
    # first pass with search for efficiency
    items = _list_scanners(cai, search=scanner_name, include_packages=True)
    exact = [s for s in items if _norm(str(getattr(s, "name", "") or "")) == _norm(scanner_name)]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, exact

    # fallback full scan to avoid search semantics mismatch
    items_full = _list_scanners(cai, search=None, include_packages=True)
    exact_full = [s for s in items_full if _norm(str(getattr(s, "name", "") or "")) == _norm(scanner_name)]
    if len(exact_full) == 1:
        return exact_full[0], []
    if len(exact_full) > 1:
        return None, exact_full
    return None, []


def _find_scanner_in_project(cai: CalypsoAI, project_id: str, scanner_name: str):
    """Best-effort scanner resolve from project scanners/configs.

    Useful when global scanner listing is restricted by availability/permissions.
    """
    target = _norm(scanner_name)
    ps = cai.projects.getScanners(project_id)
    hits = []

    # Enabled scanners: id -> scanner object (has name)
    for sid, scanner_obj in (ps.scanners or {}).items():
        name = str(getattr(scanner_obj, "name", "") or "")
        if _norm(name) == target:
            hits.append((str(getattr(scanner_obj, "id", sid) or sid), name, "project.scanners"))

    # Configured scanners: id -> ProjectConfigScanner (may not have name)
    for sid in (ps.configs or {}).keys():
        if sid in {h[0] for h in hits}:
            continue
        # Try to enrich name via direct scanner fetch; ignore permission failures.
        name = ""
        try:
            detail = cai.client.scanners.getScannerId(sid).scanner
            name = str(getattr(detail, "name", "") or "")
        except Exception:
            pass
        if name and _norm(name) == target:
            hits.append((str(sid), name, "project.configs+lookup"))

    if len(hits) == 1:
        sid, name, _src = hits[0]
        class _X:
            id = sid
            name = name
        return _X(), []
    if len(hits) > 1:
        class _Y:
            def __init__(self, sid, name):
                self.id = sid
                self.name = name
        return None, [_Y(sid, name) for sid, name, _src in hits]
    return None, []


def _current_project_scanner_version(cai: CalypsoAI, project_id: str, scanner_id: str) -> Optional[str]:
    project_scanners = cai.projects.getScanners(project_id)
    cfg = (project_scanners.configs or {}).get(scanner_id)
    if not cfg:
        return None
    version = getattr(cfg, "version", None)
    if version is None:
        return None
    return str(version)


def _resolve_targets(cai: CalypsoAI, project_id: str, package_name: str, scanner_name: Optional[str]):
    packages = _list_packages(cai, project_id)
    pkg, dup = _match_by_name(packages, package_name)
    if dup:
        print(f"[ERROR] package name duplicated: {package_name}")
        for p in dup:
            print(f"  - id={p.id} name={p.name}")
        raise SystemExit(2)
    if not pkg:
        print(f"[ERROR] package not found: {package_name}")
        raise SystemExit(2)

    _, scanners = cai.scannerPackages.getWithScanners(pkg.id)
    if scanner_name:
        scanner, dup_sc = _match_by_name(scanners, scanner_name)
        if dup_sc:
            print(f"[ERROR] scanner name duplicated in package '{package_name}': {scanner_name}")
            for s in dup_sc:
                print(f"  - id={s.id} name={s.name}")
            raise SystemExit(2)
        if not scanner:
            print(f"[ERROR] scanner not found in package '{package_name}': {scanner_name}")
            print("[INFO] Available scanners:")
            for s in scanners:
                print(f"  - {s.name}")
            raise SystemExit(2)
        return pkg, scanner
    return pkg, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable/disable Calypso project guardrail package or scanner.")
    parser.add_argument("--action", choices=["enable", "disable"], help="Target action.")
    parser.add_argument("--scope", choices=["package", "scanner"], default="scanner", help="Toggle scope.")
    parser.add_argument(
        "--mode",
        choices=["package-membership", "scanner-patch"],
        default="scanner-patch",
        help="scanner mode: package-membership uses add/remove scanner API; scanner-patch uses PATCH /projects config.scanners[].enabled.",
    )
    parser.add_argument("--package", help="Scanner package display name.")
    parser.add_argument("--scanner", help="Scanner display name (required when --scope scanner).")
    parser.add_argument("--scanner-id", help="Scanner ID override. Use this when scanner name is not searchable.")
    parser.add_argument(
        "--prompt-injection",
        action="store_true",
        help=f"Shortcut for scanner-id {PROMPT_INJECTION_SCANNER_ID} in current project.",
    )
    parser.add_argument("--version", help="Scanner version for scanner-patch mode, e.g. 2026-02.")
    parser.add_argument("--list", action="store_true", help="List scanners in package and exit.")
    parser.add_argument("--list-packages", action="store_true", help="List accessible packages in current project and exit.")
    parser.add_argument("--find-scanner", help="Find scanner ID by display name and print matches.")
    parser.add_argument("--dry-run", action="store_true", help="Only print operation, do not call API.")
    args = parser.parse_args()

    cai, project_id = _build_client()

    if args.list_packages:
        _print_packages(cai, project_id)
        return 0

    if args.list:
        if not args.package:
            parser.error("--package is required when --list is used.")
        _print_list(cai, project_id, args.package)
        return 0

    if args.find_scanner:
        scanner, dup = _resolve_scanner_by_name(cai, args.find_scanner)
        if not scanner and not dup:
            scanner, dup = _find_scanner_in_project(cai, project_id, args.find_scanner)
        if dup:
            print(f"[ERROR] scanner name duplicated: {args.find_scanner}")
            for s in dup:
                print(f"  - id={s.id} name={s.name}")
            return 2
        if not scanner:
            print(f"[ERROR] scanner not found: {args.find_scanner}")
            return 2
        print(f"id={scanner.id} name={scanner.name}")
        return 0

    if not args.action:
        parser.error("--action is required unless --list is used.")
    if args.scope == "package" and not args.package:
        parser.error("--package is required when --scope package.")
    if args.prompt_injection and args.scope != "scanner":
        parser.error("--prompt-injection only works with --scope scanner.")
    if args.scope == "scanner" and not (args.scanner or args.scanner_id or args.prompt_injection):
        parser.error("--scanner or --scanner-id or --prompt-injection is required when --scope scanner.")

    if args.scope == "package":
        pkg, _ = _resolve_targets(cai, project_id, args.package, None)
        op = f"{args.action} package '{pkg.name}' ({pkg.id}) on project {project_id}"
        print(f"[PLAN] {op}")
        if args.dry_run:
            print("[DRY-RUN] skipped API call")
            return 0
        if args.action == "enable":
            cai.client.projects.scannerPackages.postScannerPackageId(project_id, pkg.id)
        else:
            cai.client.projects.scannerPackages.deleteScannerPackageId(project_id, pkg.id)
        print("[OK] package updated")
        return 0

    # scope == scanner
    scanner = None
    scanner_id = None
    scanner_name = args.scanner
    if args.prompt_injection:
        scanner_id = PROMPT_INJECTION_SCANNER_ID
        scanner_name = "Prompt injection guardrail"
        if not args.version:
            args.version = PROMPT_INJECTION_DEFAULT_VERSION
    elif args.scanner_id:
        scanner_id = str(args.scanner_id).strip()
        if not scanner_name:
            scanner_name = "(from --scanner-id)"
    else:
        scanner, dup = _resolve_scanner_by_name(cai, args.scanner)
        if dup:
            print(f"[ERROR] scanner name duplicated: {args.scanner}")
            for s in dup:
                print(f"  - id={s.id} name={s.name}")
            return 2
        if not scanner:
            print(f"[ERROR] scanner not found: {args.scanner}")
            return 2
        scanner_id = str(scanner.id)
        scanner_name = str(scanner.name)

    enabled = args.action == "enable"

    if args.mode == "package-membership":
        op = f"{args.action} scanner '{scanner_name}' ({scanner_id}) by project scanner membership API"
        print(f"[PLAN] {op}")
        if args.dry_run:
            print("[DRY-RUN] skipped API call")
            return 0
        if enabled:
            cai.client.projects.scanners.postScannerId(project_id, scanner_id)
        else:
            cai.client.projects.scanners.deleteScannerId(project_id, scanner_id)
        print("[OK] scanner membership updated")
        return 0

    # scanner-patch mode (recommended)
    version = args.version or _current_project_scanner_version(cai, project_id, scanner_id)
    body = {"config": {"scanners": [{"id": scanner_id, "enabled": enabled}]}}
    if version:
        body["config"]["scanners"][0]["version"] = version
    op = (
        f"{args.action} scanner '{scanner_name}' ({scanner_id}) by PATCH project config "
        f"version={version or '(not set)'}"
    )
    print(f"[PLAN] {op}")
    print(f"[BODY] {body}")
    if args.dry_run:
        print("[DRY-RUN] skipped API call")
        return 0
    cai.client.projects.patchProject(project=project_id, body=body)

    # verify
    cur = cai.projects.getScanners(project_id).configs or {}
    cfg = cur.get(scanner_id)
    actual = None if cfg is None else getattr(cfg, "enabled", None)
    print(f"[OK] scanner patched, project config enabled={actual}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
