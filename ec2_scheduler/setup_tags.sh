#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/setup.sh"

tag_key="${TAG_KEY:-Environment}"
aws_region="${AWS_REGION:-$(aws configure get region)}"
AWS_DEFAULT_REGION="$aws_region" aws ec2 describe-instances \
    --filters "Name=tag-key,Values=$tag_key" \
    --max-items 1 >/dev/null || {
        printf 'ERROR: No se puede consultar EC2 en la región %s. Revisa ec2:DescribeInstances.\n' "$aws_region" >&2
        exit 1
    }

printf 'Requisitos listos para el scheduler por tags (TAG_KEY=%s).\n' "$tag_key"