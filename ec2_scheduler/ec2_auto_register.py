"""
AWS Best Practices: Auto-registro de instancias EC2 para programación de horarios
Implementa AWS Well-Architected Framework principles
"""

import boto3
import logging
import os
from datetime import datetime
import json

# AWS Best Practice: Configuración estructurada de logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Best Practice: Manejo de configuración desde variables de entorno
DEFAULT_REGION = os.environ.get('AWS_REGION', 'us-east-1')
DEFAULT_SCHEDULE = os.environ.get('DEFAULT_SCHEDULE', '20_to_05')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'ControlHorariosEC2')

# AWS Best Practice: Inicialización de clientes fuera del handler para reutilización
dynamodb = boto3.resource('dynamodb', region_name=DEFAULT_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)

def lambda_handler(event, context):
    """
    Lambda handler para auto-registro de instancias EC2.
    
    AWS Event Pattern esperado:
    {
        "source": ["aws.ec2"],
        "detail-type": ["AWS API Call via CloudTrail"],
        "detail": {
            "eventSource": ["ec2.amazonaws.com"],
            "eventName": ["RunInstances"]
        }
    }
    """
    try:
        logger.info(f"Evento recibido: {json.dumps(event, default=str)}")
        
        # AWS Best Practice: Validación del evento
        if not validate_event(event):
            logger.warning("Evento no válido para procesamiento")
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Evento no válido"})
            }
        
        # Extraer detalles de las instancias
        instances = extract_instances(event)
        
        if not instances:
            logger.info("No se encontraron instancias en el evento")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No hay instancias para registrar"})
            }
        
        registered_count = 0
        errors = []
        
        # AWS Best Practice: Procesamiento batch con manejo individual de errores
        for instance in instances:
            try:
                result = register_instance(instance)
                if result:
                    registered_count += 1
                    logger.info(f"Instancia registrada: {instance}")
                else:
                    errors.append(f"Error registrando instancia: {instance}")
            except Exception as e:
                errors.append(f"Excepción procesando {instance}: {str(e)}")
                logger.error(f"Error procesando instancia {instance}: {e}")
        
        # AWS Best Practice: Métricas y logging estructurado
        log_summary = {
            "event_id": event.get('id', 'unknown'),
            "timestamp": datetime.utcnow().isoformat(),
            "instances_found": len(instances),
            "instances_registered": registered_count,
            "errors_count": len(errors),
            "default_schedule": DEFAULT_SCHEDULE
        }
        
        logger.info(f"Resumen de ejecución: {json.dumps(log_summary)}")
        
        # AWS Best Practice: Respuesta estructurada
        response = {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Procesamiento completado",
                "summary": log_summary,
                "errors": errors if errors else None
            })
        }
        
        return response
        
    except Exception as e:
        # AWS Best Practice: Manejo centralizado de excepciones
        logger.error(f"Error en lambda_handler: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error interno del servidor",
                "error": str(e)
            })
        }

def validate_event(event):
    """Valida que el evento sea de tipo RunInstances de EC2."""
    try:
        detail = event.get('detail', {})
        
        # Verificar que sea un evento de EC2
        if detail.get('eventSource') != 'ec2.amazonaws.com':
            return False
        
        # Verificar que sea una operación RunInstances
        if detail.get('eventName') != 'RunInstances':
            return False
        
        # Verificar que haya responseElements
        if 'responseElements' not in detail:
            return False
            
        return True
        
    except Exception:
        return False

def extract_instances(event):
    """Extrae los IDs de instancia del evento."""
    try:
        detail = event.get('detail', {})
        response_elements = detail.get('responseElements', {})
        instances_set = response_elements.get('instancesSet', {})
        items = instances_set.get('items', [])
        
        instances = []
        for item in items:
            instance_id = item.get('instanceId')
            if instance_id:
                instances.append(instance_id)
        
        return instances
        
    except Exception as e:
        logger.error(f"Error extrayendo instancias: {e}")
        return []

def register_instance(instance_id):
    """
    Registra una instancia en DynamoDB con el horario por defecto.
    
    AWS Best Practice: Uso de condiciones para evitar sobrescrituras
    """
    try:
        # AWS Best Practice: Usar timestamp para tracking
        timestamp = datetime.utcnow().isoformat()
        
        # AWS Best Practice: Conditional write para evitar duplicados
        response = table.put_item(
            Item={
                'InstanceId': instance_id,
                'Schedule': DEFAULT_SCHEDULE,
                'RegisteredBy': 'Auto-Register-Lambda',
                'RegistrationTime': timestamp,
                'LastModified': timestamp,
                'Status': 'active'
            },
            ConditionExpression='attribute_not_exists(InstanceId) OR #status = :inactive',
            ExpressionAttributeNames={
                '#status': 'Status'
            },
            ExpressionAttributeValues={
                ':inactive': 'inactive'
            }
        )
        
        logger.info(f"Instancia {instance_id} registrada con schedule {DEFAULT_SCHEDULE}")
        return True
        
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info(f"Instancia {instance_id} ya existe en la tabla")
        return True  # Consideramos éxito si ya existe
        
    except Exception as e:
        logger.error(f"Error registrando instancia {instance_id}: {e}")
        return False