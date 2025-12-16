"""Shared sidebar component for all pages."""

import streamlit as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_manager.manager import JobManager


def render_sidebar():
    """Render the shared sidebar content."""
    with st.sidebar:
        st.markdown(
            """
            <style>
                [data-testid="stSidebarNav"]::before {
                    content: "SNU X CASTIS";
                    margin-left: 10px;
                    font-size: 30px;
                    position: relative;
                    top: 0px;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
        # Job summary
        st.subheader("Active Jobs")
        job_manager = JobManager()
        active_jobs = job_manager.get_active_jobs()

        if active_jobs:
            for job in active_jobs[:5]:
                state = job.get_state()
                emoji = "🔄" if state.value == "running" else "⏳"
                st.text(f"{emoji} {job.model_type}: {job.job_id[:20]}...")

            if len(active_jobs) > 5:
                st.caption(f"...and {len(active_jobs) - 5} more")

            st.caption("Jobs refresh on page interaction")
        else:
            st.caption("No active jobs")

