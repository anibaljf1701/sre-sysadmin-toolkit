"""
AWS Best Practices: Scheduler de instancias EC2 basado en Tags
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
TAG_KEY = os.environ.get('TAG_KEY', 'Environment')
TAG_VALUES = os.environ.get('TAG_VALUES', 'Dev,dev,Development,Staging,staging').split(',')

# AWS Best Practice: Inicialización de clientes con configuración
session = boto3.Session(region_name=DEFAULT_REGION)
ec2 = session.client('ec2')
cloudwatch = session.client('cloudwatch')

def lambda_handler(event, context):
    """
    Lambda handler para scheduler de instancias EC2 basado en tags.
    
    AWS Event Pattern para stop (fuera de horario laboral):
    {
        "source": ["aws.events"],
        "detail-type": ["Scheduled Event"],
        "detail": {"accion": "stop"}
    }
    
    AWS Event Pattern para start (inicio de horario laboral):
    {
        "source": ["aws.events"],
        "detail-type": ["Scheduled Event"],
        "detail": {"accion": "start"}
    }
    """
    try:
        logger.info(f"Evento recibido por tag-based scheduler: {json.dumps(event, default=str)}")
        
        # Determinar acción basada en el evento
        action = event.get('detail', {}).get('accion', 'stop')
        if action not in ['start', 'stop']:
            logger.error(f"Acción no válida: {action}")
            return error_response("Acción debe ser 'start' o 'stop'", 400)
        
        logger.info(f"Iniciando tag-based scheduler para acción: {action}")
        
        # 1. Encontrar instancias por tags
        instances = find_instances_by_tags(action)
        
        if not instances:
            logger.info(f"No hay instancias con tags apropiadas para {action}")
            return success_response(
                f"No hay instancias para {action}",
                {"action": action, "instances_processed": 0}
            )
        
        # 2. Ejecutar acción en las instancias
        results = execute_ec2_action(instances, action)
        
        # 3. Registrar métricas
        send_cloudwatch_metrics(instances, action)
        
        # 4. Preparar respuesta
        summary = {
            "action": action,
            "tag_key": TAG_KEY,
            "tag_values": TAG_VALUES,
            "instances_processed": len(instances),
            "instances_list": instances,
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Resumen de tag-based scheduler: {json.dumps(summary, default=str)}")
        
        return success_response(
            f"Tag-based scheduler ejecutado exitosamente",
            summary
        )
        
    except Exception as e:
        logger.error(f"Error en lambda_handler: {str(e)}", exc_info=True)
        return error_response(f"Error interno: {str(e)}", 500)

def find_instances_by_tags(action: str) -> List[str]:
    """
    Encuentra instancias EC2 basado en tags y estado.
    
    AWS Best Practice: Usar filters eficientes y paginación
    """
    target_state = 'running' if action == 'stop' else 'stopped'
    
    try:
        filters = [
            {'Name': 'instance-state-name', 'Values': [target_state]},
            {'Name': f'tag:{TAG_KEY}', 'Values': TAG_VALUES}
        ]
        
        instances = []
        next_token = None
        
        # AWS Best Practice: Paginación para manejar muchas instancias
        while True:
            if next_token:
                response = ec2.describe_instances(
                    Filters=filters,
                    MaxResults=100,
                    NextToken=next_token
                )
            else:
                response = ec2.describe_instances(
                    Filters=filters,
                    MaxResults=100
                )
            
            # Extraer IDs de instancia
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instances.append(instance['InstanceId'])
            
            # Verificar si hay más páginas
            next_token = response.get('NextToken')
            if not next_token:
                break
        
        logger.info(f"Instancias encontradas por tags: {len(instances)}")
        
        # AWS Best Practice: Log detallado en debug mode
        if logger.isEnabledFor(logging.DEBUG) and instances:
            for i, instance_id in enumerate(instances[:5]):  # Mostrar solo las primeras 5
                logger.debug(f"Instancia {i+1}: {instance_id}")
            if len(instances) > 5:
                logger.debug(f"... y {len(instances) - 5} más")
        
        return instances
        
    except Exception as e:
        logger.error(f"Error buscando instancias por tags: {e}")
        raise

def execute_ec2_action(instance_ids: List[str], action: str) -> Dict[str, Any]:
    """
    Ejecuta acción de start o stop en instancias EC2.
    
    AWS Best Practice: Manejo de límites de API y errores
    """
    if not instance_ids:
        return {"success": 0, "failed": 0, "errors": []}
    
    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }
    
    try:
        # AWS Best Practice: Procesar en lotes para evitar límites de API
        batch_size = 100
        
        for i in range(0, len(instance_ids), batch_size):
            batch = instance_ids[i:i + batch_size]
            
            try:
                if action == 'stop':
                    response = ec2.stop_instances(InstanceIds=batch)
                    results["success"] += len(batch)
                    logger.info(f"Lote detenido ({i//batch_size + 1}): {len(batch)} instancias")
                    
                else:  # start
                    response = ec2.start_instances(InstanceIds=batch)
                    results["success"] += len(batch)
                    logger.info(f"Lote iniciado ({i//batch_size + 1}): {len(batch)} instancias")
                    
                # AWS Best Practice: Registrar detalles para debugging
                if logger.isEnabledFor(logging.DEBUG):
                    if 'StoppingInstances' in response:
                        for instance in response['StoppingInstances'][:3]:  # Solo primeras 3
                            logger.debug(f"  - {instance['InstanceId']}: {instance['CurrentState']['Name']}")
                    elif 'StartingInstances' in response:
                        for instance in response['StartingInstances'][:3]:
                            logger.debug(f"  - {instance['InstanceId']}: {instance['CurrentState']['Name']}")
                            
            except Exception as batch_error:
                error_msg = f"Error en lote {i//batch_size + 1}: {str(batch_error)}"
                logger.error(error_msg)
                results["failed"] += len(batch)
                results["errors"].append(error_msg)
        
        return results
        
    except Exception as e:
        error_msg = f"Error general ejecutando {action}: {str(e)}"
        logger.error(error_msg)
        results["failed"] = len(instance_ids)
        results["errors"].append(error_msg)
        return results

def send_cloudwatch_metrics(instance_ids: List[str], action: str):
    """
    Envía métricas a CloudWatch para monitoreo.
    
    AWS Best Practice: Métricas para cost optimization tracking
    """
    try:
        metric_data = [{
            'MetricName': 'TagBasedInstancesProcessed',
            'Dimensions': [
                {'Name': 'Action', 'Value': action},
                {'Name': 'TagKey', 'Value': TAG_KEY}
            ],
            'Unit': 'Count',
            'Value': len(instance_ids),
            'Timestamp': datetime.utcnow(),
            'StorageResolution': 60
        }]
        
        # Métrica adicional: estimación de ahorro de costos
        if action == 'stop' and instance_ids:
            # Estimación aproximada: 16 horas de ahorro por instancia
            estimated_savings = len(instance_ids) * 16
            metric_data.append({
                'MetricName': 'EstimatedCostSavingsHours',
                'Dimensions': [{'Name': 'TagKey', 'Value': TAG_KEY}],
                'Unit': 'Count',
                'Value': estimated_savings,
                'Timestamp': datetime.utcnow()
            })
        
        cloudwatch.put_metric_data(
            Namespace='EC2TagScheduler',
            MetricData=metric_data
        )
        
        logger.debug(f"Métricas CloudWatch enviadas: {len(instance_ids)} instancias")
        
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
            "success": True,
            "timestamp": datetime.utcnow().isoformat()
        })
    }

def error_response(message: str, status_code: int = 500):
    """Respuesta de error estructurada."""
    return {
        "statusCode": status_code,
        "body": json.dumps({
            "message": message,
            "success": False,
            "error": True,
            "timestamp": datetime.utcnow().isoformat()
        })
    }

# AWS Best Practice: Configuración adicional para testing local
if __name__ == "__main__":
    # Configuración para testing local
    os.environ['AWS_REGION'] = 'us-east-1'
    os.environ['TAG_KEY'] = 'Environment'
    os.environ['TAG_VALUES'] = 'Dev,dev,Development'
    
    # Test básico
    test_event = {
        "detail": {
            "accion": "stop"
        }
    }
    
    print("Testing tag-based scheduler locally...")
    result = lambda_handler(test_event, None)
    print(f"Result: {json.dumps(result, indent=2)}")