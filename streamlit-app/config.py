"""Configuration for the GPU Model Runner Streamlit App."""

import os
import shutil

# Auto-detect environment: pod vs local
# Check if this config file itself is located under /data/ (pod environment)
# This avoids issues with /data existing as a read-only system dir on macOS
IS_POD_ENV = os.path.abspath(__file__).startswith("/data/")

if IS_POD_ENV:
    # Running inside the Kubernetes pod
    DATA_DIR = "/data"
    APP_DIR = os.path.join(DATA_DIR, "streamlit-app")
else:
    # Running locally - use relative paths from the app directory
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.dirname(APP_DIR)  # Parent of streamlit-app

# Paths
INPUT_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
TEMP_DIR = os.path.join(DATA_DIR, "tmp", "streamlit")
YAML_TEMPLATE_DIR = os.path.join(APP_DIR, "k8s", "templates")

# Input subdirectories
INPUT_VIDEOS_DIR = os.path.join(INPUT_DIR, "videos")
INPUT_TEXTS_DIR = os.path.join(INPUT_DIR, "texts")
INPUT_IMAGES_DIR = os.path.join(INPUT_DIR, "images")
INPUT_AUDIO_DIR = os.path.join(INPUT_DIR, "audio")

# Output subdirectories
OUTPUT_UPSCALED_DIR = os.path.join(OUTPUT_DIR, "upscaled")
OUTPUT_AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
OUTPUT_TALKING_FACE_DIR = os.path.join(OUTPUT_DIR, "talking_face")

# Job settings
POLL_INTERVAL_SECONDS = 5
MAX_POLL_ATTEMPTS = 720  # 1 hour max
JOBS_FILE = os.path.join(APP_DIR, "jobs.json")

# kubectl settings - find kubectl in PATH or use pod path
KUBECTL_PATH = shutil.which("kubectl") or os.path.join(DATA_DIR, "bin", "kubectl")

# Model registry
# Note: Model directories point to /data paths on the pod where models run
# Local machine doesn't need these directories - it just submits jobs to the cluster
MODELS = {
    "realesrgan": {
        "id": "realesrgan",
        "name": "Real-ESRGAN",
        "description": "Video/image upscaling (4x super-resolution)",
        "dir": "/data/Real-ESRGAN",  # Always /data path (where GPU pod runs)
        "venv": "/data/realesrgan-venv",
        "enabled": True,
        "template": "realesrgan.yaml",
        "image": "sgs-registry.snucse.org/ws-7l3atgjy3al41/svfr-base:latest",
        "input_type": "video",
        "output_type": "video",
    },
    "chatterbox": {
        "id": "chatterbox",
        "name": "Chatterbox TTS",
        "description": "Text-to-Speech generation",
        "dir": "/data/Chatterbox",
        "venv": "/data/chatterbox-venv",
        "enabled": False,  # Disabled until repo is added
        "template": "chatterbox.yaml",
        "image": "TBD",
        "input_type": "text",
        "output_type": "audio",
    },
    "stableavatar": {
        "id": "stableavatar",
        "name": "StableAvatar",
        "description": "Talking face video generation (image + audio)",
        "dir": "/data/StableAvatar",
        "venv": "/data/stableavatar-venv",
        "enabled": False,  # Disabled until repo is added
        "template": "stableavatar.yaml",
        "image": "TBD",
        "input_type": "image_audio",
        "output_type": "video",
    },
}


def get_enabled_models():
    """Return list of enabled model IDs."""
    return [model_id for model_id, config in MODELS.items() if config["enabled"]]


def get_model_config(model_id: str) -> dict:
    """Get configuration for a specific model."""
    return MODELS.get(model_id)


def is_model_available(model_id: str) -> bool:
    """
    Check if a model is enabled.

    Note: When running locally, we can't check if the model directory exists
    on the pod, so we just check if it's enabled in config.
    """
    config = MODELS.get(model_id)
    if not config:
        return False
    if not config["enabled"]:
        return False
    # When running locally, assume model is available if enabled
    if not IS_POD_ENV:
        return True
    return os.path.isdir(config["dir"])
