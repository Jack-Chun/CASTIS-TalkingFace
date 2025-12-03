"""StableAvatar page UI."""

import streamlit as st
import os

from models.stableavatar import StableAvatarModel
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


def render_stableavatar_page():
    """Render the StableAvatar page."""
    st.header("StableAvatar Talking Face")
    st.markdown("Generate talking face videos from an image and audio")

    model = StableAvatarModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)

        # Show what's needed
        st.subheader("Setup Instructions")
        st.markdown("""
        To enable StableAvatar:

        1. **Clone the repository:**
           ```bash
           cd /data
           git clone <stableavatar-repo-url> StableAvatar
           ```

        2. **Create virtual environment:**
           ```bash
           /data/python/bin/python3.11 -m venv /data/stableavatar-venv
           source /data/stableavatar-venv/bin/activate
           pip install -r /data/StableAvatar/requirements.txt
           ```

        3. **Download model weights:**
           Follow the model repository instructions to download
           pretrained weights.

        4. **Update configuration:**
           Edit `/data/streamlit-app/config.py` and set:
           ```python
           "stableavatar": {
               ...
               "enabled": True,
               "image": "<docker-image-with-stableavatar>",
               ...
           }
           ```

        5. **Update YAML template:**
           Edit `/data/streamlit-app/k8s/templates/stableavatar.yaml`
           with the correct inference commands.
        """)
        return

    # Show compact job status
    render_compact_job_status("stableavatar")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 1])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            if st.button("Generate Talking Face", type="primary", use_container_width=True):
                submit_stableavatar_job(model, inputs)
        else:
            st.button(
                "Generate Talking Face",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Upload an image and audio file to enable"
            )

    with col2:
        # Job status for this model
        render_job_status_panel(model_filter="stableavatar")

    # Output section
    st.divider()
    render_output_viewer(model_filter="stableavatar")


def submit_stableavatar_job(model: StableAvatarModel, inputs: dict):
    """Submit a StableAvatar job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save uploaded files
        image_file = inputs["files"]["image"]
        audio_file = inputs["files"]["audio"]
        input_files = model.save_uploaded_files(image_file, audio_file, job_id)

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
