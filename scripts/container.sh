#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ${1:-} == --help ]]; then
    echo 'Usage: scripts/container.sh [command [arguments...]]'
    echo 'Run in the published linux/amd64 image pinned by ci/image; default: bash.'
    echo 'Requires Docker or Podman; the public dependency image supports anonymous pulls.'
    echo 'Forwards MESON_BUILD_DIR, BOOTSTRAP_COMPILER, AURORA_BUILD_JOBS and AURORA_TEST_JOBS when set.'
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
if command -v docker >/dev/null; then
    engine=docker
elif command -v podman >/dev/null; then
    engine=podman
else
    echo 'BLOCKED: Docker or Podman is required.' >&2
    exit 2
fi
if ! engine_version="$("$engine" --version 2>&1)"; then
    echo "BLOCKED: Cannot identify $engine: $engine_version" >&2
    exit 2
fi
# docker may be Podman's compatibility command. Rootless Podman needs the host
# identity mapped into its user namespace before it can write the checkout.
case "$engine_version" in
    *[Pp]odman*) identity=(--userns=keep-id) ;;
    *[Dd]ocker*) identity=(--user "$(id -u):$(id -g)") ;;
    *) echo "BLOCKED: Unrecognized $engine implementation: $engine_version" >&2; exit 2 ;;
esac
terminal=(-i)
if [[ -t 0 && -t 1 ]]; then terminal+=(-t); fi
controls=()
for name in MESON_BUILD_DIR BOOTSTRAP_COMPILER AURORA_BUILD_JOBS AURORA_TEST_JOBS; do
    if [[ -v $name ]]; then controls+=(--env "$name=${!name}"); fi
done
if [[ $# == 0 ]]; then set -- bash; fi
exec "$engine" run --rm --init --platform linux/amd64 \
    --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    "${identity[@]}" --env HOME=/tmp "${controls[@]}" \
    --tmpfs /tmp:exec,mode=1777 \
    --mount "type=bind,source=$root,target=/workspace" --workdir /workspace \
    "${terminal[@]}" "$image" "$@"
