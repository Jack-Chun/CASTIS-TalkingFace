# CASTIS TalkingFace

Seoul National University Creative Integrated Design - CASTIS Industry-Academia Project

Streamlit web interface for running GPU models on Kubernetes

## Pipeline

```
Text → [Chatterbox TTS] → Audio → [StableAvatar] → Video → [Real-ESRGAN] → Upscaled Video
              ↓                         ↓
       [TTS Evaluator]         [Lip-sync Evaluator]
         (MOS + WER)                (SyncNet)
```

**Features:**
- Text-to-Speech: Convert text to speech with voice cloning (Korean finetuned)
- Video Generation: Image + Audio → Talking face video
- Post Processing: Video upscaling (2x/4x)
- Evaluation: TTS quality (MOS/WER) and lip-sync quality measurement


## Related Repositories

The repositories below are forked from the originals and modified for this project. **You must clone the forked repositories, not the originals** - they contain finetuned checkpoints, evaluation scripts, and shell scripts that are required.

| Repository | Purpose | Original | Added Content |
|------------|---------|----------|---------------|
| [CASTIS-TalkingFace](https://github.com/Jack-Chun/CASTIS-TalkingFace) | Streamlit Web App | - | - |
| [gwangmin-kim/StableAvatar](https://github.com/gwangmin-kim/StableAvatar) | Video Generation | [Francis-Rings/StableAvatar](https://github.com/Francis-Rings/StableAvatar) | LoRA checkpoint, inference.sh, preprocessing |
| [gwangmin-kim/syncnet_python](https://github.com/gwangmin-kim/syncnet_python) | Lip-sync Evaluation | [joonson/syncnet_python](https://github.com/joonson/syncnet_python) | eval.sh, JSON output |
| [jungbin128/Chatterbox_Finetuning](https://github.com/jungbin128/Chatterbox_Finetuning) | TTS Inference | [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) | Korean finetuned checkpoint (final.pt), inference_tts.py |
| [jungbin128/Chatterbox_Evaluation](https://github.com/jungbin128/Chatterbox_Evaluation) | TTS Evaluation | - | MOS (WV-MOS) + WER (Whisper) evaluation |


## Part A: Infrastructure Setup

Guide for setting up your own environment.

### Kubernetes Compatibility

Our team developed this on [SNU SGS (GPU Service 3.0)](https://sgs-docs.snucse.org/), but the code only uses standard Kubernetes APIs. No SGS-specific features were used, so it runs on any Kubernetes cluster.

- Standard resources: Pod, PVC, etc.
- GPU allocation: `nvidia.com/gpu` (NVIDIA device plugin standard)
- Volume: Standard PVC mount

References: [Kubernetes Docs](https://kubernetes.io/docs/home/), [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/overview.html)

### Requirements

- Kubernetes cluster with GPU nodes
- NVIDIA GPU (A100 40GB recommended, minimum 24GB)
- Persistent Volume 500GB+
- Docker Registry access

### Two-Layer Architecture

We separate the Docker image from the Persistent Volume.

**Layer 1 - Docker Image:**
System packages only (CUDA, ffmpeg, build tools, etc.)

**Layer 2 - Persistent Volume (/data/):**
Python, virtual environments, models, and code are all stored here
```
/data/
├── python/bin/python3.11       # Standalone Python
├── stableavatar-venv/          # StableAvatar venv
├── realesrgan-venv/            # Real-ESRGAN venv
├── syncnet-venv/               # SyncNet venv
├── chatterbox-venv/            # Chatterbox TTS venv
├── chatterbox-eval-venv/       # Chatterbox Evaluation venv
├── streamlit-venv/             # Streamlit app venv
├── StableAvatar/               # Video generation model
├── Real-ESRGAN/                # Upscaling model
├── syncnet_python/             # Lip-sync evaluator
├── Chatterbox_Finetuning/      # TTS model (Korean finetuned)
├── Chatterbox_Evaluation/      # TTS evaluator (MOS + WER)
└── streamlit-app/              # Web app
```

This way, the environment persists across pod restarts and keeps the image size small.

### Setup Steps

Follow these steps to set up a new environment.

#### Step 1: Build Docker Image

Use [NVIDIA CUDA image](https://hub.docker.com/r/nvidia/cuda) as the base:

```dockerfile
# Use 'devel' variant if you need to compile flash_attn (includes nvcc)
# Use 'runtime' variant for smaller image if flash_attn is not needed
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

RUN apt-get update && apt-get install -y \
    ffmpeg git wget curl vim \
    build-essential cmake libboost-all-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data
```

> Note: `devel` image (~4GB) includes nvcc compiler needed for building CUDA packages like flash_attn. If you don't need flash_attn, use `runtime` (~1GB) for a smaller image.

```bash
docker build -t YOUR_REGISTRY/YOUR_IMAGE:latest .
docker push YOUR_REGISTRY/YOUR_IMAGE:latest
```

#### Step 2: Create PVC

```yaml
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: YOUR_PVC_NAME
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 500Gi
```

```bash
kubectl apply -f pvc.yaml
```

#### Step 3: Create Shell Pod and Connect

```yaml
# shell-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: YOUR_POD_NAME
spec:
  restartPolicy: Never
  containers:
    - name: shell
      image: YOUR_REGISTRY/YOUR_IMAGE:latest
      command: ["sleep", "infinity"]
      volumeMounts:
        - name: data
          mountPath: /data
      resources:
        limits:
          nvidia.com/gpu: 1
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: YOUR_PVC_NAME
```

```bash
kubectl apply -f shell-pod.yaml
kubectl exec -it YOUR_POD_NAME -- /bin/bash
```

#### Step 4: Install Python

Install Python inside the PVC, not using system Python. This ensures it persists across pod restarts.

Download from [Python Official](https://www.python.org/downloads/):

```bash
cd /data
wget https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tgz
tar xzf Python-3.11.0.tgz
cd Python-3.11.0
./configure --prefix=/data/python --enable-optimizations
make -j$(nproc)
make install
rm -rf /data/Python-3.11.0*
```

#### Step 5: Clone Repositories

Clone all required repositories to `/data/`:

```bash
cd /data

# Streamlit web app
git clone https://github.com/Jack-Chun/CASTIS-TalkingFace.git streamlit-app

# StableAvatar (forked - contains LoRA and inference.sh)
git clone https://github.com/gwangmin-kim/StableAvatar.git

# SyncNet (forked - contains eval.sh)
git clone https://github.com/gwangmin-kim/syncnet_python.git

# Chatterbox TTS (forked - contains Korean finetuned checkpoint)
git clone https://github.com/jungbin128/Chatterbox_Finetuning.git

# Chatterbox Evaluation (MOS + WER evaluation)
git clone https://github.com/jungbin128/Chatterbox_Evaluation.git

# Real-ESRGAN (original repo)
git clone https://github.com/xinntao/Real-ESRGAN.git
```

#### Step 6: Create Virtual Environments and Install Packages

Create a separate venv for each model:

```bash
# StableAvatar
/data/python/bin/python3.11 -m venv /data/stableavatar-venv
source /data/stableavatar-venv/bin/activate
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
pip install -r /data/StableAvatar/requirements.txt
pip install flash_attn  # Only installs on GPU environment
deactivate

# Real-ESRGAN
/data/python/bin/python3.11 -m venv /data/realesrgan-venv
source /data/realesrgan-venv/bin/activate
pip install basicsr facexlib gfpgan
pip install -r /data/Real-ESRGAN/requirements.txt
cd /data/Real-ESRGAN && python setup.py develop && cd /data
deactivate

# SyncNet
/data/python/bin/python3.11 -m venv /data/syncnet-venv
source /data/syncnet-venv/bin/activate
pip install -r /data/syncnet_python/requirements.txt
deactivate

# Chatterbox TTS
/data/python/bin/python3.11 -m venv /data/chatterbox-venv
source /data/chatterbox-venv/bin/activate
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
cd /data/Chatterbox_Finetuning
pip install -e .
deactivate

# Chatterbox Evaluation
/data/python/bin/python3.11 -m venv /data/chatterbox-eval-venv
source /data/chatterbox-eval-venv/bin/activate
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
pip install -r /data/Chatterbox_Evaluation/requirements.txt
deactivate

# Streamlit app
/data/python/bin/python3.11 -m venv /data/streamlit-venv
source /data/streamlit-venv/bin/activate
pip install -r /data/streamlit-app/requirements.txt
deactivate
```

Check [PyTorch Official](https://pytorch.org/get-started/locally/) for the correct version matching your CUDA.

#### Step 7: Download Model Checkpoints

**StableAvatar checkpoints:**

Download from [HuggingFace](https://huggingface.co/FrancisRing/StableAvatar):
```bash
source /data/stableavatar-venv/bin/activate
pip install "huggingface_hub[cli]"
huggingface-cli download FrancisRing/StableAvatar --local-dir /data/StableAvatar/checkpoints
deactivate
```

Download LoRA checkpoint from [GitHub Releases](https://github.com/gwangmin-kim/StableAvatar/releases):
```bash
curl -L https://github.com/gwangmin-kim/StableAvatar/releases/download/lora-s16000/lora-checkpoint-16000.pt \
  -o /data/StableAvatar/checkpoints/lora.pt
```

**SyncNet model:**
```bash
cd /data/syncnet_python
sh download_model.sh
```

**Chatterbox TTS checkpoint:**

The Korean finetuned checkpoint (`final.pt`) is already included in the repository:
```bash
ls /data/Chatterbox_Finetuning/final.pt
```

### Configuration Files

After setup, you need to modify a few configuration files.

#### 1. Docker Image Address

In `streamlit-app/config.py`, change the image address:

```python
# Original (SNU SGS)
"image": "sgs-registry.snucse.org/ws-7l3atgjy3al41/svfr-base:latest"

# Change to
"image": "YOUR_REGISTRY/YOUR_IMAGE:latest"
```

This appears on lines 73, 85, 97, 109, and 121.

#### 2. Pod Name

In `streamlit-app/config.py` line 51:

```python
PERSISTENT_POD_NAME = "YOUR_POD_NAME"
```

#### 3. PVC Name

In `streamlit-app/k8s/templates/` YAML files:

```yaml
persistentVolumeClaim:
  claimName: YOUR_PVC_NAME
```

Update all files: `realesrgan.yaml`, `stableavatar.yaml`, `syncnet.yaml`, `chatterbox.yaml`, `chatterbox_eval.yaml`

#### Verification

After completing the setup, verify everything works:

```bash
# Check Python installation
/data/python/bin/python3.11 --version

# Check virtual environments
source /data/stableavatar-venv/bin/activate && python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')" && deactivate

# Test Chatterbox TTS
cd /data/Chatterbox_Finetuning
source /data/chatterbox-venv/bin/activate
python inference_tts.py --text "안녕하세요" --output /data/output/test.wav
deactivate

# Test StableAvatar (quick check with 1 step)
cd /data/StableAvatar
source /data/stableavatar-venv/bin/activate
./inference.sh /data/input/images/test.jpg /data/input/audio/test.wav /data/output/test --steps 1
deactivate

# Run Streamlit web app
cd /data/streamlit-app
source /data/streamlit-venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

## Part B: Model Installation and Usage

How to run each model from CLI. Can be used without the Streamlit web app.

### 1. Chatterbox TTS

Text → Speech generation with voice cloning (Korean finetuned).

**Repository:** [jungbin128/Chatterbox_Finetuning](https://github.com/jungbin128/Chatterbox_Finetuning)
- Original: [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox)
- **Added:** Korean finetuned checkpoint (`final.pt`), `inference_tts.py` CLI script

**Installation:**
```bash
git clone https://github.com/jungbin128/Chatterbox_Finetuning.git
cd Chatterbox_Finetuning
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
pip install -e .
```

**Run:**
```bash
# Basic TTS (Korean)
python inference_tts.py --text "안녕하세요, 반갑습니다." --output output.wav

# With voice cloning
python inference_tts.py --text "Your text here" --voice-prompt voice_sample.wav --output output.wav

# With custom parameters
python inference_tts.py \
  --text "Text to synthesize" \
  --voice-prompt prompt.wav \
  --output output.wav \
  --language Korean \
  --exaggeration 0.5 \
  --cfg-weight 0.5
```

**Parameters:**
- `--text`: Text to synthesize
- `--text-file`: Path to text file (alternative to --text)
- `--voice-prompt`: Voice sample for cloning (optional, uses default if not provided)
- `--output`: Output WAV file path
- `--language`: Language (Korean, English, Japanese, Chinese)
- `--exaggeration`: Speech expressiveness 0.0-1.0 (default: 0.5)
- `--cfg-weight`: Classifier-free guidance weight 0.0-1.0 (default: 0.5)
- `--checkpoint`: Custom checkpoint path (default: final.pt)

### 2. TTS Evaluator (Chatterbox Evaluation)

Evaluate TTS output quality using MOS and WER metrics.

**Repository:** [jungbin128/Chatterbox_Evaluation](https://github.com/jungbin128/Chatterbox_Evaluation)

**Metrics:**
- **MOS (Mean Opinion Score):** Predicted using WV-MOS model (1-5 scale, higher is better)
- **WER (Word Error Rate):** Calculated via Whisper ASR (0-100%, lower is better)

**Installation:**
```bash
git clone https://github.com/jungbin128/Chatterbox_Evaluation.git
cd Chatterbox_Evaluation
pip install -r requirements.txt
```

**Prepare Input:**

Create a directory with audio files and matching reference text files:
```
audio_dir/
├── sample1.wav
├── sample1.txt    # Reference text for sample1.wav
├── sample2.wav
├── sample2.txt
└── ...
```

**Run:**
```bash
python eval_tts_folder.py \
  --audio_dir /path/to/audio_files \
  --whisper_model base \
  --language Korean
```

**Parameters:**
- `--audio_dir`: Directory containing audio files and reference text files
- `--whisper_model`: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
- `--language`: Language hint for Whisper (Korean, English, Japanese, Chinese, Auto)
- `--cpu_mos`: Run MOS calculation on CPU (optional)

**Output:**
Results are saved to `tts_eval_results.csv`:
```csv
filename,reference,whisper_transcript,mos,wer
sample1.wav,"안녕하세요","안녕하세요",4.2,0.0
sample2.wav,"반갑습니다","반갑습니다",3.8,0.0
```

### 3. StableAvatar

Image + Audio → Talking face video generation.

**Repository:** [gwangmin-kim/StableAvatar](https://github.com/gwangmin-kim/StableAvatar)
- Original: [Francis-Rings/StableAvatar](https://github.com/Francis-Rings/StableAvatar)
- **Added:** LoRA checkpoint (GitHub Releases), `inference.sh` script, preprocessing improvements

**Installation:**
```bash
git clone https://github.com/gwangmin-kim/StableAvatar.git
cd StableAvatar
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
pip install flash_attn  # Requires GPU to install
```

**Download Models:**

From [HuggingFace](https://huggingface.co/FrancisRing/StableAvatar):
```bash
pip install "huggingface_hub[cli]"
huggingface-cli download FrancisRing/StableAvatar --local-dir ./checkpoints
```

LoRA checkpoint from [GitHub Releases](https://github.com/gwangmin-kim/StableAvatar/releases):
```bash
curl -L https://github.com/gwangmin-kim/StableAvatar/releases/download/lora-s16000/lora-checkpoint-16000.pt \
  -o ./checkpoints/lora.pt
```

**Run:**
```bash
./inference.sh <image> <audio> <output_dir> [--steps N]
# Output: <output_dir>/video.mp4
# --steps: Sampling steps (default 50)
```

Supported resolutions: 480x832, 832x480, 512x512

### 4. SyncNet (Lip-sync Evaluator)

Evaluate lip-sync quality of generated videos.

**Repository:** [gwangmin-kim/syncnet_python](https://github.com/gwangmin-kim/syncnet_python)
- Original: [joonson/syncnet_python](https://github.com/joonson/syncnet_python)
- **Added:** `eval.sh` one-click evaluation script, JSON output (`syncnet_summary.json`)

**Installation:**
```bash
git clone https://github.com/gwangmin-kim/syncnet_python.git
cd syncnet_python
apt install ffmpeg
pip install -r requirements.txt
sh download_model.sh
```

**Run:**
```bash
./eval.sh <video> <output_dir>
# Output: <output_dir>/pywork/evaluation_syncnet/syncnet_summary.json
```

**Interpreting Results:**
```json
{
  "offset": 0.0,      // Closer to 0 is better
  "confidence": 5.0   // Higher is better
}
```

### 5. Real-ESRGAN

Video/Image upscaling.

**Repository:** [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)

**Installation:**
```bash
git clone https://github.com/xinntao/Real-ESRGAN.git
cd Real-ESRGAN
pip install basicsr facexlib gfpgan
pip install -r requirements.txt
python setup.py develop
```

**Run:**
```bash
# 4x upscale
python inference_realesrgan_video.py -i input.mp4 -o output/ -n RealESRGAN_x4plus

# 2x upscale
python inference_realesrgan_video.py -i input.mp4 -o output/ -n RealESRGAN_x2plus
```

Options:
- `-n`: Model selection (RealESRGAN_x4plus, RealESRGAN_x2plus, etc.)
- `--face_enhance`: Face enhancement (GFPGAN)
- `--tile`: Tile size for low memory situations

## Streamlit Web App

Web UI for easy model usage.

```bash
cd /data/streamlit-app
source /data/streamlit-venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

**Pages:**
1. Text to Speech - Text → Audio (with voice cloning, finetuned vs vanilla comparison)
2. Video Generation - Image + Audio → Video
3. Post Processing - Upscaling
4. Evaluators - TTS quality (MOS/WER) and lip-sync evaluation

## Setup Checklist

Checklist for environment setup:

- [ ] Build and push Docker image
- [ ] Create PVC
- [ ] Install Python (/data/python/)
- [ ] Clone repositories (6 repos)
- [ ] Create virtual environments:
  - [ ] stableavatar-venv
  - [ ] realesrgan-venv
  - [ ] syncnet-venv
  - [ ] chatterbox-venv
  - [ ] chatterbox-eval-venv
  - [ ] streamlit-venv
- [ ] Download model checkpoints:
  - [ ] StableAvatar (HuggingFace + LoRA)
  - [ ] SyncNet
  - [ ] Chatterbox (included in repo)
- [ ] Modify config.py (image address, Pod name)
- [ ] Modify YAML files (PVC name)
- [ ] Verify GPU pod works correctly


## References

- [SNU SGS Docs](https://sgs-docs.snucse.org/) - Environment where we developed
- [Kubernetes Docs](https://kubernetes.io/docs/home/)
- [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/overview.html)
- [PyTorch Installation](https://pytorch.org/get-started/locally/)
- [HuggingFace Hub](https://huggingface.co/docs/huggingface_hub/index)