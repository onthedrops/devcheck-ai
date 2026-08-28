"""Tests for registry clients (mocked)."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from devcheck_ai.registries import (
    fetch_pypi_info,
    fetch_npm_info,
    fetch_package_info,
    PackageInfo,
)


MOCK_PYPI_RESPONSE = {
    "info": {
        "version": "1.30.0",
        "summary": "Python client for the OpenAI API",
        "home_page": "https://github.com/openai/openai-python",
        "project_urls": {
            "Repository": "https://github.com/openai/openai-python",
            "Changelog": "https://github.com/openai/openai-python/blob/main/CHANGELOG.md",
        },
    },
    "releases": {
        "1.30.0": [{"upload_time_iso_8601": "2024-05-15T10:00:00.000Z", "yanked": False}],
        "0.28.0": [{"upload_time_iso_8601": "2022-01-15T10:00:00.000Z", "yanked": False}],
    },
}

MOCK_NPM_RESPONSE = {
    "name": "openai",
    "description": "Node.js client for the OpenAI API",
    "homepage": "https://github.com/openai/openai-node",
    "repository": {"url": "git+https://github.com/openai/openai-node.git"},
    "dist-tags": {"latest": "4.20.0"},
    "time": {
        "4.20.0": "2024-05-10T10:00:00.000Z",
        "3.0.0": "2023-01-01T10:00:00.000Z",
    },
    "versions": {
        "4.20.0": {"deprecated": None},
        "3.0.0": {"deprecated": "This version is deprecated. Please upgrade."},
    },
}

MOCK_NPM_DEPRECATED = {
    "name": "old-package",
    "description": "A deprecated package",
    "dist-tags": {"latest": "1.0.0"},
    "time": {"1.0.0": "2020-01-01T10:00:00.000Z"},
    "versions": {"1.0.0": {"deprecated": "Package is no longer maintained. Use new-package instead."}},
}


class TestFetchPyPI:
    @patch("devcheck_ai.registries.requests.get")
    def test_fetch_pypi_info(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_PYPI_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = fetch_pypi_info("openai")

        assert info.name == "openai"
        assert info.ecosystem == "pypi"
        assert info.latest_version == "1.30.0"
        assert info.release_date == "2024-05-15"
        assert info.repository_url == "https://github.com/openai/openai-python"
        assert info.changelog_url == "https://github.com/openai/openai-python/blob/main/CHANGELOG.md"
        assert info.error is None

    @patch("devcheck_ai.registries.requests.get")
    def test_pypi_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        info = fetch_pypi_info("nonexistent-pkg")

        assert info.error == "Package not found on PyPI"
        assert info.latest_version is None


class TestFetchNpm:
    @patch("devcheck_ai.registries.requests.get")
    def test_fetch_npm_info(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_NPM_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = fetch_npm_info("openai")

        assert info.name == "openai"
        assert info.ecosystem == "npm"
        assert info.latest_version == "4.20.0"
        assert info.release_date == "2024-05-10"
        assert info.repository_url == "https://github.com/openai/openai-node"
        assert info.error is None

    @patch("devcheck_ai.registries.requests.get")
    def test_npm_deprecated(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_NPM_DEPRECATED
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = fetch_npm_info("old-package")

        assert info.is_deprecated is True
        assert "no longer maintained" in (info.deprecation_message or "")

    @patch("devcheck_ai.registries.requests.get")
    def test_npm_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        info = fetch_npm_info("nonexistent-pkg")

        assert info.error == "Package not found on npm"


class TestFetchPackageInfo:
    def test_unsupported_ecosystem(self):
        info = fetch_package_info("test", "gem")
        assert info.error == "Unsupported ecosystem: gem"

    @patch("devcheck_ai.registries.requests.get")
    def test_dispatches_to_pypi(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_PYPI_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = fetch_package_info("openai", "pypi")
        assert info.ecosystem == "pypi"
        assert info.latest_version == "1.30.0"
