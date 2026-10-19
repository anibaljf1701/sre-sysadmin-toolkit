#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/setup.sh"

table_name="${DYNAMODB_TABLE:-ControlHorariosEC2}"
aws_region="${AWS_REGION:-$(aws configure get region)}"
AWS_DEFAULT_REGION="$aws_region" aws dynamodb describe-table \
    --table-name "$table_name" >/dev/null || {
        printf 'ERROR: No se puede consultar la tabla DynamoDB %s en %s. Crea la tabla o revisa dynamodb:DescribeTable.\n' "$table_name" "$aws_region" >&2
        exit 1
    }
AWS_DEFAULT_REGION="$aws_region" aws ec2 describe-instances --max-items 1 >/dev/null || {
    printf 'ERROR: No se puede consultar EC2 en la región %s. Revisa ec2:DescribeInstances.\n' "$aws_region" >&2
    exit 1
}

printf 'Requisitos listos para el scheduler DynamoDB (tabla=%s).\n' "$table_name"