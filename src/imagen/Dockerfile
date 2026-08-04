# Shared ComfyUI + Ollama container for Transversal2
# RTX 4090 — Flux image gen + WanVideo animation + gemma3:12b vision
FROM nvidia/cuda:12.4.1-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── System deps ──────────────────────────────────────
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev git wget curl zstd \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu129

# ── ComfyUI ──────────────────────────────────────────
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI
WORKDIR /app/ComfyUI
RUN pip install -r requirements.txt

# Custom nodes
WORKDIR /app/ComfyUI/custom_nodes

# XLabs Flux
RUN git clone https://github.com/XLabs-AI/x-flux-comfyui.git x-flux-comfyui
WORKDIR /app/ComfyUI/custom_nodes/x-flux-comfyui
RUN python3 setup.py

# Custom Scripts
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git ComfyUI-Custom-Scripts

# LoRA Auto Trigger
RUN git clone https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words.git ComfyUI-Lora-Auto-Trigger-Words

# WAS Node Suite
RUN git clone https://github.com/WASASquatch/was-node-suite-comfyui.git was-node-suite-comfyui
WORKDIR /app/ComfyUI/custom_nodes/was-node-suite-comfyui
RUN pip install -r requirements.txt

# Comfyroll
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes ComfyUI_Comfyroll_CustomNodes

# GGUF loader
RUN git clone https://github.com/city96/ComfyUI-GGUF ComfyUI-GGUF

# rgthree (switches used in WanVideo workflow)
RUN git clone https://github.com/rgthree/rgthree-comfy.git rgthree-comfy
WORKDIR /app/ComfyUI/custom_nodes/rgthree-comfy
RUN pip install -r requirements.txt

# WanVideo nodes (for animation workflow)
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git ComfyUI-WanVideoWrapper
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper
RUN pip install -r requirements.txt

# RIFE VFI (frame interpolation for animation)
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git ComfyUI-Frame-Interpolation
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation
RUN python3 install.py

# Video Helper Suite
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git ComfyUI-VideoHelperSuite
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite
RUN pip install -r requirements.txt

# Upscale
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/ssitu/ComfyUI_UltimateSDUpscale.git ComfyUI_UltimateSDUpscale

# White Rabbit nodes (frame rolling/unrolling for seamless loops)
RUN git clone https://github.com/Artificial-Sweetener/comfyui-WhiteRabbit.git ComfyUI-WhiteRabbit
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-WhiteRabbit
RUN pip install -r requirements.txt

WORKDIR /app/ComfyUI

# ── Ollama ───────────────────────────────────────────
RUN curl -fsSL https://ollama.com/install.sh | sh

# ── Copy workflows and config ────────────────────────
COPY workflows/ /app/imagen/workflows/
COPY vision_prompt.txt /app/imagen/vision_prompt.txt
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── Expose ports ─────────────────────────────────────
# ComfyUI: 8188, Ollama: 11434
EXPOSE 8188 11434

ENV COMFYUI_MODEL_DIR=/app/ComfyUI/models
VOLUME ["/app/ComfyUI/models", "/app/ComfyUI/input", "/app/ComfyUI/output", "/app/media"]

ENTRYPOINT ["/app/entrypoint.sh"]
