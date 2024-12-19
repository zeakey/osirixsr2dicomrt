#!/bin/bash
set -ex

source_dir="/Users/kzhao/Documents/micro-us/mus_lesion"
target_dir="/Users/kzhao/Documents/micro-us/converted"

for subfolder in $(find "$source_dir" -mindepth 1 -maxdepth 1 -type d); do
    subfolder_name=$(basename "$subfolder")
    target="$target_dir/$subfolder_name"
    if [ ! -d "$target" ]; then
        python csv2rt.py "$subfolder" --save-to "$target"
    fi
done
