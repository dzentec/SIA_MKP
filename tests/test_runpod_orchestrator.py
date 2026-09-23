"""Comprehensive Unit & Mock Test Suite for RunPod Orchestrator & TUI (REQ-AC1..AC7)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from mkp_builder.tui import BuilderProgressTracker
from tools.runpod.logger import OrchestratorLogger
from tools.runpod.runpod_api import (
    RunPodClient,
    GPU_CASCADE,
    DISALLOWED_GPUS,
    DEFAULT_TEMPLATE_ID,
)
from tools.runpod.runpod_orchestrator import RunPodOrchestrator
from tools.runpod.tui import RunPodDashboard, make_bar_str


# ============================================================================
# UAT-1: GPU Cascade & Strict Filtering Tests (AC-2)
# ============================================================================

def test_gpu_cascade_priorities():
    """Verify GPU cascade prioritizes RTX 5090 -> RTX 4090 -> RTX 5000 Ada -> RTX A5000."""
    client = RunPodClient(api_key="test_key")
    best = client.select_best_gpu()
    assert best["id"] == "NVIDIA GeForce RTX 5090"
    assert best["vram_gb"] >= 24
    assert best["priority"] == 1


def test_gpu_cascade_disallows_sub_24gb_gpus():
    """Verify any GPU with < 24GB VRAM raises a ValueError."""
    client = RunPodClient(api_key="test_key")
    for disallowed in DISALLOWED_GPUS:
        with pytest.raises(ValueError, match="violates 32B VLM requirements|< 24GB VRAM"):
            client.select_best_gpu(disallowed)

        with pytest.raises(ValueError, match="violates 32B VLM requirements"):
            client.deploy_pod(gpu_type_id=disallowed)


def test_gpu_cascade_custom_selection():
    """Verify custom selection matches aliases properly."""
    client = RunPodClient(api_key="test_key")
    gpu_4090 = client.select_best_gpu("RTX 4090")
    assert gpu_4090["id"] == "NVIDIA GeForce RTX 4090"
    assert gpu_4090["vram_gb"] == 24


# ============================================================================
# UAT-2: RunPod API Client Mock Operations (AC-1, AC-3, AC-6)
# ============================================================================

@patch("tools.runpod.runpod_api.requests.post")
def test_api_client_get_pods(mock_post):
    """Test get_pods parsing and status resolution."""
    mock_post.return_value.json.return_value = {
        "data": {
            "myself": {
                "pods": [
                    {
                        "id": "pod-12345",
                        "name": "mkp-4090-worker",
                        "desiredStatus": "RUNNING",
                        "costPerHr": 0.74,
                        "gpuCount": 1,
                        "runtime": {
                            "uptimeInSeconds": 3600,
                            "ports": [
                                {"privatePort": 22, "publicPort": 22049, "ip": "69.30.85.227"}
                            ],
                        },
                    }
                ]
            }
        }
    }
    client = RunPodClient(api_key="mock_key")
    pods = client.get_pods()
    assert len(pods) == 1
    assert pods[0]["id"] == "pod-12345"

    info = client.get_pod_status_and_ip("pod-12345")
    assert info["status"] == "RUNNING"
    assert info["ip"] == "69.30.85.227"
    assert info["port"] == "22049"
    assert info["cost_per_hr"] == 0.74


@patch("tools.runpod.runpod_api.requests.post")
def test_api_client_lifecycle_methods(mock_post):
    """Test deploy_pod, stop_pod, resume_pod, and terminate_pod mutations."""
    mock_post.return_value.json.return_value = {
        "data": {
            "podFindAndDeployOnDemand": {"id": "new-pod", "name": "mkp-worker", "costPerHr": 0.99},
            "podStop": {"id": "new-pod", "desiredStatus": "STOPPED"},
            "podResume": {"id": "new-pod", "desiredStatus": "RUNNING"},
            "podTerminate": True,
        }
    }
    client = RunPodClient(api_key="mock_key")

    dep = client.deploy_pod(name="mkp-worker", gpu_type_id="NVIDIA GeForce RTX 5090")
    assert dep["podFindAndDeployOnDemand"]["id"] == "new-pod"

    stop_res = client.stop_pod("new-pod")
    assert stop_res["podStop"]["desiredStatus"] == "STOPPED"

    res_res = client.resume_pod("new-pod")
    assert res_res["podResume"]["desiredStatus"] == "RUNNING"

    term_res = client.terminate_pod("new-pod")
    assert term_res["podTerminate"] is True


# ============================================================================
# UAT-3: Telemetry Serialization Hook Tests (AC-4)
# ============================================================================

def test_builder_progress_tracker_telemetry_dump(tmp_path: Path):
    """Verify BuilderProgressTracker publishes atomic telemetry JSON."""
    telem_file = tmp_path / "telemetry.json"
    tracker = BuilderProgressTracker(headless=True, telemetry_file=telem_file)

    tracker.start("test_book")
    tracker.add_stage("parse", "Parsing Layout", total=100)
    tracker.stats["figures"] = 14
    tracker.stats["vlm_api_calls"] = 10
    tracker.update_stage("parse", completed=50)

    assert telem_file.exists()
    data = json.loads(telem_file.read_text(encoding="utf-8"))
    assert data["status"] == "running"
    assert data["current_book"] == "test_book"
    assert data["stages"]["parse"]["completed"] == 50
    assert data["stats"]["figures"] == 14

    tracker.stop("completed")
    data_final = json.loads(telem_file.read_text(encoding="utf-8"))
    assert data_final["status"] == "completed"


# ============================================================================
# UAT-4: Inactivity Guard & Safety Auto-Stop Logic (AC-6)
# ============================================================================

def test_dashboard_inactivity_guard_rendering():
    """Verify Dashboard displays countdown timer when guard is active."""
    dash = RunPodDashboard(auto_stop=True)
    dash.guard_countdown_sec = 1750  # ~29 mins
    rendered_header = dash.render_header()
    assert rendered_header is not None

    panel = dash.render_progress_panel()
    assert panel is not None

    footer = dash.render_footer()
    assert "Горячие клавиши" in footer.plain


def test_dashboard_update_telemetry_system_and_gpu_metrics():
    """Verify Dashboard.update_telemetry maps CPU, RAM, Disk, and GPU Load correctly."""
    dash = RunPodDashboard()
    raw_telem = {
        "status": "running",
        "current_book": "Sail and Rig Tuning",
        "cpu_percent": 35.5,
        "cpu_cores": 16,
        "ram_used_gb": 18.2,
        "ram_total_gb": 64.0,
        "disk_used_gb": 12.4,
        "disk_total_gb": 50.0,
        "gpu_util_percent": 98.0,
        "vram_used_gb": 22.1,
        "vram_total_gb": 32.0,
        "gpu_temp_c": 52,
        "gpu_power_w": 280,
        "gpu_tps": 22.4,
    }
    dash.update_telemetry(raw_telem)

    assert dash.cpu_percent == 35.5
    assert dash.cpu_cores == 16
    assert dash.ram_used_gb == 18.2
    assert dash.ram_total_gb == 64.0
    assert dash.disk_used_gb == 12.4
    assert dash.disk_total_gb == 50.0
    assert dash.gpu_util_percent == 98.0
    assert dash.gpu_vram_used_gb == 22.1
    assert dash.gpu_vram_total_gb == 32.0
    assert dash.gpu_temp_c == 52
    assert dash.gpu_power_w == 280
    assert dash.gpu_tps == 22.4

    header = dash.render_header()
    assert header is not None


def test_orchestrator_fetch_remote_telemetry_composite():
    """Verify RunPodOrchestrator parses composite progress + system + GPU SSH output."""
    orch = RunPodOrchestrator()
    mock_stdout = (
        '{"status": "running", "current_book": "Sail", "stages": {"vlm": {"completed": 10, "total": 50}}}\n'
        '---SYS---\n'
        '{"ram_used_gb": 14.5, "ram_total_gb": 64.0, "disk_used_gb": 22.0, "disk_total_gb": 100.0, "cpu_percent": 15.2, "cpu_cores": 16}\n'
        '---GPU---\n'
        '96, 22528, 32768, 55, 310\n'
    )
    with patch.object(orch, "run_ssh", return_value=(0, mock_stdout, "")):
        telem = orch.fetch_remote_telemetry()

    assert telem["status"] == "running"
    assert telem["ram_used_gb"] == 14.5
    assert telem["ram_total_gb"] == 64.0
    assert telem["disk_used_gb"] == 22.0
    assert telem["disk_total_gb"] == 100.0
    assert telem["cpu_percent"] == 15.2
    assert telem["gpu_util_percent"] == 96.0
    assert telem["vram_used_gb"] == 22.0
    assert telem["vram_total_gb"] == 32.0
    assert telem["gpu_temp_c"] == 55
    assert telem["gpu_power_w"] == 310


# ============================================================================
# UAT-5: Orchestrator Logger & Mirroring Tests (AC-5)
# ============================================================================

def test_orchestrator_logger_session_and_latest(tmp_path: Path):
    """Verify log records are written to timestamped file and latest.log."""
    logs_dir = tmp_path / "logs"
    logger = OrchestratorLogger(logs_dir=logs_dir)

    logger.info("Test message 1")
    logger.warning("Test warning 2")
    logger.error("Test error 3")

    assert logger.session_log_path.exists()
    assert logger.latest_log_path.exists()

    session_content = logger.session_log_path.read_text(encoding="utf-8")
    assert "Test message 1" in session_content
    assert "Test warning 2" in session_content
    assert "[ERROR] Test error 3" in session_content

    latest_content = logger.latest_log_path.read_text(encoding="utf-8")
    assert "Test error 3" in latest_content

    recent = logger.get_recent(3)
    assert len(recent) == 3
    assert recent[-1][1] == "ERROR"

    logger.close()


# ============================================================================
# UAT-6: Progress Bar Formatting Helpers
# ============================================================================

def test_make_bar_str():
    """Verify progress bar calculation and clamping."""
    assert len(make_bar_str(0.0, width=10)) == 10
    assert len(make_bar_str(50.0, width=10)) == 10
    assert len(make_bar_str(100.0, width=10)) == 10
    assert len(make_bar_str(150.0, width=10)) == 10  # Clamped to 100%


def test_format_eta_and_calculation():
    """Verify ETA formatting and dynamic calculation across stages."""
    from tools.runpod.tui import format_eta

    assert format_eta(None) == "вычисляется..."
    assert format_eta(0) == "готово"
    assert format_eta(30) == "~30 сек"
    assert format_eta(90) == "~1 мин 30 сек"
    assert format_eta(3600) == "~1 ч"
    assert format_eta(3900) == "~1 ч 5 мин"

    dash = RunPodDashboard()
    dash.total_books = 1
    dash.completed_books = 0
    dash.stages[1]["status"] = "in_progress"
    dash.stages[1]["completed"] = 10
    dash.stages[1]["total"] = 50

    # Simulate stage start times
    dash._stage_start_times[1] = time.time() - 20.0
    dash._stage_start_completed[1] = 0

    eta_sec = dash.calculate_eta_seconds()
    assert eta_sec is not None
    assert eta_sec > 0.0

    panel = dash.render_progress_panel()
    assert "Осталось:" in panel.renderable

