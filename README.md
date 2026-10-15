# SRE SysAdmin Toolkit

Herramientas independientes para automatizar tareas habituales de operación en AWS. Cada herramienta puede configurarse y desplegarse por separado.

## Herramientas

| Herramienta | Propósito | Implementación |
| --- | --- | --- |
| Rotación de logs | Comprime logs antiguos y los archiva en S3 | Bash |
| Programación de instancias EC2 | Detiene instancias fuera del horario configurado y las inicia al comienzo de la jornada | AWS Lambda, con selección por tags o DynamoDB |

## Requisitos comunes

- AWS CLI instalado y configurado para la cuenta y región objetivo.
- Permisos IAM limitados a las acciones indicadas en la guía de cada herramienta.
- Una política de horario acorde con la zona horaria del equipo. Las expresiones de EventBridge se interpretan en UTC.

Clona el repositorio:

```bash
git clone https://github.com/anibaljf1701/sre-sysadmin-toolkit.git
cd sre-sysadmin-toolkit
```

## Rotación de logs en S3

Script: `bash_scripts/log_rotation_s3.sh`

Busca archivos `*.log` con más de un día de antigüedad. Ejecuta la rotación cuando alcanza el umbral de archivos o cuando llega el día semanal configurado. Tras subir correctamente el archivo comprimido a S3, elimina los logs locales incluidos.

### Requisitos

- Bash 4 o superior, `find`, `tar`, `du` y AWS CLI.
- Acceso de escritura al directorio de logs.
- Un bucket S3 y permisos para subir objetos.

### Instalación y configuración

Valida los requisitos del host, la configuración AWS y el acceso al bucket. Define el directorio y bucket antes de ejecutar la comprobación:

```bash
LOG_DIR=/var/log/nginx \
S3_BUCKET=s3://company-logs/production \
AWS_REGION=us-east-1 \
./bash_scripts/setup.sh
```

El setup solo realiza comprobaciones de lectura; no crea recursos ni modifica archivos.

Haz ejecutable el script si el sistema de archivos no conserva el bit de ejecución:

```bash
chmod +x bash_scripts/log_rotation_s3.sh
```

Configura las variables al ejecutarlo o expórtalas en el entorno:

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `LOG_DIR` | `/var/log/myapp` | Directorio donde buscar logs |
| `S3_BUCKET` | `s3://my-log-bucket/logs` | Prefijo de destino en S3 |
| `AWS_REGION` | `us-east-1` | Región de AWS |
| `RETENTION_DAYS` | `30` | Valor incluido en los metadatos del objeto; no configura una regla de expiración de S3 |
| `FILE_THRESHOLD` | `7` | Cantidad de logs antiguos que activa la rotación |
| `WEEKLY_ROTATION_DAY` | `7` | Día semanal de mantenimiento: 1=lunes, 7=domingo |
| `LOG_LEVEL` | `INFO` | Nivel de salida: `ERROR`, `WARN`, `INFO` o `DEBUG` |

Ejemplo:

```bash
LOG_DIR=/var/log/nginx \
S3_BUCKET=s3://company-logs/production \
AWS_REGION=us-east-1 \
FILE_THRESHOLD=7 \
./bash_scripts/log_rotation_s3.sh
```

Programa el comando con cron o con el scheduler de tu entorno. Una ejecución diaria suele ser suficiente; la decisión de rotar sigue dependiendo del umbral y del día semanal configurados. Los mensajes se guardan en `/tmp/log_rotation_YYYYMMDD.log`.

Para aplicar expiración real a los objetos archivados, configura una política de ciclo de vida en el bucket S3. `RETENTION_DAYS` por sí sola no elimina objetos.

### Permisos AWS

La identidad usada por AWS CLI necesita `s3:PutObject` sobre el prefijo de destino. Si se usa un perfil distinto al predeterminado, configura `AWS_PROFILE` antes de ejecutar el script.

### Pruebas

Ejecuta las pruebas desde la raíz del repositorio. Usan un directorio temporal y un comando `aws` simulado; no necesitan credenciales ni recursos AWS:

```bash
python3 bash_scripts/test_scripts.py
```

## Programación de instancias EC2

Hay dos modalidades excluyentes para elegir las instancias objetivo. En ambas se despliega una Lambda para iniciar/detener instancias y se crean dos reglas programadas de EventBridge: una con `{"detail":{"accion":"stop"}}` y otra con `{"detail":{"accion":"start"}}`. Ajusta los horarios a tu jornada y a UTC.

Las Lambdas usan el runtime Python de AWS y `boto3`, disponible en el entorno Lambda. Empaqueta el archivo de la modalidad elegida en un ZIP y despliega una función con el handler indicado. Asigna a la función un rol de ejecución que permita escribir logs en CloudWatch y realizar las acciones EC2/DynamoDB correspondientes.

Ambos schedulers comparten los requisitos de Python 3.8 o superior, `boto3`, AWS CLI, credenciales válidas y región configurada. Compruébalos una vez:

```bash
./python_scripts/setup.sh
```

Cada modalidad tiene además un setup de solo lectura que valida acceso al servicio AWS requerido.

### Opción A: selección por tags

Archivo: `python_scripts/scheduler_tags/ec2_scheduler_tags.py`
Handler: `ec2_scheduler_tags.lambda_handler`

La Lambda busca instancias `running` para detener o `stopped` para iniciar y filtra por la clave y los valores de tag configurados.

Valida los requisitos específicos de EC2 y ejecuta las pruebas aisladas:

```bash
./python_scripts/scheduler_tags/setup.sh
python3 python_scripts/scheduler_tags/test_scripts.py
```

Las pruebas usan respuestas EC2 y CloudWatch simuladas; no llaman a AWS.

1. Empaqueta el código:

   ```bash
   cd python_scripts/scheduler_tags
   zip ec2_scheduler_tags.zip ec2_scheduler_tags.py
   cd ../..
   ```

2. Crea la función Lambda desde la consola de AWS o con AWS CLI. Usa el ZIP generado, el handler `ec2_scheduler_tags.lambda_handler` y configura estas variables:

   | Variable | Predeterminado | Descripción |
   | --- | --- | --- |
   | `AWS_REGION` | `us-east-1` | Región donde buscar instancias |
   | `TAG_KEY` | `Environment` | Clave de tag usada para seleccionar instancias |
   | `TAG_VALUES` | `Dev,dev,Development,Staging,staging` | Valores aceptados, separados por comas |

3. Crea dos reglas programadas de EventBridge dirigidas a la Lambda. Configura el input de una como `{"detail":{"accion":"stop"}}` y el de la otra como `{"detail":{"accion":"start"}}`. Autoriza a EventBridge a invocar la función.
4. Añade a las instancias que deben gestionarse el tag configurado. Ejemplo:

   ```bash
   aws ec2 create-tags \
     --resources i-0123456789abcdef0 \
     --tags Key=Environment,Value=Dev
   ```

**Permisos del rol Lambda:** `ec2:DescribeInstances`, `ec2:StartInstances`, `ec2:StopInstances`, `cloudwatch:PutMetricData` y permisos de escritura de logs de CloudWatch. Restringe los recursos siempre que el servicio lo permita.

### Opción B: registro en DynamoDB

Archivos:

- `python_scripts/scheduler_dynamo/ec2_scheduler_dynamo.py`: inicia y detiene instancias registradas.
- `python_scripts/scheduler_dynamo/ec2_auto_register.py`: registra instancias nuevas cuando se lanzan.

#### 1. Crear la tabla

Crea una tabla DynamoDB con clave de partición `InstanceId` de tipo `String`, sin clave de ordenación. El nombre predeterminado es `ControlHorariosEC2`.

Comprueba acceso a la tabla y a EC2 antes de desplegar:

```bash
./python_scripts/scheduler_dynamo/setup.sh
```

#### 2. Desplegar las funciones

Empaqueta cada archivo desde su directorio:

```bash
cd python_scripts/scheduler_dynamo
zip ec2_scheduler_dynamo.zip ec2_scheduler_dynamo.py
zip ec2_auto_register.zip ec2_auto_register.py
cd ../..
```

Despliega dos funciones Lambda, cada una con el ZIP y handler correspondientes:

- Scheduler: `ec2_scheduler_dynamo.lambda_handler`
- Auto-registro: `ec2_auto_register.lambda_handler`

Configura estas variables en el scheduler:

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Región de los recursos |
| `DYNAMODB_TABLE` | `ControlHorariosEC2` | Tabla con las instancias habilitadas |
| `SCHEDULE_NAME` | `20_to_05` | Valor de `Schedule` que procesa esta función |

Configura estas variables en la función de auto-registro:

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Región de los recursos |
| `DYNAMODB_TABLE` | `ControlHorariosEC2` | Tabla donde se registran las instancias |
| `DEFAULT_SCHEDULE` | `20_to_05` | Valor de `Schedule` asignado a las instancias nuevas |

#### 3. Configurar horarios y registros

Crea dos reglas programadas de EventBridge dirigidas a la función scheduler, con los inputs `{"detail":{"accion":"stop"}}` y `{"detail":{"accion":"start"}}`. Autoriza a EventBridge a invocar la función.

Para registrar automáticamente nuevas instancias, habilita CloudTrail y crea una regla de EventBridge para eventos de API de EC2 `RunInstances`. Dirige esa regla a la función de auto-registro y autoriza la invocación. Esta función registra las instancias nuevas con `DEFAULT_SCHEDULE`; no filtra por tags.

También puedes registrar una instancia manualmente. El scheduler procesa solo registros cuyo `Schedule` coincide con `SCHEDULE_NAME` y cuyo `Status` es `active`:

```bash
aws dynamodb put-item \
  --table-name ControlHorariosEC2 \
  --item '{"InstanceId":{"S":"i-0123456789abcdef0"},"Schedule":{"S":"20_to_05"},"Status":{"S":"active"}}'
```

**Permisos del scheduler:** `ec2:DescribeInstances`, `ec2:StartInstances`, `ec2:StopInstances`, `dynamodb:Scan`, `dynamodb:UpdateItem`, `cloudwatch:PutMetricData` y permisos de escritura de logs.
**Permisos del auto-registro:** `dynamodb:PutItem` y permisos de escritura de logs.

Prueba el scheduler y el registro automático sin AWS:

```bash
python3 python_scripts/scheduler_dynamo/test_scripts.py
```

Las pruebas mockean las respuestas de DynamoDB, EC2 y CloudWatch.

### Prueba y observabilidad

Antes de habilitar las reglas programadas, invoca la Lambda con una acción controlada y confirma el resultado. Las funciones publican logs en CloudWatch Logs; las funciones scheduler también envían métricas a CloudWatch. Verifica que la selección de instancias sea correcta antes de permitir operaciones sobre recursos de producción.

## Estructura del repositorio

```
sre-sysadmin-toolkit/
├── README.md
├── .gitignore
├── bash_scripts/
│   ├── log_rotation_s3.sh
│   ├── setup.sh
│   └── test_scripts.py
├── python_scripts/
│   ├── setup.sh
│   ├── scheduler_dynamo/
│   │   ├── ec2_auto_register.py
│   │   ├── ec2_scheduler_dynamo.py
│   │   ├── setup.sh
│   │   └── test_scripts.py
│   └── scheduler_tags/
│       ├── ec2_scheduler_tags.py
│       ├── setup.sh
│       └── test_scripts.py
```
