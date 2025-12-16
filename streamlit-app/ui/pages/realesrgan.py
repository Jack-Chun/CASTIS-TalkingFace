"""Real-ESRGAN page UI."""

import streamlit as st
import os

from models.realesrgan import RealESRGANModel
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


def render_realesrgan_page():
    """Render the Real-ESRGAN model page."""
    st.header("Real-ESRGAN Video Upscaling")
    st.markdown("Upscale videos using Real-ESRGAN super-resolution (2x or 4x)")

    model = RealESRGANModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)
        return

    # Show compact job status
    render_compact_job_status("realesrgan")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 2])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            if st.button("Start Upscaling", type="primary", use_container_width=True):
                submit_realesrgan_job(model, inputs)
        else:
            st.button(
                "Start Upscaling",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Upload a video file to enable"
            )

    with col2:
        # Job status for this model
        render_job_status_panel(model_filter="realesrgan")


def submit_realesrgan_job(model: RealESRGANModel, inputs: dict):
    """Submit a Real-ESRGAN job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save uploaded file (returns local_path, pod_path)
        video_file = inputs["files"]["video"]
        local_video_path, pod_video_path = model.save_uploaded_file(video_file, job_id)

        # Use pod paths for YAML (what the GPU pod sees)
        input_files = {"video": pod_video_path}
        params = inputs["params"]

        # Calculate output path (pod path for YAML)
        output_path = model.get_output_path(job_id, input_files)

        # Calculate local output path for tracking
        local_output_path = model.get_local_output_path(job_id, {"video": local_video_path})

        # Ensure local output directory exists (for when we copy results back)
        os.makedirs(os.path.dirname(local_output_path), exist_ok=True)

        # Create job config with pod paths
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
            # Register job - store local output path for result viewing
            job_manager = JobManager()
            job_manager.create_job(
                job_id=job_id,
                pod_name=pod_name,
                model_type=model.model_id,
                input_files={"video": local_video_path, "video_pod": pod_video_path},
                output_file=local_output_path,  # Local path for viewing results
                model_params={**params, "output_pod_path": output_path},  # Store pod path too
            )
            show_success_toast(f"Job submitted: {job_id}")
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")
