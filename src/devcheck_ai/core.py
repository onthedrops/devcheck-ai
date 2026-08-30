"""Core analysis engine: version comparison, drift detection, risk scoring."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from packaging.version import InvalidVersion, Version

from .manifests import Dependency
from .registries import PackageInfo


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DriftType(str, Enum):
    NONE = "none"
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"
    NOT_FOUND = "not_found"
    DEPRECATED = "deprecated"
    UNMAINTAINED = "unmaintained"
    YANKED = "yanked"


@dataclass
class CheckResult:
    """Result of checking a single dependency against its registry."""

    dependency: Dependency
    package_info: PackageInfo
    latest_version: Optional[str]
    drift_type: DriftType
    risk_level: RiskLevel
    details: str
    changelog_url: Optional[str] = None
    release_date: Optional[str] = None


def _safe_version(v: str) -> Optional[Version]:
    """Parse a version string, returning None on failure."""
    try:
        # Strip common prefixes/suffixes that packaging doesn't handle
        cleaned = v.strip().lstrip("v")
        return Version(cleaned)
    except (InvalidVersion, ValueError):
        return None


def detect_drift(pinned: str, latest: str) -> DriftType:
    """Detect the type of version drift between pinned and latest."""
    pinned_v = _safe_version(pinned)
    latest_v = _safe_version(latest)

    if pinned_v is None or latest_v is None:
        # Fall back to string comparison
        if pinned == latest:
            return DriftType.NONE
        return DriftType.MAJOR  # Unknown drift, assume major

    if pinned_v == latest_v:
        return DriftType.NONE

    if pinned_v.major != latest_v.major:
        return DriftType.MAJOR
    elif pinned_v.minor != latest_v.minor:
        return DriftType.MINOR
    elif pinned_v.micro != latest_v.micro:
        return DriftType.PATCH

    return DriftType.NONE


def calculate_risk(
    drift_type: DriftType,
    package_info: PackageInfo,
    dependency: Dependency,
) -> tuple[RiskLevel, str]:
    """Calculate risk level and generate details for a dependency."""
    if package_info.error:
        return RiskLevel.HIGH, f"Registry error: {package_info.error}"

    if package_info.is_deprecated:
        msg = package_info.deprecation_message or "Package is deprecated"
        return RiskLevel.CRITICAL, f"DEPRECATED: {msg}"

    if drift_type == DriftType.NOT_FOUND:
        return RiskLevel.HIGH, "Package not found in registry"

    # Check if pinned version was yanked
    if dependency.pinned_version in package_info.yanked_versions:
        return RiskLevel.CRITICAL, f"Version {dependency.pinned_version} has been yanked"

    if drift_type == DriftType.MAJOR:
        return (
            RiskLevel.HIGH,
            f"Major version drift: pinned {dependency.pinned_version} -> latest {package_info.latest_version}. "
            f"Breaking changes likely. Manual review required.",
        )

    if drift_type == DriftType.MINOR:
        return (
            RiskLevel.MEDIUM,
            f"Minor version drift: pinned {dependency.pinned_version} -> latest {package_info.latest_version}. "
            f"New features, possible deprecations.",
        )

    if drift_type == DriftType.PATCH:
        return (
            RiskLevel.LOW,
            f"Patch version drift: pinned {dependency.pinned_version} -> latest {package_info.latest_version}. "
            f"Bug fixes and security patches.",
        )

    return RiskLevel.NONE, "Up to date"


def check_dependency(
    dependency: Dependency,
    package_info: PackageInfo,
) -> CheckResult:
    """Run the full check pipeline on a single dependency."""
    if package_info.error:
        return CheckResult(
            dependency=dependency,
            package_info=package_info,
            latest_version=None,
            drift_type=DriftType.NOT_FOUND,
            risk_level=RiskLevel.HIGH,
            details=f"Registry error: {package_info.error}",
            changelog_url=package_info.changelog_url,
            release_date=package_info.release_date,
        )

    latest = package_info.latest_version or ""
    drift = detect_drift(dependency.pinned_version, latest)
    risk, details = calculate_risk(drift, package_info, dependency)

    return CheckResult(
        dependency=dependency,
        package_info=package_info,
        latest_version=latest,
        drift_type=drift,
        risk_level=risk,
        details=details,
        changelog_url=package_info.changelog_url,
        release_date=package_info.release_date,
    )


def check_all(
    dependencies: list[Dependency],
    package_infos: dict[tuple[str, str], PackageInfo],
) -> list[CheckResult]:
    """Check all dependencies against their registry info."""
    results: list[CheckResult] = []
    for dep in dependencies:
        key = (dep.base_name.lower(), dep.ecosystem)
        info = package_infos.get(key)
        if info is None:
            # Try exact name
            key = (dep.name, dep.ecosystem)
            info = package_infos.get(key)

        if info is None:
            # Create a not-found info
            info = PackageInfo(
                name=dep.name,
                ecosystem=dep.ecosystem,
                error="No registry data fetched",
            )

        results.append(check_dependency(dep, info))
    return results


def summarize_results(results: list[CheckResult]) -> dict:
    """Generate a summary of check results."""
    summary = {
        "total": len(results),
        "by_risk": {level.value: 0 for level in RiskLevel},
        "by_drift": {dtype.value: 0 for dtype in DriftType},
        "high_risk_packages": [],
        "deprecated_packages": [],
        "up_to_date": 0,
    }

    for result in results:
        summary["by_risk"][result.risk_level.value] += 1
        summary["by_drift"][result.drift_type.value] += 1

        if result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            summary["high_risk_packages"].append(
                {
                    "name": result.dependency.name,
                    "ecosystem": result.dependency.ecosystem,
                    "pinned": result.dependency.pinned_version,
                    "latest": result.latest_version,
                    "risk": result.risk_level.value,
                    "details": result.details,
                }
            )

        if result.drift_type == DriftType.DEPRECATED:
            summary["deprecated_packages"].append(
                {
                    "name": result.dependency.name,
                    "message": result.package_info.deprecation_message,
                }
            )

        if result.risk_level == RiskLevel.NONE:
            summary["up_to_date"] += 1

    return summary
