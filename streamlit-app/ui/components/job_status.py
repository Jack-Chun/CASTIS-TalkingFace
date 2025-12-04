"""Job status panel component."""

import streamlit as st
import os
import time

from job_manager.manager import JobManager, JobState
from ui.common import format_timestamp, create_status_badge

# Auto-refresh interval in seconds for running jobs
AUTO_REFRESH_INTERVAL = 5


def render_job_status_panel(model_filter: str = None):
    """
    Render the job status panel showing all jobs.

    Args:
        model_filter: Optional model type to filter jobs by
    """
    st.subheader("Job Status")

    job_manager = JobManager()

    # Initialize session state for log viewing
    if "viewing_logs" not in st.session_state:
        st.session_state.viewing_logs = set()

    # Get jobs
    if model_filter:
        jobs = job_manager.get_jobs_by_model(model_filter)
    else:
        jobs = job_manager.get_all_jobs()

    if not jobs:
        st.info("No jobs found. Submit a job to get started.")
        return

    # Check if any running jobs have logs being viewed (for auto-refresh)
    has_running_with_logs = any(
        job.job_id in st.session_state.viewing_logs
        and job.get_state() in [JobState.QUEUED, JobState.RUNNING]
        for job in jobs
    )

    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("Refresh All", key="refresh_all_jobs"):
            job_manager.update_all_active_jobs()
            st.rerun()

    with col2:
        if st.button("Clear Completed", key="clear_completed"):
            count = job_manager.cleanup_completed_jobs()
            if count > 0:
                st.toast(f"Cleared {count} completed jobs")
                st.rerun()

    st.divider()

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
                st.markdown(f"**Created:** {format_timestamp(job.created_at)}")

            with col2:
                st.markdown(f"**Status:** {status_badge}")
                st.markdown(f"**Updated:** {format_timestamp(job.updated_at)}")

                # Show output file if completed
                if state == JobState.COMPLETED and os.path.exists(job.output_file):
                    file_size = os.path.getsize(job.output_file)
                    st.markdown(f"**Output:** {file_size / 1024 / 1024:.1f} MB")

            # Input files
            if job.input_files:
                st.markdown("**Input Files:**")
                for file_type, file_path in job.input_files.items():
                    st.text(f"  {file_type}: {os.path.basename(file_path)}")

            # Action buttons for this job
            btn_col1, btn_col2, btn_col3 = st.columns(3)

            with btn_col1:
                if state in [JobState.QUEUED, JobState.RUNNING]:
                    if st.button("Refresh", key=f"refresh_{job.job_id}"):
                        job_manager.update_job_status(job.job_id)
                        st.rerun()

            with btn_col2:
                # Toggle logs viewing
                is_viewing = job.job_id in st.session_state.viewing_logs
                btn_label = "Hide Logs" if is_viewing else "View Logs"
                if st.button(btn_label, key=f"logs_{job.job_id}"):
                    if is_viewing:
                        st.session_state.viewing_logs.discard(job.job_id)
                    else:
                        st.session_state.viewing_logs.add(job.job_id)
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

                if state in [JobState.QUEUED, JobState.RUNNING]:
                    st.caption(f"Auto-refreshing every {AUTO_REFRESH_INTERVAL}s...")

                if logs:
                    st.code(logs, language="bash")
                else:
                    st.info("No logs available yet")

            # Error message for failed jobs
            if state == JobState.FAILED and job.error_message:
                st.error(f"**Error:** {job.error_message}")

            # Always show saved logs for completed/failed jobs (even if not actively viewing)
            if job.logs and state in [JobState.COMPLETED, JobState.FAILED]:
                if job.job_id not in st.session_state.viewing_logs:
                    with st.expander("Execution Logs", expanded=False):
                        st.code(job.logs, language="bash")

    # Auto-refresh for running jobs with logs being viewed
    if has_running_with_logs:
        time.sleep(AUTO_REFRESH_INTERVAL)
        # Update job statuses before rerun
        job_manager.update_all_active_jobs()
        st.rerun()


def render_compact_job_status(model_type: str):
    """
    Render a compact job status summary for a specific model.

    Shows count of active/completed/failed jobs.
    """
    job_manager = JobManager()
    jobs = job_manager.get_jobs_by_model(model_type)

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
