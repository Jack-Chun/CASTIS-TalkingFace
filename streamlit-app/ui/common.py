"""Common UI utilities and shared functions."""

import streamlit as st
from datetime import datetime
import uuid


def generate_job_id(model_id: str) -> str:
    """Generate a unique job ID."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{model_id}-{timestamp}-{short_uuid}"


def generate_pod_name(model_id: str, job_id: str) -> str:
    """Generate a Kubernetes-compliant pod name."""
    # Pod names must be lowercase and can contain - and .
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"gpu-{model_id}-{timestamp}"[:63]  # Max 63 chars for k8s names


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso_timestamp


def show_model_unavailable_message(model_name: str):
    """Display message for unavailable models."""
    st.warning(f"**{model_name}** is not yet available.")
    st.info("""
    This model will be enabled once:
    1. The model repository is added to `/data/{model_dir}`
    2. A virtual environment is created with dependencies
    3. The model is enabled in the configuration

    Please contact your team members for updates on when this model will be available.
    """)


def show_success_toast(message: str):
    """Show a success message."""
    st.success(message)


def show_error_toast(message: str):
    """Show an error message."""
    st.error(message)


def show_info_toast(message: str):
    """Show an info message."""
    st.info(message)


def create_status_badge(status: str) -> str:
    """Create a colored status badge."""
    colors = {
        "queued": "blue",
        "running": "orange",
        "completed": "green",
        "failed": "red",
    }
    color = colors.get(status.lower(), "gray")
    return f":{color}[{status.upper()}]"
