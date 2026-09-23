# Shared ComfyUI + Ollama container for Transversal2
# RTX 4090 — Flux image gen + WanVideo animation + gemma3:12b vision
FROM nvidia/cuda:12.4.1-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── System deps (rarely changed, cached first) ──────
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev git wget curl zstd ffmpeg \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# ── PyTorch stack, pinned to ONE CUDA build ──────────
# Never go back to a bare `pip install torch torchvision torchaudio`: the cu129
# index tops out at torch 2.13.0 and torchaudio 2.11.0, so an unpinned `torch`
# resolves from PyPI to a cu130 build while `torchaudio` still comes from cu129.
# ComfyUI then dies at import ("PyTorch has CUDA version 13.0 whereas TorchAudio
# has CUDA version 12.9"), which takes imagen, animate and remove-background down
# with it — the container exits about five seconds into every start.
#
# Version relationships: torchaudio mirrors torch's version (2.11.0 ↔ 2.11.0) and
# torchvision is torch's minor + 15 (2.11 → 0.26). The `+cu129` local tag exists
# only on the PyTorch index, so these pins cannot be satisfied by PyPI.
#
# PIP_CONSTRAINT, not just `-c` on this one command: ComfyUI's own
# requirements.txt lists bare `torch torchvision torchaudio`, so a later
# `pip install -r` would re-resolve and silently upgrade torch again. The env var
# covers every pip invocation in the rest of the build, including those inside a
# custom node's install.py.
RUN printf 'torch==2.11.0+cu129\ntorchvision==0.26.0+cu129\ntorchaudio==2.11.0+cu129\n' \
      > /app/torch-constraints.txt \
 && pip install --extra-index-url https://download.pytorch.org/whl/cu129 \
      torch==2.11.0+cu129 torchvision==0.26.0+cu129 torchaudio==2.11.0+cu129
ENV PIP_CONSTRAINT=/app/torch-constraints.txt

# ── Ollama (large download, rarely changed) ──────────
RUN curl -fsSL https://ollama.com/install.sh | sh

# ── ComfyUI base (rarely changed) ────────────────────
# Clones are pinned to the commits the working image was built from. Everything
# below this layer is invalidated whenever the torch pins change, so leaving a
# `git clone` at HEAD would swap ComfyUI and 15 custom nodes for whatever is on
# master that day — a rebuild that changes two things at once cannot tell you
# which one broke it.
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI \
 && git -C /app/ComfyUI checkout 3c80da7f87ee359b2d06f107cb3c0797079dfbbb
WORKDIR /app/ComfyUI
RUN pip install -r requirements.txt

# ── Custom nodes (frequently changed, at the bottom) ──
WORKDIR /app/ComfyUI/custom_nodes

# XLabs Flux
RUN git clone https://github.com/XLabs-AI/x-flux-comfyui.git x-flux-comfyui \
 && git -C x-flux-comfyui checkout 00328556efc9472410d903639dc9e68a8471f7ac
WORKDIR /app/ComfyUI/custom_nodes/x-flux-comfyui
RUN python3 setup.py

# Custom Scripts
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git ComfyUI-Custom-Scripts \
 && git -C ComfyUI-Custom-Scripts checkout 609f3afaa74b2f88ef9ce8d939626065e3247469

# LoRA Auto Trigger
RUN git clone https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words.git ComfyUI-Lora-Auto-Trigger-Words \
 && git -C ComfyUI-Lora-Auto-Trigger-Words checkout 38e89f95671e1dcdca86c9baf57ac2e1cb2f89e1

# WAS Node Suite
RUN git clone https://github.com/WASASquatch/was-node-suite-comfyui.git was-node-suite-comfyui \
 && git -C was-node-suite-comfyui checkout 9934caa92dd0ddbb533cdfd5645e08c43ec629af
WORKDIR /app/ComfyUI/custom_nodes/was-node-suite-comfyui
RUN pip install -r requirements.txt

# Comfyroll
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes ComfyUI_Comfyroll_CustomNodes \
 && git -C ComfyUI_Comfyroll_CustomNodes checkout d78b780ae43fcf8c6b7c6505e6ffb4584281ceca

# GGUF loader
RUN git clone https://github.com/city96/ComfyUI-GGUF ComfyUI-GGUF \
 && git -C ComfyUI-GGUF checkout 6ea2651e7df66d7585f6ffee804b20e92fb38b8a

# rgthree (switches used in WanVideo workflow)
RUN git clone https://github.com/rgthree/rgthree-comfy.git rgthree-comfy \
 && git -C rgthree-comfy checkout 2c5342a8cb0eaecaabf61435a5f37dd594c510ba
WORKDIR /app/ComfyUI/custom_nodes/rgthree-comfy
RUN pip install -r requirements.txt

# WanVideo nodes (for animation workflow)
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git ComfyUI-WanVideoWrapper \
 && git -C ComfyUI-WanVideoWrapper checkout 088128b224242e110d3906c6750e9a3a348a659b
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper
RUN pip install -r requirements.txt

# RIFE VFI (frame interpolation for animation)
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git ComfyUI-Frame-Interpolation \
 && git -C ComfyUI-Frame-Interpolation checkout 26545cc2dd95bc3d27f056016300673bdeee78f5
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation
RUN python3 install.py

# Video Helper Suite
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git ComfyUI-VideoHelperSuite \
 && git -C ComfyUI-VideoHelperSuite checkout 4d907bee61e92c2e65af3bd6383a4e4d356126d1
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite
RUN pip install -r requirements.txt

# Upscale
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/ssitu/ComfyUI_UltimateSDUpscale.git ComfyUI_UltimateSDUpscale \
 && git -C ComfyUI_UltimateSDUpscale checkout a5547db9e1d07d3318bb21e9e9c474f4c1e9c8df

# mxToolkit (mxSlider nodes for WanVideo workflow)
RUN git clone https://github.com/Smirnov75/ComfyUI-mxToolkit.git ComfyUI-mxToolkit \
 && git -C ComfyUI-mxToolkit checkout 7f7a0e584f12078a1c589645d866ae96bad0cc35

# ComfyUI Essentials (BatchCount+ and other missing core nodes)
RUN git clone https://github.com/cubiq/ComfyUI_essentials.git ComfyUI_essentials \
 && git -C ComfyUI_essentials checkout 9d9f4bedfc9f0321c19faf71855e228c93bd0dc9

# KJNodes (ColorMatch node for WanVideo workflow)
RUN git clone https://github.com/kijai/ComfyUI-KJNodes.git ComfyUI-KJNodes \
 && git -C ComfyUI-KJNodes checkout d3cfe21625e5170126ce06fbfcfe1d88108688c3
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-KJNodes
RUN pip install -r requirements.txt

# White Rabbit nodes (frame rolling/unrolling for seamless loops)
# Sourced from local copy — remote git clone is unreliable
COPY whiterabbit-custom/ /app/ComfyUI/custom_nodes/ComfyUI-WhiteRabbit/
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-WhiteRabbit
RUN pip install torchlanc packaging

# ── Late additions (after all custom nodes to preserve cache) ──
# Easy Use (cleanGpuUsed and other utility nodes)
WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/yolain/ComfyUI-Easy-Use.git ComfyUI-Easy-Use \
 && git -C ComfyUI-Easy-Use checkout 450b1ce4ce43b2280521c87f5fa388a898fb2ad2
WORKDIR /app/ComfyUI/custom_nodes/ComfyUI-Easy-Use
RUN pip install -r requirements.txt

# SageAttention (optimized attention for WanVideo)
RUN pip install sageattention

WORKDIR /app/ComfyUI

# ── Copy workflows and config ────────────────────────
COPY workflows/ /app/imagen/workflows/
COPY vision_prompt.txt /app/imagen/vision_prompt.txt
COPY lora_server.py /app/lora_server.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── Expose ports ─────────────────────────────────────
# ComfyUI: 8188, Ollama: 11434, LoRA: 8191
EXPOSE 8188 11434 8191

ENV COMFYUI_MODEL_DIR=/app/ComfyUI/models
VOLUME ["/app/ComfyUI/models", "/app/ComfyUI/input", "/app/ComfyUI/output", "/app/media"]

ENTRYPOINT ["/app/entrypoint.sh"]
