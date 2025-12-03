"""Chatterbox TTS model runner implementation (placeholder)."""

import os
import streamlit as st
from string import Template
from typing import Dict, Any, Optional

from models.base import BaseModelRunner, JobConfig
from config import (
    MODELS,
    YAML_TEMPLATE_DIR,
    OUTPUT_AUDIO_DIR,
    INPUT_TEXTS_DIR,
)


class ChatterboxModel(BaseModelRunner):
    """Chatterbox TTS model runner (placeholder until repo is added)."""

    @property
    def model_id(self) -> str:
        return "chatterbox"

    @property
    def display_name(self) -> str:
        return "Chatterbox TTS"

    @property
    def description(self) -> str:
        return "Text-to-Speech generation using Chatterbox"

    @property
    def model_dir(self) -> str:
        return MODELS["chatterbox"]["dir"]

    @property
    def venv_path(self) -> str:
        return MODELS["chatterbox"]["venv"]

    @property
    def is_enabled(self) -> bool:
        return MODELS["chatterbox"]["enabled"]

    def get_yaml_template_path(self) -> str:
        return os.path.join(YAML_TEMPLATE_DIR, "chatterbox.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for Chatterbox inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        st.subheader("Text Input")

        text_input = st.text_area(
            "Enter text to synthesize",
            height=150,
            placeholder="Type or paste the text you want to convert to speech...",
            key="chatterbox_text_input",
        )

        st.subheader("Voice Settings")

        col1, col2 = st.columns(2)

        with col1:
            voice = st.selectbox(
                "Voice",
                options=["default", "female1", "male1"],  # Placeholder options
                index=0,
                help="Select the voice for speech synthesis (options will be updated when model is available)"
            )

        with col2:
            speed = st.slider(
                "Speed",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                help="Speech speed multiplier"
            )

        if not text_input or not text_input.strip():
            return None

        return {
            "files": {},  # No file uploads for TTS
            "params": {
                "text": text_input.strip(),
                "voice": voice,
                "speed": speed,
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
            IMAGE=MODELS["chatterbox"]["image"],
            INPUT_TEXT=config.model_params.get("text", ""),
            OUTPUT_AUDIO=config.output_file,
            VOICE=config.model_params.get("voice", "default"),
            SPEED=config.model_params.get("speed", 1.0),
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """Calculate output path for generated audio."""
        return os.path.join(OUTPUT_AUDIO_DIR, f"tts_{job_id}.wav")

    def get_output_type(self) -> str:
        return "audio"

    def validate_inputs(self, input_files: Dict[str, str]) -> tuple[bool, str]:
        """Validate that text input is provided."""
        # For TTS, validation is done in render_input_ui
        return True, ""

    def save_text_input(self, text: str, job_id: str) -> str:
        """Save text input to file and return path."""
        job_input_dir = os.path.join(INPUT_TEXTS_DIR, job_id)
        os.makedirs(job_input_dir, exist_ok=True)

        file_path = os.path.join(job_input_dir, "input.txt")
        with open(file_path, "w") as f:
            f.write(text)

        return file_path
