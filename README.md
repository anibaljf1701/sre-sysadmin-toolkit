# SRE SysAdmin Automation Toolkit

[![AWS Well-Architected](https://img.shields.io/badge/AWS-Well--Architected-orange)](https://aws.amazon.com/architecture/well-architected/)
[![Cost Optimization](https://img.shields.io/badge/AWS-Cost%20Optimization-yellow)](https://aws.amazon.com/aws-cost-management/)
[![Operational Excellence](https://img.shields.io/badge/AWS-Operational%20Excellence-blue)](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)

Un conjunto de herramientas de automatización para SysAdmins y SREs que implementa AWS Best Practices para optimización de costos, seguridad y eficiencia operacional.

## 📋 Tabla de Contenidos

- [Descripción del Proyecto](#descripción-del-proyecto)
- [Arquitectura AWS](#arquitectura-aws)
- [Scripts Disponibles](#scripts-disponibles)
- [Requisitos](#requisitos)
- [Instalación y Configuración](#instalación-y-configuración)
- [Uso](#uso)
- [AWS Best Practices Implementadas](#aws-best-practices-implementadas)
- [Monitoreo y Métricas](#monitoreo-y-métricas)
- [Seguridad](#seguridad)
- [Contribución](#contribución)
- [Licencia](#licencia)

## 🎯 Descripción del Proyecto

Este repositorio contiene scripts de automatización diseñados para equipos de SRE y SysAdmin que operan en entornos AWS. Los scripts implementan prácticas recomendadas del AWS Well-Architected Framework para:

1. **Optimización de Costos**: Apagar instancias EC2 no productivas fuera de horario laboral
2. **Gestión de Logs**: Rotación y archivado automático de logs en S3
3. **Eficiencia Operacional**: Automatización de tareas repetitivas con manejo robusto de errores
4. **Seguridad**: Encriptación, control de acceso y seguimiento de auditoría

## 🏗️ Arquitectura AWS

### Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Well-Architected                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │   EC2 Inst  │    │   EC2 Inst  │    │   EC2 Inst  │    │
│  │   (Dev/Stg) │    │   (Dev/Stg) │    │   (Dev/Stg) │    │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    │
│         │                  │                  │            │
│  ┌──────┴──────────────────┴──────────────────┴──────┐    │
│  │              AWS CloudWatch Events                │    │
│  └──────┬──────────────────┬──────────────────┬──────┘    │
│         │                  │                  │            │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌───────▼───────┐   │
│  │   Lambda    │  │    Lambda     │  │    Lambda     │   │
│  │  Scheduler  │  │ Auto-Register │  │ Log Rotation  │   │
│  │   (Tags)    │  │   (DynamoDB)  │  │    (S3)       │   │
│  └──────┬──────┘  └───────┬───────┘  └───────┬───────┘   │
│         │                  │                  │            │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌───────▼───────┐   │
│  │    EC2 API  │  │   DynamoDB    │  │   S3 Bucket   │   │
│  │             │  │   (Horarios)  │  │  (Logs/IA)    │   │
│  └─────────────┘  └───────────────┘  └───────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               CloudWatch Metrics                    │   │
│  │  (Cost Savings, Instances Processed, Errors)       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Componentes Principales

1. **EC2 Scheduler (Tags)**: Lambda que encuentra y gestiona instancias basándose en tags
2. **EC2 Auto-Register (DynamoDB)**: Lambda que registra nuevas instancias automáticamente
3. **EC2 Scheduler (DynamoDB)**: Lambda que gestiona instancias basándose en horarios almacenados
4. **Log Rotation Script**: Script bash que rota y archiva logs en S3
5. **CloudWatch Events**: Programación de tareas automáticas
6. **CloudWatch Metrics**: Monitoreo y métricas de ahorro de costos

## 📁 Scripts Disponibles

### 📂 `bash_scripts/`

#### `log_rotation_s3.sh`
Script de rotación de logs que implementa AWS Best Practices:
- Rotación basada en volumen o tiempo
- Almacenamiento en S3 con clase STANDARD_IA
- Encriptación SSE-S3
- Retención configurable
- Logging estructurado

### 📂 `python_scripts/scheduler_dynamo/`

#### `ec2_auto_register.py`
Lambda que registra automáticamente nuevas instancias EC2 en DynamoDB:
- Detección de eventos CloudTrail
- Registro condicional (evita duplicados)
- Configuración de horarios por defecto

#### `ec2_scheduler_dynamo.py`
Lambda que gestiona instancias EC2 basándose en horarios almacenados en DynamoDB:
- Consulta eficiente con paginación
- Manejo de errores por instancia
- Métricas de CloudWatch
- Actualización de estado en DynamoDB

### 📂 `python_scripts/scheduler_tags/`

#### `ec2_scheduler_tags.py`
Lambda que gestiona instancias EC2 basándose en tags:
- Filtrado por tags y estado
- Paginación para muchas instancias
- Estimación de ahorro de costos
- Métricas detalladas

## ⚙️ Requisitos

### General
- Cuenta AWS con permisos adecuados
- AWS CLI configurado
- Python 3.8+ (para scripts Python)
- Bash 4.0+ (para script bash)

### AWS Servicios Requeridos
- AWS Lambda (con Python runtime)
- Amazon EC2
- Amazon DynamoDB
- Amazon S3
- Amazon CloudWatch Events
- AWS CloudTrail (para auto-registro)

### Permisos IAM

**Política Mínima Recomendada:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:StartInstances",
                "ec2:StopInstances",
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem",
                "s3:PutObject",
                "s3:GetObject",
                "cloudwatch:PutMetricData",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "*"
        }
    ]
}
```

## 🚀 Instalación y Configuración

### 1. Clonar el Repositorio

```bash
git clone https://github.com/tu-usuario/sre-sysadmin-toolkit.git
cd sre-sysadmin-toolkit
```

### 2. Configurar AWS CLI

```bash
aws configure
# Ingresa tus credenciales AWS
# Default region: us-east-1 (o tu región preferida)
# Default output format: json
```

### 3. Configurar Script Bash

#### Variables de Entorno (opcional, pueden setearse en runtime):

```bash
# Ejemplo de configuración
export LOG_DIR="/var/log/myapp"
export S3_BUCKET="s3://my-log-bucket/logs"
export AWS_REGION="us-east-1"
export RETENTION_DAYS=30
export FILE_THRESHOLD=7
export WEEKLY_ROTATION_DAY=7
export LOG_LEVEL="INFO"
```

#### Hacer ejecutable el script:

```bash
chmod +x bash_scripts/log_rotation_s3.sh
```

### 4. Configurar Lambdas Python

#### Crear Tabla DynamoDB:

```bash
aws dynamodb create-table \
    --table-name ControlHorariosEC2 \
    --attribute-definitions \
        AttributeName=InstanceId,AttributeType=S \
    --key-schema \
        AttributeName=InstanceId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST
```

#### Desplegar Lambdas:

**Opción A: Usando AWS SAM**

```yaml
# template.yaml (ejemplo)
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  EC2SchedulerTagsLambda:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: python_scripts/scheduler_tags/
      Handler: ec2_scheduler_tags.lambda_handler
      Runtime: python3.8
      Environment:
        Variables:
          TAG_KEY: Environment
          TAG_VALUES: Dev,dev,Development,Staging
      Events:
        StopEvent:
          Type: Schedule
          Properties:
            Schedule: cron(0 20 ? * MON-FRI *)
            Input: '{"accion": "stop"}'
        StartEvent:
          Type: Schedule
          Properties:
            Schedule: cron(0 5 ? * MON-FRI *)
            Input: '{"accion": "start"}'
```

**Opción B: Manualmente con AWS CLI**

```bash
# Empaquetar Lambda
cd python_scripts/scheduler_tags
zip -r lambda.zip .

# Crear Lambda
aws lambda create-function \
    --function-name EC2SchedulerTags \
    --runtime python3.8 \
    --handler ec2_scheduler_tags.lambda_handler \
    --role arn:aws:iam::123456789012:role/lambda-execution-role \
    --zip-file fileb://lambda.zip \
    --environment "Variables={TAG_KEY=Environment,TAG_VALUES=Dev,dev,Development}"
```

### 5. Configurar CloudWatch Events

```bash
# Evento para apagar instancias (8 PM UTC)
aws events put-rule \
    --name "EC2StopWeekdays" \
    --schedule-expression "cron(0 20 ? * MON-FRI *)" \
    --state ENABLED

# Evento para encender instancias (5 AM UTC)
aws events put-rule \
    --name "EC2StartWeekdays" \
    --schedule-expression "cron(0 5 ? * MON-FRI *)" \
    --state ENABLED

# Conectar reglas a Lambda
aws events put-targets \
    --rule "EC2StopWeekdays" \
    --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:123456789012:function:EC2SchedulerTags"

aws events put-targets \
    --rule "EC2StartWeekdays" \
    --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:123456789012:function:EC2SchedulerTags"
```

### 6. Configurar Auto-Registro (Opcional)

```bash
# Crear regla de EventBridge para capturar RunInstances
aws events put-rule \
    --name "EC2RunInstancesEvent" \
    --event-pattern '{"source":["aws.ec2"],"detail-type":["AWS API Call via CloudTrail"],"detail":{"eventSource":["ec2.amazonaws.com"],"eventName":["RunInstances"]}}' \
    --state ENABLED

# Conectar a Lambda de auto-registro
aws events put-targets \
    --rule "EC2RunInstancesEvent" \
    --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:123456789012:function:EC2AutoRegister"
```

## 🛠️ Uso

### Script de Rotación de Logs

#### Uso Básico:

```bash
./bash_scripts/log_rotation_s3.sh
```

#### Con Configuración Personalizada:

```bash
LOG_DIR="/var/log/nginx" \
S3_BUCKET="s3://company-logs/production" \
AWS_REGION="us-west-2" \
RETENTION_DAYS=90 \
LOG_LEVEL=DEBUG \
./bash_rotation_s3.sh
```

#### Programar con Cron:

```bash
# Rotación diaria a la 1 AM
0 1 * * * /ruta/a/sre-sysadmin-toolkit/bash_scripts/log_rotation_s3.sh >> /var/log/log_rotation.log 2>&1

# Rotación semanal los Domingos a las 2 AM
0 2 * * 0 /ruta/a/sre-sysadmin-toolkit/bash_scripts/log_rotation_s3.sh >> /var/log/log_rotation.log 2>&1
```

### Lambdas de Scheduler

Las lambdas se ejecutan automáticamente según la programación de CloudWatch Events:

- **Stop**: Lunes-Viernes, 8 PM UTC (fuera de horario laboral)
- **Start**: Lunes-Viernes, 5 AM UTC (antes de horario laboral)

#### Ejecución Manual (Testing):

```bash
# Probar Lambda de tags
aws lambda invoke \
    --function-name EC2SchedulerTags \
    --payload '{"accion": "stop"}' \
    response.json

cat response.json
```

#### Ver Logs de Ejecución:

```bash
# Ver logs de CloudWatch
aws logs filter-log-events \
    --log-group-name /aws/lambda/EC2SchedulerTags \
    --start-time $(date -d "1 hour ago" +%s)000 \
    --filter-pattern "INFO"
```

### Configuración de Instancias EC2

#### Método 1: Usando Tags (Recomendado)

Agregar tag a instancias de desarrollo/staging:

```bash
aws ec2 create-tags \
    --resources i-1234567890abcdef0 \
    --tags Key=Environment,Value=Dev
```

Tags soportados: `Dev`, `dev`, `Development`, `Staging`, `staging`

#### Método 2: Usando DynamoDB (Auto-Registro)

Las instancias nuevas se registran automáticamente cuando:
1. Se lanza una instancia EC2
2. El evento es capturado por CloudTrail
3. La Lambda de auto-registro la agrega a DynamoDB

Ver instancias registradas:

```bash
aws dynamodb scan \
    --table-name ControlHorariosEC2 \
    --filter-expression "Schedule = :s" \
    --expression-attribute-values '{":s":{"S":"20_to_05"}}'
```

## 🏆 AWS Best Practices Implementadas

### 1. **Pilar de Excelencia Operacional**
- ✅ Logging estructurado con múltiples niveles
- ✅ Manejo robusto de errores y retries
- ✅ Métricas de CloudWatch para monitoreo
- ✅ Documentación exhaustiva
- ✅ Validación de configuración

### 2. **Pilar de Seguridad**
- ✅ Encriptación SSE-S3 en todos los archivos
- ✅ Principio de menor privilegio en permisos IAM
- ✅ Validación de entradas y eventos
- ✅ Limpieza de archivos temporales
- ✅ No almacenamiento de credenciales en código

### 3. **Pilar de Confiabilidad**
- ✅ Timeouts y retries configurables
- ✅ Manejo de límites de API (paginación)
- ✅ Conditional writes en DynamoDB
- ✅ Verificación de estados antes de operaciones
- ✅ Circuit breakers implícitos

### 4. **Pilar de Eficiencia de Rendimiento**
- ✅ Procesamiento por lotes (batch processing)
- ✅ Uso eficiente de queries (índices, filtros)
- ✅ Almacenamiento S3 inteligente (STANDARD_IA)
- ✅ Cache de clientes AWS SDK
- ✅ Paralelismo donde aplica

### 5. **Pilar de Optimización de Costos**
- ✅ Apagado automático de instancias no productivas
- ✅ Storage class STANDARD_IA para logs antiguos
- ✅ Retención configurable de datos
- ✅ Métricas de ahorro estimado
- ✅ Eliminación de recursos innecesarios

### 6. **Pilar de Sostenibilidad**
- ✅ Reducción de consumo energético (instancias apagadas)
- ✅ Almacenamiento eficiente (compresión, clases apropiadas)
- ✅ Minimización de transferencias de datos

## 📊 Monitoreo y Métricas

### Métricas CloudWatch Automáticas

**Namespace: `EC2TagScheduler`**
- `TagBasedInstancesProcessed`: Instancias procesadas por acción
- `EstimatedCostSavingsHours`: Horas estimadas de ahorro

**Namespace: `EC2Scheduler`**
- `InstancesProcessed`: Instancias procesadas (DynamoDB)
- `DBRecordsUpdated`: Registros actualizados en DynamoDB

**Namespace: `LogRotation`** (Opcional)
- `FilesRotated`: Archivos rotados por ejecución
- `DataUploaded`: Tamaño de datos subidos a S3

### Dashboards Recomendados

1. **Dashboard de Ahorro de Costos**:
   - Instancias procesadas por día
   - Horas estimadas de ahorro
   - Costo evitado (estimado)

2. **Dashboard Operacional**:
   - Ejecuciones exitosas/fallidas
   - Tiempo de ejecución
   - Errores por tipo

3. **Dashboard de Logs**:
   - Archivos rotados
   - Espacio liberado
   - Tasa de compresión

### Alertas Configurables

```bash
# Alerta por fallos consecutivos
aws cloudwatch put-metric-alarm \
    --alarm-name "EC2Scheduler-Failures" \
    --metric-name "Errors" \
    --namespace "AWS/Lambda" \
    --statistic "Sum" \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 1 \
    --comparison-operator "GreaterThanThreshold" \
    --alarm-actions "arn:aws:sns:us-east-1:123456789012:AlertsTopic"
```

## 🔒 Seguridad

### Consideraciones de Seguridad

1. **IAM Roles y Permisos**:
   - Usar roles específicos para cada Lambda
   - Aplicar principio de menor privilegio
   - Rotar credenciales regularmente

2. **Encriptación de Datos**:
   - S3: SSE-S3 habilitado por defecto
   - DynamoDB: Encriptación en reposo habilitada
   - Tránsito: TLS 1.2+ para todas las comunicaciones

3. **Protección de Logs**:
   - Logs contienen información sensible
   - Configurar retención apropiada en CloudWatch Logs
   - Considerar enmascaramiento de datos sensibles

4. **Hardening del Script Bash**:
   - Validación de todas las entradas
   - Uso de `set -euo pipefail`
   - Limpieza de archivos temporales
   - No ejecutar como root

### Auditoría y Compliance

1. **AWS CloudTrail**:
   - Habilitado para todas las regiones
   - Registro de todas las operaciones de API
   - Integración con S3 para archivado

2. **AWS Config**:
   - Monitoreo de configuración de recursos
   - Reglas para compliance
   - Historial de cambios

3. **AWS Security Hub**:
   - Vista unificada de seguridad
   - Checks de compliance automáticos
   - Integración con estándares (CIS, PCI-DSS)

## 🤝 Contribución

### Estructura del Proyecto

```
sre-sysadmin-toolkit/
├── README.md                  # Este archivo
├── .gitignore                # Archivos ignorados por git
├── bash_scripts/             # Scripts bash
│   └── log_rotation_s3.sh    # Script principal de rotación
├── python_scripts/           # Scripts Python (Lambdas)
│   ├── scheduler_dynamo/     # Scheduler basado en DynamoDB
│   │   ├── ec2_auto_register.py
│   │   └── ec2_scheduler_dynamo.py
│   └── scheduler_tags/       # Scheduler basado en tags
│       └── ec2_scheduler_tags.py
└── .kiro/                    # Configuración Kiro (MCP)
    └── settings/
        └── mcp.json          # Configuración de servidores MCP
```

### Guías de Contribución

1. **Fork y Clone** el repositorio
2. **Crea una rama** para tu feature (`git checkout -b feature/amazing-feature`)
3. **Commit tus cambios** (`git commit -m 'Add some amazing feature'`)
4. **Push a la rama** (`git push origin feature/amazing-feature`)
5. **Abre un Pull Request**

### Convenciones de Código

- **Bash**: Sigue [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html)
- **Python**: Sigue [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- **Documentación**: Incluye docstrings y comentarios claros
- **Testing**: Incluye pruebas unitarias para nuevos features

### Checklist de Pull Request

- [ ] Código sigue las convenciones del proyecto
- [ ] Documentación actualizada
- [ ] Tests agregados/actualizados
- [ ] Variables de entorno documentadas
- [ ] Permisos IAM actualizados (si aplica)
- [ ] Backward compatibility verificada

## 📝 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## 🙏 Agradecimientos

- **AWS Well-Architected Framework** por las mejores prácticas
- **AWS Cost Optimization Pillar** por las guías de ahorro
- **Comunidad SRE** por patrones y soluciones probadas

## 📞 Soporte

Para soporte, por favor:
1. Revisa la [documentación](#) primero
2. Busca issues similares en [GitHub Issues](#)
3. Crea un nuevo issue si no encuentras solución

**Contacto del Mantenedor**: [tu-email@ejemplo.com](mailto:tu-email@ejemplo.com)

---

**Nota**: Este proyecto es para fines educativos y de demostración. Siempre prueba en entornos de staging antes de desplegar a producción. Los costos de AWS son responsabilidad del usuario.

**Última Actualización**: Octubre 2026