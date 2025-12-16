"""Evaluators page UI - contains multiple evaluation tools."""

import streamlit as st
import os
import json
import pandas as pd

from models.syncnet import SyncNetModel
from models.chatterbox_eval import ChatterboxEvalModel
from models.base import JobConfig
from job_manager.manager import JobManager, JobState
from k8s.client import KubernetesClient
from config import IS_POD_ENV, PERSISTENT_POD_NAME, MODELS
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
    st.markdown("Evaluate the quality of generated outputs")

    # Create tabs for different evaluators
    tab_names = ["Lip Sync (SyncNet)", "TTS Quality (MOS + WER)"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_syncnet_tab()

    with tabs[1]:
        render_tts_evaluator_tab()


def render_syncnet_tab():
    """Render the SyncNet lip sync evaluation tab."""
    st.subheader("SyncNet Lip Sync Evaluation")
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
    col1, col2 = st.columns([1, 1])

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

    # Results section
    st.divider()
    render_syncnet_results()


def render_tts_evaluator_tab():
    """Render the TTS quality evaluation tab."""
    st.subheader("TTS Quality Evaluation")
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
    col1, col2 = st.columns([1, 1])

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

    # Results section
    st.divider()
    render_tts_eval_results()


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


def render_syncnet_results():
    """Render evaluation results for completed SyncNet jobs."""
    st.subheader("Evaluation Results")

    job_manager = JobManager()
    all_jobs = job_manager.get_jobs_by_model("syncnet")
    completed_jobs = [j for j in all_jobs if j.get_state() == JobState.COMPLETED]

    if not completed_jobs:
        st.info("No completed evaluations yet. Submit a video to see results here.")
        return

    for job in completed_jobs:
        output_path = job.output_file
        local_output_dir = job.model_params.get("local_output_dir", os.path.dirname(output_path))

        # Try to fetch results from pod if running locally
        if not os.path.exists(output_path) and not IS_POD_ENV:
            pod_output_dir = job.model_params.get("output_pod_dir")
            if pod_output_dir:
                try:
                    k8s = KubernetesClient()
                    os.makedirs(local_output_dir, exist_ok=True)
                    # Copy the entire output directory
                    k8s.copy_from_pod(
                        PERSISTENT_POD_NAME,
                        pod_output_dir,
                        local_output_dir
                    )
                except Exception:
                    pass

        with st.expander(f"**Job: {job.job_id}**", expanded=True):
            # Try to read the summary JSON
            if os.path.exists(output_path):
                try:
                    with open(output_path, 'r') as f:
                        results = json.load(f)

                    render_sync_score(results)
                except json.JSONDecodeError:
                    st.warning("Could not parse evaluation results")
                except Exception as e:
                    st.error(f"Error reading results: {e}")
            else:
                # Check for offsets.txt in the evaluation subdirectory
                offsets_file = os.path.join(local_output_dir, "evaluation_syncnet", "offsets.txt")
                if os.path.exists(offsets_file):
                    try:
                        with open(offsets_file, 'r') as f:
                            content = f.read().strip()
                        if content:
                            parts = content.split()
                            offset = float(parts[0]) if len(parts) > 0 else 0
                            confidence = float(parts[1]) if len(parts) > 1 else 0
                            render_sync_score({"offset": offset, "confidence": confidence})
                        else:
                            st.warning("Evaluation completed but no results found")
                    except Exception as e:
                        st.error(f"Error reading offsets: {e}")
                else:
                    st.warning(f"Results not yet available: {output_path}")

            # Job metadata
            st.caption(f"Job ID: {job.job_id} | Created: {job.created_at[:19]}")


def render_sync_score(results: dict):
    """Render the sync score with visual indicators."""
    offset = results.get("offset", 0)
    confidence = results.get("confidence", 0)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Offset (frames)", f"{offset:.2f}")

    with col2:
        st.metric("Confidence", f"{confidence:.4f}")

    with col3:
        # Determine quality based on offset and confidence
        abs_offset = abs(offset)
        if abs_offset <= 2 and confidence > 5:
            quality = "Good"
            color = "green"
        elif abs_offset <= 5 and confidence > 3:
            quality = "Fair"
            color = "orange"
        else:
            quality = "Poor"
            color = "red"

        st.markdown(f"**Sync Quality:** :{color}[{quality}]")

    # Explanation
    st.caption("""
    **Offset**: Frame difference between audio and video (0 = perfectly synced)
    **Confidence**: Higher values indicate more reliable detection
    **Quality**: Good (offset ≤2, conf >5), Fair (offset ≤5, conf >3), Poor (otherwise)
    """)


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


def render_tts_eval_results():
    """Render evaluation results for completed TTS evaluation jobs."""
    st.subheader("Evaluation Results")

    job_manager = JobManager()
    all_jobs = job_manager.get_jobs_by_model("chatterbox_eval")
    completed_jobs = [j for j in all_jobs if j.get_state() == JobState.COMPLETED]

    if not completed_jobs:
        st.info("No completed evaluations yet. Upload audio files to see results here.")
        return

    for job in completed_jobs:
        output_path = job.output_file
        local_output_dir = job.model_params.get("local_output_dir", os.path.dirname(output_path))

        # Try to fetch results from pod if running locally
        if not os.path.exists(output_path) and not IS_POD_ENV:
            pod_output_dir = job.model_params.get("output_pod_dir")
            if pod_output_dir:
                try:
                    k8s = KubernetesClient()
                    os.makedirs(local_output_dir, exist_ok=True)
                    # Copy the results CSV
                    k8s.copy_from_pod(
                        PERSISTENT_POD_NAME,
                        job.model_params.get("output_pod_path"),
                        output_path
                    )
                except Exception:
                    pass

        with st.expander(f"**Job: {job.job_id}**", expanded=True):
            audio_count = job.input_files.get("audio_count", "?")
            text_count = job.input_files.get("text_count", 0)
            st.caption(f"Audio files: {audio_count} | Reference texts: {text_count}")

            # Try to read the results CSV
            if os.path.exists(output_path):
                try:
                    df = pd.read_csv(output_path)
                    render_tts_eval_scores(df)
                except Exception as e:
                    st.error(f"Error reading results: {e}")
            else:
                st.warning(f"Results not yet available: {output_path}")

            # Job metadata
            st.caption(f"Job ID: {job.job_id} | Created: {job.created_at[:19]}")


def render_tts_eval_scores(df: pd.DataFrame):
    """Render TTS evaluation scores with visual indicators."""
    # Summary metrics
    col1, col2, col3 = st.columns(3)

    mean_mos = df["mos"].mean() if "mos" in df.columns else None
    mean_wer = df["wer"].dropna().mean() if "wer" in df.columns and df["wer"].notna().any() else None

    with col1:
        if mean_mos is not None:
            st.metric("Average MOS", f"{mean_mos:.3f}")
            # MOS quality indicator
            if mean_mos >= 4.0:
                st.markdown(":green[Excellent]")
            elif mean_mos >= 3.5:
                st.markdown(":blue[Good]")
            elif mean_mos >= 3.0:
                st.markdown(":orange[Fair]")
            else:
                st.markdown(":red[Poor]")

    with col2:
        if mean_wer is not None:
            st.metric("Average WER", f"{mean_wer:.2%}")
            # WER quality indicator
            if mean_wer <= 0.05:
                st.markdown(":green[Excellent]")
            elif mean_wer <= 0.10:
                st.markdown(":blue[Good]")
            elif mean_wer <= 0.20:
                st.markdown(":orange[Fair]")
            else:
                st.markdown(":red[Poor]")
        else:
            st.metric("Average WER", "N/A")
            st.caption("No reference texts provided")

    with col3:
        st.metric("Files Evaluated", len(df))

    # Detailed results table
    st.markdown("**Per-file Results**")

    # Select columns to display
    display_cols = ["file", "mos"]
    if "wer" in df.columns:
        display_cols.append("wer")

    display_df = df[display_cols].copy()

    # Format WER as percentage
    if "wer" in display_df.columns:
        display_df["wer"] = display_df["wer"].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "N/A")

    # Format MOS
    display_df["mos"] = display_df["mos"].apply(lambda x: f"{x:.3f}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Explanation
    st.caption("""
    **MOS (Mean Opinion Score)**: Speech quality prediction (1-5 scale, higher is better)
    **WER (Word Error Rate)**: Transcription accuracy (lower is better, requires reference text)
    """)
