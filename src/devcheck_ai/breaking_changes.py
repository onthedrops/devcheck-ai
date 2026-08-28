"""Breaking changes registry integration.

Loads the ai-sdk-breakage-registry data and matches dependencies
against known breaking changes when version drift is detected.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .manifests import Dependency
from .core import DriftType, CheckResult, _safe_version
from packaging.version import Version


@dataclass
class BreakingChange:
    """A single breaking change entry from the registry."""
    package: str
    ecosystem: str
    from_version_range: str
    to_version_range: str
    severity: str
    category: str
    summary: str
    changes: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    last_verified: str = ""
    confidence: str = ""

    def get_detection_patterns(self) -> list[str]:
        """Return all regex patterns from all changes."""
        patterns = []
        for change in self.changes:
            detection = change.get("detection", {})
            patterns.extend(detection.get("regex", []))
            patterns.extend(detection.get("import_patterns", []))
        return patterns


@dataclass
class BreakingChangeMatch:
    """A match between a dependency and a breaking change entry."""
    package: str
    ecosystem: str
    pinned_version: str
    latest_version: str
    breaking_change: BreakingChange
    matched_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dict for JSON output."""
        return {
            "package": self.package,
            "ecosystem": self.ecosystem,
            "pinned_version": self.pinned_version,
            "latest_version": self.latest_version,
            "severity": self.breaking_change.severity,
            "category": self.breaking_change.category,
            "summary": self.breaking_change.summary,
            "from_version_range": self.breaking_change.from_version_range,
            "to_version_range": self.breaking_change.to_version_range,
            "changes": [
                {
                    "symbol_before": c.get("symbol_before", ""),
                    "symbol_after": c.get("symbol_after", ""),
                    "change_type": c.get("change_type", ""),
                    "before": c.get("before", ""),
                    "after": c.get("after", ""),
                    "migration_note": c.get("migration_note", ""),
                }
                for c in self.breaking_change.changes
            ],
            "sources": self.breaking_change.sources,
            "last_verified": self.breaking_change.last_verified,
            "confidence": self.breaking_change.confidence,
        }


# Path to bundled registry data
REGISTRY_PATH = Path(__file__).parent / "data" / "registry.json"

# Fallback: try to load from the sibling ai-sdk-breakage-registry project
REGISTRY_FALLBACK_PATHS = [
    Path(__file__).parent.parent.parent.parent / "ai-sdk-breakage-registry" / "generated" / "registry.json",
    Path.home() / ".ai-sdk-breakage-registry" / "registry.json",
]

# Remote URL for fetching the latest registry
REGISTRY_URL = "https://raw.githubusercontent.com/ai-sdk-breakage-registry/ai-sdk-breakage-registry/main/generated/registry.json"


def load_registry(custom_path: Optional[Path] = None) -> list[BreakingChange]:
    """Load the breaking changes registry from local data.

    Args:
        custom_path: Optional path to a registry.json file.
                     If not provided, uses bundled data or fallback paths.

    Returns:
        List of BreakingChange entries.
    """
    paths_to_try = []
    if custom_path:
        paths_to_try.append(custom_path)
    paths_to_try.append(REGISTRY_PATH)
    paths_to_try.extend(REGISTRY_FALLBACK_PATHS)

    for path in paths_to_try:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                entries = data.get("entries", [])
                return [
                    BreakingChange(
                        package=e.get("package", ""),
                        ecosystem=e.get("ecosystem", ""),
                        from_version_range=e.get("from_version_range", ""),
                        to_version_range=e.get("to_version_range", ""),
                        severity=e.get("severity", ""),
                        category=e.get("category", ""),
                        summary=e.get("summary", ""),
                        changes=e.get("changes", []),
                        sources=e.get("sources", []),
                        last_verified=e.get("last_verified", ""),
                        confidence=e.get("confidence", ""),
                    )
                    for e in entries
                ]
            except (json.JSONDecodeError, KeyError):
                continue

    return []


def _matches_version_range(version: str, range_str: str) -> bool:
    """Check if a version matches a version range string.

    Handles simple patterns like:
    - "<1.0.0"
    - ">=1.0.0"
    - ">=5.0.0,<6.0.0"
    - "*" (matches anything)
    - "google-genai >=1.0.0" (package target, extract version part)
    """
    if not range_str or range_str == "*":
        return True

    # Strip package name prefix if present (e.g., "google-genai >=1.0.0")
    # Look for version-like patterns
    range_str = range_str.strip()

    # Split on comma for compound ranges (AND)
    parts = [p.strip() for p in range_str.split(",")]

    v = _safe_version(version)
    if v is None:
        return False

    for part in parts:
        part = part.strip()
        if not part or part == "*":
            continue

        # Extract operator and version from the part
        # Handle patterns like ">=1.0.0", "<1.0.0", ">=5.0.0,<6.0.0"
        # Also handle "google-genai >=1.0.0" by extracting just the version constraint
        match = re.match(r"[^<>!=\d]*([<>!>=]+)?\s*(\d+(?:\.\d+)*)", part)
        if not match:
            continue

        op = match.group(1)
        ver_str = match.group(2)

        if not ver_str:
            continue

        range_v = _safe_version(ver_str)
        if range_v is None:
            continue

        if op == ">=":
            if not (v >= range_v):
                return False
        elif op == ">":
            if not (v > range_v):
                return False
        elif op == "<":
            if not (v < range_v):
                return False
        elif op == "<=":
            if not (v <= range_v):
                return False
        else:
            # No operator, assume exact match
            if v != range_v:
                return False

    return True


def match_breaking_changes(
    results: list[CheckResult],
    registry: list[BreakingChange],
) -> dict[str, BreakingChangeMatch]:
    """Match check results against breaking change entries.

    Returns a dict mapping package name (lowercased) to BreakingChangeMatch.
    Only matches when there's major version drift or the package is deprecated/renamed.
    """
    matches: dict[str, BreakingChangeMatch] = {}

    for result in results:
        dep = result.dependency
        pkg_name = dep.base_name.lower()

        for entry in registry:
            # Match by package name (case-insensitive)
            if entry.package.lower() != pkg_name:
                continue
            if entry.ecosystem != dep.ecosystem:
                continue

            # Check if the pinned version falls in the "from" range
            pinned = dep.pinned_version
            if not _matches_version_range(pinned, entry.from_version_range):
                continue

            # Match if there's major drift, deprecation, or package rename
            should_match = (
                result.drift_type == DriftType.MAJOR
                or result.drift_type == DriftType.DEPRECATED
                or result.drift_type == DriftType.UNMAINTAINED
                or entry.category == "package_renamed"
                or result.risk_level.value in ("high", "critical")
            )

            if should_match:
                matches[pkg_name] = BreakingChangeMatch(
                    package=dep.name,
                    ecosystem=dep.ecosystem,
                    pinned_version=pinned,
                    latest_version=result.latest_version or "unknown",
                    breaking_change=entry,
                )
                break

    return matches
