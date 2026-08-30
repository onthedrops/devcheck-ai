"""Smoke testing: verify that dependencies actually import in an isolated environment."""

from __future__ import annotations

import subprocess
import tempfile
import venv
from pathlib import Path

from .manifests import Dependency


def smoke_test_python(
    dependency: Dependency,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Test if a Python package can be imported.

    Creates an isolated venv, installs the package, and attempts import.

    Returns:
        Tuple of (success, message).
    """
    import_name = _python_import_name(dependency.base_name)

    # Create a temporary venv
    with tempfile.TemporaryDirectory(prefix="devcheck_") as tmpdir:
        venv_path = Path(tmpdir) / "venv"

        try:
            venv.create(venv_path, with_pip=True, clear=True)
        except Exception as e:
            return False, f"Failed to create venv: {e}"

        pip = str(venv_path / "bin" / "pip")
        python = str(venv_path / "bin" / "python")

        # Install the package
        install_spec = f"{dependency.base_name}=={dependency.pinned_version}"
        try:
            result = subprocess.run(
                [pip, "install", "--no-cache-dir", "--quiet", install_spec],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                # Try latest if pinned version fails
                result = subprocess.run(
                    [pip, "install", "--no-cache-dir", "--quiet", dependency.base_name],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode != 0:
                    return False, f"Install failed: {result.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"Install timed out after {timeout}s"
        except Exception as e:
            return False, f"Install error: {e}"

        # Try to import
        try:
            result = subprocess.run(
                [python, "-c", f"import {import_name}; print('OK')"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return True, f"Successfully imported {import_name}"
            else:
                stderr = result.stderr.strip()
                # Try alternative import names
                alt_names = _alternative_import_names(dependency.base_name)
                for alt in alt_names:
                    result = subprocess.run(
                        [python, "-c", f"import {alt}; print('OK')"],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    if result.returncode == 0:
                        return True, f"Successfully imported {alt}"
                return False, f"Import failed: {stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"Import timed out after {timeout}s"
        except Exception as e:
            return False, f"Import error: {e}"


def smoke_test_node(
    dependency: Dependency,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Test if a Node.js package can be required.

    Creates a temp directory, installs the package, and attempts require().

    Returns:
        Tuple of (success, message).
    """
    with tempfile.TemporaryDirectory(prefix="devcheck_") as tmpdir:
        tmp_path = Path(tmpdir)

        # Initialize a minimal package.json
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text('{"name":"devcheck-temp","version":"0.0.0"}')

        install_spec = f"{dependency.name}@{dependency.pinned_version}"
        try:
            result = subprocess.run(
                ["npm", "install", "--no-save", "--silent", install_spec],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            if result.returncode != 0:
                # Try latest
                result = subprocess.run(
                    ["npm", "install", "--no-save", "--silent", dependency.name],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmpdir,
                )
                if result.returncode != 0:
                    return False, f"npm install failed: {result.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"npm install timed out after {timeout}s"
        except FileNotFoundError:
            return False, "npm not found on PATH"
        except Exception as e:
            return False, f"npm install error: {e}"

        # Try to require
        require_name = dependency.name
        test_script = (
            f"try {{ const m = require('{require_name}'); console.log('OK'); }} catch(e) {{ console.error(e.message); process.exit(1); }}"
        )
        try:
            result = subprocess.run(
                ["node", "-e", test_script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            if result.returncode == 0:
                return True, f"Successfully required {require_name}"
            else:
                return False, f"require failed: {result.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"require timed out after {timeout}s"
        except FileNotFoundError:
            return False, "node not found on PATH"
        except Exception as e:
            return False, f"require error: {e}"


def _python_import_name(package_name: str) -> str:
    """Map a PyPI package name to its import name."""
    # Common mappings
    mappings = {
        "pillow": "PIL",
        "python-dateutil": "dateutil",
        "pyyaml": "yaml",
        "beautifulsoup4": "bs4",
        "pyjwt": "jwt",
        "python-dotenv": "dotenv",
        "google-auth": "google.auth",
        "google-cloud-storage": "google.cloud.storage",
        "azure-core": "azure.core",
        "aws-sdk": "aws",
        "opentelemetry-api": "opentelemetry",
        "opentelemetry-sdk": "opentelemetry.sdk",
        "scikit-learn": "sklearn",
        "tensorflow-gpu": "tensorflow",
        "tensorflow-cpu": "tensorflow",
        "transformers": "transformers",
        "langchain-core": "langchain_core",
        "langchain-openai": "langchain_openai",
        "langchain-anthropic": "langchain_anthropic",
        "openai": "openai",
        "anthropic": "anthropic",
        "google-generativeai": "google.generativeai",
        "google-genai": "google.genai",
        "pinecone-client": "pinecone",
        "chromadb": "chromadb",
        "qdrant-client": "qdrant_client",
        "weaviate-client": "weaviate",
        "pymongo": "pymongo",
        "redis": "redis",
        "celery": "celery",
        "fastapi": "fastapi",
        "flask": "flask",
        "django": "django",
        "uvicorn": "uvicorn",
        "gunicorn": "gunicorn",
        "pytest": "pytest",
        "httpx": "httpx",
        "aiohttp": "aiohttp",
        "requests": "requests",
        "numpy": "numpy",
        "pandas": "pandas",
        "torch": "torch",
        "torchvision": "torchvision",
        "torchaudio": "torchaudio",
        "tiktoken": "tiktoken",
        "sentence-transformers": "sentence_transformers",
        "pydantic": "pydantic",
        "sqlalchemy": "sqlalchemy",
        "alembic": "alembic",
        "click": "click",
        "rich": "rich",
        "packaging": "packaging",
    }

    return mappings.get(package_name.lower(), package_name.lower().replace("-", "_"))


def _alternative_import_names(package_name: str) -> list[str]:
    """Generate alternative import names to try."""
    base = package_name.lower()
    return [
        base,
        base.replace("-", "_"),
        base.replace("_", "-"),
        base.replace("-", ""),
        base.replace("_", ""),
    ]


def smoke_test(dependency: Dependency, timeout: int = 30) -> tuple[bool, str]:
    """Run a smoke test on a dependency.

    Args:
        dependency: The dependency to test.
        timeout: Timeout in seconds for each operation.

    Returns:
        Tuple of (success, message).
    """
    if dependency.ecosystem == "pypi":
        return smoke_test_python(dependency, timeout=timeout)
    elif dependency.ecosystem == "npm":
        return smoke_test_node(dependency, timeout=timeout)
    else:
        return False, f"Smoke testing not supported for ecosystem: {dependency.ecosystem}"
