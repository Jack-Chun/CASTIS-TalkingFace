"""Job manager for tracking and managing GPU model jobs."""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from config import JOBS_FILE
from k8s.client import KubernetesClient, PodStatus


class JobState(Enum):
    """Job state enum."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Job dataclass for tracking model jobs."""
    job_id: str
    pod_name: str
    model_type: str
    input_files: Dict[str, str]
    output_file: str
    state: str  # Store as string for JSON serialization
    created_at: str
    updated_at: str
    model_params: Dict = field(default_factory=dict)
    error_message: Optional[str] = None
    logs: Optional[str] = None

    def get_state(self) -> JobState:
        """Get state as enum."""
        return JobState(self.state)

    def set_state(self, state: JobState):
        """Set state from enum."""
        self.state = state.value


class JobManager:
    """Manager for job lifecycle and persistence."""

    def __init__(self, jobs_file: str = JOBS_FILE):
        self.jobs_file = jobs_file
        self.k8s_client = KubernetesClient()
        self._ensure_jobs_dir()

    def _ensure_jobs_dir(self):
        """Ensure the jobs file directory exists."""
        jobs_dir = os.path.dirname(self.jobs_file)
        if jobs_dir:
            os.makedirs(jobs_dir, exist_ok=True)

    def _load_jobs(self) -> Dict[str, Job]:
        """Load jobs from persistent state file."""
        if not os.path.exists(self.jobs_file):
            return {}

        try:
            with open(self.jobs_file, 'r') as f:
                data = json.load(f)
                jobs = {}
                for k, v in data.items():
                    # Handle backwards compatibility
                    if 'model_params' not in v:
                        v['model_params'] = {}
                    jobs[k] = Job(**v)
                return jobs
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error loading jobs file: {e}")
            return {}

    def _save_jobs(self, jobs: Dict[str, Job]):
        """Persist jobs to state file."""
        try:
            with open(self.jobs_file, 'w') as f:
                json.dump(
                    {k: asdict(v) for k, v in jobs.items()},
                    f,
                    indent=2,
                    default=str
                )
        except Exception as e:
            print(f"Error saving jobs file: {e}")

    def create_job(
        self,
        job_id: str,
        pod_name: str,
        model_type: str,
        input_files: Dict[str, str],
        output_file: str,
        model_params: Dict = None
    ) -> Job:
        """Create and register a new job."""
        jobs = self._load_jobs()

        now = datetime.now().isoformat()
        job = Job(
            job_id=job_id,
            pod_name=pod_name,
            model_type=model_type,
            input_files=input_files,
            output_file=output_file,
            state=JobState.QUEUED.value,
            created_at=now,
            updated_at=now,
            model_params=model_params or {},
        )

        jobs[job_id] = job
        self._save_jobs(jobs)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a specific job by ID."""
        jobs = self._load_jobs()
        return jobs.get(job_id)

    def update_job_status(self, job_id: str) -> Optional[Job]:
        """Poll Kubernetes and update job status."""
        jobs = self._load_jobs()
        job = jobs.get(job_id)

        if not job:
            return None

        pod_info = self.k8s_client.get_pod_status(job.pod_name)

        # Map pod status to job state
        status_map = {
            PodStatus.PENDING: JobState.QUEUED,
            PodStatus.RUNNING: JobState.RUNNING,
            PodStatus.SUCCEEDED: JobState.COMPLETED,
            PodStatus.FAILED: JobState.FAILED,
            PodStatus.NOT_FOUND: JobState.FAILED,
        }

        new_state = status_map.get(pod_info.status, JobState.RUNNING)
        job.set_state(new_state)
        job.updated_at = datetime.now().isoformat()

        # Get logs for failed or completed jobs
        if new_state in [JobState.FAILED, JobState.COMPLETED]:
            job.logs = self.k8s_client.get_pod_logs(job.pod_name)

        if new_state == JobState.FAILED:
            if pod_info.status == PodStatus.NOT_FOUND:
                job.error_message = "Pod not found - may have been deleted"
            elif pod_info.message:
                job.error_message = pod_info.message
            else:
                job.error_message = "Job failed - check logs for details"

        jobs[job_id] = job
        self._save_jobs(jobs)
        return job

    def update_all_active_jobs(self) -> List[Job]:
        """Update status for all active jobs."""
        updated_jobs = []
        for job in self.get_active_jobs():
            updated = self.update_job_status(job.job_id)
            if updated:
                updated_jobs.append(updated)
        return updated_jobs

    def delete_job(self, job_id: str, delete_pod: bool = True) -> bool:
        """Delete a job from tracking and optionally delete the pod."""
        jobs = self._load_jobs()
        job = jobs.get(job_id)

        if not job:
            return False

        if delete_pod:
            self.k8s_client.delete_pod(job.pod_name)

        del jobs[job_id]
        self._save_jobs(jobs)
        return True

    def cleanup_completed_jobs(self, delete_pods: bool = True) -> int:
        """Delete all completed and failed jobs. Returns count deleted."""
        jobs = self._load_jobs()
        to_delete = []

        for job_id, job in jobs.items():
            if job.get_state() in [JobState.COMPLETED, JobState.FAILED]:
                to_delete.append(job_id)
                if delete_pods:
                    self.k8s_client.delete_pod(job.pod_name)

        for job_id in to_delete:
            del jobs[job_id]

        self._save_jobs(jobs)
        return len(to_delete)

    def get_active_jobs(self) -> List[Job]:
        """Return jobs that are queued or running."""
        jobs = self._load_jobs()
        return [
            j for j in jobs.values()
            if j.get_state() in [JobState.QUEUED, JobState.RUNNING]
        ]

    def get_completed_jobs(self) -> List[Job]:
        """Return completed jobs, sorted by creation time (newest first)."""
        jobs = self._load_jobs()
        completed = [j for j in jobs.values() if j.get_state() == JobState.COMPLETED]
        return sorted(completed, key=lambda j: j.created_at, reverse=True)

    def get_failed_jobs(self) -> List[Job]:
        """Return failed jobs, sorted by creation time (newest first)."""
        jobs = self._load_jobs()
        failed = [j for j in jobs.values() if j.get_state() == JobState.FAILED]
        return sorted(failed, key=lambda j: j.created_at, reverse=True)

    def get_all_jobs(self) -> List[Job]:
        """Return all tracked jobs, sorted by creation time (newest first)."""
        jobs = self._load_jobs()
        return sorted(
            jobs.values(),
            key=lambda j: j.created_at,
            reverse=True
        )

    def get_jobs_by_model(self, model_type: str) -> List[Job]:
        """Return all jobs for a specific model type, sorted by creation time (newest first)."""
        jobs = self._load_jobs()
        filtered = [j for j in jobs.values() if j.model_type == model_type]
        return sorted(filtered, key=lambda j: j.created_at, reverse=True)

    def get_job_logs(self, job_id: str, force_refresh: bool = False) -> Optional[str]:
        """Get logs for a specific job and save them permanently."""
        jobs = self._load_jobs()
        job = jobs.get(job_id)
        if not job:
            return None

        state = job.get_state()

        # For completed/failed jobs, return cached logs if available (unless force refresh)
        if state in [JobState.COMPLETED, JobState.FAILED] and job.logs and not force_refresh:
            return job.logs

        # Fetch fresh logs from pod
        fresh_logs = self.k8s_client.get_pod_logs(job.pod_name)

        # Save logs to job (append for running jobs, replace for others)
        if fresh_logs:
            job.logs = fresh_logs
            job.updated_at = datetime.now().isoformat()
            jobs[job_id] = job
            self._save_jobs(jobs)

        return fresh_logs or job.logs
