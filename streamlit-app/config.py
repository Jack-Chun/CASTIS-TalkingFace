"""Configuration for the GPU Model Runner Streamlit App."""

import os

# Paths
DATA_DIR = "/data"
INPUT_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
TEMP_DIR = os.path.join(DATA_DIR, "tmp", "streamlit")
APP_DIR = os.path.join(DATA_DIR, "streamlit-app")
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

# kubectl settings
KUBECTL_PATH = os.path.join(DATA_DIR, "bin", "kubectl")

# Model registry
MODELS = {
    "realesrgan": {
        "id": "realesrgan",
        "name": "Real-ESRGAN",
        "description": "Video/image upscaling (4x super-resolution)",
        "dir": os.path.join(DATA_DIR, "Real-ESRGAN"),
        "venv": os.path.join(DATA_DIR, "realesrgan-venv"),
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
        "dir": os.path.join(DATA_DIR, "Chatterbox"),
        "venv": os.path.join(DATA_DIR, "chatterbox-venv"),
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
        "dir": os.path.join(DATA_DIR, "StableAvatar"),
        "venv": os.path.join(DATA_DIR, "stableavatar-venv"),
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
    """Check if a model is both enabled and has its directory present."""
    config = MODELS.get(model_id)
    if not config:
        return False
    if not config["enabled"]:
        return False
    return os.path.isdir(config["dir"])
