"""RunPod Interactive Rich Live TUI Dashboard for MKP Pipeline."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repository root is in sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from tools.runpod.logger import OrchestratorLogger


def make_bar_str(percent: float, width: int = 20) -> str:
    """Generates a progress bar string."""
    percent = max(0.0, min(100.0, percent))
    filled_len = int(width * percent / 100.0)
    empty_len = width - filled_len
    return "█" * filled_len + "░" * empty_len


def format_eta(seconds: float | None) -> str:
    """Formats estimated seconds to completion into a human-readable Russian string."""
    if seconds is None:
        return "вычисляется..."
    if seconds <= 0:
        return "готово"
    secs = int(seconds)
    if secs < 60:
        return f"~{secs} сек"
    mins = secs // 60
    rem_secs = secs % 60
    if mins < 60:
        if rem_secs >= 10:
            return f"~{mins} мин {rem_secs} сек"
        return f"~{mins} мин"
    hours = mins // 60
    rem_mins = mins % 60
    if rem_mins > 0:
        return f"~{hours} ч {rem_mins} мин"
    return f"~{hours} ч"



class RunPodDashboard:
    """Renders the Rich Live Terminal Dashboard with metrics, progress, and logs."""

    def __init__(
        self,
        console: Console | None = None,
        logger: OrchestratorLogger | None = None,
        auto_stop: bool = True,
    ) -> None:
        self.console = console or Console(legacy_windows=False, force_terminal=True)
        self.logger = logger
        self.auto_stop = auto_stop
        self.guard_active = True
        self.guard_countdown_sec: int | None = None  # None = not triggered; int = seconds remaining

        # State metrics
        self.pod_name: str = "rtx4090-worker"
        self.pod_status: str = "Running"
        self.cost_per_hr: float = 0.74
        self.uptime_sec: int = 0
        self.start_epoch: float = time.time()
        self._stage_start_times: dict[int, float] = {}
        self._stage_start_completed: dict[int, int] = {}

        self.cpu_percent: float = 0.0
        self.cpu_cores: int = 8
        self.ram_used_gb: float = 0.0
        self.ram_total_gb: float = 32.0
        self.disk_used_gb: float = 0.0
        self.disk_total_gb: float = 40.0

        self.gpu_model: str = "RTX 4090 24GB"
        self.gpu_util_percent: float = 0.0
        self.gpu_temp_c: int = 48
        self.gpu_power_w: int = 80
        self.gpu_vram_used_gb: float = 0.0
        self.gpu_vram_total_gb: float = 24.0
        self.gpu_tps: float = 0.0
        self.net_down_kb: float = 0.0
        self.net_up_kb: float = 0.0

        # Books & Stages
        self.total_books: int = 2
        self.completed_books: int = 0
        self.current_book_title: str = "Illustrated Seamanship (Ivar Dedekam) [EPUB · 5.4 MB]"
        self.stages: list[dict[str, Any]] = [
            {"name": "1. Извлечение текста и диаграмм", "status": "pending", "detail": ""},
            {"name": "2. VLM Аннотирование схем (32B)", "status": "pending", "detail": ""},
            {"name": "3. GraphRAG Семантические триплеты", "status": "pending", "detail": ""},
            {"name": "4. Синтез морских правил", "status": "pending", "detail": ""},
            {"name": "5. Экспорт .bookpack.zip", "status": "pending", "detail": ""},
        ]

    def calculate_eta_seconds(self) -> float | None:
        """Estimates remaining processing time in seconds across stages."""
        if self.completed_books >= self.total_books and all(s.get("status") == "completed" for s in self.stages):
            return 0.0

        # Look for active stage
        active_stage_idx = None
        for idx, stage in enumerate(self.stages):
            if stage.get("status") == "in_progress":
                active_stage_idx = idx
                break

        if active_stage_idx is None:
            return None

        st = self.stages[active_stage_idx]
        completed = st.get("completed", 0)
        total = st.get("total", 0)

        if active_stage_idx not in self._stage_start_times:
            self._stage_start_times[active_stage_idx] = time.time()
            self._stage_start_completed[active_stage_idx] = completed

        elapsed_in_stage = time.time() - self._stage_start_times[active_stage_idx]
        items_done = completed - self._stage_start_completed.get(active_stage_idx, 0)

        if items_done > 0 and total > completed:
            sec_per_item = elapsed_in_stage / items_done
            remaining_in_stage = (total - completed) * sec_per_item

            subsequent_stage_sec = 0.0
            for next_idx in range(active_stage_idx + 1, len(self.stages)):
                if next_idx == 2:  # triplets
                    subsequent_stage_sec += 45.0
                elif next_idx == 3:  # rules
                    subsequent_stage_sec += 15.0
                elif next_idx == 4:  # export
                    subsequent_stage_sec += 5.0

            remaining_for_book = remaining_in_stage + subsequent_stage_sec
            remaining_books = max(0, self.total_books - self.completed_books - 1)
            total_eta = remaining_for_book + (remaining_books * remaining_for_book)
            return max(5.0, total_eta)

        # Fallback to overall weighted elapsed progress
        overall_elapsed = time.time() - self.start_epoch
        stage_weights = [0.05, 0.80, 0.10, 0.03, 0.02]
        current_book_progress = 0.0
        for idx, stage in enumerate(self.stages):
            st_status = stage.get("status", "pending")
            w = stage_weights[idx] if idx < len(stage_weights) else 0.1
            if st_status == "completed":
                current_book_progress += w
            elif st_status == "in_progress":
                comp = stage.get("completed", 0)
                tot = stage.get("total", 100)
                current_book_progress += w * (comp / max(tot, 1))

        overall_progress = (self.completed_books + current_book_progress) / max(self.total_books, 1)
        if overall_progress > 0.05 and overall_elapsed > 3.0:
            total_estimated_time = overall_elapsed / overall_progress
            remaining = total_estimated_time - overall_elapsed
            return max(5.0, remaining)

        return None

    def update_telemetry(self, telem: dict[str, Any]) -> None:
        """Updates internal dashboard state from raw telemetry snapshot."""
        if not telem:
            return

        if "current_book" in telem and telem["current_book"]:
            self.current_book_title = telem["current_book"]

        if "cpu_percent" in telem:
            self.cpu_percent = float(telem["cpu_percent"])
        if "cpu_cores" in telem:
            self.cpu_cores = int(telem["cpu_cores"])
        if "ram_used_gb" in telem:
            self.ram_used_gb = float(telem["ram_used_gb"])
        if "ram_total_gb" in telem:
            self.ram_total_gb = float(telem["ram_total_gb"])
        if "disk_used_gb" in telem:
            self.disk_used_gb = float(telem["disk_used_gb"])
        if "disk_total_gb" in telem:
            self.disk_total_gb = float(telem["disk_total_gb"])
        if "gpu_util" in telem or "gpu_util_percent" in telem:
            self.gpu_util_percent = float(telem.get("gpu_util_percent", telem.get("gpu_util", 0.0)))
        if "vram_used_gb" in telem:
            self.gpu_vram_used_gb = float(telem["vram_used_gb"])
        if "vram_total_gb" in telem:
            self.gpu_vram_total_gb = float(telem["vram_total_gb"])
        if "gpu_temp_c" in telem:
            self.gpu_temp_c = int(telem["gpu_temp_c"])
        if "gpu_power_w" in telem:
            self.gpu_power_w = int(telem["gpu_power_w"])
        if "gpu_tps" in telem:
            self.gpu_tps = float(telem["gpu_tps"])
        elif "stats" in telem and isinstance(telem["stats"], dict) and "gpu_tps" in telem["stats"]:
            self.gpu_tps = float(telem["stats"]["gpu_tps"])

        stages_dict = telem.get("stages", {})
        # Map known stages to 5 dashboard stages
        stage_keys = ["parse", "vlm", "triplets", "rules", "export"]
        labels = [
            "1. Извлечение текста и диаграмм",
            "2. VLM Аннотирование схем (32B)",
            "3. GraphRAG Семантические триплеты",
            "4. Синтез морских правил",
            "5. Экспорт .bookpack.zip",
        ]

        new_stages = []
        for key, label in zip(stage_keys, labels):
            st = stages_dict.get(key, {})
            st_status = st.get("status", "pending")
            completed = st.get("completed", 0)
            total = st.get("total", 0)
            detail = ""
            if st_status != "pending":
                if key == "vlm" and total > 0:
                    detail = f"({completed}/{total} схем)"
                elif key == "triplets" and total > 0:
                    detail = f"({completed}/{total} чанков)"
                elif key == "parse" and st_status == "completed":
                    figures = telem.get("stats", {}).get("figures", 0)
                    detail = f"({figures} изображений найдено)"
                elif key == "rules" and st_status == "completed":
                    detail = f"({completed} правил синтезировано)" if completed > 0 else ""
                elif key == "export" and st_status == "completed":
                    detail = "(архив сформирован)"
            elif key == "parse" and st_status == "completed":
                figures = telem.get("stats", {}).get("figures", 0)
                detail = f"({figures} изображений найдено)"

            new_stages.append({
                "name": label,
                "status": st_status,
                "completed": completed,
                "total": total,
                "detail": detail,
            })
        self.stages = new_stages

    def render_header(self) -> Panel:
        """Builds the top cluster status & system resources panel."""
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(int(time.time() - self.start_epoch)))
        auto_stop_str = "ON (Защита бюджета)" if self.auto_stop else "OFF"
        
        eta_sec = self.calculate_eta_seconds()
        eta_str = format_eta(eta_sec)

        guard_str = ""
        if self.guard_countdown_sec is not None:
            mins, secs = divmod(self.guard_countdown_sec, 60)
            guard_str = f" · [bold red]Auto-Stop Countdown: {mins:02d}:{secs:02d}[/bold red]"

        header_table = Table.grid(expand=True)
        header_table.add_column(justify="left", ratio=1)
        header_table.add_column(justify="right", ratio=1)

        title_text = f"[bold cyan]MKP PIPELINE DASHBOARD — RUNPOD CLUSTER[/bold cyan]    Pod: [bold green]{self.pod_name}[/bold green] ([green]{self.pod_status}[/green] · [yellow]${self.cost_per_hr:.2f}/hr[/yellow])"
        sub_text = f"[bold green][Auto-Stop: {auto_stop_str}][/bold green]{guard_str}"
        uptime_text = f"Uptime: [bold white]{uptime_str}[/bold white] · ETA: [bold green]{eta_str}[/bold green]"

        header_table.add_row(title_text, "")
        header_table.add_row(sub_text, uptime_text)

        # Resources sub-table (2 balanced columns)
        res_table = Table.grid(expand=True, padding=(0, 2))
        res_table.add_column(ratio=1)
        res_table.add_column(ratio=1)

        cpu_bar = make_bar_str(self.cpu_percent, 14)
        gpu_load_bar = make_bar_str(self.gpu_util_percent, 14)

        ram_percent = (self.ram_used_gb / max(self.ram_total_gb, 1)) * 100
        ram_bar = make_bar_str(ram_percent, 14)

        vram_percent = (self.gpu_vram_used_gb / max(self.gpu_vram_total_gb, 1)) * 100
        vram_bar = make_bar_str(vram_percent, 14)

        disk_percent = (self.disk_used_gb / max(self.disk_total_gb, 1)) * 100
        disk_bar = make_bar_str(disk_percent, 14)

        res_table.add_row(
            f"• CPU Load:  [{cpu_bar}] {self.cpu_percent:.0f}% ({self.cpu_cores} vCPUs)",
            f"• GPU Load:  [{gpu_load_bar}] {self.gpu_util_percent:.0f}% ({self.gpu_model})",
        )
        res_table.add_row(
            f"• RAM Usage: [{ram_bar}] {self.ram_used_gb:.1f} / {self.ram_total_gb:.1f} GB ({ram_percent:.0f}%)",
            f"• VRAM:      [{vram_bar}] {self.gpu_vram_used_gb:.1f} / {self.gpu_vram_total_gb:.1f} GB ({vram_percent:.0f}%)",
        )
        res_table.add_row(
            f"• Pod Disk:  [{disk_bar}] {self.disk_used_gb:.1f} / {self.disk_total_gb:.1f} GB ({disk_percent:.0f}%)",
            f"• GPU Stats: Temp: {self.gpu_temp_c}°C · Power: {self.gpu_power_w}W · Speed: [bold cyan]{self.gpu_tps:.1f} t/s[/bold cyan]",
        )

        content = Group(
            header_table,
            Text("━" * 96, style="blue"),
            Text("🖥️ СИСТЕМНЫЕ РЕСУРСЫ:", style="bold yellow"),
            res_table,
        )

        return Panel(content, border_style="blue", padding=(0, 1))

    def render_progress_panel(self) -> Panel:
        """Builds the book queue and processing stages panel."""
        books_pct = (self.completed_books / max(self.total_books, 1)) * 100.0
        books_bar = make_bar_str(books_pct, 24)
        eta_sec = self.calculate_eta_seconds()
        eta_str = format_eta(eta_sec)

        lines = [
            f"[bold cyan][ОЧЕРЕДЬ КНИГ][/bold cyan]",
            f"  Всего книг: [[bold green]{books_bar}[/bold green]] {books_pct:.1f}% (Обработано {self.completed_books} из {self.total_books}) · [bold cyan]Осталось: {eta_str}[/bold cyan]",
            f"  Текущая:    [bold white]{self.current_book_title}[/bold white]",
            "",
            f"[bold cyan][ЭТАПЫ ОБРАБОТКИ][/bold cyan]",
        ]

        symbols = ["├──", "├──", "├──", "├──", "└──"]
        for idx, stage in enumerate(self.stages):
            prefix = symbols[idx] if idx < len(symbols) else "├──"
            name = stage["name"]
            st = stage.get("status", "pending")
            detail = stage.get("detail", "")

            if st == "completed":
                status_str = "[bold green][✓ ВЫПОЛНЕНО ][/bold green]"
            elif st == "in_progress":
                comp = stage.get("completed", 0)
                tot = stage.get("total", 100)
                pct = (comp / max(tot, 1)) * 100.0
                bar = make_bar_str(pct, 14)
                status_str = f"[[bold cyan]{bar}[/bold cyan]] {pct:.1f}%"
            else:
                status_str = "[yellow][· В ОЧЕРЕДИ ][/yellow]"

            if detail:
                lines.append(f"  {prefix} {name:<40} {status_str} {detail}")
            else:
                lines.append(f"  {prefix} {name:<40} {status_str}")

        return Panel("\n".join(lines), border_style="cyan", padding=(0, 1))

    def render_logs_panel(self) -> Panel:
        """Builds the live log event box."""
        log_lines = []
        if self.logger:
            for ts, level, msg in self.logger.get_recent(6):
                lvl_style = "bold red" if level == "ERROR" else "bold yellow" if level == "WARN" else "bold blue"
                log_lines.append(f"[dim]{ts}[/dim] [{lvl_style}][{level}][/{lvl_style}] {msg}")

        if not log_lines:
            log_lines = [
                "[dim]18:21:31[/dim] [bold blue][INFO][/bold blue] Initializing RunPod Orchestration Pipeline...",
                "[dim]18:21:35[/dim] [bold blue][INFO][/bold blue] Connected to cluster pod via SSH.",
            ]

        return Panel("\n".join(log_lines), title="Живой лог событий и ошибок", border_style="dim", padding=(0, 1))

    def render_footer(self) -> Text:
        """Builds hotkeys guide."""
        return Text(
            " [Горячие клавиши: 'q' - выход из TUI | 'd' - скачать архивы | 's' - остановить под | 't' - переключить auto-stop] ",
            style="bold white on dark_blue",
            justify="center",
        )

    def render(self) -> Group:
        """Assembles full TUI frame."""
        return Group(
            self.render_header(),
            self.render_progress_panel(),
            self.render_logs_panel(),
            self.render_footer(),
        )


def check_keypress() -> str | None:
    """Non-blocking keyboard reader."""
    if os.name == "nt":
        try:
            import msvcrt
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    return ch.decode("utf-8").lower()
                except UnicodeDecodeError:
                    return None
        except Exception:
            return None
    else:
        import select
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower()
    return None


def run_mock_demo(duration_sec: int = 10) -> None:
    """Dry-run synthetic demonstration for testing TUI aesthetics."""
    logger = OrchestratorLogger()
    logger.info("Starting TUI Mock Dry-Run Demonstration...")
    logger.info("Simulated pod: RTX 4090 @ $0.74/hr connected.")
    logger.info("Ollama 32B loaded into VRAM (21.5 GB allocated).")

    dash = RunPodDashboard(logger=logger, auto_stop=True)
    dash.pod_name = "rtx4090-worker (MOCK)"
    dash.gpu_model = "NVIDIA GeForce RTX 4090"
    dash.gpu_util_percent = 94.0
    dash.gpu_vram_used_gb = 21.8
    dash.gpu_vram_total_gb = 24.0
    dash.gpu_tps = 16.8
    dash.cpu_percent = 28.0
    dash.ram_used_gb = 16.4
    dash.ram_total_gb = 32.0
    dash.disk_used_gb = 24.2
    dash.disk_total_gb = 40.0

    start_time = time.time()
    with Live(dash.render(), refresh_per_second=4, console=dash.console) as live:
        step = 0
        while time.time() - start_time < duration_sec:
            step += 1
            # Simulate progress
            elapsed = time.time() - start_time
            progress_ratio = min(1.0, elapsed / max(duration_sec, 1))

            if progress_ratio < 0.5:
                dash.completed_books = 0
                dash.current_book_title = "Illustrated Seamanship (Ivar Dedekam) [EPUB · 5.4 MB]"
                vlm_done = int(28 * (progress_ratio * 2))
                dash.stages[0]["status"] = "completed"
                dash.stages[0]["detail"] = "(28 изображений найдено)"
                dash.stages[1]["status"] = "in_progress"
                dash.stages[1]["completed"] = vlm_done
                dash.stages[1]["total"] = 28
                dash.stages[1]["detail"] = f"({vlm_done}/28 схем)"
            else:
                dash.completed_books = 1
                dash.current_book_title = "Sail and Rig Tuning (Dedekam) [PDF · 12.1 MB]"
                dash.stages[0]["status"] = "completed"
                dash.stages[1]["status"] = "completed"
                dash.stages[1]["detail"] = "(28/28 схем, 0 ошибок)"
                triplets_done = int(96 * ((progress_ratio - 0.5) * 2))
                dash.stages[2]["status"] = "in_progress"
                dash.stages[2]["completed"] = triplets_done
                dash.stages[2]["total"] = 96
                dash.stages[2]["detail"] = f"({triplets_done}/96 чанков)"

            if step % 8 == 0:
                logger.info(f"VLM Inference step {step}: generated tokens at {dash.gpu_tps:.1f} t/s")

            # Check keypress
            k = check_keypress()
            if k == "q":
                logger.info("User requested exit ('q').")
                break
            elif k == "t":
                dash.auto_stop = not dash.auto_stop
                logger.info(f"Auto-stop toggled to: {dash.auto_stop}")

            live.update(dash.render())
            time.sleep(0.25)

    dash.console.print("[bold green]Mock TUI demo completed successfully![/bold green]")


def main() -> None:
    parser = argparse.ArgumentParser(description="RunPod Rich TUI Dashboard")
    parser.add_argument("--mock", action="store_true", help="Run mock synthetic telemetry demo")
    parser.add_argument("--duration", type=int, default=8, help="Mock demo duration in seconds")
    args = parser.parse_args()

    if args.mock:
        run_mock_demo(duration_sec=args.duration)
    else:
        run_mock_demo(duration_sec=args.duration)


if __name__ == "__main__":
    main()
