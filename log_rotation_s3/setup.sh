#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

for command_name in bash find tar du aws; do
    command -v "$command_name" >/dev/null 2>&1 || fail "Falta el comando requerido: $command_name"
done

(( BASH_VERSINFO[0] >= 4 )) || fail "Se requiere Bash 4 o superior."

log_dir="${LOG_DIR:-/var/log/myapp}"
[[ -d "$log_dir" ]] || fail "LOG_DIR no existe: $log_dir. Configura LOG_DIR antes de ejecutar setup."
[[ -w "$log_dir" ]] || fail "No hay permisos de escritura en LOG_DIR: $log_dir"

s3_bucket="${S3_BUCKET:-}"
[[ "$s3_bucket" == s3://* ]] || fail "Configura S3_BUCKET con un destino s3://bucket/prefix válido."

aws_region="${AWS_REGION:-$(aws configure get region)}"
[[ -n "$aws_region" ]] || fail "Configura AWS_REGION o la región predeterminada de AWS CLI."
export AWS_DEFAULT_REGION="$aws_region"

aws sts get-caller-identity >/dev/null || fail "AWS CLI no tiene credenciales válidas. Ejecuta aws configure o configura un rol/perfil."
bucket_name="${s3_bucket#s3://}"
bucket_name="${bucket_name%%/*}"
aws s3api head-bucket --bucket "$bucket_name" >/dev/null || fail "No se puede acceder al bucket S3: $bucket_name"

[[ -f "$script_dir/log_rotation_s3.sh" ]] || fail "No se encontró log_rotation_s3.sh junto al setup."

printf 'Requisitos listos para rotación de logs.\n'
printf 'Directorio: %s\nBucket: %s\nRegión: %s\n' "$log_dir" "$bucket_name" "$aws_region"