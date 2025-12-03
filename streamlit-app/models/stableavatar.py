"""StableAvatar model runner implementation (placeholder)."""

import os
import streamlit as st
from string import Template
from typing import Dict, Any, Optional

from models.base import BaseModelRunner, JobConfig
from config import (
    MODELS,
    YAML_TEMPLATE_DIR,
    OUTPUT_TALKING_FACE_DIR,
    INPUT_IMAGES_DIR,
    INPUT_AUDIO_DIR,
)


class StableAvatarModel(BaseModelRunner):
    """StableAvatar talking face model runner (placeholder until repo is added)."""

    @property
    def model_id(self) -> str:
        return "stableavatar"

    @property
    def display_name(self) -> str:
        return "StableAvatar"

    @property
    def description(self) -> str:
        return "Talking face video generation from image and audio"

    @property
    def model_dir(self) -> str:
        return MODELS["stableavatar"]["dir"]

    @property
    def venv_path(self) -> str:
        return MODELS["stableavatar"]["venv"]

    @property
    def is_enabled(self) -> bool:
        return MODELS["stableavatar"]["enabled"]

    def get_yaml_template_path(self) -> str:
        return os.path.join(YAML_TEMPLATE_DIR, "stableavatar.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for StableAvatar inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        st.subheader("Face Image")

        image_file = st.file_uploader(
            "Upload a face image",
            type=["png", "jpg", "jpeg", "webp"],
            key="stableavatar_image_upload",
            help="Upload a clear frontal face image (PNG, JPG, JPEG, WebP)"
        )

        if image_file:
            st.image(image_file, caption="Uploaded face image", width=200)

        st.subheader("Driving Audio")

        audio_file = st.file_uploader(
            "Upload audio file",
            type=["wav", "mp3", "m4a", "flac"],
            key="stableavatar_audio_upload",
            help="Upload the audio that will drive the talking animation"
        )

        if audio_file:
            st.audio(audio_file, format=f"audio/{audio_file.type.split('/')[-1]}")

        st.subheader("Parameters")

        col1, col2 = st.columns(2)

        with col1:
            pose_style = st.selectbox(
                "Pose Style",
                options=["natural", "still", "expressive"],  # Placeholder options
                index=0,
                help="Head movement style (options will be updated when model is available)"
            )

        with col2:
            expression_scale = st.slider(
                "Expression Scale",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                help="Scale of facial expressions"
            )

        if image_file is None or audio_file is None:
            return None

        return {
            "files": {
                "image": image_file,
                "audio": audio_file,
            },
            "params": {
                "pose_style": pose_style,
                "expression_scale": expression_scale,
            }
        }

    def generate_yaml(self, config: JobConfig) -> str:
        """Generate YAML manifest from template."""
        template_path = self.get_yaml_template_path()

        with open(template_path, 'r') as f:
            template_content = f.read()

        template = Template(template_content)

        yaml_content = template.safe_substitute(
            POD_NAME=config.pod_name,
            JOB_ID=config.job_id,
            IMAGE=MODELS["stableavatar"]["image"],
            INPUT_IMAGE=config.input_files.get("image", ""),
            INPUT_AUDIO=config.input_files.get("audio", ""),
            OUTPUT_VIDEO=config.output_file,
            POSE_STYLE=config.model_params.get("pose_style", "natural"),
            EXPRESSION_SCALE=config.model_params.get("expression_scale", 1.0),
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """Calculate output path for generated video."""
        return os.path.join(OUTPUT_TALKING_FACE_DIR, f"talking_face_{job_id}.mp4")

    def get_output_type(self) -> str:
        return "video"

    def validate_inputs(self, input_files: Dict[str, str]) -> tuple[bool, str]:
        """Validate that both image and audio files exist."""
        image_path = input_files.get("image")
        audio_path = input_files.get("audio")

        if not image_path:
            return False, "No face image provided"
        if not audio_path:
            return False, "No audio file provided"
        if not os.path.exists(image_path):
            return False, f"Image file not found: {image_path}"
        if not os.path.exists(audio_path):
            return False, f"Audio file not found: {audio_path}"

        return True, ""

    def save_uploaded_files(self, image_file, audio_file, job_id: str) -> Dict[str, str]:
        """Save uploaded files to input directories and return paths."""
        paths = {}

        # Save image
        image_dir = os.path.join(INPUT_IMAGES_DIR, job_id)
        os.makedirs(image_dir, exist_ok=True)
        image_path = os.path.join(image_dir, image_file.name)
        with open(image_path, "wb") as f:
            f.write(image_file.getbuffer())
        paths["image"] = image_path

        # Save audio
        audio_dir = os.path.join(INPUT_AUDIO_DIR, job_id)
        os.makedirs(audio_dir, exist_ok=True)
        audio_path = os.path.join(audio_dir, audio_file.name)
        with open(audio_path, "wb") as f:
            f.write(audio_file.getbuffer())
        paths["audio"] = audio_path

        return paths
