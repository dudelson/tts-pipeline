#!/usr/bin/env bash

# this script is intended to work with vast.ai's Linux Desktop Container image

echo '========================== TTS PIPELINE BOOTSTRAP START =========================='
echo 'Debug: Info on SSH file ownership:'
ls -l /root/.ssh

# install system-wide deps
echo "installing system-wide deps"
cd "$HOME"
apt -y install portaudio19-dev libsox-dev ffmpeg

# grab fish-speech repo
echo "installing fish audio"
git clone "https://github.com/fishaudio/fish-speech"
cd fish-speech

# grab model weights
echo "installing model weights"
mkdir -p checkpoints/s2-pro
cd checkpoints/s2-pro

BASE="https://huggingface.co/fishaudio/s2-pro/resolve/main"

for f in config.json \
  model-00001-of-00002.safetensors \
  model-00002-of-00002.safetensors \
  model.safetensors.index.json \
  tokenizer.json \
  tokenizer_config.json \
  special_tokens_map.json \
  chat_template.jinja \
  codec.pth; do
  curl -L -C - --retry 5 -o "$f" "$BASE/$f"
done

# copy reference voices
cp -R "$HOME/tts-pipeline/references" "$HOME/fish-speech"

# install server python deps (CUDA version 12.9)
#echo "installing server deps"
#cd "$HOME/fish-speech"
#uv sync --python 3.12 --extra cu129

# start server
echo "starting server"
cd "$HOME/fish-speech"
uv run tools/api_server.py \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --compile \
  --listen 0.0.0.0:8080
