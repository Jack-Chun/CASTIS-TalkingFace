"""Output viewer component for displaying model results."""

import streamlit as st
import os

from job_manager.manager import JobManager, JobState
from ui.common import format_file_size


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

        if not os.path.exists(output_path):
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
    """Render video output with player."""
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

    if not os.path.exists(output_path):
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
