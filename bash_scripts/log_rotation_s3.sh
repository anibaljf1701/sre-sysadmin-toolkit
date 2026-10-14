#!/bin/bash

# Configuración estricta (fail fast)
set -euo pipefail

LOG_DIR="/var/log/<app_name>"
S3_BUCKET="s3://<bucket_app_name>/logs"
DATE=$(date +%Y-%m-%d_%H-%M-%S)

# Lógica interna (Configuración sin parámetros)
UMBRAL_ARCHIVOS=7                # Rotar si se acumulan 7 o más logs
DIA_ROTACION_SEMANAL=7           # 7 = Domingo
DIA_ACTUAL=$(date +%u)           # Obtiene el día actual (1-7)

echo "Iniciando evaluación de rotación de logs..."

# Buscamos logs con más de 1 día para no tocar el archivo que la app está escribiendo hoy
ARCHIVOS_A_ROTAR=$(find "$LOG_DIR" -name '*.log' -mtime +1 | wc -l)

# Evaluación de condiciones
EJECUTAR_ROTACION=false
TIPO_ROTACION=""

if [ "$ARCHIVOS_A_ROTAR" -ge "$UMBRAL_ARCHIVOS" ]; then
    EJECUTAR_ROTACION=true
    TIPO_ROTACION="por_volumen"
    echo "Condición cumplida: Umbral de archivos superado ($ARCHIVOS_A_ROTAR >=$UMBRAL_ARCHIVOS)."
elif [ "$DIA_ACTUAL" -eq "$DIA_ROTACION_SEMANAL" ]; then
    if [ "$ARCHIVOS_A_ROTAR" -gt 0 ]; then
        EJECUTAR_ROTACION=true
        TIPO_ROTACION="semanal"
        echo "Condición cumplida: Mantenimiento semanal (Domingo)."
    else
        echo "Es Domingo, pero no hay archivos antiguos para rotar. Saliendo..."
        exit 0
    fi
else
    echo "No se superó el umbral ($ARCHIVOS_A_ROTAR/$UMBRAL_ARCHIVOS) ni es Domingo. Nada que hacer."
    exit 0
fi

# Bloque de ejecución principal
if [ "$EJECUTAR_ROTACION" = true ]; then
    ARCHIVE_NAME="logs_${TIPO_ROTACION}_${DATE}.tar.gz"
    echo "Comprimiendo $ARCHIVOS_A_ROTAR archivo(s)..."

    # Empaquetado a prueba de fallos para miles de archivos
    find "$LOG_DIR" -name '*.log' -mtime +1 -print0 \vert{} tar -czvf "/tmp/$ARCHIVE_NAME" --null -T -

    echo "Subiendo /tmp/$ARCHIVE_NAME a AWS S3..."
    aws s3 cp "/tmp/$ARCHIVE_NAME" "$S3_BUCKET/$ARCHIVE_NAME" --storage-class STANDARD_IA

    echo "Eliminando archivos locales rotados..."
    find "$LOG_DIR" -name '*.log' -mtime +1 -exec rm -f {} +
    rm -f "/tmp/$ARCHIVE_NAME"

    echo "Rotación ($TIPO_ROTACION) completada con éxito."
fi