"""Manifest parsers for Python and Node.js dependency files."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class Dependency:
    """A single dependency with its pinned version and source manifest."""

    name: str
    pinned_version: str
    ecosystem: str  # "pypi" or "npm"
    manifest: str  # filename it was found in
    extras: list[str] = field(default_factory=list)
    marker: Optional[str] = None  # environment marker, e.g. "python_version >= '3.10'"

    @property
    def base_name(self) -> str:
        """Name without extras (for registry lookups)."""
        return self.name.split("[")[0]


@dataclass
class ParsedManifest:
    """Result of parsing a dependency manifest file."""

    dependencies: list[Dependency]
    manifest_path: str
    ecosystem: str


def parse_requirements_txt(path: Path) -> ParsedManifest:
    """Parse a requirements.txt file."""
    deps: list[Dependency] = []
    content = path.read_text(encoding="utf-8")

    # Match package==version or package>=version or package~=version
    pattern = re.compile(
        r"^([a-zA-Z0-9_-]+(?:\[[a-zA-Z0-9_,\s]+\])?)"  # package name + extras
        r"\s*([=~<>!]=?\s*)"  # operator
        r"([0-9][0-9a-zA-Z.*+!-]*)"  # version
        r"(?:\s*;\s*(.*))?$",  # optional marker
        re.MULTILINE,
    )

    for match in pattern.finditer(content):
        raw_name = match.group(1).strip()
        version = match.group(3).strip()
        marker = match.group(4).strip() if match.group(4) else None

        extras: list[str] = []
        if "[" in raw_name:
            base = raw_name.split("[")[0]
            extras_str = raw_name.split("[")[1].rstrip("]")
            extras = [e.strip() for e in extras_str.split(",") if e.strip()]
        else:
            base = raw_name

        deps.append(
            Dependency(
                name=base,
                pinned_version=version,
                ecosystem="pypi",
                manifest=str(path.name),
                extras=extras,
                marker=marker,
            )
        )

    return ParsedManifest(dependencies=deps, manifest_path=str(path), ecosystem="pypi")


def parse_pyproject_toml(path: Path) -> ParsedManifest:
    """Parse a pyproject.toml file for dependencies."""
    if tomllib is None:
        raise RuntimeError("tomllib/tomli not available. Install with: pip install tomli")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    deps: list[Dependency] = []

    # PEP 621 project.dependencies
    project = data.get("project", {})
    for dep_str in project.get("dependencies", []):
        parsed = _parse_pep508(dep_str, str(path.name))
        if parsed:
            deps.append(parsed)

    # Optional dependencies (extra groups)
    for group_name, group_deps in project.get("optional-dependencies", {}).items():
        for dep_str in group_deps:
            parsed = _parse_pep508(dep_str, str(path.name))
            if parsed:
                parsed.extras.append(group_name)
                deps.append(parsed)

    # Poetry-style [tool.poetry.dependencies]
    poetry = data.get("tool", {}).get("poetry", {})
    for name, version_spec in poetry.get("dependencies", {}).items():
        if name.lower() == "python":
            continue
        version = _extract_version_from_poetry(version_spec)
        if version:
            deps.append(
                Dependency(
                    name=name,
                    pinned_version=version,
                    ecosystem="pypi",
                    manifest=str(path.name),
                )
            )

    return ParsedManifest(dependencies=deps, manifest_path=str(path), ecosystem="pypi")


def _parse_pep508(dep_str: str, manifest: str) -> Optional[Dependency]:
    """Parse a PEP 508 dependency string."""
    dep_str = dep_str.strip()

    # Remove comments
    if "#" in dep_str:
        dep_str = dep_str.split("#")[0].strip()

    if not dep_str:
        return None

    # Extract marker (after ;)
    marker = None
    if ";" in dep_str:
        parts = dep_str.split(";", 1)
        dep_str = parts[0].strip()
        marker = parts[1].strip()

    # Extract extras
    extras: list[str] = []
    if "[" in dep_str:
        base = dep_str.split("[")[0].strip()
        extras_str = dep_str.split("[")[1].split("]")[0]
        extras = [e.strip() for e in extras_str.split(",") if e.strip()]
    else:
        base = dep_str

    # Extract version
    match = re.match(
        r"^([a-zA-Z0-9_.-]+)\s*([=~<>!]=?\s*)\s*([0-9][0-9a-zA-Z.*+!-]*)",
        base,
    )
    if not match:
        # No version pinned
        return None

    name = match.group(1).strip()
    version = match.group(3).strip()

    return Dependency(
        name=name,
        pinned_version=version,
        ecosystem="pypi",
        manifest=manifest,
        extras=extras,
        marker=marker,
    )


def _extract_version_from_poetry(spec) -> Optional[str]:
    """Extract a version string from Poetry dependency spec."""
    if isinstance(spec, str):
        match = re.search(r"([0-9][0-9a-zA-Z.*+!-]+)", spec)
        return match.group(1) if match else None
    if isinstance(spec, dict):
        version = spec.get("version", "")
        if version:
            match = re.search(r"([0-9][0-9a-zA-Z.*+!-]+)", version)
            return match.group(1) if match else None
    return None


def parse_package_json(path: Path) -> ParsedManifest:
    """Parse a package.json file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    deps: list[Dependency] = []

    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, version_spec in data.get(section, {}).items():
            version = _extract_npm_version(version_spec)
            if version:
                deps.append(
                    Dependency(
                        name=name,
                        pinned_version=version,
                        ecosystem="npm",
                        manifest=str(path.name),
                    )
                )

    return ParsedManifest(dependencies=deps, manifest_path=str(path), ecosystem="npm")


def _extract_npm_version(spec: str) -> Optional[str]:
    """Extract a clean version from npm version spec strings."""
    # Remove prefixes: ^, ~, >=, >, <=, <, =, v
    cleaned = re.sub(r"^[\^~>=<=]+v?", "", spec.strip())

    # Handle ranges like "1.2.3 - 2.0.0"
    if " - " in cleaned:
        cleaned = cleaned.split(" - ")[0]

    # Handle || (OR ranges) - take first
    if "||" in cleaned:
        cleaned = cleaned.split("||")[0].strip()

    # Handle x ranges like "1.x" or "1.2.x"
    cleaned = cleaned.replace("x", "0").replace("*", "0")

    # Extract version
    match = re.match(r"^([0-9][0-9a-zA-Z.-]*)", cleaned)
    return match.group(1) if match else None


def discover_manifests(project_path: Path) -> list[ParsedManifest]:
    """Discover and parse all dependency manifests in a project."""
    manifests: list[ParsedManifest] = []
    seen_paths: set[str] = set()

    manifest_configs = [
        ("pyproject.toml", parse_pyproject_toml),
        ("requirements.txt", parse_requirements_txt),
        ("requirements-dev.txt", parse_requirements_txt),
        ("requirements_prod.txt", parse_requirements_txt),
        ("package.json", parse_package_json),
    ]

    for filename, parser in manifest_configs:
        for found in project_path.rglob(filename):
            # Skip node_modules and virtual environments
            if any(part in {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build"} for part in found.parts):
                continue

            resolved = str(found.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            try:
                parsed = parser(found)
                if parsed.dependencies:
                    manifests.append(parsed)
            except Exception as e:
                print(f"Warning: Failed to parse {found}: {e}", file=sys.stderr)

    return manifests


def collect_dependencies(manifests: list[ParsedManifest]) -> list[Dependency]:
    """Collect all unique dependencies from parsed manifests."""
    seen: dict[tuple[str, str], Dependency] = {}
    for manifest in manifests:
        for dep in manifest.dependencies:
            key = (dep.base_name.lower(), dep.ecosystem)
            if key not in seen:
                seen[key] = dep
    return list(seen.values())
