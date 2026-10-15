#!/usr/bin/env bash

set -euo pipefail

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

for command_name in python3 aws; do
    command -v "$command_name" >/dev/null 2>&1 || fail "Falta el comando requerido: $command_name"
done

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || fail "Se requiere Python 3.8 o superior."
python3 -c 'import boto3' >/dev/null 2>&1 || fail "No se encontró boto3. Instálalo en el entorno de Python 3: python3 -m pip install boto3"
aws sts get-caller-identity >/dev/null || fail "AWS CLI no tiene credenciales válidas. Ejecuta aws configure o configura un rol/perfil."

aws_region="${AWS_REGION:-$(aws configure get region)}"
[[ -n "$aws_region" ]] || fail "Configura AWS_REGION o la región predeterminada de AWS CLI."

printf 'Requisitos compartidos de Python listos.\nPython: %s\nRegión: %s\n' "$(python3 --version)" "$aws_region"