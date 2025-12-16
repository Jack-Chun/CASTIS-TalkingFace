"""Evaluators page UI - contains multiple evaluation tools."""

import streamlit as st
import os

from models.syncnet import SyncNetModel
from models.chatterbox_eval import ChatterboxEvalModel
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


def render_evaluators_page():
    """Render the evaluators page with tabs for different evaluation tools."""
    st.header("Evaluators")

    # Create tabs for different evaluators
    tab_names = ["TTS Quality (MOS + WER)", "Lip Sync Quality (SyncNet)"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_tts_evaluator_tab()

    with tabs[1]:
        render_syncnet_tab()


def render_syncnet_tab():
    """Render the SyncNet lip sync evaluation tab."""
    st.markdown("Evaluate the lip sync quality of talking face videos")

    model = SyncNetModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)
        return

    # Show compact job status
    render_compact_job_status("syncnet")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 2])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            if st.button("Evaluate Lip Sync", type="primary", use_container_width=True, key="syncnet_submit"):
                submit_syncnet_job(model, inputs)
        else:
            st.button(
                "Evaluate Lip Sync",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Upload a video file to enable",
                key="syncnet_submit_disabled"
            )

    with col2:
        # Job status for this model
        render_job_status_panel(model_filter="syncnet")


def render_tts_evaluator_tab():
    """Render the TTS quality evaluation tab."""
    st.markdown("Evaluate TTS audio quality using MOS (Mean Opinion Score) and WER (Word Error Rate)")

    model = ChatterboxEvalModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)
        return

    # Show compact job status
    render_compact_job_status("chatterbox_eval")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 2])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            if st.button("Evaluate TTS Quality", type="primary", use_container_width=True, key="tts_eval_submit"):
                submit_tts_eval_job(model, inputs)
        else:
            st.button(
                "Evaluate TTS Quality",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Upload audio files to enable",
                key="tts_eval_submit_disabled"
            )

    with col2:
        # Job status for this model
        render_job_status_panel(model_filter="chatterbox_eval")


def submit_syncnet_job(model: SyncNetModel, inputs: dict):
    """Submit a SyncNet evaluation job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save uploaded file (returns local_path, pod_path)
        video_file = inputs["files"]["video"]
        local_video_path, pod_video_path = model.save_uploaded_file(video_file, job_id)

        params = inputs["params"]

        # Calculate output path (pod path for YAML)
        output_path = model.get_output_path(job_id, {"video": pod_video_path})
        output_dir = model.get_pod_output_dir(job_id)

        # Calculate local output path for tracking
        local_output_path = model.get_local_output_path(job_id)
        local_output_dir = model.get_local_output_dir(job_id)

        # Ensure local output directory exists
        os.makedirs(local_output_dir, exist_ok=True)

        # Create job config with pod paths
        config = JobConfig(
            job_id=job_id,
            pod_name=pod_name,
            model_id=model.model_id,
            input_files={"video": pod_video_path},
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
                input_files={
                    "video": local_video_path,
                    "video_pod": pod_video_path,
                },
                output_file=local_output_path,
                model_params={
                    **params,
                    "output_pod_path": output_path,
                    "output_pod_dir": output_dir,
                    "local_output_dir": local_output_dir,
                },
            )
            show_success_toast(f"Evaluation job submitted: {job_id}")
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")


def submit_tts_eval_job(model: ChatterboxEvalModel, inputs: dict):
    """Submit a TTS evaluation job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save uploaded files (returns local_dir, pod_dir)
        audio_files = inputs["files"]["audio_files"]
        text_files = inputs["files"]["text_files"] or []
        local_input_dir, pod_input_dir = model.save_uploaded_files(audio_files, text_files, job_id)

        params = inputs["params"]

        # Calculate output path (pod path for YAML)
        output_path = model.get_output_path(job_id, {"audio_dir": pod_input_dir})
        output_dir = model.get_pod_output_dir(job_id)

        # Calculate local output path for tracking
        local_output_path = model.get_local_output_path(job_id)
        local_output_dir = model.get_local_output_dir(job_id)

        # Ensure local output directory exists
        os.makedirs(local_output_dir, exist_ok=True)

        # Create job config with pod paths
        config = JobConfig(
            job_id=job_id,
            pod_name=pod_name,
            model_id=model.model_id,
            input_files={"audio_dir": pod_input_dir},
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
                input_files={
                    "audio_dir": local_input_dir,
                    "audio_dir_pod": pod_input_dir,
                    "audio_count": len(audio_files),
                    "text_count": len(text_files),
                },
                output_file=local_output_path,
                model_params={
                    **params,
                    "output_pod_path": output_path,
                    "output_pod_dir": output_dir,
                    "local_output_dir": local_output_dir,
                },
            )
            show_success_toast(f"TTS evaluation job submitted: {job_id}")
            # Clear uploaded files from session state
            st.session_state.tts_eval_audio_files = []
            st.session_state.tts_eval_text_files = []
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")
