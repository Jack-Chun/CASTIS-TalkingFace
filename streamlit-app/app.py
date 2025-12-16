"""
GPU Model Runner - Streamlit Web Application (Home Page)

A web interface for running deep learning models via Kubernetes GPU pods.
"""

import streamlit as st
import sys
import os

# Add app directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import is_model_available
from job_manager.manager import JobManager
from ui.sidebar import render_sidebar


# Page configuration
st.set_page_config(
    page_title="GPU Model Runner",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Render shared sidebar
render_sidebar()

# Main content - Home Page
st.title("🎬 GPU Model Runner")
st.markdown("""
Welcome to the GPU Model Runner! This application allows you to run
deep learning models on GPU-powered Kubernetes pods.
""")

st.divider()

# Model overview with page links - ordered by pipeline flow
st.header("Available Models")

chatterbox_available = is_model_available("chatterbox")
stableavatar_available = is_model_available("stableavatar")
realesrgan_available = is_model_available("realesrgan")
syncnet_available = is_model_available("syncnet")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🎤 1. Chatterbox TTS")
    if chatterbox_available:
        st.success("Available")
    else:
        st.info("Coming Soon")
    st.markdown("""
    **Text-to-Speech**

    Generate natural-sounding speech from text.

    - Input: Text
    - Output: Audio file (WAV)
    """)
    st.page_link(
        "pages/1_Text_to_Speech.py",
        label="Go to Text to Speech →",
        use_container_width=True
    )

with col2:
    st.subheader("👤 2. StableAvatar")
    if stableavatar_available:
        st.success("Available")
    else:
        st.info("Coming Soon")
    st.markdown("""
    **Talking Face Generation**

    Generate talking face videos from image + audio.

    - Input: Face image + Audio
    - Output: Talking face video
    """)
    st.page_link(
        "pages/2_Video_Generation.py",
        label="Go to Video Generation →",
        use_container_width=True
    )

col3, col4 = st.columns(2)

with col3:
    st.subheader("🖼️ 3. Post Processing")
    if realesrgan_available:
        st.success("Available")
    else:
        st.warning("Not Available")
    st.markdown("""
    **Video/Image Upscaling**

    Upscale videos using Real-ESRGAN (2x/4x).

    - Input: Video file (MP4, MOV, etc.)
    - Output: Upscaled video
    """)
    st.page_link(
        "pages/3_Post_Processing.py",
        label="Go to Post Processing →",
        use_container_width=True
    )

with col4:
    st.subheader("📊 4. Evaluators")
    if syncnet_available:
        st.success("Available")
    else:
        st.warning("Not Available")
    st.markdown("""
    **Quality Evaluation**

    Evaluate output quality (lip sync, TTS).

    - Input: Generated video/audio
    - Output: Quality metrics
    """)
    st.page_link(
        "pages/4_Evaluators.py",
        label="Go to Evaluators →",
        use_container_width=True
    )

st.divider()

# How it works
st.header("How It Works")

st.markdown("""
1. **Select a Model** - Choose from the available models in the sidebar
2. **Upload Input** - Upload your video, image, or text input
3. **Configure Parameters** - Adjust model-specific settings
4. **Submit Job** - Click to create a GPU pod that processes your input
5. **Monitor Progress** - Watch the job status as it runs
6. **Download Output** - Get your processed file when complete
""")

# Architecture diagram
st.subheader("Architecture")
st.markdown("""
```
┌─────────────────────────────────────────────────────────────┐
│  Streamlit Web App (This Interface)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐   │
│  │  Upload  │→ │  kubectl │→ │   Job    │→ │   Output   │   │
│  │   UI     │  │  Client  │  │ Manager  │  │   Viewer   │   │ 
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘   │
│       │             │                                       │
│       ▼             ▼                                       │
│  /data/input/   GPU Pod (Kubernetes)                        │
│                     │                                       │
│                     ▼                                       │
│                /data/output/                                │
└─────────────────────────────────────────────────────────────┘
```
""")

st.divider()

# Recent jobs
st.header("Recent Jobs")

job_manager = JobManager()
all_jobs = job_manager.get_all_jobs()

if all_jobs:
    job_data = []
    for job in all_jobs[:10]:
        job_data.append({
            "ID": job.job_id[:25] + "..." if len(job.job_id) > 25 else job.job_id,
            "Model": job.model_type,
            "Status": job.get_state().value.upper(),
            "Created": job.created_at[:19],
        })

    st.dataframe(
        job_data,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No jobs yet. Select a model from the sidebar to get started!")
