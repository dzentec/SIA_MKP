"""RunPod GraphQL API Client for lifecycle management and auto-shutdown."""

from __future__ import annotations

import os
import requests
from typing import Any

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"


class RunPodClient:
    """Client for controlling RunPod instances via GraphQL API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY", "")
        if not self.api_key:
            # Check local .env file if available
            env_file = os.path.join(os.path.dirname(__file__), ".env")
            if os.path.exists(env_file):
                for line in open(env_file):
                    if line.startswith("RUNPOD_API_KEY="):
                        self.api_key = line.strip().split("=", 1)[1]
                        break
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = requests.post(
            RUNPOD_GRAPHQL_URL,
            headers=self.headers,
            json={"query": query, "variables": variables or {}},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"RunPod GraphQL Error: {data['errors']}")
        return data.get("data", {})

    def get_pods(self) -> list[dict[str, Any]]:
        """List all active and stopped pods."""
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
                }
            }
        }
        """
        data = self._query(query)
        return data.get("myself", {}).get("pods", [])

    def get_templates(self) -> list[dict[str, Any]]:
        """List all available templates including custom user templates."""
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

    def deploy_pod(
        self,
        name: str = "mkp-4090-worker",
        gpu_type_id: str = "NVIDIA GeForce RTX 4090",
        template_id: str = "7229lmi7rz",
        gpu_count: int = 1,
        volume_in_gb: int = 40,
        container_disk_in_gb: int = 40,
    ) -> dict[str, Any]:
        """Deploy a new pod using a custom template (e.g. base_sia_mkp)."""
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
            }
        }
        return self._query(mutation, variables)


    def get_pod(self, pod_id: str) -> dict[str, Any] | None:
        """Fetch details for a specific pod."""
        pods = self.get_pods()
        for p in pods:
            if p.get("id") == pod_id:
                return p
        return None

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

    def start_pod(self, pod_id: str, gpu_count: int = 1) -> dict[str, Any]:
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


if __name__ == "__main__":
    client = RunPodClient()
    pods = client.get_pods()
    print(f"Found {len(pods)} pod(s):")
    for p in pods:
        print(f"  - ID: {p['id']} | Name: {p['name']} | Status: {p['desiredStatus']} | Cost: ${p['costPerHr']}/hr")
