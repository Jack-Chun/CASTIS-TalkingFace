"""StableAvatar page UI."""

import streamlit as st
import os

from models.stableavatar import StableAvatarModel
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
from ui.components.output_viewer import render_output_viewer


def render_stableavatar_page():
    """Render the StableAvatar page."""
    st.header("StableAvatar Talking Face")
    st.markdown("Generate talking face videos from an image and audio")

    model = StableAvatarModel()

    # Check if model is available
    if not model.is_available():
        show_model_unavailable_message(model.display_name)
        return

    # Show compact job status for both stableavatar and stableavatar-vanilla
    render_compact_job_status("stableavatar")

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
            button_label = "Generate & Compare" if compare_mode else "Generate Talking Face"

            if st.button(button_label, type="primary", use_container_width=True):
                if compare_mode:
                    submit_comparison_jobs(model, inputs)
                else:
                    submit_stableavatar_job(model, inputs)
        else:
            st.button(
                "Generate Talking Face",
                type="primary",
                use_container_width=True,
                disabled=True,
                help="Upload an image and audio file to enable"
            )

    with col2:
        # Job status for this model (show both stableavatar and stableavatar-vanilla)
        render_job_status_panel(model_filter="stableavatar")

    # Output section
    st.divider()
    render_stableavatar_output_viewer()


def submit_stableavatar_job(model: StableAvatarModel, inputs: dict):
    """Submit a StableAvatar job."""
    try:
        # Generate IDs
        job_id = generate_job_id(model.model_id)
        pod_name = generate_pod_name(model.model_id, job_id)

        # Save uploaded files (returns local_paths, pod_paths)
        image_file = inputs["files"]["image"]
        audio_file = inputs["files"]["audio"]
        local_paths, pod_paths = model.save_uploaded_files(image_file, audio_file, job_id)

        params = inputs["params"]

        # Calculate output path (pod path for YAML)
        output_path = model.get_output_path(job_id, pod_paths)

        # Calculate local output path for tracking
        local_output_path = model.get_local_output_path(job_id)

        # Ensure local output directory exists (for when we copy results back)
        os.makedirs(os.path.dirname(local_output_path), exist_ok=True)

        # Create job config with pod paths
        config = JobConfig(
            job_id=job_id,
            pod_name=pod_name,
            model_id=model.model_id,
            input_files=pod_paths,  # Use pod paths for YAML
            output_file=output_path,
            model_params=params,
        )

        # Generate YAML
        yaml_content = model.generate_yaml(config)

        # Apply to Kubernetes
        k8s = KubernetesClient()
        success, message = k8s.apply_yaml(yaml_content)

        if success:
            # Register job - store local paths for result viewing
            job_manager = JobManager()
            job_manager.create_job(
                job_id=job_id,
                pod_name=pod_name,
                model_type=model.model_id,
                input_files={
                    "image": local_paths["image"],
                    "audio": local_paths["audio"],
                    "image_pod": pod_paths["image"],
                    "audio_pod": pod_paths["audio"],
                },
                output_file=local_output_path,  # Local path for viewing results
                model_params={**params, "output_pod_path": output_path},  # Store pod path too
            )
            show_success_toast(f"Job submitted: {job_id}")
            st.rerun()
        else:
            show_error_toast(f"Failed to create pod: {message}")

    except Exception as e:
        show_error_toast(f"Error submitting job: {str(e)}")


def submit_comparison_jobs(model: StableAvatarModel, inputs: dict):
    """Submit both LoRA and vanilla StableAvatar jobs for comparison."""
    try:
        # Generate a shared base job ID for the comparison pair
        base_job_id = generate_job_id(model.model_id)

        # Save uploaded files once (shared between both jobs)
        image_file = inputs["files"]["image"]
        audio_file = inputs["files"]["audio"]
        local_paths, pod_paths = model.save_uploaded_files(image_file, audio_file, base_job_id)

        params = inputs["params"]
        k8s = KubernetesClient()
        job_manager = JobManager()

        # Job 1: LoRA fine-tuned model
        lora_job_id = f"{base_job_id}-lora"
        lora_pod_name = generate_pod_name(model.model_id, lora_job_id)
        lora_output_path = model.get_output_path(lora_job_id, pod_paths, vanilla=False)
        lora_local_output_path = model.get_local_output_path(lora_job_id, vanilla=False)

        os.makedirs(os.path.dirname(lora_local_output_path), exist_ok=True)

        lora_config = JobConfig(
            job_id=lora_job_id,
            pod_name=lora_pod_name,
            model_id=model.model_id,
            input_files=pod_paths,
            output_file=lora_output_path,
            model_params=params,
        )

        lora_yaml = model.generate_yaml(lora_config, vanilla=False)
        lora_success, lora_message = k8s.apply_yaml(lora_yaml)

        # Job 2: Vanilla model (no LoRA)
        vanilla_job_id = f"{base_job_id}-vanilla"
        vanilla_pod_name = generate_pod_name("stableavatar-vanilla", vanilla_job_id)
        vanilla_output_path = model.get_output_path(vanilla_job_id, pod_paths, vanilla=True)
        vanilla_local_output_path = model.get_local_output_path(vanilla_job_id, vanilla=True)

        os.makedirs(os.path.dirname(vanilla_local_output_path), exist_ok=True)

        vanilla_config = JobConfig(
            job_id=vanilla_job_id,
            pod_name=vanilla_pod_name,
            model_id="stableavatar-vanilla",
            input_files=pod_paths,
            output_file=vanilla_output_path,
            model_params=params,
        )

        vanilla_yaml = model.generate_yaml(vanilla_config, vanilla=True)
        vanilla_success, vanilla_message = k8s.apply_yaml(vanilla_yaml)

        # Register both jobs with comparison link
        if lora_success:
            job_manager.create_job(
                job_id=lora_job_id,
                pod_name=lora_pod_name,
                model_type=model.model_id,
                input_files={
                    "image": local_paths["image"],
                    "audio": local_paths["audio"],
                    "image_pod": pod_paths["image"],
                    "audio_pod": pod_paths["audio"],
                },
                output_file=lora_local_output_path,
                model_params={
                    **params,
                    "output_pod_path": lora_output_path,
                    "comparison_pair": vanilla_job_id,
                    "model_variant": "lora",
                },
            )

        if vanilla_success:
            job_manager.create_job(
                job_id=vanilla_job_id,
                pod_name=vanilla_pod_name,
                model_type="stableavatar-vanilla",
                input_files={
                    "image": local_paths["image"],
                    "audio": local_paths["audio"],
                    "image_pod": pod_paths["image"],
                    "audio_pod": pod_paths["audio"],
                },
                output_file=vanilla_local_output_path,
                model_params={
                    **params,
                    "output_pod_path": vanilla_output_path,
                    "comparison_pair": lora_job_id,
                    "model_variant": "vanilla",
                },
            )

        if lora_success and vanilla_success:
            show_success_toast(f"Comparison jobs submitted: {lora_job_id} & {vanilla_job_id}")
        elif lora_success:
            show_success_toast(f"LoRA job submitted: {lora_job_id}")
            show_error_toast(f"Vanilla job failed: {vanilla_message}")
        elif vanilla_success:
            show_success_toast(f"Vanilla job submitted: {vanilla_job_id}")
            show_error_toast(f"LoRA job failed: {lora_message}")
        else:
            show_error_toast(f"Both jobs failed: LoRA: {lora_message}, Vanilla: {vanilla_message}")

        st.rerun()

    except Exception as e:
        show_error_toast(f"Error submitting comparison jobs: {str(e)}")


def render_stableavatar_output_viewer():
    """Custom output viewer for StableAvatar with comparison support."""
    import base64
    from job_manager.manager import JobState
    from config import IS_POD_ENV, PERSISTENT_POD_NAME
    from ui.components.output_viewer import get_mime_type

    st.subheader("Outputs")

    job_manager = JobManager()

    # Get all stableavatar jobs (both lora and vanilla)
    lora_jobs = job_manager.get_jobs_by_model("stableavatar")
    vanilla_jobs = job_manager.get_jobs_by_model("stableavatar-vanilla")

    completed_lora = [j for j in lora_jobs if j.get_state() == JobState.COMPLETED]
    completed_vanilla = [j for j in vanilla_jobs if j.get_state() == JobState.COMPLETED]

    # Build a map of comparison pairs
    comparison_pairs = {}
    for job in completed_lora:
        pair_id = job.model_params.get("comparison_pair")
        if pair_id:
            comparison_pairs[job.job_id] = pair_id

    # Render comparison outputs first
    rendered_jobs = set()

    for lora_job in completed_lora:
        vanilla_pair_id = lora_job.model_params.get("comparison_pair")
        vanilla_job = next((j for j in completed_vanilla if j.job_id == vanilla_pair_id), None)

        if vanilla_job and vanilla_job.job_id not in rendered_jobs:
            # Both jobs completed - render comparison view
            render_comparison_output(lora_job, vanilla_job)
            rendered_jobs.add(lora_job.job_id)
            rendered_jobs.add(vanilla_job.job_id)
        elif lora_job.job_id not in rendered_jobs:
            # Single LoRA job - render normally
            render_single_output(lora_job, "LoRA")
            rendered_jobs.add(lora_job.job_id)

    # Render remaining vanilla jobs that don't have a pair
    for vanilla_job in completed_vanilla:
        if vanilla_job.job_id not in rendered_jobs:
            render_single_output(vanilla_job, "Vanilla")
            rendered_jobs.add(vanilla_job.job_id)

    if not rendered_jobs:
        st.info("No completed outputs yet. Submit a job to see results here.")


def render_comparison_output(lora_job, vanilla_job):
    """Render side-by-side comparison of LoRA and vanilla outputs."""
    import base64
    from config import IS_POD_ENV, PERSISTENT_POD_NAME
    from ui.components.output_viewer import get_mime_type

    with st.expander(f"**Comparison: {lora_job.job_id.replace('-lora', '')}**", expanded=True):
        lora_path = lora_job.output_file
        vanilla_path = vanilla_job.output_file

        # Try to fetch files from pod if needed
        if not IS_POD_ENV:
            k8s = KubernetesClient()
            for job, path in [(lora_job, lora_path), (vanilla_job, vanilla_path)]:
                if not os.path.exists(path):
                    pod_path = job.model_params.get("output_pod_path")
                    if pod_path:
                        try:
                            os.makedirs(os.path.dirname(path), exist_ok=True)
                            k8s.copy_from_pod(PERSISTENT_POD_NAME, pod_path, path)
                        except Exception:
                            pass

        lora_exists = os.path.exists(lora_path)
        vanilla_exists = os.path.exists(vanilla_path)

        if lora_exists and vanilla_exists:
            try:
                with open(lora_path, "rb") as f:
                    lora_b64 = base64.b64encode(f.read()).decode()
                with open(vanilla_path, "rb") as f:
                    vanilla_b64 = base64.b64encode(f.read()).decode()

                mime = get_mime_type(".mp4")
                comp_id = lora_job.job_id.replace("-", "_")

                html_code = f"""
                <style>
                    .comparison-{comp_id} {{
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
                <div class="comparison-{comp_id}">
                    <div>
                        <button class="control-btn-{comp_id} play-btn-{comp_id}" onclick="playBoth_{comp_id}()">Play Both</button>
                        <button class="control-btn-{comp_id} reset-btn-{comp_id}" onclick="resetBoth_{comp_id}()">Reset</button>
                    </div>
                    <div class="video-row-{comp_id}">
                        <div class="video-container-{comp_id}">
                            <div class="video-label-{comp_id}">Vanilla (No LoRA)</div>
                            <video id="vanilla_{comp_id}" controls>
                                <source src="data:{mime};base64,{vanilla_b64}" type="{mime}">
                            </video>
                        </div>
                        <div class="video-container-{comp_id}">
                            <div class="video-label-{comp_id}">LoRA Fine-tuned</div>
                            <video id="lora_{comp_id}" controls>
                                <source src="data:{mime};base64,{lora_b64}" type="{mime}">
                            </video>
                        </div>
                    </div>
                </div>
                <script>
                    function playBoth_{comp_id}() {{
                        var vanilla = document.getElementById('vanilla_{comp_id}');
                        var lora = document.getElementById('lora_{comp_id}');
                        vanilla.currentTime = 0;
                        lora.currentTime = 0;
                        vanilla.play();
                        lora.play();
                    }}
                    function resetBoth_{comp_id}() {{
                        var vanilla = document.getElementById('vanilla_{comp_id}');
                        var lora = document.getElementById('lora_{comp_id}');
                        vanilla.pause();
                        lora.pause();
                        vanilla.currentTime = 0;
                        lora.currentTime = 0;
                    }}
                </script>
                """
                st.components.v1.html(html_code, height=500, scrolling=True)

                # Download buttons
                col1, col2 = st.columns(2)
                with col1:
                    with open(vanilla_path, "rb") as f:
                        st.download_button(
                            "Download Vanilla",
                            f.read(),
                            file_name=os.path.basename(vanilla_path),
                            mime=mime,
                            key=f"dl_vanilla_{vanilla_job.job_id}"
                        )
                with col2:
                    with open(lora_path, "rb") as f:
                        st.download_button(
                            "Download LoRA",
                            f.read(),
                            file_name=os.path.basename(lora_path),
                            mime=mime,
                            key=f"dl_lora_{lora_job.job_id}"
                        )

            except Exception as e:
                st.error(f"Error loading comparison videos: {e}")
        else:
            if not lora_exists:
                st.warning(f"LoRA output not found: {lora_path}")
            if not vanilla_exists:
                st.warning(f"Vanilla output not found: {vanilla_path}")

        st.caption(f"LoRA Job: {lora_job.job_id} | Vanilla Job: {vanilla_job.job_id}")


def render_single_output(job, variant_label: str):
    """Render a single output video."""
    from config import IS_POD_ENV, PERSISTENT_POD_NAME
    from ui.components.output_viewer import get_mime_type

    with st.expander(f"**{variant_label}: {job.job_id}**", expanded=True):
        output_path = job.output_file

        # Try to fetch from pod if needed
        if not IS_POD_ENV and not os.path.exists(output_path):
            pod_path = job.model_params.get("output_pod_path")
            if pod_path:
                try:
                    k8s = KubernetesClient()
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    k8s.copy_from_pod(PERSISTENT_POD_NAME, pod_path, output_path)
                except Exception:
                    pass

        if os.path.exists(output_path):
            st.video(output_path)
            with open(output_path, "rb") as f:
                st.download_button(
                    f"Download {variant_label}",
                    f.read(),
                    file_name=os.path.basename(output_path),
                    mime=get_mime_type(".mp4"),
                    key=f"dl_{job.job_id}"
                )
        else:
            st.warning(f"Output not found: {output_path}")

        st.caption(f"Job ID: {job.job_id}")
