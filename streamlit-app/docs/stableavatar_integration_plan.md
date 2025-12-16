# Integration Plan: StableAvatar & SyncNet

## Task
Integrate two GitHub repos into the existing Streamlit GPU model runner:
- **StableAvatar** (gwangmin-kim/StableAvatar): Talking face video generation
- **SyncNet** (gwangmin-kim/syncnet_python): Lip sync evaluation tool

## Summary of Changes

| Component | Action |
|-----------|--------|
| Clone repos | `/data/StableAvatar`, `/data/syncnet_python` |
| Docker image | Build new `stableavatar:latest` image |
| Virtual envs | `/data/stableavatar-venv`, `/data/syncnet-venv` |
| Config | Enable StableAvatar, add SyncNet model |
| YAML templates | Update `stableavatar.yaml`, create `syncnet.yaml` |
| Model classes | Update `stableavatar.py`, create `syncnet.py` |
| UI pages | Update StableAvatar page, create SyncNet page |
| Streamlit pages | Add `4_SyncNet_Eval.py` |

---

## Phase 1: Clone Repositories

```bash
# Clone StableAvatar
cd /data
git clone https://github.com/gwangmin-kim/StableAvatar.git

# Clone SyncNet
git clone https://github.com/gwangmin-kim/syncnet_python.git
```

---

## Phase 2: Create Virtual Environments

### StableAvatar venv
```bash
/data/python/bin/python3.11 -m venv /data/stableavatar-venv
source /data/stableavatar-venv/bin/activate

# PyTorch 2.6.0 with CUDA 12.4
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
    --index-url https://download.pytorch.org/whl/cu124

# Requirements
pip install -r /data/StableAvatar/requirements.txt

# Flash Attention
pip install flash-attn --no-build-isolation
```

### SyncNet venv
```bash
/data/python/bin/python3.11 -m venv /data/syncnet-venv
source /data/syncnet-venv/bin/activate
pip install -r /data/syncnet_python/requirements.txt

# Download SyncNet model
cd /data/syncnet_python
sh download_model.sh
```

---

## Phase 3: Download StableAvatar Model Weights

```bash
cd /data/StableAvatar
# Download from HuggingFace (FrancisRing/StableAvatar)
# May need to set HF_ENDPOINT for mirror if needed
python -c "from huggingface_hub import snapshot_download; snapshot_download('FrancisRing/StableAvatar', local_dir='./checkpoints')"

# Download LoRA checkpoint from GitHub releases if available
```

---

## Phase 4: Build Docker Image

### Create Dockerfile: `/data/Dockerfile.stableavatar`
```dockerfile
FROM sgs-registry.snucse.org/ws-7l3atgjy3al41/svfr-base:latest

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Note: Python packages are installed in venv on persistent volume
# This image provides the CUDA runtime environment
```

### Build and push:
```bash
cd /data
docker build -f Dockerfile.stableavatar -t sgs-registry.snucse.org/ws-7l3atgjy3al41/stableavatar:latest .
docker push sgs-registry.snucse.org/ws-7l3atgjy3al41/stableavatar:latest
```

---

## Phase 5: Update Configuration

### File: `/data/streamlit-app/config.py`

**Changes:**
1. Enable StableAvatar model
2. Update StableAvatar image to new Docker image
3. Add SyncNet model entry

```python
MODELS = {
    # ... existing models ...
    "stableavatar": {
        "id": "stableavatar",
        "name": "StableAvatar",
        "description": "Talking face video generation (image + audio)",
        "dir": "/data/StableAvatar",
        "venv": "/data/stableavatar-venv",
        "enabled": True,  # CHANGED: Enable
        "template": "stableavatar.yaml",
        "image": "sgs-registry.snucse.org/ws-7l3atgjy3al41/stableavatar:latest",  # CHANGED
        "input_type": "image_audio",
        "output_type": "video",
    },
    "syncnet": {  # NEW
        "id": "syncnet",
        "name": "SyncNet Evaluator",
        "description": "Lip sync quality evaluation for talking face videos",
        "dir": "/data/syncnet_python",
        "venv": "/data/syncnet-venv",
        "enabled": True,
        "template": "syncnet.yaml",
        "image": "sgs-registry.snucse.org/ws-7l3atgjy3al41/stableavatar:latest",
        "input_type": "video",
        "output_type": "evaluation",
    },
}
```

---

## Phase 6: Update YAML Templates

### File: `/data/streamlit-app/k8s/templates/stableavatar.yaml`

**Key command using inference.sh:**
```yaml
command:
  - /bin/bash
  - -c
  - |
    source /data/stableavatar-venv/bin/activate

    echo "=== StableAvatar Talking Face Generation ==="
    echo "Input Image: ${INPUT_IMAGE}"
    echo "Input Audio: ${INPUT_AUDIO}"
    echo "Output Video: ${OUTPUT_VIDEO}"

    OUTPUT_DIR=$(dirname "${OUTPUT_VIDEO}")
    mkdir -p "${OUTPUT_DIR}"

    cd /data/StableAvatar

    # Run inference (uses inference.sh)
    ./inference.sh "${INPUT_IMAGE}" "${INPUT_AUDIO}" "${OUTPUT_DIR}" --steps ${INFERENCE_STEPS}

    # Find generated output and rename
    GENERATED=$(ls -t "${OUTPUT_DIR}"/*.mp4 | head -1)
    if [ -f "${GENERATED}" ] && [ "${GENERATED}" != "${OUTPUT_VIDEO}" ]; then
      mv "${GENERATED}" "${OUTPUT_VIDEO}"
    fi

    # Verify output
    if [ ! -f "${OUTPUT_VIDEO}" ]; then
      echo "ERROR: Output video not created!"
      exit 1
    fi

    echo "=== Generation complete! ==="
    ls -lh "${OUTPUT_VIDEO}"
    echo "DONE"
```

### File: `/data/streamlit-app/k8s/templates/syncnet.yaml` (NEW)

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
  labels:
    app: gpu-model-runner
    model: syncnet
    job-id: ${JOB_ID}
spec:
  restartPolicy: Never
  volumes:
    - name: my-volume
      persistentVolumeClaim:
        claimName: persistent-volume
  terminationGracePeriodSeconds: 1
  containers:
    - name: gpu-worker
      image: ${IMAGE}
      env:
        - name: HOME
          value: /data
        - name: PATH
          value: /data/python/bin:/data/syncnet-venv/bin:/usr/local/bin:/usr/bin:/bin
        - name: CUDA_VISIBLE_DEVICES
          value: "0"
      command:
        - /bin/bash
        - -c
        - |
          source /data/syncnet-venv/bin/activate

          echo "=== SyncNet Lip Sync Evaluation ==="
          echo "Input Video: ${INPUT_VIDEO}"
          echo "Output Dir: ${OUTPUT_DIR}"

          mkdir -p "${OUTPUT_DIR}"

          cd /data/syncnet_python

          # Run evaluation
          ./eval.sh "${INPUT_VIDEO}" "${OUTPUT_DIR}"

          # Copy results to expected location
          echo "=== Evaluation complete! ==="
          cat "${OUTPUT_DIR}/syncnet_summary.json" 2>/dev/null || echo "No summary generated"

          echo "DONE"
      resources:
        limits:
          nvidia.com/gpu: 1
      volumeMounts:
        - name: my-volume
          mountPath: /data
```

---

## Phase 7: Update Model Classes

### File: `/data/streamlit-app/models/stableavatar.py`

**Key changes:**
1. Update UI parameters (remove placeholder options, add inference_steps)
2. Update `generate_yaml()` with correct template variables
3. Add `kubectl cp` support for local execution (like realesrgan.py)

**New parameters:**
- `inference_steps`: Number of inference steps (default: 50)
- `resolution`: Output resolution (480×832, 832×480, 512×512)

### File: `/data/streamlit-app/models/syncnet.py` (NEW)

New model class for SyncNet evaluation:
- Input: Video file upload
- Output: Evaluation results (JSON with sync scores)
- Methods: `render_input_ui()`, `generate_yaml()`, `get_output_path()`

---

## Phase 8: Create SyncNet UI Page

### File: `/data/streamlit-app/ui/pages/syncnet.py` (NEW)

Features:
- Video file uploader
- "Evaluate Lip Sync" button
- Display evaluation results (offset, confidence scores)
- Visual indicator of sync quality (good/medium/poor)

### File: `/data/streamlit-app/pages/4_SyncNet_Eval.py` (NEW)

Streamlit page entry point:
```python
import streamlit as st
from ui.sidebar import render_sidebar
from ui.pages.syncnet import render_syncnet_page

st.set_page_config(page_title="SyncNet Evaluation", page_icon="📊", layout="wide")
render_sidebar()
render_syncnet_page()
```

---

## Phase 9: Update StableAvatar UI Page

### File: `/data/streamlit-app/ui/pages/stableavatar.py`

**Changes:**
1. Remove setup instructions (model will be available)
2. Update parameter UI (inference_steps slider, resolution selector)
3. Add `kubectl cp` support for local execution

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `/data/streamlit-app/config.py` | Modify - enable StableAvatar, add SyncNet |
| `/data/streamlit-app/k8s/templates/stableavatar.yaml` | Modify - real inference command |
| `/data/streamlit-app/k8s/templates/syncnet.yaml` | Create |
| `/data/streamlit-app/models/stableavatar.py` | Modify - update params, add kubectl cp |
| `/data/streamlit-app/models/syncnet.py` | Create |
| `/data/streamlit-app/ui/pages/stableavatar.py` | Modify - update UI |
| `/data/streamlit-app/ui/pages/syncnet.py` | Create |
| `/data/streamlit-app/pages/4_SyncNet_Eval.py` | Create |
| `/data/Dockerfile.stableavatar` | Create |

---

## Execution Order

1. Clone repositories to `/data`
2. Create virtual environments and install dependencies
3. Download model weights
4. Build and push Docker image
5. Update `config.py`
6. Update `stableavatar.yaml` template
7. Create `syncnet.yaml` template
8. Update `models/stableavatar.py`
9. Create `models/syncnet.py`
10. Update `ui/pages/stableavatar.py`
11. Create `ui/pages/syncnet.py`
12. Create `pages/4_SyncNet_Eval.py`
13. Test StableAvatar end-to-end
14. Test SyncNet evaluation

---

## StableAvatar Input/Output

| Parameter | Value |
|-----------|-------|
| Input Image | Face/avatar image (PNG, JPG) |
| Input Audio | Speech audio (WAV, MP3) |
| Output | MP4 video |
| Resolutions | 480×832, 832×480, 512×512 |
| Inference Steps | 50 (default), adjustable |

## SyncNet Input/Output

| Parameter | Value |
|-----------|-------|
| Input Video | Talking face video (MP4) |
| Output | JSON with sync scores, offset values |
| Visualization | Optional video with sync overlay |
