"""CLI commands for mkp-server (Typer interface for storage, imports, rollback and serving)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
import typer
import yaml
from rich.console import Console
from rich.table import Table

from mkp_server.lifecycle import LifecycleManager
from mkp_server.models import RollbackMode, StorageConfig
from mkp_server.rollback import RollbackManager
from mkp_server.server import MKPServerEngine, create_fastmcp_server
from mkp_server.storage import StorageManager

app = typer.Typer(
    name="mkp-server",
    help="Maritime Knowledge Pack MCP Server & Storage Manager (HLD v3.3.1)",
    add_completion=False,
)
console = Console()


def resolve_storage_path(storage: Optional[Path] = None, config_path: Optional[Path] = None) -> Path:
    """Resolve storage path from explicit CLI argument, config file, environment variable, or default."""
    if storage is not None and str(storage) not in (".", "./storage", "storage"):
        return storage

    candidate_configs = [config_path] if config_path else [Path("server_config.yaml"), Path("config.yaml")]
    for cfg in candidate_configs:
        if cfg and cfg.exists():
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if "storage_path" in data and data["storage_path"]:
                    return Path(data["storage_path"])
            except Exception:
                pass

    if "MKP_STORAGE_PATH" in os.environ and os.environ["MKP_STORAGE_PATH"]:
        return Path(os.environ["MKP_STORAGE_PATH"])

    return storage if storage is not None else Path("./storage")


@app.command("info")
def info_command(
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
):
    """Display comprehensive storage metrics, generation and registered books."""
    resolved_storage = resolve_storage_path(storage, config)
    mgr = StorageManager(resolved_storage)
    stats = mgr.get_stats()
    reg = mgr.load_registry()

    table = Table(title=f"MKP-Server Storage Dashboard [{stats.topic.upper()}]")
    table.add_column("Metric", style="cyan bold")
    table.add_column("Value", style="green")

    table.add_row("Storage Path", stats.storage_path)
    table.add_row("Active Generation", str(stats.active_generation))
    table.add_row("Total Books", str(stats.total_books))
    table.add_row("Total Chunks", str(stats.total_chunks))
    table.add_row("Total Rules", str(stats.total_rules))
    table.add_row("Total Triplets", str(stats.total_triplets))
    table.add_row("Disk Usage", f"{stats.disk_usage_bytes / (1024*1024):.2f} MB")
    table.add_row("Backup Available", "Yes" if stats.has_backup else "No")
    table.add_row("Fallback Available", "Yes" if stats.has_fallback else "No")
    table.add_row("WAL Status", stats.wal_status)

    console.print(table)

    if reg.books:
        b_table = Table(title="Registered Books")
        b_table.add_column("Book ID", style="cyan")
        b_table.add_column("Title", style="white")
        b_table.add_column("T1 Version", style="yellow")
        b_table.add_column("Imported At", style="dim")

        for b_id, rec in reg.books.items():
            b_table.add_row(rec.book_id, rec.title, rec.t1_version, rec.imported_at)

        console.print(b_table)


@app.command("import")
def import_command(
    package: Path = typer.Argument(..., help="Path to .bookpack.zip package or delta"),
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
    update_type: str = typer.Option("full", "--type", "-t", help="Update type: full | t1_delta | user_delta"),
    skip_sig: bool = typer.Option(False, "--skip-sig", help="Skip signature verification (testing only)"),
):
    """Import and apply a Bookpack package or delta with full transactional WAL pipeline."""
    resolved_storage = resolve_storage_path(storage, config)
    mgr = StorageManager(resolved_storage)
    lifecycle = LifecycleManager(mgr)

    console.print(f"[bold cyan]Applying {update_type} from {package.name}...[/bold cyan]")
    ok, msg = lifecycle.apply_bookpack(
        package_path=package,
        update_type=update_type,  # type: ignore
        skip_signature=skip_sig,
    )

    if ok:
        console.print(f"[bold green]SUCCESS:[/bold green] {msg}")
    else:
        console.print(f"[bold red]FAILED:[/bold red] {msg}")
        raise typer.Exit(code=1)


@app.command("rollback")
def rollback_command(
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
    mode: str = typer.Option("auto", "--mode", "-m", help="Rollback mode: auto | base-reset | factory"),
):
    """Rollback storage state using 1-backup (N-1) or multi-tier fallback (Invariants I1, I5, I8)."""
    resolved_storage = resolve_storage_path(storage, config)
    mgr = StorageManager(resolved_storage)
    rb_mgr = RollbackManager(mgr.config)

    rb_mode = RollbackMode(mode)
    console.print(f"[bold yellow]Executing rollback in mode: {rb_mode.value}...[/bold yellow]")
    ok, msg = rb_mgr.execute_rollback(mode=rb_mode)

    if ok:
        console.print(f"[bold green]SUCCESS:[/bold green] {msg}")
    else:
        console.print(f"[bold red]FAILED:[/bold red] {msg}")
        raise typer.Exit(code=1)


@app.command("verify")
def verify_command(
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
):
    """Verify integrity of storage layers and checksums."""
    resolved_storage = resolve_storage_path(storage, config)
    mgr = StorageManager(resolved_storage)
    active_bp = mgr.config.active_dir / "bookpack"
    if not active_bp.exists():
        console.print("[yellow]Active storage is empty.[/yellow]")
        return

    from mkp_server.security import verify_checksums

    ok, errors = verify_checksums(active_bp)
    if ok:
        console.print("[bold green]Storage integrity verified successfully (Invariant I3 PASS).[/bold green]")
    else:
        console.print(f"[bold red]Storage verification errors:[/bold red]\n" + "\n".join(errors))
        raise typer.Exit(code=1)


@app.command("guardrails")
def guardrails_command(
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
):
    """Print compiled static guardrails markdown."""
    resolved_storage = resolve_storage_path(storage, config)
    engine = MKPServerEngine(resolved_storage)
    md = engine.get_guardrails()
    if md:
        console.print(md)
    else:
        console.print("[yellow]No guardrails compiled in active base.[/yellow]")


@app.command("query-rules")
def query_rules_command(
    archetype: str = typer.Option(..., "--archetype", "-a", help="Boat archetype"),
    telemetry: str = typer.Option("{}", "--telemetry", "-t", help="Telemetry JSON dict e.g. '{\"tws\": 25}'"),
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain filter"),
    tier: Optional[str] = typer.Option(None, "--tier", help="Tier filter"),
):
    """Query operational rules matching archetype and telemetry conditions."""
    try:
        telemetry_dict = json.loads(telemetry)
    except Exception as e:
        console.print(f"[bold red]Invalid telemetry JSON:[/bold red] {e}")
        raise typer.Exit(code=1)

    resolved_storage = resolve_storage_path(storage, config)
    engine = MKPServerEngine(resolved_storage)
    rules = engine.query_rules(
        archetype=archetype,
        telemetry=telemetry_dict,
        domain=domain,
        tier=tier,  # type: ignore
    )

    console.print(f"[bold cyan]Found {len(rules)} matching rules:[/bold cyan]")
    for r in rules:
        console.print(f" • [bold yellow]{r['rule_id']}[/bold yellow] ({r['severity'].upper()} | {r['domain']}):")
        for a in r.get("actions", []):
            console.print(f"    - Action: {a.get('action_id')} | {a.get('description')}")


@app.command("remove-book")
def remove_book_command(
    book_id: str = typer.Argument(..., help="Book ID to remove"),
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
):
    """Remove a book record from base registry."""
    resolved_storage = resolve_storage_path(storage, config)
    mgr = StorageManager(resolved_storage)
    removed = mgr.remove_book_from_registry(book_id)
    if removed:
        console.print(f"[bold green]Removed book '{book_id}' from registry.[/bold green]")
    else:
        console.print(f"[yellow]Book '{book_id}' was not found in registry.[/yellow]")


@app.command("serve")
def serve_command(
    storage: Optional[Path] = typer.Option(None, "--storage", "-s", help="Storage root directory"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to server_config.yaml"),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport mode: stdio | http"),
    port: int = typer.Option(8000, "--port", "-p", help="HTTP port (only used with --transport http)"),
):
    """Start FastMCP server serving 10 knowledge tools."""
    resolved_storage = resolve_storage_path(storage, config)
    server = create_fastmcp_server(resolved_storage)
    if transport == "http":
        console.print(f"[bold green]Starting FastMCP server on http://127.0.0.1:{port} (storage: {resolved_storage})[/bold green]")
        server.run(transport="sse", port=port, host="127.0.0.1")
    else:
        console.print(f"[bold green]Starting FastMCP server via stdio transport (storage: {resolved_storage})[/bold green]")
        server.run(transport="stdio")


def main():
    app()


if __name__ == "__main__":
    main()
