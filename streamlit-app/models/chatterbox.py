"""Chatterbox TTS model runner implementation."""

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
    INPUT_AUDIO_DIR,
    POD_INPUT_TEXTS_DIR,
    POD_INPUT_AUDIO_DIR,
    POD_OUTPUT_AUDIO_DIR,
)

# Supported languages for ChatterboxMultilingualTTS
# Note: Finetuned checkpoint (final.pt) is optimized for Korean
SUPPORTED_LANGUAGES = {
    "ko": "Korean (finetuned)",
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
}


class ChatterboxModel(BaseModelRunner):
    """Chatterbox TTS model runner with voice cloning support."""

    @property
    def model_id(self) -> str:
        return "chatterbox"

    @property
    def display_name(self) -> str:
        return "Chatterbox TTS"

    @property
    def description(self) -> str:
        return "Text-to-Speech generation with voice cloning (finetuned for Korean)"

    @property
    def model_dir(self) -> str:
        return MODELS["chatterbox"]["dir"]

    @property
    def venv_path(self) -> str:
        return MODELS["chatterbox"]["venv"]

    @property
    def is_enabled(self) -> bool:
        return MODELS["chatterbox"]["enabled"]

    def get_yaml_template_path(self, vanilla: bool = False) -> str:
        if vanilla:
            return os.path.join(YAML_TEMPLATE_DIR, "chatterbox_vanilla.yaml")
        return os.path.join(YAML_TEMPLATE_DIR, "chatterbox.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for Chatterbox inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        # Initialize session state for voice prompt
        if "chatterbox_voice_prompt" not in st.session_state:
            st.session_state.chatterbox_voice_prompt = None
        if "chatterbox_voice_prompt_name" not in st.session_state:
            st.session_state.chatterbox_voice_prompt_name = None

        st.subheader("Text Input")

        text_input = st.text_area(
            "Enter text to synthesize",
            height=150,
            placeholder="Type or paste the text you want to convert to speech...",
            key="chatterbox_text_input",
        )

        st.subheader("Voice Settings")

        # Language selection
        language_options = list(SUPPORTED_LANGUAGES.keys())
        language_labels = [f"{SUPPORTED_LANGUAGES[k]} ({k})" for k in language_options]

        col1, col2 = st.columns(2)

        with col1:
            language_idx = st.selectbox(
                "Language",
                options=range(len(language_options)),
                format_func=lambda x: language_labels[x],
                index=0,  # Korean as default
                help="Select the language for speech synthesis"
            )
            language = language_options[language_idx]

        with col2:
            # Voice prompt upload
            voice_file = st.file_uploader(
                "Voice Prompt (optional)",
                type=["wav", "mp3", "m4a", "flac"],
                help="Upload a voice sample for voice cloning (10+ seconds recommended)",
                key="chatterbox_voice_uploader",
            )

            if voice_file is not None:
                st.session_state.chatterbox_voice_prompt = voice_file.getvalue()
                st.session_state.chatterbox_voice_prompt_name = voice_file.name
                st.success(f"Voice prompt loaded: {voice_file.name}")

            # Show current voice prompt status
            if st.session_state.chatterbox_voice_prompt_name:
                st.caption(f"Current: {st.session_state.chatterbox_voice_prompt_name}")
                if st.button("Clear voice prompt", key="clear_voice"):
                    st.session_state.chatterbox_voice_prompt = None
                    st.session_state.chatterbox_voice_prompt_name = None
                    st.rerun()

        st.subheader("Advanced Settings")

        col3, col4 = st.columns(2)

        with col3:
            exaggeration = st.slider(
                "Exaggeration",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                help="Higher values create more expressive speech"
            )

        with col4:
            cfg_weight = st.slider(
                "CFG Weight",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                help="Classifier-free guidance weight for voice matching"
            )

        st.subheader("Comparison Mode")

        compare_with_vanilla = st.checkbox(
            "Compare with vanilla model (no finetuning)",
            value=False,
            help="Run both finetuned and vanilla models to compare results side by side"
        )

        if not text_input or not text_input.strip():
            return None

        return {
            "files": {
                "voice_prompt": st.session_state.chatterbox_voice_prompt,
                "voice_prompt_name": st.session_state.chatterbox_voice_prompt_name,
            },
            "params": {
                "text": text_input.strip(),
                "language": language,
                "exaggeration": exaggeration,
                "cfg_weight": cfg_weight,
                "compare_with_vanilla": compare_with_vanilla,
            }
        }

    def generate_yaml(self, config: JobConfig, vanilla: bool = False) -> str:
        """Generate YAML manifest from template."""
        template_path = self.get_yaml_template_path(vanilla=vanilla)

        with open(template_path, 'r') as f:
            template_content = f.read()

        template = Template(template_content)

        # Get voice prompt path (pod path)
        voice_prompt_path = config.model_params.get("voice_prompt_path", "")
        if not voice_prompt_path:
            # Use default prompt if available
            voice_prompt_path = "/data/chatterbox/prompt.wav"

        # Extract base job_id (remove _vanilla suffix if present for vanilla jobs)
        base_job_id = config.job_id.replace("_vanilla", "")

        yaml_content = template.safe_substitute(
            POD_NAME=config.pod_name,
            JOB_ID=config.job_id,
            IMAGE=MODELS["chatterbox"]["image"],
            INPUT_TEXT_FILE=f"{POD_INPUT_TEXTS_DIR}/{base_job_id}/input.txt",
            OUTPUT_AUDIO=config.output_file,
            VOICE_PROMPT=voice_prompt_path,
            LANGUAGE=config.model_params.get("language", "ko"),
            EXAGGERATION=config.model_params.get("exaggeration", 0.5),
            CFG_WEIGHT=config.model_params.get("cfg_weight", 0.5),
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str], vanilla: bool = False) -> str:
        """Calculate output path for generated audio (POD path for YAML)."""
        suffix = "_vanilla" if vanilla else ""
        return f"{POD_OUTPUT_AUDIO_DIR}/tts_{job_id}{suffix}.wav"

    def get_local_output_path(self, job_id: str, vanilla: bool = False) -> str:
        """Calculate local output path for generated audio."""
        suffix = "_vanilla" if vanilla else ""
        return os.path.join(OUTPUT_AUDIO_DIR, f"tts_{job_id}{suffix}.wav")

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

    def save_voice_prompt(self, audio_data: bytes, filename: str, job_id: str) -> str:
        """Save voice prompt audio file and return path."""
        job_input_dir = os.path.join(INPUT_AUDIO_DIR, job_id)
        os.makedirs(job_input_dir, exist_ok=True)

        # Keep original extension
        file_path = os.path.join(job_input_dir, filename)
        with open(file_path, "wb") as f:
            f.write(audio_data)

        return file_path

    def get_pod_voice_prompt_path(self, job_id: str, filename: str) -> str:
        """Get the pod path for the voice prompt."""
        return f"{POD_INPUT_AUDIO_DIR}/{job_id}/{filename}"
