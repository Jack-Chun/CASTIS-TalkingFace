"""SyncNet evaluation model runner implementation."""

import os
import streamlit as st
from string import Template
from typing import Dict, Any, Optional

from models.base import BaseModelRunner, JobConfig
from config import (
    MODELS,
    YAML_TEMPLATE_DIR,
    OUTPUT_DIR,
    INPUT_VIDEOS_DIR,
    POD_INPUT_VIDEOS_DIR,
    POD_OUTPUT_DIR,
    IS_POD_ENV,
    PERSISTENT_POD_NAME,
)
from k8s.client import KubernetesClient


class SyncNetModel(BaseModelRunner):
    """SyncNet lip sync evaluation model runner."""

    @property
    def model_id(self) -> str:
        return "syncnet"

    @property
    def display_name(self) -> str:
        return "SyncNet Evaluator"

    @property
    def description(self) -> str:
        return "Lip sync quality evaluation for talking face videos"

    @property
    def model_dir(self) -> str:
        return MODELS["syncnet"]["dir"]

    @property
    def venv_path(self) -> str:
        return MODELS["syncnet"]["venv"]

    @property
    def is_enabled(self) -> bool:
        return MODELS["syncnet"]["enabled"]

    def get_yaml_template_path(self) -> str:
        return os.path.join(YAML_TEMPLATE_DIR, "syncnet.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for SyncNet inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        # Initialize session state for uploaded file
        if "syncnet_video" not in st.session_state:
            st.session_state.syncnet_video = None

        st.subheader("Video to Evaluate")

        if st.session_state.syncnet_video is None:
            # Show uploader if no video uploaded
            video_file = st.file_uploader(
                "Upload a talking face video",
                type=["mp4", "mov", "avi", "mkv", "webm"],
                key="syncnet_video_upload",
                help="Upload a talking face video to evaluate its lip sync quality"
            )
            if video_file:
                st.session_state.syncnet_video = video_file
                st.rerun()
        else:
            # Show preview and remove button
            video_file = st.session_state.syncnet_video
            col1, col2 = st.columns([5, 1])
            with col1:
                st.video(video_file)
                st.caption(f"{video_file.name} ({video_file.size / 1024 / 1024:.2f} MB)")
            with col2:
                if st.button("Remove", key="remove_syncnet_video"):
                    st.session_state.syncnet_video = None
                    st.rerun()

        # Get file from session state
        video_file = st.session_state.syncnet_video

        if video_file is None:
            return None

        return {
            "files": {
                "video": video_file,
            },
            "params": {}
        }

    def generate_yaml(self, config: JobConfig) -> str:
        """Generate YAML manifest from template."""
        template_path = self.get_yaml_template_path()

        with open(template_path, 'r') as f:
            template_content = f.read()

        template = Template(template_content)

        # Output directory for syncnet results
        output_dir = os.path.dirname(config.output_file)

        yaml_content = template.safe_substitute(
            POD_NAME=config.pod_name,
            JOB_ID=config.job_id,
            IMAGE=MODELS["syncnet"]["image"],
            INPUT_VIDEO=config.input_files.get("video", ""),
            OUTPUT_DIR=output_dir,
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """Calculate output path for evaluation results (POD path for YAML)."""
        return os.path.join(POD_OUTPUT_DIR, "syncnet", job_id, "syncnet_summary.json")

    def get_local_output_path(self, job_id: str) -> str:
        """Calculate local output path for displaying results."""
        return os.path.join(OUTPUT_DIR, "syncnet", job_id, "syncnet_summary.json")

    def get_local_output_dir(self, job_id: str) -> str:
        """Calculate local output directory."""
        return os.path.join(OUTPUT_DIR, "syncnet", job_id)

    def get_pod_output_dir(self, job_id: str) -> str:
        """Calculate pod output directory."""
        return os.path.join(POD_OUTPUT_DIR, "syncnet", job_id)

    def get_pod_input_path(self, job_id: str, filename: str) -> str:
        """Get the pod path for an input file."""
        return os.path.join(POD_INPUT_VIDEOS_DIR, job_id, filename)

    def get_output_type(self) -> str:
        return "evaluation"

    def validate_inputs(self, input_files: Dict[str, str]) -> tuple[bool, str]:
        """Validate that video file exists."""
        video_path = input_files.get("video")

        if not video_path:
            return False, "No video file provided"
        if not os.path.exists(video_path):
            return False, f"Video file not found: {video_path}"

        return True, ""

    def save_uploaded_file(self, video_file, job_id: str) -> tuple[str, str]:
        """
        Save uploaded file to input directory.

        When running locally, also copies to the persistent volume pod.

        Returns:
            Tuple of (local_path, pod_path)
        """
        # Create local job-specific directory
        job_input_dir = os.path.join(INPUT_VIDEOS_DIR, job_id)
        os.makedirs(job_input_dir, exist_ok=True)

        # Save file locally
        local_path = os.path.join(job_input_dir, video_file.name)
        with open(local_path, "wb") as f:
            f.write(video_file.getbuffer())

        # Calculate pod path
        pod_path = self.get_pod_input_path(job_id, video_file.name)

        # If running locally, copy to the persistent volume pod
        if not IS_POD_ENV:
            k8s = KubernetesClient()
            import subprocess

            # Create directory on the pod
            pod_job_dir = os.path.join(POD_INPUT_VIDEOS_DIR, job_id)
            subprocess.run(
                [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--",
                 "mkdir", "-p", pod_job_dir],
                capture_output=True,
                timeout=30
            )

            # Copy the file to the pod
            success, msg = k8s.copy_to_pod(local_path, PERSISTENT_POD_NAME, pod_path)
            if not success:
                raise RuntimeError(f"Failed to copy file to pod: {msg}")

        return local_path, pod_path
