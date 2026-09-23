"""RunPod GraphQL API Client for lifecycle management, GPU cascade selection, and auto-shutdown."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import requests

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
DEFAULT_TEMPLATE_ID = "7229lmi7rz"  # base_sia_mkp

# Strictly prioritized list of GPUs with VRAM >= 24GB for Qwen2.5-VL 32B inference
GPU_CASCADE = [
    {
        "id": "NVIDIA GeForce RTX 5090",
        "aliases": ["RTX 5090", "GeForce RTX 5090"],
        "vram_gb": 32,
        "priority": 1,
        "expected_tps": "~30 t/s",
        "description": "TOP-1: GDDR7 · 1792 GB/s · 10.5 GB VRAM headroom",
    },
    {
        "id": "NVIDIA GeForce RTX 4090",
        "aliases": ["RTX 4090", "GeForce RTX 4090"],
        "vram_gb": 24,
        "priority": 2,
        "expected_tps": "~16 t/s",
        "description": "TOP-2: GDDR6X · 1008 GB/s · 2.5 GB VRAM headroom",
    },
    {
        "id": "NVIDIA RTX 5000 Ada Generation",
        "aliases": ["RTX 5000 Ada", "RTX A6000", "NVIDIA RTX A6000", "A6000"],
        "vram_gb": 32,
        "priority": 3,
        "expected_tps": "~18 t/s",
        "description": "TOP-3: High VRAM enterprise reserve (32-48 GB)",
    },
    {
        "id": "NVIDIA RTX A5000",
        "aliases": ["RTX A5000", "NVIDIA GeForce RTX 3090", "RTX 3090"],
        "vram_gb": 24,
        "priority": 4,
        "expected_tps": "~3-6 t/s",
        "description": "TOP-4: Budget reserve (24 GB)",
    },
]

# Explicit blacklist of GPUs with VRAM < 24GB that will cause OOM or swapping
DISALLOWED_GPUS = [
    "NVIDIA GeForce RTX 5080",
    "NVIDIA GeForce RTX 4080",
    "NVIDIA GeForce RTX 3080",
    "NVIDIA GeForce RTX 4070",
    "NVIDIA RTX 4000 Ada Generation",
]


class RunPodClient:
    """Client for controlling RunPod instances via GraphQL API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY", "")
        if not self.api_key:
            # Check local .env file if available
            env_file = Path(__file__).parent / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("RUNPOD_API_KEY="):
                        self.api_key = line.strip().split("=", 1)[1].strip()
                        break
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("RUNPOD_API_KEY is not set. Please provide it in tools/runpod/.env or environment.")
        resp = requests.post(
            RUNPOD_GRAPHQL_URL,
            headers=self.headers,
            json={"query": query, "variables": variables or {}},
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"RunPod GraphQL Error: {data['errors']}")
        return data.get("data", {})

    def get_pods(self) -> list[dict[str, Any]]:
        """List all active and stopped pods for the current account."""
        query = """
        query getPods {
            myself {
                pods {
                    id
                    name
                    runtime {
                        uptimeInSeconds
                        ports {
                            ip
                            isIpPublic
                            privatePort
                            publicPort
                            type
                        }
                        gpus {
                            id
                            gpuUtilPercent
                            memoryUtilPercent
                        }
                    }
                    gpuCount
                    costPerHr
                    desiredStatus
                    lastStatusChange
                    machine {
                        gpuDisplayName
                    }
                }
            }
        }
        """
        data = self._query(query)
        return data.get("myself", {}).get("pods", [])

    def get_pod(self, pod_id: str) -> dict[str, Any] | None:
        """Fetch details for a specific pod by ID."""
        pods = self.get_pods()
        for p in pods:
            if p.get("id") == pod_id:
                return p
        return None

    def get_pod_status_and_ip(self, pod_id: str) -> dict[str, Any]:
        """Extract public IP, SSH exposed port, status, and metrics for a given pod."""
        pod = self.get_pod(pod_id)
        if not pod:
            return {"status": "NOT_FOUND", "ip": "", "port": "", "uptime": 0, "cost_per_hr": 0.0}

        runtime = pod.get("runtime") or {}
        ports = runtime.get("ports") or []
        public_ip = ""
        ssh_port = ""

        for port_info in ports:
            # Look for mapped SSH port 22
            if port_info.get("privatePort") == 22:
                public_ip = port_info.get("ip", "")
                ssh_port = str(port_info.get("publicPort", ""))
                break

        # Fallback to any public port if not explicitly 22
        if not public_ip and ports:
            public_ip = ports[0].get("ip", "")

        gpu_name = pod.get("machine", {}).get("gpuDisplayName", "") if pod.get("machine") else ""

        return {
            "id": pod.get("id"),
            "name": pod.get("name"),
            "status": pod.get("desiredStatus", "UNKNOWN"),
            "ip": public_ip,
            "port": ssh_port,
            "uptime": runtime.get("uptimeInSeconds", 0),
            "cost_per_hr": pod.get("costPerHr", 0.0),
            "gpu_name": gpu_name,
            "gpu_count": pod.get("gpuCount", 1),
        }

    def get_gpu_types(self) -> list[dict[str, Any]]:
        """List available GPU types with memory and pricing."""
        query = """
        query gpuTypes {
            gpuTypes {
                id
                displayName
                memoryInGb
                communityPrice
                lowestPrice(input: { gpuCount: 1 }) {
                    minimumBidPrice
                    uninterruptablePrice
                }
            }
        }
        """
        try:
            data = self._query(query)
            return data.get("gpuTypes", [])
        except Exception:
            return []

    def get_templates(self) -> list[dict[str, Any]]:
        """List all user templates."""
        query = """
        query getTemplates {
            myself {
                podTemplates {
                    id
                    name
                    imageName
                    containerDiskInGb
                    volumeInGb
                    isPublic
                }
            }
        }
        """
        data = self._query(query)
        return data.get("myself", {}).get("podTemplates", [])

    def find_template(self, name_or_id: str) -> dict[str, Any] | None:
        """Find template by exact ID or case-insensitive name."""
        templates = self.get_templates()
        for t in templates:
            if t.get("id") == name_or_id or t.get("name", "").lower() == name_or_id.lower():
                return t
        return None

    def select_best_gpu(self, preferred_gpu: str | None = None) -> dict[str, Any]:
        """Returns the best eligible GPU according to the GPU Cascade specification (VRAM >= 24GB)."""
        if preferred_gpu:
            # Verify preferred GPU is >= 24GB
            for disallowed in DISALLOWED_GPUS:
                if disallowed.lower() in preferred_gpu.lower():
                    raise ValueError(f"GPU '{preferred_gpu}' has < 24GB VRAM and is strictly disallowed for 32B VLM.")
            for item in GPU_CASCADE:
                if item["id"].lower() == preferred_gpu.lower() or any(a.lower() == preferred_gpu.lower() for a in item["aliases"]):
                    return item
            # Generic fallback if custom 24GB+ GPU specified
            return {"id": preferred_gpu, "vram_gb": 24, "priority": 99, "description": f"Custom {preferred_gpu}"}

        # Default to highest cascade priority (RTX 5090 -> RTX 4090 -> RTX 5000 Ada -> RTX A5000)
        return GPU_CASCADE[0]

    def deploy_pod(
        self,
        name: str = "mkp-32b-worker",
        gpu_type_id: str = "NVIDIA GeForce RTX 4090",
        template_id: str = DEFAULT_TEMPLATE_ID,
        gpu_count: int = 1,
        volume_in_gb: int = 40,
        container_disk_in_gb: int = 40,
        public_key: str | None = None,
    ) -> dict[str, Any]:
        """Deploy a new pod on-demand using template and selected GPU."""
        # Sanity check GPU memory constraint
        for disallowed in DISALLOWED_GPUS:
            if disallowed.lower() in gpu_type_id.lower():
                raise ValueError(f"Cannot deploy pod on {gpu_type_id}: VRAM < 24GB violates 32B VLM requirements.")

        if not public_key:
            # Try to read local public key or derive from id_ed25519
            local_key = Path(__file__).parent / "id_ed25519"
            if local_key.exists():
                try:
                    import subprocess
                    res = subprocess.run(["ssh-keygen", "-y", "-f", str(local_key)], capture_output=True, text=True)
                    if res.returncode == 0 and res.stdout.strip():
                        public_key = res.stdout.strip()
                except Exception:
                    pass

        env_list = []
        if public_key:
            env_list.append({"key": "PUBLIC_KEY", "value": public_key})

        mutation = """
        mutation deployPod($input: PodFindAndDeployOnDemandInput!) {
            podFindAndDeployOnDemand(input: $input) {
                id
                name
                desiredStatus
                costPerHr
            }
        }
        """
        variables = {
            "input": {
                "name": name,
                "gpuTypeId": gpu_type_id,
                "templateId": template_id,
                "gpuCount": gpu_count,
                "volumeInGb": volume_in_gb,
                "containerDiskInGb": container_disk_in_gb,
                "env": env_list,
            }
        }
        return self._query(mutation, variables)

    def stop_pod(self, pod_id: str) -> dict[str, Any]:
        """Stop a running pod to halt GPU charges immediately."""
        mutation = """
        mutation stopPod($input: PodStopInput!) {
            podStop(input: $input) {
                id
                desiredStatus
            }
        }
        """
        return self._query(mutation, {"input": {"podId": pod_id}})

    def resume_pod(self, pod_id: str, gpu_count: int = 1) -> dict[str, Any]:
        """Resume a stopped pod."""
        mutation = """
        mutation resumePod($input: PodResumeInput!) {
            podResume(input: $input) {
                id
                desiredStatus
            }
        }
        """
        return self._query(mutation, {"input": {"podId": pod_id, "gpuCount": gpu_count}})

    def terminate_pod(self, pod_id: str) -> dict[str, Any]:
        """Completely terminate and delete a pod."""
        mutation = """
        mutation terminatePod($input: PodTerminateInput!) {
            podTerminate(input: $input)
        }
        """
        return self._query(mutation, {"input": {"podId": pod_id}})
