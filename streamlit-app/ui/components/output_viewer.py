"""Output viewer component for displaying model results."""

import streamlit as st
import os

from job_manager.manager import JobManager, JobState
from ui.common import format_file_size
from config import IS_POD_ENV, PERSISTENT_POD_NAME
from k8s.client import KubernetesClient


def ensure_output_local(job) -> bool:
    """
    Ensure the output file is available locally.

    When running locally, copies the file from the pod if needed.

    Returns:
        True if file is available locally, False otherwise
    """
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


def render_output_viewer(model_filter: str = None):
    """
    Render output viewer for completed jobs.

    Args:
        model_filter: Optional model type to filter outputs by
    """
    st.subheader("Outputs")

    job_manager = JobManager()

    # Get completed jobs
    if model_filter:
        all_jobs = job_manager.get_jobs_by_model(model_filter)
        completed_jobs = [j for j in all_jobs if j.get_state() == JobState.COMPLETED]
    else:
        completed_jobs = job_manager.get_completed_jobs()

    if not completed_jobs:
        st.info("No completed outputs yet. Process a file to see results here.")
        return

    for job in completed_jobs:
        output_path = job.output_file

        # Ensure file is available locally (copies from pod if needed)
        if not ensure_output_local(job):
            st.warning(f"Output file not found: {output_path}")
            continue

        file_size = os.path.getsize(output_path)
        file_name = os.path.basename(output_path)
        file_ext = os.path.splitext(output_path)[1].lower()

        with st.expander(f"**{file_name}** ({format_file_size(file_size)})", expanded=True):
            # Display based on file type
            if file_ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                render_video_output(output_path, job)
            elif file_ext in ['.wav', '.mp3', '.m4a', '.flac', '.ogg']:
                render_audio_output(output_path, job)
            elif file_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                render_image_output(output_path, job)
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

            # Job info
            st.caption(f"Job ID: {job.job_id} | Model: {job.model_type}")


def render_video_output(video_path: str, job):
    """Render video output with player, showing input and output side by side."""
    import base64

    # Get input video path for comparison
    input_video_path = job.input_files.get("video") if job.input_files else None

    # Display videos side by side if input exists
    if input_video_path and os.path.exists(input_video_path):
        # Read video files and encode as base64 for HTML embedding
        try:
            with open(input_video_path, "rb") as f:
                input_video_b64 = base64.b64encode(f.read()).decode()
            with open(video_path, "rb") as f:
                output_video_b64 = base64.b64encode(f.read()).decode()

            # Get video mime type
            input_ext = os.path.splitext(input_video_path)[1].lower()
            output_ext = os.path.splitext(video_path)[1].lower()
            input_mime = get_mime_type(input_ext)
            output_mime = get_mime_type(output_ext)

            # Unique ID for this comparison
            comp_id = job.job_id.replace("-", "_")

            # Custom HTML with synchronized playback
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
            st.components.v1.html(html_code, height=650, scrolling=True)

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


def render_audio_output(audio_path: str, job):
    """Render audio output with player."""
    try:
        st.audio(audio_path)
    except Exception as e:
        st.error(f"Error playing audio: {e}")
        st.info("You can still download the file using the button below.")


def render_image_output(image_path: str, job):
    """Render image output."""
    try:
        st.image(image_path)
    except Exception as e:
        st.error(f"Error displaying image: {e}")
        st.info("You can still download the file using the button below.")


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


def render_single_output(job_id: str):
    """Render output for a single job."""
    job_manager = JobManager()
    job = job_manager.get_job(job_id)

    if not job:
        st.warning("Job not found")
        return

    if job.get_state() != JobState.COMPLETED:
        st.info("Job has not completed yet")
        return

    output_path = job.output_file

    # Ensure file is available locally (copies from pod if needed)
    if not ensure_output_local(job):
        st.warning(f"Output file not found: {output_path}")
        return

    file_ext = os.path.splitext(output_path)[1].lower()

    # Display based on file type
    if file_ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
        render_video_output(output_path, job)
    elif file_ext in ['.wav', '.mp3', '.m4a', '.flac', '.ogg']:
        render_audio_output(output_path, job)
    elif file_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
        render_image_output(output_path, job)

    # Download button
    file_name = os.path.basename(output_path)
    with open(output_path, "rb") as f:
        st.download_button(
            label=f"Download {file_name}",
            data=f.read(),
            file_name=file_name,
            mime=get_mime_type(file_ext),
            key=f"download_single_{job.job_id}"
        )
