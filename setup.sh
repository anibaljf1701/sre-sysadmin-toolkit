#!/bin/bash

# Setup script for SRE SysAdmin Toolkit
# AWS Best Practices implementation helper

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  $1${NC}"
    echo -e "${GREEN}========================================${NC}"
}

print_step() {
    echo -e "\n${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${NC}ℹ $1${NC}"
}

check_aws_cli() {
    print_step "Verificando AWS CLI..."
    if command -v aws &> /dev/null; then
        aws_version=$(aws --version 2>&1 | cut -d' ' -f1 | cut -d'/' -f2)
        print_success "AWS CLI encontrado (v$aws_version)"
        
        # Check if configured
        if aws sts get-caller-identity &> /dev/null; then
            account_id=$(aws sts get-caller-identity --query Account --output text)
            print_success "AWS CLI configurado (Account: $account_id)"
        else
            print_error "AWS CLI no configurado o credenciales inválidas"
            print_info "Ejecuta: aws configure"
            exit 1
        fi
    else
        print_error "AWS CLI no encontrado"
        print_info "Instala AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
}

check_python() {
    print_step "Verificando Python..."
    if command -v python3 &> /dev/null; then
        python_version=$(python3 --version | cut -d' ' -f2)
        print_success "Python3 encontrado (v$python_version)"
        
        # Check for boto3
        if python3 -c "import boto3" &> /dev/null; then
            print_success "boto3 instalado"
        else
            print_info "Instalando boto3..."
            pip3 install boto3 --user
            print_success "boto3 instalado"
        fi
    else
        print_error "Python3 no encontrado"
        print_info "Instala Python 3.8 o superior"
        exit 1
    fi
}

setup_dynamodb_table() {
    print_step "Configurando tabla DynamoDB..."
    
    table_name="ControlHorariosEC2"
    
    # Check if table exists
    if aws dynamodb describe-table --table-name "$table_name" &> /dev/null; then
        print_success "Tabla DynamoDB ya existe: $table_name"
    else
        print_info "Creando tabla DynamoDB: $table_name"
        
        aws dynamodb create-table \
            --table-name "$table_name" \
            --attribute-definitions \
                AttributeName=InstanceId,AttributeType=S \
            --key-schema \
                AttributeName=InstanceId,KeyType=HASH \
            --billing-mode PAY_PER_REQUEST \
            --tags Key=Project,Value=SRE-Toolkit
        
        print_info "Esperando a que la tabla esté activa..."
        aws dynamodb wait table-exists --table-name "$table_name"
        print_success "Tabla DynamoDB creada: $table_name"
    fi
}

setup_s3_bucket() {
    print_step "Configurando bucket S3 para logs..."
    
    # Generate unique bucket name
    account_id=$(aws sts get-caller-identity --query Account --output text)
    region=$(aws configure get region)
    bucket_name="sre-toolkit-logs-${account_id}-${region}"
    
    # Check if bucket exists
    if aws s3api head-bucket --bucket "$bucket_name" &> /dev/null; then
        print_success "Bucket S3 ya existe: $bucket_name"
    else
        print_info "Creando bucket S3: $bucket_name"
        
        # Create bucket with region-specific command
        if [[ "$region" == "us-east-1" ]]; then
            aws s3api create-bucket \
                --bucket "$bucket_name"
        else
            aws s3api create-bucket \
                --bucket "$bucket_name" \
                --create-bucket-configuration LocationConstraint="$region"
        fi
        
        # Enable versioning and default encryption
        aws s3api put-bucket-versioning \
            --bucket "$bucket_name" \
            --versioning-configuration Status=Enabled
        
        aws s3api put-bucket-encryption \
            --bucket "$bucket_name" \
            --server-side-encryption-configuration '{
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }]
            }'
        
        # Add lifecycle policy for STANDARD_IA transition
        aws s3api put-bucket-lifecycle-configuration \
            --bucket "$bucket_name" \
            --lifecycle-configuration '{
                "Rules": [{
                    "ID": "LogsToStandardIA",
                    "Status": "Enabled",
                    "Filter": {
                        "Prefix": "logs/"
                    },
                    "Transitions": [{
                        "Days": 30,
                        "StorageClass": "STANDARD_IA"
                    }]
                }]
            }'
        
        print_success "Bucket S3 creado y configurado: $bucket_name"
    fi
    
    # Save bucket name to env file
    echo "export S3_BUCKET=\"s3://$bucket_name/logs\"" >> .env.example
}

create_env_file() {
    print_step "Creando archivos de configuración..."
    
    # Create .env.example
    cat > .env.example << EOF
# AWS Configuration
export AWS_REGION=$(aws configure get region)
export AWS_DEFAULT_REGION=\$AWS_REGION

# Log Rotation Configuration
export LOG_DIR="/var/log/myapp"
export S3_BUCKET="s3://sre-toolkit-logs-$(aws sts get-caller-identity --query Account --output text)-\$AWS_REGION/logs"
export RETENTION_DAYS=30
export FILE_THRESHOLD=7
export WEEKLY_ROTATION_DAY=7
export LOG_LEVEL="INFO"

# EC2 Scheduler Configuration
export TAG_KEY="Environment"
export TAG_VALUES="Dev,dev,Development,Staging,staging"
export DYNAMODB_TABLE="ControlHorariosEC2"
export SCHEDULE_NAME="20_to_05"
export DEFAULT_SCHEDULE="20_to_05"
EOF
    
    print_success "Archivo .env.example creado"
    print_info "Copia .env.example a .env y ajusta los valores:"
    print_info "  cp .env.example .env"
    print_info "  nano .env (o tu editor favorito)"
}

setup_bash_script() {
    print_step "Configurando script bash..."
    
    chmod +x bash_scripts/log_rotation_s3.sh
    
    # Test the script
    if ./bash_scripts/log_rotation_s3.sh --help &> /dev/null; then
        print_success "Script bash configurado correctamente"
    else
        print_error "Error probando el script bash"
        exit 1
    fi
}

print_next_steps() {
    print_header "✅ Configuración Completada"
    
    cat << EOF

📋 Próximos Pasos:

1. Revisa y ajusta la configuración:
   cp .env.example .env
   nano .env

2. Prueba el script de rotación de logs:
   source .env
   ./bash_scripts/log_rotation_s3.sh --help

3. Despliega las funciones Lambda:
   - Revisa README.md para instrucciones de despliegue
   - Usa AWS SAM o AWS CLI según prefieras

4. Configura CloudWatch Events:
   - Stop: cron(0 20 ? * MON-FRI *)  # 8 PM UTC
   - Start: cron(0 5 ? * MON-FRI *)   # 5 AM UTC

5. Etiqueta tus instancias EC2:
   aws ec2 create-tags \\
     --resources i-1234567890abcdef0 \\
     --tags Key=Environment,Value=Dev

6. Monitorea las ejecuciones:
   - CloudWatch Logs: /aws/lambda/EC2Scheduler*
   - CloudWatch Metrics: namespaces EC2Scheduler y EC2TagScheduler

📚 Documentación Completa:
   Consulta README.md para detalles avanzados y AWS Best Practices.

🔧 Soporte:
   Issues en GitHub: https://github.com/tu-usuario/sre-sysadmin-toolkit/issues

EOF
}

# Main execution
main() {
    print_header "🚀 SRE SysAdmin Toolkit - Setup Script"
    print_info "Este script ayuda a configurar el toolkit con AWS Best Practices"
    print_info "Fecha: $(date)"
    
    check_aws_cli
    check_python
    setup_dynamodb_table
    setup_s3_bucket
    create_env_file
    setup_bash_script
    print_next_steps
}

# Run main function
main