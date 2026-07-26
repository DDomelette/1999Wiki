#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$#" -eq 2 ]] || {
    printf 'tag-guard: expected Backend and Frontend tag references\n' >&2
    exit 2
}

for image in "$@"; do
    [[ "$image" =~ ^ghcr\.io/ddomelette/1999wiki-(backend|frontend):sha-[0-9a-f]{7}$ ]] || {
        printf 'tag-guard: invalid target tag reference: %s\n' "$image" >&2
        exit 2
    }
    output_file="$(mktemp)"
    trap 'rm -f -- "$output_file"' EXIT
    if docker buildx imagetools inspect "$image" >"$output_file" 2>&1; then
        printf 'tag-guard: target tag already exists: %s\n' "$image" >&2
        exit 1
    fi
    if ! grep -Eiq '(manifest unknown|not found|no such manifest)' "$output_file"; then
        printf 'tag-guard: could not prove target tag is absent: %s\n' "$image" >&2
        exit 1
    fi
    rm -f -- "$output_file"
    trap - EXIT
done
