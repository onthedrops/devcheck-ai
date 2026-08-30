"""Tests for manifest parsing."""

from pathlib import Path

from devcheck_ai.manifests import (
    collect_dependencies,
    discover_manifests,
    parse_package_json,
    parse_pyproject_toml,
    parse_requirements_txt,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestRequirementsTxt:
    def test_parse_basic(self):
        req_path = FIXTURES / "requirements.txt"
        result = parse_requirements_txt(req_path)

        assert result.ecosystem == "pypi"
        assert len(result.dependencies) == 11

        # Check specific packages
        names = {d.name.lower() for d in result.dependencies}
        assert "requests" in names
        assert "openai" in names
        assert "anthropic" in names
        assert "fastapi" in names
        assert "pydantic" in names

    def test_version_extraction(self):
        req_path = FIXTURES / "requirements.txt"
        result = parse_requirements_txt(req_path)

        req_dep = next(d for d in result.dependencies if d.name.lower() == "requests")
        assert req_dep.pinned_version == "2.28.0"

        openai_dep = next(d for d in result.dependencies if d.name.lower() == "openai")
        assert openai_dep.pinned_version == "1.0.0"

    def test_extras_parsing(self):
        req_path = FIXTURES / "requirements.txt"
        result = parse_requirements_txt(req_path)

        uvicorn = next(d for d in result.dependencies if d.name.lower() == "uvicorn")
        assert "standard" in uvicorn.extras

    def test_pillow_import_name(self):
        req_path = FIXTURES / "requirements.txt"
        result = parse_requirements_txt(req_path)

        pillow = next(d for d in result.dependencies if d.name.lower() == "pillow")
        assert pillow.base_name == "pillow"


class TestPyprojectToml:
    def test_parse_pep621(self):
        py_path = FIXTURES / "pyproject.toml"
        result = parse_pyproject_toml(py_path)

        assert result.ecosystem == "pypi"
        assert len(result.dependencies) == 6  # 4 main + 2 dev

        names = {d.name.lower() for d in result.dependencies}
        assert "openai" in names
        assert "anthropic" in names
        assert "fastapi" in names
        assert "pydantic" in names
        assert "pytest" in names
        assert "ruff" in names

    def test_dev_extras(self):
        py_path = FIXTURES / "pyproject.toml"
        result = parse_pyproject_toml(py_path)

        pytest_dep = next(d for d in result.dependencies if d.name.lower() == "pytest")
        assert "dev" in pytest_dep.extras


class TestPackageJson:
    def test_parse_basic(self):
        pkg_path = FIXTURES / "package.json"
        result = parse_package_json(pkg_path)

        assert result.ecosystem == "npm"
        assert len(result.dependencies) == 9  # 6 deps + 3 devDeps

        names = {d.name for d in result.dependencies}
        assert "openai" in names
        assert "anthropic" in names
        assert "express" in names
        assert "typescript" in names
        assert "jest" in names

    def test_version_extraction(self):
        pkg_path = FIXTURES / "package.json"
        result = parse_package_json(pkg_path)

        openai = next(d for d in result.dependencies if d.name == "openai")
        assert openai.pinned_version == "4.20.0"

        express = next(d for d in result.dependencies if d.name == "express")
        assert express.pinned_version == "4.18.0"


class TestDiscoverManifests:
    def test_discover_all(self):
        manifests = discover_manifests(FIXTURES)
        ecosystems = {m.ecosystem for m in manifests}
        assert "pypi" in ecosystems
        assert "npm" in ecosystems

    def test_collect_unique(self):
        manifests = discover_manifests(FIXTURES)
        deps = collect_dependencies(manifests)

        # Should deduplicate across requirements.txt and pyproject.toml
        openai_deps = [d for d in deps if d.name.lower() == "openai" and d.ecosystem == "pypi"]
        assert len(openai_deps) == 1
