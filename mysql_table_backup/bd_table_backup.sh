#!/bin/bash
set -euo pipefail

: "${SECRET_ID:?Define SECRET_ID con el nombre o ARN del secreto de RDS}"
: "${REGION:?Define REGION con la región AWS}"
: "${BACKUP_DIR:?Define BACKUP_DIR con el directorio local de backups}"
: "${DB_TABLES:?Define DB_TABLES como una lista separada por espacios}"

for command_name in aws jq mysqldump gzip; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Error: falta el comando requerido '$command_name'." >&2
    exit 1
  fi
done

if [[ ! -d "$BACKUP_DIR" || ! -w "$BACKUP_DIR" ]]; then
  echo "Error: BACKUP_DIR debe existir y ser escribible: $BACKUP_DIR" >&2
  exit 1
fi

read -r -a TABLAS_CRITICAS <<< "$DB_TABLES"
if [[ ${#TABLAS_CRITICAS[@]} -eq 0 ]]; then
  echo "Error: DB_TABLES no contiene tablas." >&2
  exit 1
fi

DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="${BACKUP_DIR}/db_business_tables_${DATE}_$$.sql.gz"
TEMP_FILE="${BACKUP_FILE}.tmp"
trap 'rm -f "$TEMP_FILE"' EXIT

echo "Obteniendo credenciales seguras desde AWS Secrets Manager..."
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --region "$REGION" --query SecretString --output text)

DB_USER=$(jq -er '.username | select(type == "string" and length > 0)' <<< "$SECRET_JSON")
DB_PASS=$(jq -er '.password | select(type == "string" and length > 0)' <<< "$SECRET_JSON")
DB_READER_HOST=$(jq -er '.reader_endpoint | select(type == "string" and length > 0)' <<< "$SECRET_JSON")
DB_NAME=$(jq -er '.dbname | select(type == "string" and length > 0)' <<< "$SECRET_JSON")

echo "Iniciando backup lógico en caliente de tablas críticas en $DB_READER_HOST..."

MYSQLDUMP_OPTIONS=(--single-transaction --quick)
if mysqldump --help 2>&1 | grep -- '--set-gtid-purged' >/dev/null; then
  MYSQLDUMP_OPTIONS+=(--set-gtid-purged=OFF)
fi

MYSQL_PWD="$DB_PASS" mysqldump -h "$DB_READER_HOST" -u "$DB_USER" \
  "${MYSQLDUMP_OPTIONS[@]}" \
  "$DB_NAME" "${TABLAS_CRITICAS[@]}" | gzip > "$TEMP_FILE"

mv "$TEMP_FILE" "$BACKUP_FILE"
trap - EXIT

echo "Backup completado y comprimido exitosamente: $BACKUP_FILE"
