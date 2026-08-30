"""Tests for the core analysis engine."""

from devcheck_ai.core import (
    DriftType,
    RiskLevel,
    calculate_risk,
    check_all,
    check_dependency,
    detect_drift,
    summarize_results,
)
from devcheck_ai.manifests import Dependency
from devcheck_ai.registries import PackageInfo


class TestDetectDrift:
    def test_no_drift(self):
        assert detect_drift("1.2.3", "1.2.3") == DriftType.NONE

    def test_patch_drift(self):
        assert detect_drift("1.2.3", "1.2.5") == DriftType.PATCH

    def test_minor_drift(self):
        assert detect_drift("1.2.3", "1.3.0") == DriftType.MINOR

    def test_major_drift(self):
        assert detect_drift("1.2.3", "2.0.0") == DriftType.MAJOR

    def test_major_drift_large(self):
        assert detect_drift("1.2.3", "5.0.0") == DriftType.MAJOR

    def test_invalid_version_fallback(self):
        # Should still work, falling back to string comparison
        result = detect_drift("abc", "abc")
        assert result == DriftType.NONE


class TestCalculateRisk:
    def test_no_risk(self):
        dep = Dependency(name="test", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="test", ecosystem="pypi", latest_version="1.0.0")
        risk, details = calculate_risk(DriftType.NONE, info, dep)
        assert risk == RiskLevel.NONE

    def test_patch_risk(self):
        dep = Dependency(name="test", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="test", ecosystem="pypi", latest_version="1.0.1")
        risk, details = calculate_risk(DriftType.PATCH, info, dep)
        assert risk == RiskLevel.LOW

    def test_minor_risk(self):
        dep = Dependency(name="test", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="test", ecosystem="pypi", latest_version="1.1.0")
        risk, details = calculate_risk(DriftType.MINOR, info, dep)
        assert risk == RiskLevel.MEDIUM

    def test_major_risk(self):
        dep = Dependency(name="test", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="test", ecosystem="pypi", latest_version="2.0.0")
        risk, details = calculate_risk(DriftType.MAJOR, info, dep)
        assert risk == RiskLevel.HIGH
        assert "Manual review required" in details

    def test_deprecated(self):
        dep = Dependency(name="test", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(
            name="test",
            ecosystem="pypi",
            latest_version="1.0.0",
            is_deprecated=True,
            deprecation_message="Use new-package instead",
        )
        risk, details = calculate_risk(DriftType.NONE, info, dep)
        assert risk == RiskLevel.CRITICAL
        assert "DEPRECATED" in details

    def test_yanked_version(self):
        dep = Dependency(name="test", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(
            name="test",
            ecosystem="pypi",
            latest_version="1.0.0",
            yanked_versions=["1.0.0"],
        )
        risk, details = calculate_risk(DriftType.NONE, info, dep)
        assert risk == RiskLevel.CRITICAL
        assert "yanked" in details


class TestCheckDependency:
    def test_up_to_date(self):
        dep = Dependency(name="requests", pinned_version="2.31.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="requests", ecosystem="pypi", latest_version="2.31.0")
        result = check_dependency(dep, info)

        assert result.risk_level == RiskLevel.NONE
        assert result.drift_type == DriftType.NONE

    def test_major_drift(self):
        dep = Dependency(name="openai", pinned_version="0.28.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="openai", ecosystem="pypi", latest_version="1.30.0")
        result = check_dependency(dep, info)

        assert result.risk_level == RiskLevel.HIGH
        assert result.drift_type == DriftType.MAJOR

    def test_not_found(self):
        dep = Dependency(name="nonexistent", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt")
        info = PackageInfo(name="nonexistent", ecosystem="pypi", error="Package not found")
        result = check_dependency(dep, info)

        assert result.risk_level == RiskLevel.HIGH
        assert result.drift_type == DriftType.NOT_FOUND


class TestCheckAll:
    def test_multiple_deps(self):
        deps = [
            Dependency(name="pkg1", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt"),
            Dependency(name="pkg2", pinned_version="2.0.0", ecosystem="npm", manifest="pkg.json"),
        ]
        infos = {
            ("pkg1", "pypi"): PackageInfo(name="pkg1", ecosystem="pypi", latest_version="1.0.0"),
            ("pkg2", "npm"): PackageInfo(name="pkg2", ecosystem="npm", latest_version="3.0.0"),
        }
        results = check_all(deps, infos)

        assert len(results) == 2
        assert results[0].risk_level == RiskLevel.NONE
        assert results[1].risk_level == RiskLevel.HIGH


class TestSummarizeResults:
    def test_summary_counts(self):
        deps = [
            Dependency(name="pkg1", pinned_version="1.0.0", ecosystem="pypi", manifest="req.txt"),
            Dependency(name="pkg2", pinned_version="2.0.0", ecosystem="pypi", manifest="req.txt"),
            Dependency(name="pkg3", pinned_version="3.0.0", ecosystem="pypi", manifest="req.txt"),
        ]
        infos = {
            ("pkg1", "pypi"): PackageInfo(name="pkg1", ecosystem="pypi", latest_version="1.0.0"),
            ("pkg2", "pypi"): PackageInfo(name="pkg2", ecosystem="pypi", latest_version="2.0.1"),
            ("pkg3", "pypi"): PackageInfo(name="pkg3", ecosystem="pypi", latest_version="4.0.0"),
        }
        results = check_all(deps, infos)
        summary = summarize_results(results)

        assert summary["total"] == 3
        assert summary["up_to_date"] == 1
        assert summary["by_risk"]["low"] == 1
        assert summary["by_risk"]["high"] == 1
        assert len(summary["high_risk_packages"]) == 1
