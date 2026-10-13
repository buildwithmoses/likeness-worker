# likeness-worker

ComfyUI serverless worker for likeness tests: Qwen-Image-Edit 2511, InfiniteTalk (Wan2.1 I2V 480p), Chatterbox TTS.

**How it runs now:** the RunPod endpoint uses the stock public image `runpod/worker-comfyui:5.10.0-base`
with its start command overridden to fetch and run `boot.sh`. The first boot installs ComfyUI v0.39.0, the
custom nodes and every model in `models.txt` onto the network volume (~75 GB); later boots reuse it.

`Dockerfile` + `.github/workflows/build.yml` are the baked-image alternative (needs a working GitHub Actions account).

`inputs/` (your photos/voice) is gitignored and never leaves the Mac.
