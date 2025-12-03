"""Real-ESRGAN Video Upscaling Page."""

import streamlit as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.sidebar import render_sidebar
from ui.pages.realesrgan import render_realesrgan_page

st.set_page_config(
    page_title="Real-ESRGAN | GPU Model Runner",
    page_icon="🖼️",
    layout="wide",
)

# Render shared sidebar
render_sidebar()

# Render page content
render_realesrgan_page()
