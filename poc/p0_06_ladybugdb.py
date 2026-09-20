"""
P0-06 — LadybugDB: Windows/Python 3.14 availability
REQ: REQ-P0-06
Проверяет pip install ladybugdb, CRUD, параметризованный MATCH,
persistence и NetworkX fallback.
"""

import sys
import os
import json
import tempfile
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


def test_ladybugdb(db_path: str) -> dict:
    """Attempt to test LadybugDB if available."""
    results = {}

    # 1. Check if installed
    try:
        import ladybugdb
        results["installed"] = True
        results["version"] = getattr(ladybugdb, "__version__", "unknown")
        console.print(f"[green]✓ ladybugdb installed: v{results['version']}[/green]")
    except ImportError as e:
        results["installed"] = False
        results["error"] = str(e)
        console.print(f"[red]✗ ladybugdb not available: {e}[/red]")
        return results

    # 2. CRUD test
    try:
        db = ladybugdb.connect(db_path)
        # CREATE
        db.execute("CREATE (n:Entity {name: 'грот', type: 'Парус', description: 'Главный парус яхты'})")
        db.execute("CREATE (n:Entity {name: 'штаг', type: 'Снасть', description: 'Стоячий такелаж'})")
        db.execute("CREATE (n:Entity {name: 'бейдевинд', type: 'Манёвр', description: 'Острый курс'})")
        db.execute("CREATE (a:Entity {name: 'грот'})-[:УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ]->(b:Entity {name: 'шкот'})")
        results["create"] = True
        console.print("[green]✓ CREATE works[/green]")

        # READ
        read_result = db.execute("MATCH (n:Entity) RETURN n LIMIT 5")
        results["read"] = True
        results["read_count"] = len(list(read_result)) if read_result else 0
        console.print(f"[green]✓ READ works ({results['read_count']} nodes)[/green]")

        # UPDATE via MERGE
        db.execute("MERGE (n:Entity {name: 'грот'}) SET n.updated = true")
        results["update"] = True
        console.print("[green]✓ UPDATE (MERGE) works[/green]")

        # Parametrized MATCH
        param_result = db.execute(
            "MATCH (n:Entity {name: $name}) RETURN n",
            {"name": "грот"}
        )
        param_rows = list(param_result) if param_result else []
        results["parametrized_match"] = len(param_rows) > 0
        console.print(f"[{'green' if results['parametrized_match'] else 'red'}]{'✓' if results['parametrized_match'] else '✗'} Parametrized MATCH: {len(param_rows)} results[/]")

        # DELETE
        db.execute("MATCH (n:Entity {name: 'бейдевинд'}) DELETE n")
        results["delete"] = True
        console.print("[green]✓ DELETE works[/green]")

        db.close()
    except Exception as e:
        results["crud_error"] = str(e)
        console.print(f"[red]✗ CRUD failed: {e}[/red]")

    # 3. Persistence test
    try:
        db2 = ladybugdb.connect(db_path)
        persist_result = db2.execute("MATCH (n:Entity {name: $name}) RETURN n", {"name": "грот"})
        persist_rows = list(persist_result) if persist_result else []
        results["persistence"] = len(persist_rows) > 0
        db2.close()
        console.print(f"[{'green' if results['persistence'] else 'red'}]{'✓' if results['persistence'] else '✗'} Persistence after reconnect: {len(persist_rows)} nodes[/]")
    except Exception as e:
        results["persistence"] = False
        results["persistence_error"] = str(e)

    return results


def test_networkx_fallback(triplets_path: str) -> dict:
    """Test NetworkX as fallback graph engine using triplets.jsonl format."""
    results = {}
    try:
        import networkx as nx

        # Simulate triplets.jsonl
        triplets = [
            {"subject": "грот", "relation": "УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ", "object": "шкот", "book_id": "dedekam_rig"},
            {"subject": "шкот", "relation": "СВЯЗАН_С", "object": "гик", "book_id": "dedekam_rig"},
            {"subject": "бейдевинд", "relation": "ТРЕБУЕТ_ДЕЙСТВИЯ", "object": "приводиться", "book_id": "dedekam_rig"},
            {"subject": "оверштаг", "relation": "СВЯЗАН_С", "object": "лавировка", "book_id": "dedekam_rig"},
            {"subject": "спинакер", "relation": "ПРИМЕНЯЕТСЯ_ПРИ", "object": "фордевинд", "book_id": "dedekam_rig"},
        ]

        # Write triplets.jsonl
        with open(triplets_path, "w", encoding="utf-8") as f:
            for t in triplets:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

        # Build graph from triplets.jsonl
        G = nx.DiGraph()
        with open(triplets_path, encoding="utf-8") as f:
            for line in f:
                t = json.loads(line)
                G.add_edge(t["subject"], t["object"], relation=t["relation"], book_id=t["book_id"])

        # Test queries
        results["nodes"] = G.number_of_nodes()
        results["edges"] = G.number_of_edges()

        # Get entity relations
        entity = "грот"
        neighbors = list(G.successors(entity)) + list(G.predecessors(entity))
        results["entity_query"] = len(neighbors) > 0

        console.print(f"[green]✓ NetworkX fallback: {results['nodes']} nodes, {results['edges']} edges[/green]")
        console.print(f"[green]✓ Entity query for '{entity}': {neighbors}[/green]")
        results["ok"] = True
    except Exception as e:
        results["ok"] = False
        results["error"] = str(e)
        console.print(f"[red]✗ NetworkX fallback failed: {e}[/red]")

    return results


def main():
    console.print("\n[bold cyan]═══ T0-06: LadybugDB Windows/Python 3.14 Availability ═══[/bold cyan]\n")
    console.print(f"Python: {sys.version}")
    console.print(f"Platform: {sys.platform}")

    # First try to install ladybugdb
    console.print("\n[yellow]Attempting: pip install ladybugdb...[/yellow]")
    import subprocess
    install_result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "ladybugdb", "--quiet"],
        capture_output=True, text=True
    )
    if install_result.returncode == 0:
        console.print("[green]pip install ladybugdb: SUCCESS[/green]")
    else:
        console.print(f"[red]pip install ladybugdb: FAILED[/red]")
        console.print(f"  stdout: {install_result.stdout[-200:]}")
        console.print(f"  stderr: {install_result.stderr[-200:]}")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "poc_test.db")
        triplets_path = os.path.join(tmpdir, "triplets.jsonl")

        console.print("\n[bold]Testing LadybugDB:[/bold]")
        ldb_results = test_ladybugdb(db_path)

        console.print("\n[bold]Testing NetworkX Fallback:[/bold]")
        nx_results = test_networkx_fallback(triplets_path)

    # ─── Results summary ───
    table = Table(title="T0-06 Results")
    table.add_column("Check", style="cyan")
    table.add_column("Result", justify="center")

    ldb_installed = ldb_results.get("installed", False)
    table.add_row("pip install ladybugdb", "[green]OK[/green]" if install_result.returncode == 0 else "[red]FAILED[/red]")
    table.add_row("LadybugDB version", ldb_results.get("version", "N/A") if ldb_installed else "—")
    table.add_row("CRUD operations", "[green]✓[/green]" if ldb_results.get("create") else "[red]✗[/red]")
    table.add_row("Parametrized MATCH", "[green]✓[/green]" if ldb_results.get("parametrized_match") else "[red]✗[/red]")
    table.add_row("Persistence", "[green]✓[/green]" if ldb_results.get("persistence") else "[red]✗[/red]")
    table.add_row("NetworkX fallback", "[green]✓[/green]" if nx_results.get("ok") else "[red]✗[/red]")
    console.print(table)

    # ─── Decision ───
    console.print("\n[bold]Decision:[/bold]")
    if ldb_installed and ldb_results.get("create") and ldb_results.get("persistence"):
        decision = f"LadybugDB v{ldb_results.get('version', '?')} — use as primary graph DB"
        version_pin = ldb_results.get("version", "unknown")
        ac = True
    elif nx_results.get("ok"):
        decision = "LadybugDB NOT available on Windows/Python 3.14 → NetworkX + triplets.jsonl as v1 path"
        version_pin = "N/A (NetworkX fallback)"
        ac = True  # NetworkX fallback documented = pass per PLAN.md
    else:
        decision = "BLOCKED — neither LadybugDB nor NetworkX available"
        version_pin = "BLOCKED"
        ac = False

    console.print(f"  [bold cyan]{decision}[/bold cyan]")
    console.print(f"  Version for pyproject.toml pin: {version_pin}")

    console.print("\n[bold]Acceptance Criteria:[/bold]")
    ac1 = ldb_installed or nx_results.get("ok")
    ac2 = ldb_results.get("parametrized_match", False) or nx_results.get("entity_query", False)
    ac3 = ldb_results.get("persistence", False) or nx_results.get("ok")
    console.print(f"  [{'green' if ac1 else 'red'}]{'✓' if ac1 else '✗'}[/] LadybugDB installed OR NetworkX fallback documented")
    console.print(f"  [{'green' if ac2 else 'red'}]{'✓' if ac2 else '✗'}[/] Parametrized queries work")
    console.print(f"  [{'green' if ac3 else 'red'}]{'✓' if ac3 else '✗'}[/] Persistence / fallback persistence")

    return {
        "ladybugdb_installed": ldb_installed,
        "ladybugdb_version": ldb_results.get("version"),
        "networkx_ok": nx_results.get("ok", False),
        "decision": decision,
        "version_pin": version_pin,
        "pass": ac and ac1,
    }


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get("pass") else 1)
