"""CLI entry point for devcheck-ai."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from .manifests import discover_manifests, collect_dependencies
from .registries import fetch_batch
from .core import check_all, RiskLevel
from .reporters import report_cli, report_json, report_markdown, report_fix
from .smoke import smoke_test
from .breaking_changes import load_registry, match_breaking_changes
from .autofix import FixEngine


@click.command()
@click.argument("project_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json", "markdown"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--output", "-o", "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write output to file (default: stdout)",
)
@click.option(
    "--smoke", is_flag=True,
    help="Run import smoke tests on high-risk dependencies",
)
@click.option(
    "--show-urls", is_flag=True,
    help="Show changelog/repository URLs in output",
)
@click.option(
    "--timeout", default=15, show_default=True,
    help="Registry request timeout in seconds",
)
@click.option(
    "--delay", default=0.1, show_default=True,
    help="Delay between registry requests (rate limiting, seconds)",
)
@click.option(
    "--fail-on", "fail_on",
    type=click.Choice(["none", "medium", "high", "critical"], case_sensitive=False),
    default="high",
    help="Exit with non-zero code if dependencies at or above this risk level are found (default: high)",
)
@click.option(
    "--breaking-changes", "breaking_changes_flag", is_flag=True,
    help="Check dependencies against the AI SDK breaking changes registry for known migration details",
)
@click.option(
    "--fix", "fix_flag", is_flag=True,
    help="Scan source files and show planned auto-fixes as a diff (dry run, no files modified)",
)
@click.option(
    "--write-fixes", "write_fixes_flag", is_flag=True,
    help="Apply auto-fixes to source files (creates backups in .devcheck-ai-backups/ first)",
)
@click.option(
    "--fix-package", "fix_package", default=None,
    help="Only apply fixes for a specific package (e.g., openai, google-generativeai)",
)
def main(
    project_path: Path,
    output_format: str,
    output_file: Path | None,
    smoke: bool,
    show_urls: bool,
    timeout: int,
    delay: float,
    fail_on: str,
    breaking_changes_flag: bool,
    fix_flag: bool,
    write_fixes_flag: bool,
    fix_package: str | None,
):
    """Preflight dependency reality check for AI-generated code.

    Scans a project for dependency manifests (requirements.txt, pyproject.toml,
    package.json), checks each dependency against its live registry (PyPI, npm),
    and reports version drift, deprecations, and risk levels.

    \b
    Examples:
      devcheck-ai ./my-project
      devcheck-ai ./my-project --format json -o report.json
      devcheck-ai ./my-project --smoke --show-urls
      devcheck-ai ./my-project --breaking-changes
      devcheck-ai ./my-project --fix  # dry run, shows diff
      devcheck-ai ./my-project --write-fixes  # applies with backup
      devcheck-ai ./my-project --write-fixes --fix-package openai
    """
    quiet = output_format.lower() in ("json", "markdown") and output_file is None
    console = Console(stderr=True) if quiet else Console()

    # Discover and parse manifests
    console.print(f"[dim]Scanning {project_path} for dependency manifests...[/dim]")
    manifests = discover_manifests(project_path)

    if not manifests and not (fix_flag or write_fixes_flag):
        console.print("[yellow]No dependency manifests found.[/yellow]")
        console.print(
            "Expected: pyproject.toml, requirements.txt, requirements-dev.txt, or package.json"
        )
        sys.exit(2)

    # Collect dependencies (skip if no manifests)
    dependencies = collect_dependencies(manifests) if manifests else []
    if dependencies:
        console.print(f"[dim]Found {len(dependencies)} unique dependencies across "
                       f"{len(manifests)} manifest(s)[/dim]")
    elif manifests:
        console.print("[yellow]No dependencies found in manifests.[/yellow]")
    else:
        console.print("[dim]No manifests found — running source file scan only[/dim]")

    # Skip registry checks if no dependencies
    if not dependencies and not (fix_flag or write_fixes_flag):
        sys.exit(0)

    # Fetch registry info (skip if no dependencies)
    package_infos = {}
    if dependencies:
        console.print("[dim]Fetching live registry data...[/dim]")
        dep_keys = [(dep.base_name, dep.ecosystem) for dep in dependencies]
        package_infos = fetch_batch(dep_keys, timeout=timeout, delay=delay)

        # Check dependencies
        results = check_all(dependencies, package_infos)
    else:
        results = []

    # Run smoke tests if requested
    if smoke:
        console.print()
        console.print("[bold cyan]Running smoke tests on high-risk dependencies...[/bold cyan]")
        for result in results:
            if result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                console.print(f"  Testing {result.dependency.name}... ", end="")
                success, message = smoke_test(result.dependency, timeout=timeout * 2)
                if success:
                    console.print(f"[green]PASS[/green] - {message}")
                    result.details = f"{result.details} | Smoke: {message}"
                else:
                    console.print(f"[red]FAIL[/red] - {message}")
                    result.details = f"{result.details} | Smoke FAIL: {message}"

    # Check breaking changes registry if requested
    bc_matches = {}
    if breaking_changes_flag:
        console.print()
        console.print("[bold cyan]Checking AI SDK breaking changes registry...[/bold cyan]")
        registry = load_registry()
        if registry:
            bc_matches = match_breaking_changes(results, registry)
            if bc_matches:
                console.print(f"  Found {len(bc_matches)} known breaking change(s)")
            else:
                console.print("  No known breaking changes matched")
        else:
            console.print("  [yellow]Registry not found — skipping breaking changes check[/yellow]")

    # Auto-fix mode
    if fix_flag or write_fixes_flag:
        console.print()
        mode = "write" if write_fixes_flag else "dry-run (show diff)"
        console.print(f"[bold cyan]Auto-fix mode: {mode}[/bold cyan]")
        if fix_package:
            console.print(f"  Filtering fixes for package: {fix_package}")

        engine = FixEngine(project_path, package_filter=fix_package)
        plans = engine.scan_all()

        if not plans:
            console.print("  No fixable patterns found in source files.")
        else:
            console.print(f"  Found {len(plans)} fixable pattern(s) across "
                           f"{len(set(p.file_path for p in plans))} file(s)")

            if write_fixes_flag:
                report = engine.apply_fixes(plans, dry_run=False)
                report_fix(report, console)
                if report.syntax_errors:
                    console.print(f"  [bold red]Syntax errors detected in {len(report.syntax_errors)} file(s) — rolled back[/bold red]")
                if report.backup_dir:
                    console.print(f"  [dim]Backups saved to: {report.backup_dir}[/dim]")
            else:
                diff = engine.generate_diff(plans)
                if diff:
                    console.print()
                    console.print("[bold]Planned changes (diff):[/bold]")
                    console.print(diff)
                else:
                    console.print("  [yellow]No changes to apply.[/yellow]")
                console.print()
                console.print("  [dim]Run with --write-fixes to apply these changes.[/dim]")

    # Report
    if output_format.lower() == "json":
        output = report_json(results, breaking_changes=bc_matches)
        if output_file:
            output_file.write_text(output, encoding="utf-8")
            console.print(f"[green]Report written to {output_file}[/green]")
        else:
            print(output)
    elif output_format.lower() == "markdown":
        output = report_markdown(results, breaking_changes=bc_matches)
        if output_file:
            output_file.write_text(output, encoding="utf-8")
            console.print(f"[green]Report written to {output_file}[/green]")
        else:
            print(output)
    else:
        if output_file is None:
            report_cli(results, show_urls=show_urls, breaking_changes=bc_matches)
        else:
            output = report_markdown(results, breaking_changes=bc_matches)
            output_file.write_text(output, encoding="utf-8")
            console.print(f"[green]Report written to {output_file}[/green]")

    # Exit codes
    fail_levels = {
        "none": set(),
        "medium": {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL},
        "high": {RiskLevel.HIGH, RiskLevel.CRITICAL},
        "critical": {RiskLevel.CRITICAL},
    }

    threshold = fail_levels.get(fail_on, {RiskLevel.HIGH, RiskLevel.CRITICAL})
    has_failures = any(r.risk_level in threshold for r in results)

    if has_failures:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
