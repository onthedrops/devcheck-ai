"""Output reporters: CLI table, JSON, and Markdown."""

from __future__ import annotations

import json
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .core import CheckResult, RiskLevel, summarize_results
from .breaking_changes import BreakingChangeMatch
from .autofix import FixReport


RISK_COLORS = {
    RiskLevel.NONE: "green",
    RiskLevel.LOW: "yellow",
    RiskLevel.MEDIUM: "dark_orange",
    RiskLevel.HIGH: "red",
    RiskLevel.CRITICAL: "bold red on black",
}

RISK_ICONS = {
    RiskLevel.NONE: "[green]OK[/green]",
    RiskLevel.LOW: "[yellow]LOW[/yellow]",
    RiskLevel.MEDIUM: "[dark_orange]MED[/dark_orange]",
    RiskLevel.HIGH: "[red]HIGH[/red]",
    RiskLevel.CRITICAL: "[bold red]CRIT[/bold red]",
}


def report_cli(
    results: list[CheckResult],
    show_urls: bool = False,
    breaking_changes: dict[str, BreakingChangeMatch] | None = None,
) -> None:
    """Print results as a rich CLI table."""
    console = Console()
    summary = summarize_results(results)

    # Summary panel
    total = summary["total"]
    up_to_date = summary["up_to_date"]
    high = len(summary["high_risk_packages"])
    deprecated = len(summary["deprecated_packages"])

    summary_text = (
        f"[bold]{total}[/bold] dependencies checked  |  "
        f"[green]{up_to_date} up to date[/green]  |  "
        f"[red]{high} high risk[/red]  |  "
        f"[bold red]{deprecated} deprecated[/bold red]"
    )
    console.print(Panel(summary_text, title="devcheck-ai Report", border_style="blue"))
    console.print()

    # Results table
    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Status", width=8)
    table.add_column("Package", style="bold")
    table.add_column("Ecosystem", width=10)
    table.add_column("Pinned", width=14)
    table.add_column("Latest", width=14)
    table.add_column("Released", width=12)
    table.add_column("Details", overflow="fold")

    for result in sorted(results, key=lambda r: list(RiskLevel).index(r.risk_level), reverse=True):
        risk_icon = RISK_ICONS.get(result.risk_level, "?")
        color = RISK_COLORS.get(result.risk_level, "white")

        latest = result.latest_version or "N/A"
        released = result.release_date or "N/A"
        if show_urls and result.changelog_url:
            details = f"{result.details}\n[dim]{result.changelog_url}[/dim]"
        else:
            details = result.details

        table.add_row(
            risk_icon,
            result.dependency.name,
            result.dependency.ecosystem,
            result.dependency.pinned_version,
            latest,
            released,
            details,
        )

    console.print(table)
    console.print()

    # High risk details
    if summary["high_risk_packages"]:
        console.print("[bold red]High Risk Dependencies:[/bold red]")
        for pkg in summary["high_risk_packages"]:
            console.print(
                f"  [red]{pkg['name']}[/red] ({pkg['ecosystem']}) "
                f"pinned={pkg['pinned']} latest={pkg.get('latest', 'N/A')}"
            )
            console.print(f"    {pkg['details']}")
        console.print()

    # Breaking changes details
    if breaking_changes:
        console.print("[bold magenta]Known Breaking Changes:[/bold magenta]")
        console.print()
        for pkg_name, match in breaking_changes.items():
            bc = match.breaking_change
            sev_color = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "dim"}.get(bc.severity, "white")
            console.print(
                f"  [{sev_color}]{bc.severity.upper()}[/] [bold]{match.package}[/bold] "
                f"({match.ecosystem}) {match.pinned_version} -> {match.latest_version}"
            )
            console.print(f"    {bc.summary}")
            for change in bc.changes:
                before = change.get("symbol_before", "")
                after = change.get("symbol_after", "")
                if before or after:
                    console.print(f"    [dim]{before}[/dim] -> [cyan]{after}[/cyan]")
                note = change.get("migration_note", "")
                if note:
                    console.print(f"    [dim]{note}[/dim]")
            for source in bc.sources[:2]:
                console.print(f"    [blue]{source.get('title', 'Source')}[/blue]: {source.get('url', '')}")
            console.print()


def report_json(
    results: list[CheckResult],
    breaking_changes: dict[str, BreakingChangeMatch] | None = None,
) -> str:
    """Generate JSON output."""
    summary = summarize_results(results)

    output = {
        "summary": summary,
        "results": [
            {
                "name": r.dependency.name,
                "ecosystem": r.dependency.ecosystem,
                "pinned_version": r.dependency.pinned_version,
                "latest_version": r.latest_version,
                "release_date": r.release_date,
                "drift_type": r.drift_type.value,
                "risk_level": r.risk_level.value,
                "details": r.details,
                "changelog_url": r.changelog_url,
                "manifest": r.dependency.manifest,
                "deprecated": r.package_info.is_deprecated,
                "deprecation_message": r.package_info.deprecation_message,
                "repository_url": r.package_info.repository_url,
            }
            for r in results
        ],
    }
    if breaking_changes:
        output["breaking_changes"] = {
            name: match.to_dict() for name, match in breaking_changes.items()
        }
    return json.dumps(output, indent=2)


def report_markdown(
    results: list[CheckResult],
    breaking_changes: dict[str, BreakingChangeMatch] | None = None,
) -> str:
    """Generate a Markdown report."""
    summary = summarize_results(results)
    total = summary["total"]
    up_to_date = summary["up_to_date"]
    high = len(summary["high_risk_packages"])
    deprecated = len(summary["deprecated_packages"])

    lines = [
        "# devcheck-ai Report",
        "",
        f"**{total} dependencies checked** | "
        f"{up_to_date} up to date | "
        f"{high} high risk | "
        f"{deprecated} deprecated",
        "",
    ]

    if summary["high_risk_packages"]:
        lines.append("## High Risk Dependencies")
        lines.append("")
        lines.append("| Package | Ecosystem | Pinned | Latest | Risk | Details |")
        lines.append("|---------|-----------|--------|--------|------|---------|")
        for pkg in summary["high_risk_packages"]:
            lines.append(
                f"| {pkg['name']} | {pkg['ecosystem']} | "
                f"{pkg['pinned']} | {pkg.get('latest', 'N/A')} | "
                f"{pkg['risk'].upper()} | {pkg['details']} |"
            )
        lines.append("")

    if breaking_changes:
        lines.append("## Known Breaking Changes")
        lines.append("")
        lines.append("| Package | Ecosystem | Pinned | Latest | Severity | Summary |")
        lines.append("|---------|-----------|--------|--------|----------|---------|")
        for name, match in breaking_changes.items():
            bc = match.breaking_change
            lines.append(
                f"| {match.package} | {match.ecosystem} | "
                f"{match.pinned_version} | {match.latest_version} | "
                f"{bc.severity.upper()} | {bc.summary} |"
            )
        lines.append("")
        # Detailed changes
        for name, match in breaking_changes.items():
            bc = match.breaking_change
            lines.append(f"### {match.package} ({match.ecosystem})")
            lines.append("")
            lines.append(f"**{bc.summary}**")
            lines.append("")
            for change in bc.changes:
                before = change.get("symbol_before", "")
                after = change.get("symbol_after", "")
                ctype = change.get("change_type", "")
                lines.append(f"- **{ctype}**: `{before}` -> `{after}`")
                note = change.get("migration_note", "")
                if note:
                    lines.append(f"  - {note}")
            lines.append("")
            lines.append("**Sources:**")
            for source in bc.sources:
                lines.append(f"- [{source.get('title', 'Source')}]({source.get('url', '')})")
            lines.append("")

    lines.append("## Full Results")
    lines.append("")
    lines.append("| Status | Package | Ecosystem | Pinned | Latest | Released | Details |")
    lines.append("|--------|---------|-----------|--------|--------|----------|---------|")

    for result in sorted(results, key=lambda r: list(RiskLevel).index(r.risk_level), reverse=True):
        status = result.risk_level.value.upper()
        latest = result.latest_version or "N/A"
        released = result.release_date or "N/A"
        details = result.details.replace("|", "\\|")
        lines.append(
            f"| {status} | {result.dependency.name} | "
            f"{result.dependency.ecosystem} | "
            f"{result.dependency.pinned_version} | {latest} | "
            f"{released} | {details} |"
        )

    lines.append("")
    return "\n".join(lines)


def report_fix(report: FixReport, console: Console) -> None:
    """Print auto-fix results to the console."""
    console.print()
    console.print(f"  [green]Applied:[/green] {report.total_applied} fix(es)")
    console.print(f"  [yellow]Skipped:[/yellow] {report.total_skipped} fix(es)")
    console.print(f"  Files modified: {report.total_files_modified}")

    if report.syntax_errors:
        console.print()
        console.print("  [bold red]Syntax Errors (files rolled back):[/bold red]")
        for err in report.syntax_errors:
            console.print(f"    {err}")

    # Show per-fix details
    applied = [p for p in report.plans if p.applied]
    skipped = [p for p in report.plans if not p.applied]

    if applied:
        console.print()
        console.print("  [bold green]Applied Fixes:[/bold green]")
        for plan in applied:
            console.print(
                f"    [green]✓[/green] {plan.file_path.name}:{plan.line} "
                f"[{plan.rule_id}] {plan.old_text[:60]}"
            )
            if plan.migration_note:
                console.print(f"      [dim]{plan.migration_note}[/dim]")

    if skipped:
        console.print()
        console.print("  [bold yellow]Skipped Fixes:[/bold yellow]")
        for plan in skipped:
            reason = plan.skipped_reason or "unknown"
            console.print(
                f"    [yellow]→[/yellow] {plan.file_path.name}:{plan.line} "
                f"[{plan.rule_id}] — {reason}"
            )
