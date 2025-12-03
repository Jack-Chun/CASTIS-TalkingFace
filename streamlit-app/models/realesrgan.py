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
)


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
        st.subheader("Upload Video")

        uploaded_file = st.file_uploader(
            "Choose a video file to upscale",
            type=["mp4", "mov", "avi", "mkv", "webm"],
            key="realesrgan_video_upload",
            help="Supported formats: MP4, MOV, AVI, MKV, WebM"
        )

        if uploaded_file:
            st.info(f"**File:** {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")

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
        """Calculate output path for upscaled video."""
        video_path = input_files.get("video", "")
        if video_path:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
        else:
            base_name = "output"

        return os.path.join(OUTPUT_UPSCALED_DIR, f"{base_name}_{job_id}.mp4")

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

    def save_uploaded_file(self, uploaded_file, job_id: str) -> str:
        """Save uploaded file to input directory and return path."""
        # Create job-specific directory
        job_input_dir = os.path.join(INPUT_VIDEOS_DIR, job_id)
        os.makedirs(job_input_dir, exist_ok=True)

        # Save file
        file_path = os.path.join(job_input_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        return file_path
