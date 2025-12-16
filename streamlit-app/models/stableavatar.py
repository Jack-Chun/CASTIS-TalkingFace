"""StableAvatar model runner implementation."""

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
    POD_INPUT_IMAGES_DIR,
    POD_INPUT_AUDIO_DIR,
    POD_OUTPUT_TALKING_FACE_DIR,
    IS_POD_ENV,
    PERSISTENT_POD_NAME,
)
from k8s.client import KubernetesClient


class StableAvatarModel(BaseModelRunner):
    """StableAvatar talking face model runner."""

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

    def get_yaml_template_path(self, vanilla: bool = False) -> str:
        if vanilla:
            return os.path.join(YAML_TEMPLATE_DIR, "stableavatar_vanilla.yaml")
        return os.path.join(YAML_TEMPLATE_DIR, "stableavatar.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for StableAvatar inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        # Initialize session state for uploaded files
        if "stableavatar_image" not in st.session_state:
            st.session_state.stableavatar_image = None
        if "stableavatar_audio" not in st.session_state:
            st.session_state.stableavatar_audio = None

        # Face Image section
        st.subheader("Face Image")

        if st.session_state.stableavatar_image is None:
            # Show uploader if no image uploaded
            image_file = st.file_uploader(
                "Upload a face image",
                type=["png", "jpg", "jpeg", "webp"],
                key="stableavatar_image_upload",
                help="Upload a clear frontal face image (PNG, JPG, JPEG, WebP)"
            )
            if image_file:
                st.session_state.stableavatar_image = image_file
                st.rerun()
        else:
            # Show preview and remove button
            image_file = st.session_state.stableavatar_image
            col1, col2 = st.columns([5, 1])
            with col1:
                st.image(image_file, caption=image_file.name, width=600)
            with col2:
                if st.button("Remove", key="remove_image"):
                    st.session_state.stableavatar_image = None
                    st.rerun()

        # Driving Audio section
        st.subheader("Driving Audio")

        if st.session_state.stableavatar_audio is None:
            # Show uploader if no audio uploaded
            audio_file = st.file_uploader(
                "Upload audio file",
                type=["wav", "mp3", "m4a", "flac"],
                key="stableavatar_audio_upload",
                help="Upload the audio that will drive the talking animation"
            )
            if audio_file:
                st.session_state.stableavatar_audio = audio_file
                st.rerun()
        else:
            # Show preview and remove button
            audio_file = st.session_state.stableavatar_audio
            col1, col2 = st.columns([5, 1])
            with col1:
                st.audio(audio_file)
                st.caption(audio_file.name)
            with col2:
                if st.button("Remove", key="remove_audio"):
                    st.session_state.stableavatar_audio = None
                    st.rerun()

        st.subheader("Parameters")

        inference_steps = st.slider(
            "Inference Steps",
            min_value=20,
            max_value=100,
            value=50,
            step=5,
            help="Number of diffusion steps. Higher = better quality but slower. Default: 50"
        )

        st.subheader("Comparison Mode")

        compare_with_vanilla = st.checkbox(
            "Compare with vanilla model (no LoRA)",
            value=False,
            help="Run both LoRA fine-tuned and vanilla models concurrently to compare results side by side"
        )

        # Get files from session state
        image_file = st.session_state.stableavatar_image
        audio_file = st.session_state.stableavatar_audio

        if image_file is None or audio_file is None:
            return None

        return {
            "files": {
                "image": image_file,
                "audio": audio_file,
            },
            "params": {
                "inference_steps": inference_steps,
                "compare_with_vanilla": compare_with_vanilla,
            }
        }

    def generate_yaml(self, config: JobConfig, vanilla: bool = False) -> str:
        """Generate YAML manifest from template."""
        template_path = self.get_yaml_template_path(vanilla=vanilla)

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
            INFERENCE_STEPS=config.model_params.get("inference_steps", 50),
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str], vanilla: bool = False) -> str:
        """Calculate output path for generated video (POD path for YAML)."""
        suffix = "_vanilla" if vanilla else ""
        return os.path.join(POD_OUTPUT_TALKING_FACE_DIR, f"talking_face_{job_id}{suffix}.mp4")

    def get_local_output_path(self, job_id: str, vanilla: bool = False) -> str:
        """Calculate local output path for displaying results."""
        suffix = "_vanilla" if vanilla else ""
        return os.path.join(OUTPUT_TALKING_FACE_DIR, f"talking_face_{job_id}{suffix}.mp4")

    def get_pod_input_paths(self, job_id: str, image_name: str, audio_name: str) -> Dict[str, str]:
        """Get the pod paths for input files."""
        return {
            "image": os.path.join(POD_INPUT_IMAGES_DIR, job_id, image_name),
            "audio": os.path.join(POD_INPUT_AUDIO_DIR, job_id, audio_name),
        }

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

    def save_uploaded_files(self, image_file, audio_file, job_id: str) -> tuple[Dict[str, str], Dict[str, str]]:
        """
        Save uploaded files to input directories.

        When running locally, also copies to the persistent volume pod.

        Returns:
            Tuple of (local_paths, pod_paths)
        """
        local_paths = {}
        pod_paths = {}

        # Save image locally
        image_dir = os.path.join(INPUT_IMAGES_DIR, job_id)
        os.makedirs(image_dir, exist_ok=True)
        local_image_path = os.path.join(image_dir, image_file.name)
        with open(local_image_path, "wb") as f:
            f.write(image_file.getbuffer())
        local_paths["image"] = local_image_path

        # Save audio locally
        audio_dir = os.path.join(INPUT_AUDIO_DIR, job_id)
        os.makedirs(audio_dir, exist_ok=True)
        local_audio_path = os.path.join(audio_dir, audio_file.name)
        with open(local_audio_path, "wb") as f:
            f.write(audio_file.getbuffer())
        local_paths["audio"] = local_audio_path

        # Calculate pod paths
        pod_paths = self.get_pod_input_paths(job_id, image_file.name, audio_file.name)

        # If running locally, copy to the persistent volume pod
        if not IS_POD_ENV:
            k8s = KubernetesClient()
            import subprocess

            # Create directories on the pod
            pod_image_dir = os.path.join(POD_INPUT_IMAGES_DIR, job_id)
            pod_audio_dir = os.path.join(POD_INPUT_AUDIO_DIR, job_id)

            subprocess.run(
                [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--",
                 "mkdir", "-p", pod_image_dir, pod_audio_dir],
                capture_output=True,
                timeout=30
            )

            # Copy image to pod
            success, msg = k8s.copy_to_pod(local_image_path, PERSISTENT_POD_NAME, pod_paths["image"])
            if not success:
                raise RuntimeError(f"Failed to copy image to pod: {msg}")

            # Copy audio to pod
            success, msg = k8s.copy_to_pod(local_audio_path, PERSISTENT_POD_NAME, pod_paths["audio"])
            if not success:
                raise RuntimeError(f"Failed to copy audio to pod: {msg}")

        return local_paths, pod_paths
