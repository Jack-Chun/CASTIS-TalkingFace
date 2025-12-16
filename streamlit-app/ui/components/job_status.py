"""Job status panel component."""

import streamlit as st
import os
import html
from datetime import timedelta

from job_manager.manager import JobManager, JobState
from ui.common import format_timestamp, create_status_badge
from config import IS_POD_ENV, PERSISTENT_POD_NAME

# Auto-refresh interval in seconds for running jobs
AUTO_REFRESH_INTERVAL = 5

# Max height for log container in pixels
LOG_MAX_HEIGHT = 400


def render_scrollable_logs(logs: str, key: str):
    """Render logs in a scrollable container with fixed max height."""
    escaped_logs = html.escape(logs)
    st.markdown(
        f"""
        <div style="
            max-height: {LOG_MAX_HEIGHT}px;
            overflow-y: auto;
            background-color: #0e1117;
            border-radius: 8px;
            padding: 12px;
            font-family: 'Source Code Pro', monospace;
            font-size: 13px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
            color: #fafafa;
        ">
<pre style="margin: 0; background: transparent; color: inherit;">{escaped_logs}</pre>
        </div>
        """,
        unsafe_allow_html=True
    )


def ensure_output_local(job) -> bool:
    """
    Ensure the output file is available locally.
    When running locally, copies the file from the pod if needed.
    """
    from k8s.client import KubernetesClient

    output_path = job.output_file

    # If file already exists locally, we're good
    if os.path.exists(output_path):
        return True

    # If running on pod, file should exist - if not, it's missing
    if IS_POD_ENV:
        return False

    # Running locally - try to copy from pod
    pod_output_path = job.model_params.get("output_pod_path")
    if not pod_output_path:
        return False

    # Ensure local directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Copy from pod
    k8s = KubernetesClient()
    success, msg = k8s.copy_from_pod(
        PERSISTENT_POD_NAME,
        pod_output_path,
        output_path
    )

    return success


def get_mime_type(file_ext: str) -> str:
    """Get MIME type for file extension."""
    mime_types = {
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.mkv': 'video/x-matroska',
        '.webm': 'video/webm',
        '.wav': 'audio/wav',
        '.mp3': 'audio/mpeg',
        '.m4a': 'audio/mp4',
        '.flac': 'audio/flac',
        '.ogg': 'audio/ogg',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
    }
    return mime_types.get(file_ext.lower(), 'application/octet-stream')


def render_job_output(job):
    """Render the output for a completed job."""
    # Handle evaluation jobs specially
    if job.model_type == "syncnet":
        render_syncnet_output(job)
        return
    elif job.model_type == "chatterbox_eval":
        render_tts_eval_output(job)
        return

    output_path = job.output_file

    # Ensure file is available locally (copies from pod if needed)
    if not ensure_output_local(job):
        st.warning(f"Output file not found: {output_path}")
        return

    file_ext = os.path.splitext(output_path)[1].lower()
    file_name = os.path.basename(output_path)

    st.markdown("**Output:**")

    # Display based on file type
    if file_ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
        render_video_comparison(output_path, job)
    elif file_ext in ['.wav', '.mp3', '.m4a', '.flac', '.ogg']:
        st.audio(output_path)
    elif file_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
        st.image(output_path)
    else:
        st.info(f"Preview not available for {file_ext} files")

    # Download button
    with open(output_path, "rb") as f:
        st.download_button(
            label=f"Download {file_name}",
            data=f.read(),
            file_name=file_name,
            mime=get_mime_type(file_ext),
            key=f"download_{job.job_id}"
        )


def render_video_comparison(video_path: str, job):
    """Render video output with input/output comparison if input video exists."""
    import base64

    # Get input video path for comparison
    input_video_path = job.input_files.get("video") if job.input_files else None

    # Display videos side by side if input exists
    if input_video_path and os.path.exists(input_video_path):
        try:
            with open(input_video_path, "rb") as f:
                input_video_b64 = base64.b64encode(f.read()).decode()
            with open(video_path, "rb") as f:
                output_video_b64 = base64.b64encode(f.read()).decode()

            input_ext = os.path.splitext(input_video_path)[1].lower()
            output_ext = os.path.splitext(video_path)[1].lower()
            input_mime = get_mime_type(input_ext)
            output_mime = get_mime_type(output_ext)

            comp_id = job.job_id.replace("-", "_")

            html_code = f"""
            <style>
                .video-comparison-{comp_id} {{
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }}
                .video-row-{comp_id} {{
                    display: flex;
                    gap: 20px;
                }}
                .video-container-{comp_id} {{
                    flex: 1;
                }}
                .video-container-{comp_id} video {{
                    width: 100%;
                    border-radius: 8px;
                }}
                .video-label-{comp_id} {{
                    font-weight: bold;
                    margin-bottom: 8px;
                    color: #333;
                }}
                .control-btn-{comp_id} {{
                    padding: 10px 24px;
                    font-size: 14px;
                    font-weight: 500;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    margin-right: 8px;
                    transition: background-color 0.2s;
                }}
                .play-btn-{comp_id} {{
                    background-color: #ff4b4b;
                    color: white;
                }}
                .play-btn-{comp_id}:hover {{
                    background-color: #ff3333;
                }}
                .reset-btn-{comp_id} {{
                    background-color: #f0f2f6;
                    color: #333;
                }}
                .reset-btn-{comp_id}:hover {{
                    background-color: #e0e2e6;
                }}
            </style>
            <div class="video-comparison-{comp_id}">
                <div>
                    <button class="control-btn-{comp_id} play-btn-{comp_id}" onclick="playBoth_{comp_id}()">Play Both</button>
                    <button class="control-btn-{comp_id} reset-btn-{comp_id}" onclick="resetBoth_{comp_id}()">Reset</button>
                </div>
                <div class="video-row-{comp_id}">
                    <div class="video-container-{comp_id}">
                        <div class="video-label-{comp_id}">Input Video</div>
                        <video id="input_{comp_id}" controls>
                            <source src="data:{input_mime};base64,{input_video_b64}" type="{input_mime}">
                        </video>
                    </div>
                    <div class="video-container-{comp_id}">
                        <div class="video-label-{comp_id}">Output Video</div>
                        <video id="output_{comp_id}" controls>
                            <source src="data:{output_mime};base64,{output_video_b64}" type="{output_mime}">
                        </video>
                    </div>
                </div>
            </div>
            <script>
                function playBoth_{comp_id}() {{
                    var input = document.getElementById('input_{comp_id}');
                    var output = document.getElementById('output_{comp_id}');
                    input.currentTime = 0;
                    output.currentTime = 0;
                    input.play();
                    output.play();
                }}
                function resetBoth_{comp_id}() {{
                    var input = document.getElementById('input_{comp_id}');
                    var output = document.getElementById('output_{comp_id}');
                    input.pause();
                    output.pause();
                    input.currentTime = 0;
                    output.currentTime = 0;
                }}
            </script>
            """
            st.components.v1.html(html_code, height=350, scrolling=True)

        except Exception as e:
            st.error(f"Error loading videos for comparison: {e}")
            # Fallback to regular display
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Input Video**")
                st.video(input_video_path)
            with col2:
                st.markdown("**Output Video**")
                st.video(video_path)
    else:
        # Just show output video if input not available
        try:
            st.video(video_path)
        except Exception as e:
            st.error(f"Error playing video: {e}")
            st.info("You can still download the file using the button below.")


def render_syncnet_output(job):
    """Render SyncNet evaluation results."""
    import json
    from k8s.client import KubernetesClient

    output_path = job.output_file
    local_output_dir = job.model_params.get("local_output_dir", os.path.dirname(output_path))

    # The actual SyncNet results are in pywork/evaluation_syncnet/syncnet_summary.json
    actual_results_path = os.path.join(local_output_dir, "pywork", "evaluation_syncnet", "syncnet_summary.json")

    # Try to fetch results from pod if running locally
    if not os.path.exists(actual_results_path) and not IS_POD_ENV:
        pod_output_dir = job.model_params.get("output_pod_dir")
        if pod_output_dir:
            try:
                k8s = KubernetesClient()
                os.makedirs(local_output_dir, exist_ok=True)
                k8s.copy_from_pod(PERSISTENT_POD_NAME, pod_output_dir, local_output_dir)
            except Exception:
                pass

    # Try to read the summary JSON from the correct location
    results = None

    if os.path.exists(actual_results_path):
        try:
            with open(actual_results_path, 'r') as f:
                results = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass

    # Fallback to the root output path
    if results is None and os.path.exists(output_path):
        try:
            with open(output_path, 'r') as f:
                results = json.load(f)
                if results.get("status") == "completed" and "av_offset" not in results:
                    results = None
        except (json.JSONDecodeError, Exception):
            pass

    st.markdown("**Evaluation Results:**")

    if results and "av_offset" in results:
        render_sync_score(results)
    else:
        # Check for offsets.txt as last resort
        offsets_file = os.path.join(local_output_dir, "pywork", "evaluation_syncnet", "offsets.txt")
        if os.path.exists(offsets_file):
            try:
                with open(offsets_file, 'r') as f:
                    content = f.read().strip()
                if content:
                    parts = content.split()
                    offset = float(parts[0]) if len(parts) > 0 else 0
                    confidence = float(parts[1]) if len(parts) > 1 else 0
                    render_sync_score({"av_offset": offset, "confidence": confidence})
                else:
                    st.warning("Evaluation completed but no results found")
            except Exception as e:
                st.error(f"Error reading offsets: {e}")
        else:
            st.warning("Results not yet available. Check logs for details.")


def render_sync_score(results: dict):
    """Render the sync score with visual indicators."""
    offset = results.get("av_offset", results.get("offset", 0))
    confidence = results.get("confidence", 0)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Offset (frames)", f"{offset:.2f}")

    with col2:
        st.metric("Confidence", f"{confidence:.4f}")

    with col3:
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

    st.caption("""
    **Offset**: Frame difference between audio and video (0 = perfectly synced)
    **Confidence**: Higher values indicate more reliable detection
    """)


def render_tts_eval_output(job):
    """Render TTS evaluation results."""
    import pandas as pd
    from k8s.client import KubernetesClient

    output_path = job.output_file
    local_output_dir = job.model_params.get("local_output_dir", os.path.dirname(output_path))

    # Try to fetch results from pod if running locally
    if not os.path.exists(output_path) and not IS_POD_ENV:
        pod_output_path = job.model_params.get("output_pod_path")
        if pod_output_path:
            try:
                k8s = KubernetesClient()
                os.makedirs(local_output_dir, exist_ok=True)
                k8s.copy_from_pod(PERSISTENT_POD_NAME, pod_output_path, output_path)
            except Exception:
                pass

    st.markdown("**Evaluation Results:**")

    if os.path.exists(output_path):
        try:
            df = pd.read_csv(output_path)
            render_tts_eval_scores(df, job.job_id)
        except Exception as e:
            st.error(f"Error reading results: {e}")
    else:
        st.warning(f"Results not yet available: {output_path}")


def render_tts_eval_scores(df, job_id: str):
    """Render TTS evaluation scores with visual indicators."""
    import pandas as pd

    col1, col2, col3 = st.columns(3)

    mean_mos = df["mos"].mean() if "mos" in df.columns else None
    mean_wer = df["wer"].dropna().mean() if "wer" in df.columns and df["wer"].notna().any() else None

    with col1:
        if mean_mos is not None:
            st.metric("Average MOS", f"{mean_mos:.3f}")
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
            st.caption("No reference texts")

    with col3:
        st.metric("Files Evaluated", len(df))

    # Detailed results table
    with st.expander("Per-file Results"):
        display_cols = ["file", "mos"]
        if "wer" in df.columns:
            display_cols.append("wer")

        display_df = df[display_cols].copy()

        if "wer" in display_df.columns:
            display_df["wer"] = display_df["wer"].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "N/A")

        display_df["mos"] = display_df["mos"].apply(lambda x: f"{x:.3f}")

        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.caption("**MOS**: Speech quality (1-5, higher=better) | **WER**: Word error rate (lower=better)")


@st.fragment(run_every=timedelta(seconds=AUTO_REFRESH_INTERVAL))
def render_job_status_panel(model_filter: str = None):
    """
    Render the job status panel showing all jobs.
    Uses @st.fragment with run_every to auto-refresh without affecting other page sections.

    Args:
        model_filter: Optional model type to filter jobs by
    """
    job_manager = JobManager()

    # Create a unique key prefix based on model_filter to avoid duplicate keys
    # when this component is rendered multiple times on the same page
    key_prefix = f"{model_filter or 'all'}_"

    # Initialize session state for log viewing and output viewing
    if "viewing_logs" not in st.session_state:
        st.session_state.viewing_logs = set()
    if "viewing_outputs" not in st.session_state:
        st.session_state.viewing_outputs = set()

    # Get jobs and update active ones
    if model_filter:
        jobs = job_manager.get_jobs_by_model(model_filter)
        # Also include related model variants (e.g., stableavatar-vanilla for stableavatar)
        if model_filter == "stableavatar":
            vanilla_jobs = job_manager.get_jobs_by_model("stableavatar-vanilla")
            jobs = jobs + vanilla_jobs
            # Re-sort combined list by creation time (newest first)
            jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)
    else:
        jobs = job_manager.get_all_jobs()

    # Auto-update active jobs on each refresh
    job_manager.update_all_active_jobs()

    if not jobs:
        st.info("No jobs found. Submit a job to get started.")
        return

    # Action buttons
    col1, col2, col3 = st.columns([4, 1, 1], vertical_alignment="bottom")

    with col1:
        st.subheader("Job Status")
    
    with col2:
        if st.button("Refresh All", key=f"{key_prefix}refresh_all_jobs"):
            job_manager.update_all_active_jobs()
            st.rerun()

    with col3:
        if st.button("Clear Completed", key=f"{key_prefix}clear_completed"):
            count = job_manager.cleanup_completed_jobs()
            if count > 0:
                st.toast(f"Cleared {count} completed jobs")
                st.rerun()

    # Display jobs
    for job in jobs:
        state = job.get_state()
        status_badge = create_status_badge(state.value)

        with st.expander(
            f"{status_badge} **{job.job_id}**",
            expanded=(state in [JobState.RUNNING, JobState.FAILED])
        ):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Model:** {job.model_type}")
                st.markdown(f"**Pod:** `{job.pod_name}`")

                # Input files
                if job.input_files:
                    st.markdown("**Input Files:**")
                    for file_type, file_value in job.input_files.items():
                        # Handle both file paths (strings) and other values (counts, etc.)
                        if file_type.endswith("_pod"):
                            continue

                        if isinstance(file_value, str):
                            st.caption(f"- {file_type}: {os.path.basename(file_value)}")
                        else:
                            st.caption(f"- {file_type}: {file_value}")

            with col2:
                st.markdown(f"**Status:** {status_badge}")
                st.markdown(f"**Created:** {format_timestamp(job.created_at)}")
                st.markdown(f"**Updated:** {format_timestamp(job.updated_at)}")

                # Show output file if completed
                if state == JobState.COMPLETED and os.path.exists(job.output_file):
                    file_size = os.path.getsize(job.output_file)
                    st.markdown(f"**Output:** {file_size / 1024 / 1024:.1f} MB")

            # Action buttons for this job
            col1, col2, col3 = st.columns([1, 1, 1])

            with col1:
                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
                
                with btn_col1:
                    # Toggle logs viewing
                    is_viewing = job.job_id in st.session_state.viewing_logs
                    btn_label = "Hide Logs" if is_viewing else "View Logs"
                    if st.button(btn_label, key=f"logs_{job.job_id}"):
                        if is_viewing:
                            st.session_state.viewing_logs.discard(job.job_id)
                        else:
                            st.session_state.viewing_logs.add(job.job_id)
                        st.rerun()

                with btn_col2:
                    # View Output button (only for completed jobs)
                    if state == JobState.COMPLETED:
                        is_viewing_output = job.job_id in st.session_state.viewing_outputs
                        output_btn_label = "Hide Output" if is_viewing_output else "View Output"
                        if st.button(output_btn_label, key=f"output_{job.job_id}"):
                            if is_viewing_output:
                                st.session_state.viewing_outputs.discard(job.job_id)
                            else:
                                st.session_state.viewing_outputs.add(job.job_id)
                            st.rerun()

                with btn_col3:
                    if st.button("Delete", key=f"delete_{job.job_id}", type="secondary"):
                        st.session_state.viewing_logs.discard(job.job_id)
                        job_manager.delete_job(job.job_id, delete_pod=True)
                        st.toast(f"Deleted job {job.job_id}")
                        st.rerun()

            # Display logs in full width (outside columns)
            if job.job_id in st.session_state.viewing_logs:
                # Fetch and save logs
                logs = job_manager.get_job_logs(job.job_id)

                if logs:
                    render_scrollable_logs(logs, key=f"logs_view_{job.job_id}")
                else:
                    st.info("No logs available yet")

            # Display output for completed jobs
            if job.job_id in st.session_state.viewing_outputs and state == JobState.COMPLETED:
                render_job_output(job)

            # Error message for failed jobs
            if state == JobState.FAILED and job.error_message:
                st.error(f"**Error:** {job.error_message}")


def render_compact_job_status(model_type: str):
    """
    Render a compact job status summary for a specific model.

    Shows count of active/completed/failed jobs.
    """
    job_manager = JobManager()
    jobs = job_manager.get_jobs_by_model(model_type)

    # Also include related model variants (e.g., stableavatar-vanilla for stableavatar)
    if model_type == "stableavatar":
        vanilla_jobs = job_manager.get_jobs_by_model("stableavatar-vanilla")
        jobs = jobs + vanilla_jobs

    if not jobs:
        return

    active = sum(1 for j in jobs if j.get_state() in [JobState.QUEUED, JobState.RUNNING])
    completed = sum(1 for j in jobs if j.get_state() == JobState.COMPLETED)
    failed = sum(1 for j in jobs if j.get_state() == JobState.FAILED)

    status_text = []
    if active > 0:
        status_text.append(f":orange[{active} active]")
    if completed > 0:
        status_text.append(f":green[{completed} completed]")
    if failed > 0:
        status_text.append(f":red[{failed} failed]")

    if status_text:
        st.caption(f"Jobs: {' | '.join(status_text)}")
