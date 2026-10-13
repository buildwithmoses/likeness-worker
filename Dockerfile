# Likeness-test worker: Qwen-Image-Edit, InfiniteTalk, Chatterbox on ComfyUI.
# Models are NOT baked in. They live on the network volume and seed-models.sh
# fetches whatever is missing on boot, so the first worker pays the download once.
FROM runpod/worker-comfyui:5.10.0-base

# ComfyUI-Chatterbox needs ComfyUI >= 0.37 (V3 node API); the base ships older.
ARG COMFYUI_TAG=v0.39.0
RUN cd /comfyui \
    && git fetch --depth 1 origin tag ${COMFYUI_TAG} \
    && git checkout -q ${COMFYUI_TAG} \
    && uv pip install -r /comfyui/requirements.txt \
    && uv pip install "transformers>=4.50.3,<5" "huggingface-hub<1.0"

# Custom nodes: InfiniteTalk (WanVideoWrapper), Set/Get + resize (KJNodes),
# mp4 out (VideoHelperSuite), vocal separation (MelBandRoFormer), TTS (Chatterbox).
RUN cd /comfyui/custom_nodes \
    && git clone --depth 1 https://github.com/kijai/ComfyUI-WanVideoWrapper.git \
    && git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git \
    && git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git \
    && git clone --depth 1 https://github.com/kijai/ComfyUI-MelBandRoFormer.git \
    && git clone --depth 1 https://github.com/wildminder/ComfyUI-Chatterbox.git \
    && for r in /comfyui/custom_nodes/*/requirements.txt; do uv pip install -r "$r"; done \
    && uv pip install "transformers>=4.50.3,<5" "huggingface-hub<1.0" hf_transfer \
    && apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Fail the build, not the worker, if a node pack breaks the import graph.
RUN cd /comfyui && timeout 300 python main.py --quick-test-for-ci --cpu

COPY models.txt /models.txt
COPY seed-models.sh /seed-models.sh
RUN chmod +x /seed-models.sh

CMD ["/seed-models.sh"]
