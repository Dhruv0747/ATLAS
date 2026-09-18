#!/usr/bin/env bash
# Runtime/model installation only. No service restart, ROS command or sudo.
set -euo pipefail
atlas_runtime="$HOME/.local/share/atlas-llm"
atlas_source="$atlas_runtime/llama.cpp"
atlas_model_dir="$atlas_runtime/models"
atlas_commit=b29c606e28a01b1bc8c1351026a0fa6e616bf6c4
atlas_revision=90862c4b9d2787eaed51d12237eafdfe7c5f6077
atlas_sha=061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a
atlas_q8="$atlas_model_dir/Qwen3-1.7B-Q8_0.gguf"
atlas_q4="$atlas_model_dir/Qwen3-1.7B-Q4_K_M.gguf"
mkdir -p "$atlas_model_dir"
if [[ ! -d "$atlas_source" ]]; then
  git clone --depth 1 --branch v0.4.1 https://github.com/ggml-org/llama.cpp.git "$atlas_source"
fi
[[ "$(git -C "$atlas_source" rev-parse HEAD)" == "$atlas_commit" ]] || {
  echo 'Runtime checkout differs from the validated revision; refusing to replace it.' >&2
  exit 1
}
[[ -z "$(git -C "$atlas_source" status --porcelain)" ]] || {
  echo 'Runtime checkout has local changes; refusing to build an unverified tree.' >&2
  exit 1
}
if [[ ! -f "$atlas_q8" ]]; then
  curl -fL --retry 3 --connect-timeout 15 --max-time 1200 \
    "https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/$atlas_revision/Qwen3-1.7B-Q8_0.gguf" \
    -o "$atlas_q8.part"
  printf '%s  %s\n' "$atlas_sha" "$atlas_q8.part" | sha256sum --check
  mv -- "$atlas_q8.part" "$atlas_q8"
fi
printf '%s  %s\n' "$atlas_sha" "$atlas_q8" | sha256sum --check
nice -n 15 cmake -S "$atlas_source" -B "$atlas_source/build" \
  -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES=87 -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF \
  -DCMAKE_BUILD_TYPE=Release
nice -n 15 cmake --build "$atlas_source/build" --target llama-server llama-quantize -j 2
if [[ ! -f "$atlas_q4" ]]; then
  nice -n 15 "$atlas_source/build/bin/llama-quantize" --allow-requantize \
    "$atlas_q8" "$atlas_q4.part" Q4_K_M 2
  mv -- "$atlas_q4.part" "$atlas_q4"
fi
sha256sum "$atlas_q4"
echo 'Runtime prepared. Services were NOT enabled or restarted. Follow docs/LOCAL_LLM_2026-09-18.md.'
