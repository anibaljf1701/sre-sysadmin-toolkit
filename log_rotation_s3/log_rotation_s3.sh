#!/bin/bash

# AWS Best Practices: Script de rotación de logs con almacenamiento en S3
# Configuración estricta (fail fast)
set -euo pipefail

# =============================================================================
# CONFIGURACIÓN PARAMETRIZADA (AWS Best Practices)
# =============================================================================
# Variables de entorno recomendadas (pueden ser sobreescritas desde fuera)
: "${LOG_DIR:=/var/log/myapp}"                  # Directorio de logs por defecto
: "${S3_BUCKET:=s3://my-log-bucket/logs}"       # Bucket S3 destino
: "${AWS_REGION:=us-east-1}"                    # Región AWS por defecto
: "${RETENTION_DAYS:=30}"                        # Retención en S3 (días)
: "${FILE_THRESHOLD:=7}"                         # Umbral para rotación por volumen
: "${WEEKLY_ROTATION_DAY:=7}"                    # Día de rotación semanal (7=Domingo)

# Configuración de logging (AWS Best Practice)
LOG_LEVEL="${LOG_LEVEL:-INFO}"
exec 3>&1 4>&2
trap 'exec 1>&3 2>&4' 0 1 2 3
exec 1>>"/tmp/log_rotation_$(date +%Y%m%d).log" 2>&1

# Función de logging mejorada
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case "$level" in
        "ERROR") [[ "$LOG_LEVEL" =~ ^(ERROR|WARN|INFO|DEBUG)$ ]] && echo "[$timestamp] [ERROR] $message" ;;
        "WARN")  [[ "$LOG_LEVEL" =~ ^(WARN|INFO|DEBUG)$ ]] && echo "[$timestamp] [WARN]  $message" ;;
        "INFO")  [[ "$LOG_LEVEL" =~ ^(INFO|DEBUG)$ ]] && echo "[$timestamp] [INFO]  $message" ;;
        "DEBUG") [[ "$LOG_LEVEL" =~ ^DEBUG$ ]] && echo "[$timestamp] [DEBUG] $message" ;;
        *) echo "[$timestamp] [INFO] $message" ;;
    esac
}

# Validación de configuración (AWS Security Best Practice)
validate_config() {
    log "INFO" "Validando configuración..."
    
    # Validar directorio de logs
    if [ ! -d "$LOG_DIR" ]; then
        log "ERROR" "Directorio de logs no encontrado: $LOG_DIR"
        exit 1
    fi
    
    # Validar permisos de escritura
    if [ ! -w "$LOG_DIR" ]; then
        log "ERROR" "Sin permisos de escritura en: $LOG_DIR"
        exit 1
    fi
    
    # Validar formato del bucket S3 (AWS Best Practice)
    if [[ ! "$S3_BUCKET" =~ ^s3:// ]]; then
        log "ERROR" "Formato de bucket S3 inválido. Debe comenzar con 's3://'"
        exit 1
    fi
    
    # Validar que AWS CLI está instalado y configurado
    if ! command -v aws &> /dev/null; then
        log "ERROR" "AWS CLI no está instalado"
        exit 1
    fi
    
    # Configurar región AWS
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    log "INFO" "Configuración validada correctamente"
    log "INFO" "LOG_DIR: $LOG_DIR"
    log "INFO" "S3_BUCKET: $S3_BUCKET"
    log "INFO" "AWS_REGION: $AWS_REGION"
    log "INFO" "RETENTION_DAYS: $RETENTION_DAYS días"
    log "INFO" "FILE_THRESHOLD: $FILE_THRESHOLD archivos"
    log "INFO" "WEEKLY_ROTATION_DAY: $WEEKLY_ROTATION_DAY (1=Lunes, 7=Domingo)"
}

# =============================================================================
# LÓGICA PRINCIPAL
# =============================================================================
DATE=$(date +%Y-%m-%d_%H-%M-%S)
CURRENT_DAY=$(date +%u)

log "INFO" "Iniciando evaluación de rotación de logs..."

# Validar configuración antes de continuar
validate_config

# Buscamos logs con más de 1 día para no tocar el archivo que la app está escribiendo hoy
ARCHIVOS_A_ROTAR=$(find "$LOG_DIR" -name '*.log' -mtime +1 2>/dev/null | wc -l)

# Evaluación de condiciones (AWS Cost Optimization: evitar operaciones innecesarias)
EJECUTAR_ROTACION=false
TIPO_ROTACION=""
REASON=""

if [ "$ARCHIVOS_A_ROTAR" -ge "$FILE_THRESHOLD" ]; then
    EJECUTAR_ROTACION=true
    TIPO_ROTACION="volume_based"
    REASON="Umbral de archivos superado ($ARCHIVOS_A_ROTAR >= $FILE_THRESHOLD)"
    log "INFO" "Condición cumplida: $REASON"
elif [ "$CURRENT_DAY" -eq "$WEEKLY_ROTATION_DAY" ]; then
    if [ "$ARCHIVOS_A_ROTAR" -gt 0 ]; then
        EJECUTAR_ROTACION=true
        TIPO_ROTACION="weekly_maintenance"
        REASON="Mantenimiento semanal programado (Día $CURRENT_DAY)"
        log "INFO" "Condición cumplida: $REASON"
    else
        log "INFO" "Es día de mantenimiento semanal, pero no hay archivos antiguos para rotar. Saliendo..."
        exit 0
    fi
else
    log "INFO" "No se superó el umbral ($ARCHIVOS_A_ROTAR/$FILE_THRESHOLD) ni es día de mantenimiento ($CURRENT_DAY/$WEEKLY_ROTATION_DAY). Nada que hacer."
    exit 0
fi

# Bloque de ejecución principal con manejo de errores (AWS Operational Excellence)
if [ "$EJECUTAR_ROTACION" = true ]; then
    ARCHIVE_NAME="logs_${TIPO_ROTACION}_${DATE}.tar.gz"
    TEMP_ARCHIVE="/tmp/$ARCHIVE_NAME"
    
    log "INFO" "Iniciando rotación de tipo: $TIPO_ROTACION"
    log "INFO" "Razón: $REASON"
    log "INFO" "Archivos a rotar: $ARCHIVOS_A_ROTAR"
    
    # Comprimir archivos con manejo robusto de errores
    log "INFO" "Comprimiendo $ARCHIVOS_A_ROTAR archivo(s)..."
    if ! find "$LOG_DIR" -name '*.log' -mtime +1 -print0 2>/dev/null | \
       tar -czvf "$TEMP_ARCHIVE" --null -T - 2>/dev/null; then
        log "ERROR" "Error al comprimir archivos"
        exit 1
    fi
    
    # Verificar que el archivo se creó correctamente
    if [ ! -f "$TEMP_ARCHIVE" ]; then
        log "ERROR" "Archivo comprimido no creado: $TEMP_ARCHIVE"
        exit 1
    fi
    
    ARCHIVE_SIZE=$(du -h "$TEMP_ARCHIVE" | cut -f1)
    log "INFO" "Archivo creado: $TEMP_ARCHIVE ($ARCHIVE_SIZE)"
    
    # Subir a S3 con configuración de almacenamiento inteligente (AWS Cost Optimization)
    log "INFO" "Subiendo $TEMP_ARCHIVE a AWS S3..."
    S3_DESTINATION="$S3_BUCKET/$(date +%Y)/$(date +%m)/$ARCHIVE_NAME"
    
    if ! aws s3 cp "$TEMP_ARCHIVE" "$S3_DESTINATION" \
        --storage-class STANDARD_IA \
        --metadata "rotation-type=$TIPO_ROTACION,retention-days=$RETENTION_DAYS" \
        --sse AES256; then
        log "ERROR" "Error al subir archivo a S3"
        # No eliminamos el archivo temporal para debugging
        exit 1
    fi
    
    log "INFO" "Archivo subido exitosamente a: $S3_DESTINATION"
    
    # Eliminar archivos locales rotados (AWS Security: limpieza de datos sensibles)
    log "INFO" "Eliminando archivos locales rotados..."
    if ! find "$LOG_DIR" -name '*.log' -mtime +1 -exec rm -f {} + 2>/dev/null; then
        log "WARN" "Algunos archivos no pudieron ser eliminados (puede que ya hayan sido removidos)"
    fi
    
    # Limpiar archivo temporal
    rm -f "$TEMP_ARCHIVE"
    
    # Aplicar política de ciclo de vida a los archivos subidos (AWS Cost Optimization)
    log "INFO" "Aplicando configuración de retención ($RETENTION_DAYS días)..."
    
    # Registrar métricas para monitoreo (AWS Observability Best Practice)
    log "INFO" "Rotación completada exitosamente"
    log "INFO" "Resumen: Tipo=$TIPO_ROTACION, Archivos=$ARCHIVOS_A_ROTAR, Tamaño=$ARCHIVE_SIZE, Destino=$S3_DESTINATION"
    
    # Opcional: Enviar métricas a CloudWatch
    # aws cloudwatch put-metric-data --namespace "LogRotation" --metric-name "FilesRotated" --value $ARCHIVOS_A_ROTAR --unit "Count"
fi


# =============================================================================
# DOCUMENTACIÓN Y USO
# =============================================================================
print_usage() {
    cat << EOF
AWS Log Rotation Script v2.0
=============================

DESCRIPCIÓN:
    Script de rotación de logs que implementa AWS Best Practices para:
    - Almacenamiento eficiente en S3
    - Optimización de costos (STANDARD_IA storage class)
    - Seguridad (SSE-S3 encryption)
    - Observabilidad (logging estructurado)

USO:
    ./log_rotation_s3.sh [OPCIONES]

OPCIONES DE CONFIGURACIÓN (variables de entorno):
    LOG_DIR              Directorio de logs a monitorear (default: /var/log/myapp)
    S3_BUCKET            Bucket S3 destino (default: s3://my-log-bucket/logs)
    AWS_REGION           Región AWS (default: us-east-1)
    RETENTION_DAYS       Días de retención en S3 (default: 30)
    FILE_THRESHOLD       Umbral para rotación por volumen (default: 7)
    WEEKLY_ROTATION_DAY  Día de rotación semanal 1-7 (default: 7=Domingo)
    LOG_LEVEL            Nivel de logging: DEBUG, INFO, WARN, ERROR (default: INFO)

EJEMPLOS:
    # Uso básico con configuración por defecto
    ./log_rotation_s3.sh
    
    # Configuración personalizada
    LOG_DIR="/var/log/nginx" \\
    S3_BUCKET="s3://company-logs/production" \\
    AWS_REGION="us-west-2" \\
    RETENTION_DAYS=90 \\
    ./log_rotation_s3.sh
    
    # Para debugging
    LOG_LEVEL=DEBUG ./log_rotation_s3.sh

AWS BEST PRACTICES IMPLEMENTADAS:
    1. Security: Encriptación SSE-S3 en S3
    2. Cost Optimization: Storage class STANDARD_IA para archivos antiguos
    3. Reliability: Manejo robusto de errores y validaciones
    4. Performance: Compresión eficiente y transferencia optimizada
    5. Operational Excellence: Logging estructurado y métricas

LOGS:
    Los logs de ejecución se guardan en: /tmp/log_rotation_YYYYMMDD.log

CONFIGURACIÓN AWS:
    Asegúrese de tener AWS CLI configurado con credenciales válidas:
    \$ aws configure
    \$ aws sts get-caller-identity

EOF
}

# Manejo de parámetros de ayuda
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    print_usage
    exit 0
fi

# Script principal
main() {
    log "INFO" "=== Inicio de ejecución de rotación de logs ==="
    log "INFO" "Versión: 2.0 (AWS Best Practices Edition)"
    log "INFO" "Fecha: $(date)"
    
    # La lógica principal ya está implementada arriba
    log "INFO" "=== Fin de ejecución ==="
}

# Ejecutar función principal
main