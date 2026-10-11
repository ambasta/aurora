#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ${1:-} == --help ]]; then
    echo 'Usage: scripts/container.sh [command [arguments...]]'
    echo 'Run in the published linux/amd64 image pinned by ci/image; default: bash.'
    echo 'Requires Docker; the public dependency image supports anonymous pulls.'
    exit 0
fi
if [[ ! -f "$root/ci/image" ]]; then
    echo 'BLOCKED: No published image is pinned yet. Complete the toolchain workflow and add its verified digest to ci/image.' >&2
    exit 2
fi
image="$(cat "$root/ci/image")"
if [[ ! "$image" =~ ^ghcr\.io/ambasta/aurora-toolchain@sha256:[0-9a-f]{64}$ ]]; then
    echo 'BLOCKED: ci/image must contain one ghcr.io/ambasta/aurora-toolchain@sha256: digest.' >&2
    exit 2
fi
command -v docker >/dev/null || { echo 'BLOCKED: Docker is required.' >&2; exit 2; }
terminal=(-i)
if [[ -t 0 && -t 1 ]]; then terminal+=(-t); fi
if [[ $# == 0 ]]; then set -- bash; fi
exec docker run --rm --init --platform linux/amd64 \
    --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --env HOME=/tmp \
    --tmpfs /tmp:exec,mode=1777 \
    --mount "type=bind,source=$root,target=/workspace" --workdir /workspace \
    "${terminal[@]}" "$image" "$@"
