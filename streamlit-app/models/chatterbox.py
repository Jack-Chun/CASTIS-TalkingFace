"""Chatterbox TTS model runner implementation."""

import os
import streamlit as st
from string import Template
from typing import Dict, Any, Optional, Tuple

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
    IS_POD_ENV,
    PERSISTENT_POD_NAME,
)
from k8s.client import KubernetesClient

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
        # Initialize session state for inputs (consistent with StableAvatar/Real-ESRGAN pattern)
        if "chatterbox_voice_prompt" not in st.session_state:
            st.session_state.chatterbox_voice_prompt = None
        if "chatterbox_text" not in st.session_state:
            st.session_state.chatterbox_text = ""

        # Text Input section
        st.subheader("Text Input")

        text_input = st.text_area(
            "Enter text to synthesize",
            value=st.session_state.chatterbox_text,
            height=150,
            placeholder="Type or paste the text you want to convert to speech...",
            key="chatterbox_text_input",
        )
        # Update session state
        st.session_state.chatterbox_text = text_input

        # Voice Prompt section (consistent UX with StableAvatar file uploads)
        st.subheader("Voice Prompt (optional)")

        if st.session_state.chatterbox_voice_prompt is None:
            # Show uploader if no voice prompt uploaded
            voice_file = st.file_uploader(
                "Upload a voice sample for voice cloning",
                type=["wav", "mp3", "m4a", "flac"],
                key="chatterbox_voice_upload",
                help="Upload a voice sample for voice cloning (10+ seconds recommended)"
            )
            if voice_file:
                st.session_state.chatterbox_voice_prompt = voice_file
                st.rerun()
        else:
            # Show preview and remove button (consistent with StableAvatar pattern)
            voice_file = st.session_state.chatterbox_voice_prompt
            col1, col2 = st.columns([5, 1])
            with col1:
                st.audio(voice_file)
                st.caption(voice_file.name)
            with col2:
                if st.button("Remove", key="remove_voice"):
                    st.session_state.chatterbox_voice_prompt = None
                    st.rerun()

        st.subheader("Voice Settings")

        # Language selection
        language_options = list(SUPPORTED_LANGUAGES.keys())
        language_labels = [f"{SUPPORTED_LANGUAGES[k]} ({k})" for k in language_options]

        language_idx = st.selectbox(
            "Language",
            options=range(len(language_options)),
            format_func=lambda x: language_labels[x],
            index=0,  # Korean as default
            help="Select the language for speech synthesis"
        )
        language = language_options[language_idx]

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

        st.subheader("Model Selection")

        use_vanilla = st.radio(
            "Model Type",
            options=["finetuned", "vanilla"],
            index=0,
            format_func=lambda x: "Finetuned (Korean optimized)" if x == "finetuned" else "Vanilla (No finetuning)",
            help="Choose between the finetuned model (optimized for Korean) or the vanilla model",
            horizontal=True,
        )

        if not text_input or not text_input.strip():
            return None

        return {
            "files": {
                "voice_prompt": st.session_state.chatterbox_voice_prompt,
            },
            "params": {
                "text": text_input.strip(),
                "language": language,
                "exaggeration": exaggeration,
                "cfg_weight": cfg_weight,
                "use_vanilla": use_vanilla == "vanilla",
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
            voice_prompt_path = "/data/Chatterbox_Finetuning/voice_sample.wav"

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

    def get_pod_text_path(self, job_id: str) -> str:
        """Get the pod path for the text input file."""
        return f"{POD_INPUT_TEXTS_DIR}/{job_id}/input.txt"

    def get_pod_voice_prompt_path(self, job_id: str, filename: str) -> str:
        """Get the pod path for the voice prompt."""
        return f"{POD_INPUT_AUDIO_DIR}/{job_id}/{filename}"

    def save_uploaded_files(
        self,
        text: str,
        voice_file,  # Streamlit UploadedFile or None
        job_id: str
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Save text and optional voice prompt to input directories.

        When running locally, also copies to the persistent volume pod.
        Consistent with StableAvatar/Real-ESRGAN pattern.

        Returns:
            Tuple of (local_paths, pod_paths)
        """
        import subprocess

        local_paths = {}
        pod_paths = {}

        # Save text locally
        text_dir = os.path.join(INPUT_TEXTS_DIR, job_id)
        os.makedirs(text_dir, exist_ok=True)
        local_text_path = os.path.join(text_dir, "input.txt")
        with open(local_text_path, "w") as f:
            f.write(text)
        local_paths["text"] = local_text_path
        pod_paths["text"] = self.get_pod_text_path(job_id)

        # Save voice prompt if provided
        if voice_file is not None:
            voice_dir = os.path.join(INPUT_AUDIO_DIR, job_id)
            os.makedirs(voice_dir, exist_ok=True)
            local_voice_path = os.path.join(voice_dir, voice_file.name)
            with open(local_voice_path, "wb") as f:
                f.write(voice_file.getbuffer())
            local_paths["voice_prompt"] = local_voice_path
            pod_paths["voice_prompt"] = self.get_pod_voice_prompt_path(job_id, voice_file.name)
        else:
            # Use default prompt
            pod_paths["voice_prompt"] = "/data/chatterbox/prompt.wav"

        # If running locally, copy to the persistent volume pod
        if not IS_POD_ENV:
            k8s = KubernetesClient()

            # Create directories on the pod
            pod_text_dir = f"{POD_INPUT_TEXTS_DIR}/{job_id}"
            mkdir_cmd = [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--", "mkdir", "-p", pod_text_dir]

            if voice_file is not None:
                pod_voice_dir = f"{POD_INPUT_AUDIO_DIR}/{job_id}"
                mkdir_cmd = [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--", "mkdir", "-p", pod_text_dir, pod_voice_dir]

            mkdir_result = subprocess.run(mkdir_cmd, capture_output=True, timeout=30, text=True)
            if mkdir_result.returncode != 0:
                raise RuntimeError(f"Failed to create directories on pod: {mkdir_result.stderr}")

            # Copy text file to pod
            success, msg = k8s.copy_to_pod(local_text_path, PERSISTENT_POD_NAME, pod_paths["text"])
            if not success:
                raise RuntimeError(f"Failed to copy text file to pod: {msg}")

            # Copy voice file if provided
            if voice_file is not None and "voice_prompt" in local_paths:
                success, msg = k8s.copy_to_pod(local_paths["voice_prompt"], PERSISTENT_POD_NAME, pod_paths["voice_prompt"])
                if not success:
                    raise RuntimeError(f"Failed to copy voice file to pod: {msg}")

        return local_paths, pod_paths
