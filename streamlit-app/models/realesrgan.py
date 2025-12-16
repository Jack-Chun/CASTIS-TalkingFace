"""Real-ESRGAN model runner implementation."""

import os
import streamlit as st
from string import Template
from typing import Dict, Any, Optional

from models.base import BaseModelRunner, JobConfig
from config import (
    MODELS,
    YAML_TEMPLATE_DIR,
    OUTPUT_UPSCALED_DIR,
    INPUT_VIDEOS_DIR,
    POD_INPUT_VIDEOS_DIR,
    POD_OUTPUT_UPSCALED_DIR,
    IS_POD_ENV,
    PERSISTENT_POD_NAME,
)
from k8s.client import KubernetesClient


class RealESRGANModel(BaseModelRunner):
    """Real-ESRGAN video upscaling model runner."""

    @property
    def model_id(self) -> str:
        return "realesrgan"

    @property
    def display_name(self) -> str:
        return "Real-ESRGAN"

    @property
    def description(self) -> str:
        return "Video/image upscaling using Real-ESRGAN (4x or 2x super-resolution)"

    @property
    def model_dir(self) -> str:
        return MODELS["realesrgan"]["dir"]

    @property
    def venv_path(self) -> str:
        return MODELS["realesrgan"]["venv"]

    @property
    def is_enabled(self) -> bool:
        return MODELS["realesrgan"]["enabled"]

    def get_yaml_template_path(self) -> str:
        return os.path.join(YAML_TEMPLATE_DIR, "realesrgan.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for Real-ESRGAN inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        # Initialize session state for uploaded file
        if "realesrgan_video" not in st.session_state:
            st.session_state.realesrgan_video = None

        st.subheader("Upload Video")

        if st.session_state.realesrgan_video is None:
            # Show uploader if no video uploaded
            uploaded_file = st.file_uploader(
                "Choose a video file to upscale",
                type=["mp4", "mov", "avi", "mkv", "webm"],
                key="realesrgan_video_upload",
                help="Supported formats: MP4, MOV, AVI, MKV, WebM"
            )
            if uploaded_file:
                st.session_state.realesrgan_video = uploaded_file
                st.rerun()
        else:
            # Show preview and remove button
            uploaded_file = st.session_state.realesrgan_video
            col1, col2 = st.columns([5, 1])
            with col1:
                st.video(uploaded_file)
                st.caption(f"{uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")
            with col2:
                if st.button("Remove", key="remove_realesrgan_video"):
                    st.session_state.realesrgan_video = None
                    st.rerun()

        st.subheader("Parameters")

        col1, col2 = st.columns(2)

        with col1:
            scale = st.selectbox(
                "Upscale Factor",
                options=[2, 4],
                index=1,  # Default to 4x
                help="2x or 4x upscaling. 4x produces higher resolution but takes longer."
            )

        with col2:
            use_fp32 = st.checkbox(
                "Use FP32 precision",
                value=True,
                help="FP32 is slower but more accurate. Recommended for best quality."
            )

        # Get file from session state
        uploaded_file = st.session_state.realesrgan_video

        if uploaded_file is None:
            return None

        return {
            "files": {"video": uploaded_file},
            "params": {
                "scale": scale,
                "fp32": use_fp32,
            }
        }

    def generate_yaml(self, config: JobConfig) -> str:
        """Generate YAML manifest from template."""
        template_path = self.get_yaml_template_path()

        with open(template_path, 'r') as f:
            template_content = f.read()

        template = Template(template_content)

        # Prepare template variables
        fp32_flag = "--fp32" if config.model_params.get("fp32", True) else ""

        yaml_content = template.safe_substitute(
            POD_NAME=config.pod_name,
            JOB_ID=config.job_id,
            INPUT_VIDEO=config.input_files.get("video", ""),
            OUTPUT_VIDEO=config.output_file,
            SCALE=config.model_params.get("scale", 4),
            FP32_FLAG=fp32_flag,
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """Calculate output path for upscaled video (POD path for YAML)."""
        video_path = input_files.get("video", "")
        if video_path:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
        else:
            base_name = "output"

        # Always return pod path for YAML templates
        return os.path.join(POD_OUTPUT_UPSCALED_DIR, f"{base_name}_{job_id}.mp4")

    def get_local_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """Calculate local output path for displaying results."""
        video_path = input_files.get("video", "")
        if video_path:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
        else:
            base_name = "output"

        return os.path.join(OUTPUT_UPSCALED_DIR, f"{base_name}_{job_id}.mp4")

    def get_pod_input_path(self, job_id: str, filename: str) -> str:
        """Get the pod path for an input file."""
        return os.path.join(POD_INPUT_VIDEOS_DIR, job_id, filename)

    def get_output_type(self) -> str:
        return "video"

    def validate_inputs(self, input_files: Dict[str, str]) -> tuple[bool, str]:
        """Validate that video file exists."""
        video_path = input_files.get("video")
        if not video_path:
            return False, "No video file provided"
        if not os.path.exists(video_path):
            return False, f"Video file not found: {video_path}"
        return True, ""

    def save_uploaded_file(self, uploaded_file, job_id: str) -> tuple[str, str]:
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
        local_path = os.path.join(job_input_dir, uploaded_file.name)
        with open(local_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Calculate pod path
        pod_path = self.get_pod_input_path(job_id, uploaded_file.name)

        # If running locally, copy to the persistent volume pod
        if not IS_POD_ENV:
            k8s = KubernetesClient()

            # First, create the directory on the pod
            pod_job_dir = os.path.join(POD_INPUT_VIDEOS_DIR, job_id)
            # Use exec to create directory
            import subprocess
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
