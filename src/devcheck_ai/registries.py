"""Registry clients for PyPI and npm."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class PackageInfo:
    """Information about a package from its registry."""

    name: str
    ecosystem: str  # "pypi" or "npm"
    latest_version: Optional[str] = None
    latest_stable_version: Optional[str] = None
    release_date: Optional[str] = None  # ISO date of latest release
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    repository_url: Optional[str] = None
    homepage_url: Optional[str] = None
    changelog_url: Optional[str] = None
    description: Optional[str] = None
    error: Optional[str] = None
    yanked_versions: list[str] = field(default_factory=list)


PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
NPM_JSON_URL = "https://registry.npmjs.org/{package}"


def fetch_pypi_info(package_name: str, timeout: int = 15) -> PackageInfo:
    """Fetch package information from PyPI JSON API."""
    url = PYPI_JSON_URL.format(package=package_name)
    info = PackageInfo(name=package_name, ecosystem="pypi")

    try:
        resp = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        if resp.status_code == 404:
            info.error = "Package not found on PyPI"
            return info
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        info.error = f"Request failed: {e}"
        return info

    info_data = data.get("info", {})
    info.latest_version = info_data.get("version")
    info.description = info_data.get("summary")
    info.homepage_url = info_data.get("home_page") or info_data.get("project_url")

    # Get release date from the latest version's uploads
    releases = data.get("releases", {})
    if info.latest_version and info.latest_version in releases:
        upload_list = releases[info.latest_version]
        if upload_list:
            upload_time = upload_list[0].get("upload_time_iso_8601")
            if upload_time:
                info.release_date = upload_time[:10]  # ISO date only

    # Check for yanked versions
    for version, upload_list in releases.items():
        if upload_list and upload_list[0].get("yanked"):
            info.yanked_versions.append(version)

    # Repository URL and changelog URL
    project_urls = info_data.get("project_urls") or {}
    for label, url in project_urls.items():
        label_lower = label.lower()
        if "repository" in label_lower or "source" in label_lower:
            if not info.repository_url:
                info.repository_url = url
        if "changelog" in label_lower or "change" in label_lower:
            if not info.changelog_url:
                info.changelog_url = url
    if not info.repository_url:
        info.repository_url = info_data.get("project_url")

    # PyPI doesn't have a "deprecated" flag, but we can check
    # if the package has been replaced or if the description mentions it
    desc = (info.description or "").lower()
    if "deprecated" in desc or "no longer maintained" in desc or "unmaintained" in desc:
        info.is_deprecated = True
        info.deprecation_message = info.description

    return info


def fetch_npm_info(package_name: str, timeout: int = 15) -> PackageInfo:
    """Fetch package information from npm registry."""
    url = NPM_JSON_URL.format(package=package_name)
    info = PackageInfo(name=package_name, ecosystem="npm")

    try:
        resp = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        if resp.status_code == 404:
            info.error = "Package not found on npm"
            return info
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        info.error = f"Request failed: {e}"
        return info

    # Latest version
    dist_tags = data.get("dist-tags", {})
    info.latest_version = dist_tags.get("latest")

    # Release date from the latest version's time
    times = data.get("time", {})
    if info.latest_version and info.latest_version in times:
        release_time = times[info.latest_version]
        if release_time:
            info.release_date = release_time[:10]

    # Package metadata
    latest_data = data.get("versions", {}).get(info.latest_version, {})

    info.description = data.get("description") or latest_data.get("description")
    info.homepage_url = data.get("homepage") or latest_data.get("homepage")

    # Repository URL
    repo = data.get("repository") or latest_data.get("repository")
    if isinstance(repo, dict):
        repo_url = repo.get("url", "")
        # Clean up git+ and git:// prefixes, strip .git suffix
        repo_url = repo_url.replace("git+", "").replace("git://", "https://")
        repo_url = repo_url.removesuffix(".git")
        info.repository_url = repo_url
    elif isinstance(repo, str):
        repo_url = repo.replace("git+", "").replace("git://", "https://")
        repo_url = repo_url.removesuffix(".git")
        info.repository_url = repo_url

    # Check for npm deprecation (can be at package level or version level)
    deprecated_msg = data.get("deprecated")
    if deprecated_msg:
        info.is_deprecated = True
        info.deprecation_message = deprecated_msg
    elif latest_data.get("deprecated"):
        info.is_deprecated = True
        info.deprecation_message = latest_data["deprecated"]

    # Check for unmaintained: no release in over 2 years
    if info.release_date:
        try:
            from datetime import datetime, timedelta

            release_dt = datetime.fromisoformat(info.release_date)
            two_years_ago = datetime.now() - timedelta(days=730)
            if release_dt < two_years_ago:
                if not info.is_deprecated:
                    info.is_deprecated = True
                    info.deprecation_message = f"Potentially unmaintained: last release {info.release_date}"
        except (ValueError, TypeError):
            pass

    return info


def fetch_package_info(package_name: str, ecosystem: str, timeout: int = 15) -> PackageInfo:
    """Fetch package info from the appropriate registry."""
    if ecosystem == "pypi":
        return fetch_pypi_info(package_name, timeout=timeout)
    elif ecosystem == "npm":
        return fetch_npm_info(package_name, timeout=timeout)
    else:
        return PackageInfo(
            name=package_name,
            ecosystem=ecosystem,
            error=f"Unsupported ecosystem: {ecosystem}",
        )


def fetch_batch(
    dependencies: list[tuple[str, str]],
    timeout: int = 15,
    delay: float = 0.1,
) -> dict[tuple[str, str], PackageInfo]:
    """Fetch info for multiple packages with rate limiting.

    Args:
        dependencies: List of (package_name, ecosystem) tuples.
        timeout: Request timeout in seconds.
        delay: Delay between requests in seconds (for rate limiting).

    Returns:
        Dict mapping (name, ecosystem) -> PackageInfo
    """
    results: dict[tuple[str, str], PackageInfo] = {}
    for name, ecosystem in dependencies:
        key = (name, ecosystem)
        if key in results:
            continue
        results[key] = fetch_package_info(name, ecosystem, timeout=timeout)
        if delay > 0:
            time.sleep(delay)
    return results
