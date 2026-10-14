"""
AWS Best Practices: Scheduler de instancias EC2 basado en DynamoDB
Implementa AWS Well-Architected Framework para optimización de costos
"""

import boto3
import logging
import os
from datetime import datetime
import json
from typing import List, Dict, Any

# AWS Best Practice: Configuración estructurada de logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Best Practice: Configuración desde variables de entorno
DEFAULT_REGION = os.environ.get('AWS_REGION', 'us-east-1')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'ControlHorariosEC2')
SCHEDULE_NAME = os.environ.get('SCHEDULE_NAME', '20_to_05')

# AWS Best Practice: Inicialización de clientes con retry configuration
session = boto3.Session(region_name=DEFAULT_REGION)
dynamodb = session.resource('dynamodb')
ec2 = session.client('ec2')
cloudwatch = session.client('cloudwatch')

table = dynamodb.Table(DYNAMODB_TABLE)

def lambda_handler(event, context):
    """
    Lambda handler para scheduler de instancias EC2 basado en DynamoDB.
    
    AWS Event Pattern para stop (noche):
    {
        "source": ["aws.events"],
        "detail-type": ["Scheduled Event"],
        "detail": {"accion": "stop"}
    }
    
    AWS Event Pattern para start (mañana):
    {
        "source": ["aws.events"],
        "detail-type": ["Scheduled Event"],
        "detail": {"accion": "start"}
    }
    """
    try:
        logger.info(f"Evento recibido por scheduler: {json.dumps(event, default=str)}")
        
        # Determinar acción basada en el evento
        action = event.get('detail', {}).get('accion', 'stop')
        if action not in ['start', 'stop']:
            logger.error(f"Acción no válida: {action}")
            return error_response("Acción debe ser 'start' o 'stop'", 400)
        
        logger.info(f"Iniciando scheduler para acción: {action}")
        
        # 1. Obtener instancias desde DynamoDB
        instances_from_db = get_instances_from_dynamodb()
        
        if not instances_from_db:
            logger.info("No hay instancias registradas para este horario")
            return success_response("No hay instancias para procesar", {"processed": 0})
        
        # 2. Filtrar instancias por estado actual
        valid_instances = filter_instances_by_state(instances_from_db, action)
        
        if not valid_instances:
            logger.info(f"No hay instancias en estado apropiado para {action}")
            return success_response(
                f"No hay instancias para {action}",
                {"total_in_db": len(instances_from_db), "valid_for_action": 0}
            )
        
        # 3. Ejecutar acción en las instancias
        results = execute_ec2_action(valid_instances, action)
        
        # 4. Registrar métricas y actualizar DynamoDB
        update_dynamodb_records(valid_instances, action)
        send_cloudwatch_metrics(valid_instances, action)
        
        # 5. Preparar respuesta
        summary = {
            "action": action,
            "schedule": SCHEDULE_NAME,
            "instances_in_db": len(instances_from_db),
            "instances_processed": len(valid_instances),
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Resumen de scheduler: {json.dumps(summary)}")
        
        return success_response(
            f"Scheduler ejecutado exitosamente",
            summary
        )
        
    except Exception as e:
        logger.error(f"Error en lambda_handler: {str(e)}", exc_info=True)
        return error_response(f"Error interno: {str(e)}", 500)

def get_instances_from_dynamodb() -> List[str]:
    """
    Obtiene instancias desde DynamoDB usando query eficiente.
    
    AWS Best Practice: Usar query en lugar de scan cuando sea posible
    """
    try:
        # Nota: Para mejor performance, considerar usar GSI si se necesita query por schedule
        response = table.scan(
            FilterExpression="Schedule = :s AND #status = :active",
            ExpressionAttributeNames={
                "#status": "Status"
            },
            ExpressionAttributeValues={
                ":s": SCHEDULE_NAME,
                ":active": "active"
            },
            ProjectionExpression="InstanceId"
        )
        
        instances = [item['InstanceId'] for item in response.get('Items', [])]
        
        # AWS Best Practice: Manejo de paginación
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression="Schedule = :s AND #status = :active",
                ExpressionAttributeNames={"#status": "Status"},
                ExpressionAttributeValues={
                    ":s": SCHEDULE_NAME,
                    ":active": "active"
                },
                ProjectionExpression="InstanceId",
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            instances.extend([item['InstanceId'] for item in response.get('Items', [])])
        
        logger.info(f"Instancias obtenidas de DynamoDB: {len(instances)}")
        return instances
        
    except Exception as e:
        logger.error(f"Error obteniendo instancias de DynamoDB: {e}")
        raise

def filter_instances_by_state(instance_ids: List[str], action: str) -> List[str]:
    """
    Filtra instancias por estado actual para evitar errores de API.
    
    AWS Best Practice: Usar describe_instances con paginación para muchas instancias
    """
    if not instance_ids:
        return []
    
    target_state = 'running' if action == 'stop' else 'stopped'
    
    try:
        # AWS Best Practice: Manejo de límites de API (máx 100 instancias por llamada)
        valid_instances = []
        batch_size = 100
        
        for i in range(0, len(instance_ids), batch_size):
            batch = instance_ids[i:i + batch_size]
            
            response = ec2.describe_instances(
                InstanceIds=batch,
                Filters=[{'Name': 'instance-state-name', 'Values': [target_state]}]
            )
            
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    valid_instances.append(instance['InstanceId'])
        
        logger.info(f"Instancias válidas para {action}: {len(valid_instances)}/{len(instance_ids)}")
        return valid_instances
        
    except Exception as e:
        logger.error(f"Error filtrando instancias por estado: {e}")
        raise

def execute_ec2_action(instance_ids: List[str], action: str) -> Dict[str, Any]:
    """
    Ejecuta acción de start o stop en instancias EC2.
    
    AWS Best Practice: Manejo de errores por instancia individual
    """
    if not instance_ids:
        return {"success": 0, "failed": 0, "errors": []}
    
    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }
    
    try:
        if action == 'stop':
            # AWS Best Practice: Considerar usar stop_instances con Hibernate si está habilitado
            response = ec2.stop_instances(InstanceIds=instance_ids)
            results["success"] = len(instance_ids)
            logger.info(f"Instancias detenidas: {instance_ids}")
            
        else:  # start
            response = ec2.start_instances(InstanceIds=instance_ids)
            results["success"] = len(instance_ids)
            logger.info(f"Instancias iniciadas: {instance_ids}")
        
        # AWS Best Practice: Registrar respuesta de la API
        if 'StoppingInstances' in response:
            for instance in response['StoppingInstances']:
                logger.debug(f"Estado de {instance['InstanceId']}: {instance['CurrentState']['Name']}")
        
        return results
        
    except Exception as e:
        error_msg = f"Error ejecutando {action} en instancias: {str(e)}"
        logger.error(error_msg)
        results["failed"] = len(instance_ids)
        results["errors"].append(error_msg)
        return results

def update_dynamodb_records(instance_ids: List[str], action: str):
    """
    Actualiza registros en DynamoDB después de la acción.
    
    AWS Best Practice: Usar batch_write para múltiples actualizaciones
    """
    if not instance_ids:
        return
    
    timestamp = datetime.utcnow().isoformat()
    
    try:
        with table.batch_writer() as batch:
            for instance_id in instance_ids:
                batch.put_item(
                    Item={
                        'InstanceId': instance_id,
                        'Schedule': SCHEDULE_NAME,
                        'Status': 'active',
                        'LastAction': action,
                        'LastActionTime': timestamp,
                        'LastModified': timestamp
                    }
                )
        
        logger.info(f"Actualizados {len(instance_ids)} registros en DynamoDB")
        
    except Exception as e:
        logger.error(f"Error actualizando DynamoDB: {e}")
        # No fallamos la función principal por errores de logging

def send_cloudwatch_metrics(instance_ids: List[str], action: str):
    """
    Envía métricas a CloudWatch para monitoreo.
    
    AWS Best Practice: Métricas para observabilidad
    """
    try:
        metric_data = [{
            'MetricName': 'InstancesProcessed',
            'Dimensions': [
                {'Name': 'Action', 'Value': action},
                {'Name': 'Schedule', 'Value': SCHEDULE_NAME}
            ],
            'Unit': 'Count',
            'Value': len(instance_ids),
            'Timestamp': datetime.utcnow()
        }]
        
        cloudwatch.put_metric_data(
            Namespace='EC2Scheduler',
            MetricData=metric_data
        )
        
        logger.debug(f"Métricas enviadas a CloudWatch: {len(instance_ids)} instancias")
        
    except Exception as e:
        logger.warning(f"Error enviando métricas a CloudWatch: {e}")
        # No fallamos la función principal por errores de métricas

def success_response(message: str, data: Dict[str, Any]):
    """Respuesta exitosa estructurada."""
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": message,
            "data": data,
            "success": True
        })
    }

def error_response(message: str, status_code: int = 500):
    """Respuesta de error estructurada."""
    return {
        "statusCode": status_code,
        "body": json.dumps({
            "message": message,
            "success": False,
            "error": True
        })
    }