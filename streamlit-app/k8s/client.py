"""Kubernetes client wrapper using kubectl subprocess."""

import subprocess
import json
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from config import KUBECTL_PATH


class PodStatus(Enum):
    """Pod status enum."""
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    UNKNOWN = "Unknown"
    NOT_FOUND = "NotFound"


@dataclass
class PodInfo:
    """Pod information dataclass."""
    name: str
    status: PodStatus
    message: Optional[str] = None
    start_time: Optional[str] = None


class KubernetesClient:
    """Client for interacting with Kubernetes via kubectl."""

    def __init__(self, kubectl_path: str = KUBECTL_PATH):
        self.kubectl = kubectl_path

    def _run_kubectl(self, *args, timeout: int = 30) -> subprocess.CompletedProcess:
        """Execute kubectl command and return result."""
        cmd = [self.kubectl] + list(args)
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=-1,
                stdout="",
                stderr="Command timed out"
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=-1,
                stdout="",
                stderr=f"kubectl not found at {self.kubectl}"
            )

    def apply_yaml(self, yaml_content: str) -> tuple[bool, str]:
        """
        Apply YAML content to create a pod.

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            result = subprocess.run(
                [self.kubectl, "apply", "-f", "-"],
                input=yaml_content,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "kubectl apply timed out"
        except FileNotFoundError:
            return False, f"kubectl not found at {self.kubectl}"
        except Exception as e:
            return False, str(e)

    def get_pod_status(self, pod_name: str) -> PodInfo:
        """Get current status of a pod."""
        # Get pod phase
        result = self._run_kubectl(
            "get", "pod", pod_name,
            "-o", "jsonpath={.status.phase}"
        )

        if result.returncode != 0:
            if "not found" in result.stderr.lower():
                return PodInfo(name=pod_name, status=PodStatus.NOT_FOUND)
            return PodInfo(
                name=pod_name,
                status=PodStatus.UNKNOWN,
                message=result.stderr
            )

        status_str = result.stdout.strip()

        # Map phase to enum
        status_map = {
            "Pending": PodStatus.PENDING,
            "Running": PodStatus.RUNNING,
            "Succeeded": PodStatus.SUCCEEDED,
            "Failed": PodStatus.FAILED,
        }
        status = status_map.get(status_str, PodStatus.UNKNOWN)

        # Get container status message for more details
        message = None
        if status in [PodStatus.PENDING, PodStatus.UNKNOWN]:
            msg_result = self._run_kubectl(
                "get", "pod", pod_name,
                "-o", "jsonpath={.status.conditions[?(@.type=='PodScheduled')].message}"
            )
            if msg_result.returncode == 0 and msg_result.stdout:
                message = msg_result.stdout.strip()

        return PodInfo(name=pod_name, status=status, message=message)

    def get_pod_logs(self, pod_name: str, tail: int = 100) -> str:
        """Get pod logs for display."""
        result = self._run_kubectl("logs", pod_name, f"--tail={tail}")
        if result.returncode == 0:
            return result.stdout
        return f"Error getting logs: {result.stderr}"

    def delete_pod(self, pod_name: str) -> tuple[bool, str]:
        """Delete a pod."""
        result = self._run_kubectl("delete", "pod", pod_name, "--ignore-not-found")
        if result.returncode == 0:
            return True, f"Pod {pod_name} deleted"
        return False, result.stderr

    def pod_exists(self, pod_name: str) -> bool:
        """Check if a pod exists."""
        result = self._run_kubectl("get", "pod", pod_name, "-o", "name")
        return result.returncode == 0

    def get_pod_json(self, pod_name: str) -> Optional[dict]:
        """Get full pod details as JSON."""
        result = self._run_kubectl("get", "pod", pod_name, "-o", "json")
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return None
        return None

    def copy_to_pod(
        self,
        local_path: str,
        pod_name: str,
        pod_path: str,
        container: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Copy a file from local machine to a pod.

        Args:
            local_path: Local file path
            pod_name: Target pod name
            pod_path: Destination path inside the pod
            container: Optional container name if pod has multiple containers

        Returns:
            Tuple of (success: bool, message: str)
        """
        args = ["cp", local_path, f"{pod_name}:{pod_path}"]
        if container:
            args.extend(["-c", container])

        result = self._run_kubectl(*args, timeout=300)  # 5 min timeout for large files
        if result.returncode == 0:
            return True, f"Copied {local_path} to {pod_name}:{pod_path}"
        return False, result.stderr

    def copy_from_pod(
        self,
        pod_name: str,
        pod_path: str,
        local_path: str,
        container: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Copy a file from a pod to local machine.

        Args:
            pod_name: Source pod name
            pod_path: Source path inside the pod
            local_path: Local destination path
            container: Optional container name if pod has multiple containers

        Returns:
            Tuple of (success: bool, message: str)
        """
        args = ["cp", f"{pod_name}:{pod_path}", local_path]
        if container:
            args.extend(["-c", container])

        result = self._run_kubectl(*args, timeout=300)  # 5 min timeout for large files
        if result.returncode == 0:
            return True, f"Copied {pod_name}:{pod_path} to {local_path}"
        return False, result.stderr
