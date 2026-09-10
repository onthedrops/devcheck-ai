"""Tests for breaking changes registry integration."""

import hashlib
import json
import os
import time

from devcheck_ai import breaking_changes as bc
from devcheck_ai.breaking_changes import (
    BreakingChange,
    _matches_version_range,
    load_registry,
    match_breaking_changes,
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


class TestRegistryCache:
    """Cache and remote-refresh behaviour for the breaking-changes registry."""

    def test_cache_not_fresh_when_missing(self, tmp_path):
        assert bc._cache_is_fresh(tmp_path / "absent.json") is False

    def test_cache_fresh_when_just_written(self, tmp_path):
        p = tmp_path / "registry.json"
        p.write_text("{}")
        assert bc._cache_is_fresh(p) is True

    def test_cache_stale_past_ttl(self, tmp_path):
        p = tmp_path / "registry.json"
        p.write_text("{}")
        old = time.time() - (bc.CACHE_TTL_SECONDS + 60)
        os.utime(p, (old, old))
        assert bc._cache_is_fresh(p) is False

    def test_fetch_returns_none_on_network_error(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no network")

        monkeypatch.setattr("requests.get", boom)
        assert bc.fetch_registry() is None

    def test_fetch_rejects_payload_without_entries(self, monkeypatch, tmp_path):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"version": "1", "total_changes": 0}

        monkeypatch.setattr("requests.get", lambda *a, **k: Resp())
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "registry.json")
        assert bc.fetch_registry() is None
        assert not (tmp_path / "registry.json").exists()

    def test_fetch_rejects_empty_entries(self, monkeypatch, tmp_path):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"entries": []}

        monkeypatch.setattr("requests.get", lambda *a, **k: Resp())
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "registry.json")
        assert bc.fetch_registry() is None

    def test_fetch_writes_cache_on_valid_payload(self, monkeypatch, tmp_path):
        payload = {"entries": [{"package": "openai", "ecosystem": "pypi"}]}

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr("requests.get", lambda *a, **k: Resp())
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "registry.json")
        result = bc.fetch_registry()
        assert result == tmp_path / "registry.json"
        assert json.loads(result.read_text())["entries"][0]["package"] == "openai"

    def test_load_falls_back_to_bundled_when_offline(self, monkeypatch, tmp_path):
        monkeypatch.setattr("requests.get", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "registry.json")
        registry = bc.load_registry()
        assert len(registry) > 0

    def test_custom_path_skips_network(self, monkeypatch, tmp_path):
        def fail(*a, **k):
            raise AssertionError("network should not be used with custom_path")

        monkeypatch.setattr(bc, "fetch_registry", fail)
        p = tmp_path / "custom.json"
        p.write_text(json.dumps({"entries": [{"package": "cohere", "ecosystem": "pypi"}]}))
        registry = bc.load_registry(custom_path=p)
        assert len(registry) == 1
        assert registry[0].package == "cohere"


class TestRegistryPinning:
    """Optional SHA-256 pinning of the fetched registry."""

    @staticmethod
    def _resp(payload: bytes):
        class Resp:
            content = payload

            def raise_for_status(self):
                pass

            def json(self):
                return json.loads(payload)

        return Resp()

    def test_matching_digest_is_accepted(self, monkeypatch, tmp_path):
        payload = json.dumps({"entries": [{"package": "openai"}]}).encode()
        digest = hashlib.sha256(payload).hexdigest()
        monkeypatch.setenv(bc.REGISTRY_SHA256_ENV, digest)
        monkeypatch.setattr("requests.get", lambda *a, **k: self._resp(payload))
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "r.json")
        assert bc.fetch_registry() is not None

    def test_mismatched_digest_is_rejected(self, monkeypatch, tmp_path):
        payload = json.dumps({"entries": [{"package": "openai"}]}).encode()
        monkeypatch.setenv(bc.REGISTRY_SHA256_ENV, "0" * 64)
        monkeypatch.setattr("requests.get", lambda *a, **k: self._resp(payload))
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "r.json")
        assert bc.fetch_registry() is None
        assert not (tmp_path / "r.json").exists()

    def test_uppercase_pin_is_accepted(self, monkeypatch, tmp_path):
        payload = json.dumps({"entries": [{"package": "openai"}]}).encode()
        digest = hashlib.sha256(payload).hexdigest().upper()
        monkeypatch.setenv(bc.REGISTRY_SHA256_ENV, digest)
        monkeypatch.setattr("requests.get", lambda *a, **k: self._resp(payload))
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "r.json")
        assert bc.fetch_registry() is not None

    def test_no_pin_skips_the_check(self, monkeypatch, tmp_path):
        payload = json.dumps({"entries": [{"package": "openai"}]}).encode()
        monkeypatch.delenv(bc.REGISTRY_SHA256_ENV, raising=False)
        monkeypatch.setattr("requests.get", lambda *a, **k: self._resp(payload))
        monkeypatch.setattr(bc, "CACHE_PATH", tmp_path / "r.json")
        assert bc.fetch_registry() is not None
