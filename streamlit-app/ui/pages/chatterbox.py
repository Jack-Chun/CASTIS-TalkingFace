"""Chatterbox TTS page UI."""

import streamlit as st
import os
import subprocess

from models.chatterbox import ChatterboxModel
from models.base import JobConfig
from job_manager.manager import JobManager
from k8s.client import KubernetesClient
from config import IS_POD_ENV, PERSISTENT_POD_NAME, POD_INPUT_TEXTS_DIR, POD_INPUT_AUDIO_DIR
from ui.common import (
    generate_job_id,
    generate_pod_name,
    show_success_toast,
    show_error_toast,
    show_model_unavailable_message,
)
from ui.components.job_status import render_job_status_panel, render_compact_job_status
from ui.components.output_viewer import render_output_viewer


def copy_files_to_pod(job_id: str, text_path: str, voice_path: str = None, voice_name: str = None):
    """Copy input files to the persistent volume pod when running locally."""
    k8s = KubernetesClient()

    # Create directories on the pod
    pod_text_dir = f"{POD_INPUT_TEXTS_DIR}/{job_id}"
    mkdir_cmd = [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--", "mkdir", "-p", pod_text_dir]

    if voice_path and voice_name:
        pod_audio_dir = f"{POD_INPUT_AUDIO_DIR}/{job_id}"
        mkdir_cmd = [k8s.kubectl, "exec", PERSISTENT_POD_NAME, "--", "mkdir", "-p", pod_text_dir, pod_audio_dir]

    result = subprocess.run(mkdir_cmd, capture_output=True, timeout=30, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create directories on pod: {result.stderr}")

    # Copy text file
    pod_text_path = f"{pod_text_dir}/input.txt"
    success, msg = k8s.copy_to_pod(text_path, PERSISTENT_POD_NAME, pod_text_path)
    if not success:
        raise RuntimeError(f"Failed to copy text file to pod: {msg}")

    # Copy voice file if provided
    if voice_path and voice_name:
        pod_voice_path = f"{POD_INPUT_AUDIO_DIR}/{job_id}/{voice_name}"
        success, msg = k8s.copy_to_pod(voice_path, PERSISTENT_POD_NAME, pod_voice_path)
        if not success:
            raise RuntimeError(f"Failed to copy voice file to pod: {msg}")


def render_chatterbox_page():
    """Render the Chatterbox TTS page."""
    st.header("Chatterbox Text-to-Speech")
    st.markdown("Generate speech from text using Chatterbox TTS (finetuned for Korean)")

    model = ChatterboxModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)

        # Show what's needed
        st.subheader("Setup Instructions")
        st.markdown("""
        To enable Chatterbox TTS:

        1. **Clone the repository:**
           ```bash
           cd /data
           git clone <chatterbox-repo-url> chatterbox
           ```

        2. **Create virtual environment:**
           ```bash
           /data/python/bin/python3.11 -m venv /data/chatterbox-venv
           source /data/chatterbox-venv/bin/activate
           pip install -e /data/chatterbox
           ```

        3. **Update configuration:**
           Edit `/data/streamlit-app/config.py` and set:
           ```python
           "chatterbox": {
               ...
               "enabled": True,
               ...
           }
           ```
        """)
        return

    # Show compact job status
    render_compact_job_status("chatterbox")

    st.divider()

    # Two-column layout
    col1, col2 = st.columns([1, 1])

    with col1:
        # Input UI
        inputs = model.render_input_ui()

        # Submit button
        st.divider()

        if inputs:
            compare_mode = inputs["params"].get("compare_with_vanilla", False)
            button_label = "Generate Speech (Compare)" if compare_mode else "Generate Speech"

            if st.button(button_label, type="primary", use_container_width=True):
                submit_chatterbox_job(model, inputs)
        else:
            st.button(
                "Generate Speech",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Enter text to enable"
            )

    with col2:
        # Job status for this model
        render_job_status_panel(model_filter="chatterbox")

    # Output section
    st.divider()
    render_chatterbox_output_viewer()


def submit_chatterbox_job(model: ChatterboxModel, inputs: dict):
    """Submit a Chatterbox TTS job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save text input locally
        text = inputs["params"]["text"]
        local_text_path = model.save_text_input(text, job_id)

        input_files = {"text": local_text_path}
        params = inputs["params"].copy()

        # Handle voice prompt if provided
        voice_prompt_data = inputs["files"].get("voice_prompt")
        voice_prompt_name = inputs["files"].get("voice_prompt_name")

        local_voice_path = None
        if voice_prompt_data and voice_prompt_name:
            # Save voice prompt file locally
            local_voice_path = model.save_voice_prompt(voice_prompt_data, voice_prompt_name, job_id)
            input_files["voice_prompt"] = local_voice_path
            # Add pod path to params for YAML generation
            params["voice_prompt_path"] = model.get_pod_voice_prompt_path(job_id, voice_prompt_name)
        else:
            # Use default prompt
            params["voice_prompt_path"] = "/data/chatterbox/prompt.wav"

        # If running locally, copy files to persistent volume pod
        if not IS_POD_ENV:
            copy_files_to_pod(job_id, local_text_path, local_voice_path, voice_prompt_name)

        # Calculate output path
        output_path = model.get_output_path(job_id, input_files)

        # Ensure output directory exists (local)
        local_output_dir = os.path.dirname(model.get_local_output_path(job_id))
        os.makedirs(local_output_dir, exist_ok=True)

        # Create job config for finetuned model
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
            # Register job
            job_manager = JobManager()
            job_manager.create_job(
                job_id=job_id,
                pod_name=pod_name,
                model_type=model.model_id,
                input_files=input_files,
                output_file=output_path,
                model_params=params,
            )
            show_success_toast(f"Finetuned job submitted: {job_id}")

            # If comparison mode, also submit vanilla job
            if params.get("compare_with_vanilla", False):
                submit_vanilla_job(model, job_id, input_files, params)

            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")


def submit_vanilla_job(model: ChatterboxModel, base_job_id: str, input_files: dict, params: dict):
    """Submit a vanilla (non-finetuned) Chatterbox TTS job for comparison."""
    try:
        # Generate IDs for vanilla job
        vanilla_job_id = f"{base_job_id}_vanilla"
        vanilla_pod_name = generate_pod_name(model.model_id, vanilla_job_id)

        # Calculate output path for vanilla
        vanilla_output_path = model.get_output_path(base_job_id, input_files, vanilla=True)

        # Create job config for vanilla model
        vanilla_params = params.copy()
        vanilla_params["is_vanilla"] = True
        vanilla_params["comparison_job_id"] = base_job_id

        vanilla_config = JobConfig(
            job_id=vanilla_job_id,
            pod_name=vanilla_pod_name,
            model_id=model.model_id,
            input_files=input_files,
            output_file=vanilla_output_path,
            model_params=vanilla_params,
        )

        # Generate YAML for vanilla model
        yaml_content = model.generate_yaml(vanilla_config, vanilla=True)

        # Apply to Kubernetes
        k8s = KubernetesClient()
        success, message = k8s.apply_yaml(yaml_content)

        if success:
            # Register vanilla job
            job_manager = JobManager()
            job_manager.create_job(
                job_id=vanilla_job_id,
                pod_name=vanilla_pod_name,
                model_type=model.model_id,
                input_files=input_files,
                output_file=vanilla_output_path,
                model_params=vanilla_params,
            )
            show_success_toast(f"Vanilla job submitted: {vanilla_job_id}")
        else:
            show_error_toast(f"Failed to create vanilla pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting vanilla job: {str(e)}")


def render_chatterbox_output_viewer():
    """Render output viewer for Chatterbox with comparison support."""
    import base64
    from job_manager.manager import JobState
    from ui.components.output_viewer import ensure_output_local, get_mime_type
    from ui.common import format_file_size

    st.subheader("Outputs")

    job_manager = JobManager()
    all_jobs = job_manager.get_jobs_by_model("chatterbox")
    completed_jobs = [j for j in all_jobs if j.get_state() == JobState.COMPLETED]

    if not completed_jobs:
        st.info("No completed outputs yet. Generate speech to see results here.")
        return

    # Group jobs by base job_id (for comparison view)
    job_groups = {}
    for job in completed_jobs:
        # Check if it's a vanilla job
        if "_vanilla" in job.job_id:
            base_id = job.job_id.replace("_vanilla", "")
            if base_id not in job_groups:
                job_groups[base_id] = {"finetuned": None, "vanilla": None}
            job_groups[base_id]["vanilla"] = job
        else:
            if job.job_id not in job_groups:
                job_groups[job.job_id] = {"finetuned": None, "vanilla": None}
            job_groups[job.job_id]["finetuned"] = job

    for base_job_id, jobs in job_groups.items():
        finetuned_job = jobs["finetuned"]
        vanilla_job = jobs["vanilla"]

        # Determine display name
        if finetuned_job and vanilla_job:
            display_name = f"Comparison: {base_job_id}"
        elif finetuned_job:
            display_name = f"Finetuned: {base_job_id}"
        elif vanilla_job:
            display_name = f"Vanilla: {vanilla_job.job_id}"
        else:
            continue

        with st.expander(f"**{display_name}**", expanded=True):
            # Show comparison view if both exist
            if finetuned_job and vanilla_job:
                render_audio_comparison(finetuned_job, vanilla_job, base_job_id)
            elif finetuned_job:
                render_single_audio(finetuned_job, "Finetuned")
            elif vanilla_job:
                render_single_audio(vanilla_job, "Vanilla")


def render_audio_comparison(finetuned_job, vanilla_job, base_job_id: str):
    """Render side-by-side audio comparison."""
    import base64
    from ui.components.output_viewer import ensure_output_local, get_mime_type
    from ui.common import format_file_size

    # Ensure both files are available locally
    finetuned_available = ensure_output_local(finetuned_job)
    vanilla_available = ensure_output_local(vanilla_job)

    if not finetuned_available or not vanilla_available:
        st.warning("Some output files are not available yet.")
        if finetuned_available:
            render_single_audio(finetuned_job, "Finetuned")
        if vanilla_available:
            render_single_audio(vanilla_job, "Vanilla")
        return

    finetuned_path = finetuned_job.output_file
    vanilla_path = vanilla_job.output_file

    # Read and encode audio files
    try:
        with open(finetuned_path, "rb") as f:
            finetuned_b64 = base64.b64encode(f.read()).decode()
        with open(vanilla_path, "rb") as f:
            vanilla_b64 = base64.b64encode(f.read()).decode()

        finetuned_ext = os.path.splitext(finetuned_path)[1].lower()
        vanilla_ext = os.path.splitext(vanilla_path)[1].lower()
        finetuned_mime = get_mime_type(finetuned_ext)
        vanilla_mime = get_mime_type(vanilla_ext)

        # Unique ID for this comparison
        comp_id = base_job_id.replace("-", "_")

        # Custom HTML with synchronized playback
        html_code = f"""
        <style>
            .audio-comparison-{comp_id} {{
                display: flex;
                flex-direction: column;
                gap: 15px;
                padding: 10px;
            }}
            .audio-row-{comp_id} {{
                display: flex;
                gap: 20px;
            }}
            .audio-container-{comp_id} {{
                flex: 1;
                background: #f8f9fa;
                padding: 15px;
                border-radius: 10px;
            }}
            .audio-container-{comp_id} audio {{
                width: 100%;
            }}
            .audio-label-{comp_id} {{
                font-weight: bold;
                margin-bottom: 10px;
                font-size: 14px;
            }}
            .finetuned-label {{
                color: #ff4b4b;
            }}
            .vanilla-label {{
                color: #666;
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
        <div class="audio-comparison-{comp_id}">
            <div>
                <button class="control-btn-{comp_id} play-btn-{comp_id}" onclick="playBoth_{comp_id}()">Play Both</button>
                <button class="control-btn-{comp_id} reset-btn-{comp_id}" onclick="resetBoth_{comp_id}()">Reset</button>
            </div>
            <div class="audio-row-{comp_id}">
                <div class="audio-container-{comp_id}">
                    <div class="audio-label-{comp_id} finetuned-label">Finetuned Model (Korean)</div>
                    <audio id="finetuned_{comp_id}" controls>
                        <source src="data:{finetuned_mime};base64,{finetuned_b64}" type="{finetuned_mime}">
                    </audio>
                </div>
                <div class="audio-container-{comp_id}">
                    <div class="audio-label-{comp_id} vanilla-label">Vanilla Model (No Finetuning)</div>
                    <audio id="vanilla_{comp_id}" controls>
                        <source src="data:{vanilla_mime};base64,{vanilla_b64}" type="{vanilla_mime}">
                    </audio>
                </div>
            </div>
        </div>
        <script>
            function playBoth_{comp_id}() {{
                var finetuned = document.getElementById('finetuned_{comp_id}');
                var vanilla = document.getElementById('vanilla_{comp_id}');
                finetuned.currentTime = 0;
                vanilla.currentTime = 0;
                finetuned.play();
                vanilla.play();
            }}
            function resetBoth_{comp_id}() {{
                var finetuned = document.getElementById('finetuned_{comp_id}');
                var vanilla = document.getElementById('vanilla_{comp_id}');
                finetuned.pause();
                vanilla.pause();
                finetuned.currentTime = 0;
                vanilla.currentTime = 0;
            }}
        </script>
        """
        st.components.v1.html(html_code, height=200)

    except Exception as e:
        st.error(f"Error loading audio for comparison: {e}")
        # Fallback to separate displays
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Finetuned Model**")
            st.audio(finetuned_path)
        with col2:
            st.markdown("**Vanilla Model**")
            st.audio(vanilla_path)

    # Download buttons
    col1, col2 = st.columns(2)
    with col1:
        with open(finetuned_path, "rb") as f:
            st.download_button(
                label="Download Finetuned",
                data=f.read(),
                file_name=os.path.basename(finetuned_path),
                mime=finetuned_mime,
                key=f"download_finetuned_{base_job_id}"
            )
    with col2:
        with open(vanilla_path, "rb") as f:
            st.download_button(
                label="Download Vanilla",
                data=f.read(),
                file_name=os.path.basename(vanilla_path),
                mime=vanilla_mime,
                key=f"download_vanilla_{base_job_id}"
            )

    # Job info
    st.caption(f"Job ID: {base_job_id}")


def render_single_audio(job, label: str):
    """Render a single audio output."""
    from ui.components.output_viewer import ensure_output_local, get_mime_type
    from ui.common import format_file_size

    if not ensure_output_local(job):
        st.warning(f"Output file not found: {job.output_file}")
        return

    output_path = job.output_file
    file_ext = os.path.splitext(output_path)[1].lower()

    st.markdown(f"**{label}**")
    st.audio(output_path)

    # Download button
    with open(output_path, "rb") as f:
        st.download_button(
            label=f"Download {label}",
            data=f.read(),
            file_name=os.path.basename(output_path),
            mime=get_mime_type(file_ext),
            key=f"download_{job.job_id}"
        )

    st.caption(f"Job ID: {job.job_id}")
