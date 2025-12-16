"""Chatterbox TTS evaluation model runner implementation."""

import os
import streamlit as st
from string import Template
from typing import Dict, Any, Optional

from models.base import BaseModelRunner, JobConfig
from config import (
    MODELS,
    YAML_TEMPLATE_DIR,
    OUTPUT_DIR,
    INPUT_AUDIO_DIR,
    POD_INPUT_AUDIO_DIR,
    POD_OUTPUT_DIR,
    IS_POD_ENV,
    PERSISTENT_POD_NAME,
)
from k8s.client import KubernetesClient


# Whisper model options
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]


class ChatterboxEvalModel(BaseModelRunner):
    """Chatterbox TTS evaluation model runner (MOS + WER)."""

    @property
    def model_id(self) -> str:
        return "chatterbox_eval"

    @property
    def display_name(self) -> str:
        return "TTS Evaluator"

    @property
    def description(self) -> str:
        return "TTS quality evaluation with MOS (WV-MOS) and WER (Whisper ASR)"

    @property
    def model_dir(self) -> str:
        return MODELS["chatterbox_eval"]["dir"]

    @property
    def venv_path(self) -> str:
        return MODELS["chatterbox_eval"]["venv"]

    @property
    def is_enabled(self) -> bool:
        return MODELS["chatterbox_eval"]["enabled"]

    def get_yaml_template_path(self) -> str:
        return os.path.join(YAML_TEMPLATE_DIR, "chatterbox_eval.yaml")

    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI for TTS evaluation inputs.

        Returns dict with 'files' and 'params' or None if incomplete.
        """
        # Initialize session state (consistent with other models)
        if "tts_eval_audio_files" not in st.session_state:
            st.session_state.tts_eval_audio_files = []
        if "tts_eval_text_files" not in st.session_state:
            st.session_state.tts_eval_text_files = []

        # Audio Files section
        st.subheader("Audio Files to Evaluate")

        if not st.session_state.tts_eval_audio_files:
            # Show uploader if no files uploaded
            audio_files = st.file_uploader(
                "Upload TTS audio files to evaluate",
                type=["wav", "mp3", "m4a", "flac", "ogg"],
                accept_multiple_files=True,
                key="tts_eval_audio_uploader",
                help="Upload TTS audio files to evaluate. For WER calculation, also upload matching .txt files."
            )
            if audio_files:
                st.session_state.tts_eval_audio_files = audio_files
                st.rerun()
        else:
            # Show uploaded files with preview and remove button (consistent with other models)
            audio_files = st.session_state.tts_eval_audio_files
            col1, col2 = st.columns([4, 1])
            with col1:
                # Show first file preview, then list others
                if len(audio_files) == 1:
                    st.audio(audio_files[0])
                    st.caption(f"{audio_files[0].name} ({audio_files[0].size / 1024:.1f} KB)")
                else:
                    st.audio(audio_files[0])
                    st.caption(f"{audio_files[0].name} and {len(audio_files) - 1} more file(s)")
            with col2:
                if st.button("Remove", key="remove_tts_audio"):
                    st.session_state.tts_eval_audio_files = []
                    st.rerun()

        # Reference Text Files section (optional)
        st.subheader("Reference Texts (Optional)")

        if not st.session_state.tts_eval_text_files:
            # Show uploader if no files uploaded
            text_files = st.file_uploader(
                "Upload reference text files for WER calculation",
                type=["txt"],
                accept_multiple_files=True,
                key="tts_eval_text_uploader",
                help="Each text file should match its audio file name (e.g., sample.wav + sample.txt)"
            )
            if text_files:
                st.session_state.tts_eval_text_files = text_files
                st.rerun()
        else:
            # Show uploaded text files with remove button (consistent with other models)
            text_files = st.session_state.tts_eval_text_files
            col1, col2 = st.columns([4, 1])
            with col1:
                file_list = ", ".join(f.name for f in text_files[:3])
                if len(text_files) > 3:
                    file_list += f" and {len(text_files) - 3} more"
                st.caption(f"{len(text_files)} text file(s): {file_list}")
            with col2:
                if st.button("Remove", key="remove_tts_text"):
                    st.session_state.tts_eval_text_files = []
                    st.rerun()

        st.subheader("Evaluation Settings")

        col1, col2 = st.columns(2)

        with col1:
            whisper_model = st.selectbox(
                "Whisper ASR Model",
                options=WHISPER_MODELS,
                index=WHISPER_MODELS.index("large-v3"),
                help="Larger models are more accurate but slower"
            )

        with col2:
            language = st.selectbox(
                "Language",
                options=["Korean", "English", "Japanese", "Chinese", "Auto-detect"],
                index=0,
                help="Language hint for Whisper ASR"
            )

        # Get files from session state
        audio_files = st.session_state.tts_eval_audio_files
        text_files = st.session_state.tts_eval_text_files

        if not audio_files:
            return None

        return {
            "files": {
                "audio_files": audio_files,
                "text_files": text_files,
            },
            "params": {
                "whisper_model": whisper_model,
                "language": language if language != "Auto-detect" else None,
            }
        }

    def generate_yaml(self, config: JobConfig) -> str:
        """Generate YAML manifest from template."""
        template_path = self.get_yaml_template_path()

        with open(template_path, 'r') as f:
            template_content = f.read()

        template = Template(template_content)

        # Get language for Whisper
        language = config.model_params.get("language")
        language_arg = language if language else ""

        yaml_content = template.safe_substitute(
            POD_NAME=config.pod_name,
            JOB_ID=config.job_id,
            IMAGE=MODELS["chatterbox_eval"]["image"],
            INPUT_AUDIO_DIR=config.input_files.get("audio_dir", ""),
            OUTPUT_DIR=config.output_file.rsplit('/', 1)[0],  # Directory part
            WHISPER_MODEL=config.model_params.get("whisper_model", "large-v2"),
            LANGUAGE=language_arg,
        )

        return yaml_content

    def get_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """Calculate output path for evaluation results (POD path for YAML)."""
        return os.path.join(POD_OUTPUT_DIR, "tts_eval", job_id, "tts_eval_results.csv")

    def get_local_output_path(self, job_id: str) -> str:
        """Calculate local output path for displaying results."""
        return os.path.join(OUTPUT_DIR, "tts_eval", job_id, "tts_eval_results.csv")

    def get_local_output_dir(self, job_id: str) -> str:
        """Calculate local output directory."""
        return os.path.join(OUTPUT_DIR, "tts_eval", job_id)

    def get_pod_output_dir(self, job_id: str) -> str:
        """Calculate pod output directory."""
        return os.path.join(POD_OUTPUT_DIR, "tts_eval", job_id)

    def get_pod_input_dir(self, job_id: str) -> str:
        """Get the pod path for input audio directory."""
        return os.path.join(POD_INPUT_AUDIO_DIR, "tts_eval", job_id)

    def get_local_input_dir(self, job_id: str) -> str:
        """Get local path for input audio directory."""
        return os.path.join(INPUT_AUDIO_DIR, "tts_eval", job_id)

    def get_output_type(self) -> str:
        return "evaluation"

    def validate_inputs(self, input_files: Dict[str, str]) -> tuple[bool, str]:
        """Validate that audio files are provided."""
        audio_dir = input_files.get("audio_dir")

        if not audio_dir:
            return False, "No audio files provided"

        return True, ""

    def save_uploaded_files(self, audio_files: list, text_files: list, job_id: str) -> tuple[str, str]:
        """
        Save uploaded files to input directory.

        When running locally, also copies to the persistent volume pod.

        Returns:
            Tuple of (local_dir, pod_dir)
        """
        # Create local job-specific directory
        local_input_dir = self.get_local_input_dir(job_id)
        os.makedirs(local_input_dir, exist_ok=True)

        # Save audio files locally
        for audio_file in audio_files:
            local_path = os.path.join(local_input_dir, audio_file.name)
            with open(local_path, "wb") as f:
                f.write(audio_file.getbuffer())

        # Save text files locally
        for text_file in text_files:
            local_path = os.path.join(local_input_dir, text_file.name)
            with open(local_path, "wb") as f:
                f.write(text_file.getbuffer())

        # Calculate pod path
        pod_input_dir = self.get_pod_input_dir(job_id)

        # If running locally, copy to the persistent volume pod
        if not IS_POD_ENV:
            k8s = KubernetesClient()
            import subprocess

            # Create directory on the pod
            subprocess.run(
                [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--",
                 "mkdir", "-p", pod_input_dir],
                capture_output=True,
                timeout=30
            )

            # Copy each file to the pod
            for audio_file in audio_files:
                local_path = os.path.join(local_input_dir, audio_file.name)
                pod_path = os.path.join(pod_input_dir, audio_file.name)
                success, msg = k8s.copy_to_pod(local_path, PERSISTENT_POD_NAME, pod_path)
                if not success:
                    raise RuntimeError(f"Failed to copy audio file to pod: {msg}")

            for text_file in text_files:
                local_path = os.path.join(local_input_dir, text_file.name)
                pod_path = os.path.join(pod_input_dir, text_file.name)
                success, msg = k8s.copy_to_pod(local_path, PERSISTENT_POD_NAME, pod_path)
                if not success:
                    raise RuntimeError(f"Failed to copy text file to pod: {msg}")

        return local_input_dir, pod_input_dir
