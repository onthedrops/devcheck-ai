"""Tests for breaking changes registry integration."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from devcheck_ai.breaking_changes import (
    BreakingChange,
    BreakingChangeMatch,
    load_registry,
    match_breaking_changes,
    _matches_version_range,
)
from devcheck_ai.core import CheckResult, DriftType, RiskLevel
from devcheck_ai.manifests import Dependency
from devcheck_ai.registries import PackageInfo


class TestVersionRangeMatching:
    def test_wildcard_matches_anything(self):
        assert _matches_version_range("1.0.0", "*") is True
        assert _matches_version_range("5.2.1", "*") is True

    def test_less_than(self):
        assert _matches_version_range("0.28.0", "<1.0.0") is True
        assert _matches_version_range("0.9.9", "<1.0.0") is True
        assert _matches_version_range("1.0.0", "<1.0.0") is False
        assert _matches_version_range("2.0.0", "<1.0.0") is False

    def test_greater_equal(self):
        assert _matches_version_range("1.0.0", ">=1.0.0") is True
        assert _matches_version_range("2.5.0", ">=1.0.0") is True
        assert _matches_version_range("0.9.0", ">=1.0.0") is False

    def test_compound_range(self):
        assert _matches_version_range("0.1.0", ">=0.1.0,<0.2.0") is True
        assert _matches_version_range("0.1.5", ">=0.1.0,<0.2.0") is True
        assert _matches_version_range("0.2.0", ">=0.1.0,<0.2.0") is False
        assert _matches_version_range("1.0.0", ">=0.1.0,<0.2.0") is False

    def test_package_prefix_in_range(self):
        # Some entries have "google-genai >=1.0.0" as the to_version_range
        # The from_version_range should still match
        assert _matches_version_range("0.5.0", "*") is True


class TestLoadRegistry:
    def test_load_registry_returns_list(self):
        registry = load_registry()
        assert isinstance(registry, list)

    def test_load_registry_has_entries(self):
        registry = load_registry()
        assert len(registry) > 0, "Registry should have at least one entry"

    def test_load_registry_entries_are_breaking_changes(self):
        registry = load_registry()
        for entry in registry:
            assert isinstance(entry, BreakingChange)
            assert entry.package
            assert entry.ecosystem in ("pypi", "npm")
            assert entry.severity in ("low", "medium", "high", "critical")

    def test_load_registry_has_openai(self):
        registry = load_registry()
        packages = [e.package.lower() for e in registry]
        assert "openai" in packages

    def test_load_registry_has_google(self):
        registry = load_registry()
        packages = [e.package.lower() for e in registry]
        assert "google-generativeai" in packages

    def test_load_registry_has_transformers(self):
        registry = load_registry()
        packages = [e.package.lower() for e in registry]
        assert "transformers" in packages


class TestMatchBreakingChanges:
    def _make_result(self, name, ecosystem, pinned, latest, drift=DriftType.MAJOR, risk=RiskLevel.HIGH):
        dep = Dependency(name=name, ecosystem=ecosystem, pinned_version=pinned, manifest="test")
        info = PackageInfo(name=name, ecosystem=ecosystem, latest_version=latest)
        return CheckResult(
            dependency=dep,
            package_info=info,
            latest_version=latest,
            drift_type=drift,
            risk_level=risk,
            details="test",
        )

    def test_match_openai_major_drift(self):
        registry = load_registry()
        results = [self._make_result("openai", "pypi", "0.28.0", "3.1.0")]
        matches = match_breaking_changes(results, registry)
        assert "openai" in matches
        assert matches["openai"].breaking_change.package == "openai"

    def test_no_match_when_up_to_date(self):
        registry = load_registry()
        results = [self._make_result("openai", "pypi", "3.1.0", "3.1.0", drift=DriftType.NONE, risk=RiskLevel.NONE)]
        matches = match_breaking_changes(results, registry)
        assert "openai" not in matches

    def test_no_match_when_minor_drift(self):
        registry = load_registry()
        results = [self._make_result("openai", "pypi", "1.0.0", "1.5.0", drift=DriftType.MINOR, risk=RiskLevel.MEDIUM)]
        matches = match_breaking_changes(results, registry)
        assert "openai" not in matches

    def test_match_google_generativeai(self):
        registry = load_registry()
        results = [self._make_result("google-generativeai", "pypi", "0.7.0", "0.8.0", risk=RiskLevel.CRITICAL)]
        matches = match_breaking_changes(results, registry)
        assert "google-generativeai" in matches

    def test_match_transformers_v4_to_v5(self):
        registry = load_registry()
        results = [self._make_result("transformers", "pypi", "4.30.0", "5.0.0", risk=RiskLevel.HIGH)]
        matches = match_breaking_changes(results, registry)
        assert "transformers" in matches

    def test_match_returns_correct_ecosystem(self):
        registry = load_registry()
        results = [self._make_result("openai", "npm", "3.0.0", "4.0.0")]
        matches = match_breaking_changes(results, registry)
        assert "openai" in matches
        assert matches["openai"].ecosystem == "npm"

    def test_no_match_for_unknown_package(self):
        registry = load_registry()
        results = [self._make_result("some-random-pkg", "pypi", "1.0.0", "2.0.0")]
        matches = match_breaking_changes(results, registry)
        assert "some-random-pkg" not in matches

    def test_match_to_dict_has_fields(self):
        registry = load_registry()
        results = [self._make_result("openai", "pypi", "0.28.0", "3.1.0")]
        matches = match_breaking_changes(results, registry)
        d = matches["openai"].to_dict()
        assert "package" in d
        assert "severity" in d
        assert "changes" in d
        assert "sources" in d
        assert len(d["sources"]) > 0
        assert len(d["changes"]) > 0
