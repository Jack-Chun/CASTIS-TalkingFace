"""Chatterbox TTS page UI."""

import streamlit as st
import os

from models.chatterbox import ChatterboxModel
from models.base import JobConfig
from job_manager.manager import JobManager
from k8s.client import KubernetesClient
from config import PERSISTENT_POD_NAME
from ui.common import (
    generate_job_id,
    generate_pod_name,
    show_success_toast,
    show_error_toast,
    show_model_unavailable_message,
)
from ui.components.job_status import render_job_status_panel, render_compact_job_status


def render_chatterbox_page():
    """Render the Chatterbox TTS page."""
    st.header("Chatterbox Text-to-Speech")
    st.markdown("Generate speech from text using Chatterbox TTS")

    model = ChatterboxModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)

        # Show what's needed
        st.subheader("Setup Instructions")
        st.markdown("""
        To enable Chatterbox TTS:

        1. **Clone the repository:**
           ```bash
           cd /data
           git clone <chatterbox-repo-url> chatterbox
           ```

        2. **Create virtual environment:**
           ```bash
           /data/python/bin/python3.11 -m venv /data/chatterbox-venv
           source /data/chatterbox-venv/bin/activate
           pip install -e /data/chatterbox
           ```

        3. **Update configuration:**
           Edit `/data/streamlit-app/config.py` and set:
           ```python
           "chatterbox": {
               ...
               "enabled": True,
               ...
           }
           ```
        """)
        return

    # Show compact job status
    render_compact_job_status("chatterbox")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 2])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            use_vanilla = inputs["params"].get("use_vanilla", False)
            button_label = "Generate Speech (Vanilla)" if use_vanilla else "Generate Speech (Finetuned)"

            if st.button(button_label, type="primary", use_container_width=True):
                submit_chatterbox_job(model, inputs)
        else:
            st.button(
                "Generate Speech",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Enter text to enable"
            )

    with col2:
        # Job status for this model
        render_job_status_panel(model_filter="chatterbox")


def submit_chatterbox_job(model: ChatterboxModel, inputs: dict):
    """Submit a Chatterbox TTS job."""
    try:
        # Determine if using vanilla model
        use_vanilla = inputs["params"].get("use_vanilla", False)

        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save uploaded files (returns local_paths, pod_paths)
        text = inputs["params"]["text"]
        voice_file = inputs["files"].get("voice_prompt")
        local_paths, pod_paths = model.save_uploaded_files(text, voice_file, job_id)

        params = inputs["params"].copy()
        params["voice_prompt_path"] = pod_paths["voice_prompt"]

        # Calculate output paths
        pod_output_path = model.get_output_path(job_id, local_paths, vanilla=use_vanilla)
        local_output_path = model.get_local_output_path(job_id, vanilla=use_vanilla)

        # Add pod output path to params for copying from pod later
        params["output_pod_path"] = pod_output_path

        # Ensure output directory exists (local)
        os.makedirs(os.path.dirname(local_output_path), exist_ok=True)

        # Create job config
        config = JobConfig(
            job_id=job_id,
            pod_name=pod_name,
            model_id=model.model_id,
            input_files=pod_paths,
            output_file=pod_output_path,
            model_params=params,
        )

        # Generate YAML (vanilla or finetuned based on selection)
        yaml_content = model.generate_yaml(config, vanilla=use_vanilla)

        # Apply to Kubernetes
        k8s = KubernetesClient()
        success, message = k8s.apply_yaml(yaml_content)

        if success:
            # Register job
            job_manager = JobManager()
            job_manager.create_job(
                job_id=job_id,
                pod_name=pod_name,
                model_type=model.model_id,
                input_files={
                    "text": local_paths["text"],
                    "text_pod": pod_paths["text"],
                    "voice_prompt_pod": pod_paths["voice_prompt"],
                    **({"voice_prompt": local_paths["voice_prompt"]} if "voice_prompt" in local_paths else {}),
                },
                output_file=local_output_path,
                model_params=params,
            )
            model_type = "Vanilla" if use_vanilla else "Finetuned"
            show_success_toast(f"{model_type} job submitted: {job_id}")
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")
