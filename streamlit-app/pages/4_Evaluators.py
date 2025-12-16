"""Evaluators page entry point - contains multiple evaluation tools."""

import streamlit as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.sidebar import render_sidebar
from ui.pages.evaluators import render_evaluators_page


st.set_page_config(
    page_title="Evaluators",
    page_icon="📊",
    layout="wide"
)

render_sidebar()
render_evaluators_page()
