"""Chatterbox TTS page UI."""

import streamlit as st
import os

from models.chatterbox import ChatterboxModel
from models.base import JobConfig
from job_manager.manager import JobManager
from k8s.client import KubernetesClient
from ui.common import (
    generate_job_id,
    generate_pod_name,
    show_success_toast,
    show_error_toast,
    show_model_unavailable_message,
)
from ui.components.job_status import render_job_status_panel, render_compact_job_status
from ui.components.output_viewer import render_output_viewer


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
           git clone <chatterbox-repo-url> Chatterbox
           ```

        2. **Create virtual environment:**
           ```bash
           /data/python/bin/python3.11 -m venv /data/chatterbox-venv
           source /data/chatterbox-venv/bin/activate
           pip install -r /data/Chatterbox/requirements.txt
           ```

        3. **Update configuration:**
           Edit `/data/streamlit-app/config.py` and set:
           ```python
           "chatterbox": {
               ...
               "enabled": True,
               "image": "<docker-image-with-chatterbox>",
               ...
           }
           ```

        4. **Update YAML template:**
           Edit `/data/streamlit-app/k8s/templates/chatterbox.yaml`
           with the correct inference commands.
        """)
        return

    # Show compact job status
    render_compact_job_status("chatterbox")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 1])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            if st.button("Generate Speech", type="primary", use_container_width=True):
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

    # Output section
    st.divider()
    render_output_viewer(model_filter="chatterbox")


def submit_chatterbox_job(model: ChatterboxModel, inputs: dict):
    """Submit a Chatterbox TTS job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save text input
        text = inputs["params"]["text"]
        text_path = model.save_text_input(text, job_id)

        input_files = {"text": text_path}
        params = inputs["params"]

        # Calculate output path
        output_path = model.get_output_path(job_id, input_files)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Create job config
        config = JobConfig(
            job_id=job_id,
            pod_name=pod_name,
            model_id=model.model_id,
            input_files=input_files,
            output_file=output_path,
            model_params=params,
        )

        # Generate YAML
        yaml_content = model.generate_yaml(config)

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
                input_files=input_files,
                output_file=output_path,
                model_params=params,
            )
            show_success_toast(f"Job submitted: {job_id}")
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")
