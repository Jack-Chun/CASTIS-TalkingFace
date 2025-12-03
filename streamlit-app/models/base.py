"""Abstract base class for model runners."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
import os


@dataclass
class JobConfig:
    """Configuration for a model job."""
    job_id: str
    pod_name: str
    model_id: str
    input_files: Dict[str, str]  # type -> path mapping
    output_file: str
    model_params: Dict[str, Any]


class BaseModelRunner(ABC):
    """Abstract base class for model runners."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Unique identifier for the model."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the model does."""
        pass

    @property
    @abstractmethod
    def model_dir(self) -> str:
        """Path to the model directory."""
        pass

    @property
    @abstractmethod
    def venv_path(self) -> str:
        """Path to the model's virtual environment."""
        pass

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Whether the model is enabled in config."""
        pass

    def is_available(self) -> bool:
        """Check if model directory exists and is accessible."""
        return os.path.isdir(self.model_dir) and self.is_enabled

    @abstractmethod
    def get_yaml_template_path(self) -> str:
        """Return the path to the YAML template file."""
        pass

    @abstractmethod
    def render_input_ui(self) -> Optional[Dict[str, Any]]:
        """
        Render Streamlit UI elements for model inputs.

        Returns:
            Dictionary containing:
            - 'files': Dict[str, uploaded_file] - uploaded files by type
            - 'params': Dict[str, Any] - model parameters
            Or None if inputs are incomplete/invalid.
        """
        pass

    @abstractmethod
    def generate_yaml(self, config: JobConfig) -> str:
        """
        Generate the YAML manifest for kubectl apply.

        Args:
            config: JobConfig containing all job details

        Returns:
            YAML string ready for kubectl apply
        """
        pass

    @abstractmethod
    def get_output_path(self, job_id: str, input_files: Dict[str, str]) -> str:
        """
        Calculate the expected output path for a job.

        Args:
            job_id: Unique job identifier
            input_files: Dictionary of input file paths

        Returns:
            Expected output file path
        """
        pass

    def get_output_type(self) -> str:
        """Return the type of output (video, audio, image)."""
        return "video"  # Default, override in subclasses

    def validate_inputs(self, input_files: Dict[str, str]) -> tuple[bool, str]:
        """
        Validate that all required inputs are present.

        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, ""  # Override in subclasses for specific validation
