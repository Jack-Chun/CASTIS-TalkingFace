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

        # Save uploaded files (returns local_paths, pod_paths)
        image_file = inputs["files"]["image"]
        audio_file = inputs["files"]["audio"]
        local_paths, pod_paths = model.save_uploaded_files(image_file, audio_file, job_id)

        params = inputs["params"]

        # Calculate output path (pod path for YAML)
        output_path = model.get_output_path(job_id, pod_paths)

        # Calculate local output path for tracking
        local_output_path = model.get_local_output_path(job_id)

        # Ensure local output directory exists (for when we copy results back)
        os.makedirs(os.path.dirname(local_output_path), exist_ok=True)

        # Create job config with pod paths
        config = JobConfig(
            job_id=job_id,
            pod_name=pod_name,
            model_id=model.model_id,
            input_files=pod_paths,  # Use pod paths for YAML
            output_file=output_path,
            model_params=params,
        )

        # Generate YAML
        yaml_content = model.generate_yaml(config)

        # Apply to Kubernetes
        k8s = KubernetesClient()
        success, message = k8s.apply_yaml(yaml_content)

        if success:
            # Register job - store local paths for result viewing
            job_manager = JobManager()
            job_manager.create_job(
                job_id=job_id,
                pod_name=pod_name,
                model_type=model.model_id,
                input_files={
                    "image": local_paths["image"],
                    "audio": local_paths["audio"],
                    "image_pod": pod_paths["image"],
                    "audio_pod": pod_paths["audio"],
                },
                output_file=local_output_path,  # Local path for viewing results
                model_params={**params, "output_pod_path": output_path},  # Store pod path too
            )
            show_success_toast(f"Job submitted: {job_id}")
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")
