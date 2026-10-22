# SRE SysAdmin Toolkit

Herramientas independientes para automatizar tareas habituales de operación en AWS. Cada herramienta puede configurarse y desplegarse por separado.

## Herramientas

| Herramienta | Propósito | Implementación |
| --- | --- | --- |
| Rotación de logs | Comprime logs antiguos y los archiva en S3 | Bash |
| Backup selectivo de RDS | Exporta tablas MySQL críticas a un archivo comprimido y purga copias locales con más de siete días | Bash, AWS Secrets Manager y Ansible |
| Programación de instancias EC2 | Detiene instancias fuera del horario configurado y las inicia al comienzo de la jornada | AWS Lambda, con selección por tags o DynamoDB |
| Monitoring de instancias EC2 | Recopila métricas de sistema y ofrece dashboards y alertas por email | Prometheus, Grafana, Docker Compose y Ansible |
| Análisis de logs grandes | Resume solicitudes, errores 5xx, respuestas 404 y páginas más visitadas leyendo línea por línea | Python, solo biblioteca estándar |

## Requisitos comunes

- AWS CLI instalado y configurado para la cuenta y región objetivo.
- Permisos IAM limitados a las acciones indicadas en la guía de cada herramienta.
- Una política de horario acorde con la zona horaria del equipo. Las expresiones de EventBridge se interpretan en UTC.

Clona el repositorio:

```bash
git clone https://github.com/anibaljf1701/sre-sysadmin-toolkit.git
cd sre-sysadmin-toolkit
```

## Análisis de logs grandes

Script: `big-log-reader/big_log_file_reader.py`

Analiza logs de acceso grandes con un generador: lee y procesa una línea por vez, sin cargar el archivo completo en memoria. Informa el total de solicitudes, errores HTTP 5xx, respuestas 404, las tres rutas más solicitadas y la ruta con más errores. No requiere instalar dependencias externas ni importar paquetes de terceros; usa exclusivamente la biblioteca estándar de Python.

Ejecuta el script indicando un archivo de log existente:

```bash
python3 big-log-reader/big_log_file_reader.py /var/log/nginx/access.log
```

El parser espera líneas compatibles con el formato de access log de Apache que incluye la solicitud y el estado HTTP entre los campos habituales. El archivo se recorre en streaming, pero los contadores conservan una entrada por cada ruta distinta; por eso el uso de memoria no depende del tamaño total del log, aunque sí de la cardinalidad de rutas. La medición de memoria usa `tracemalloc` y añade algo de sobrecarga durante el análisis.

En el script quedaron comentados el generador de archivos sintéticos y la variante que guarda todas las solicitudes en una lista. Son ejemplos de prueba para comparar el comportamiento y el consumo de memoria, no forman parte del flujo normal. La idea original y parte del proyecto están inspiradas en [Daily Python Projects](https://dailypythonprojects.substack.com/).

## Rotación de logs en S3

Script: `log_rotation_s3/log_rotation_s3.sh`

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
./log_rotation_s3/setup.sh
```

El setup solo realiza comprobaciones de lectura; no crea recursos ni modifica archivos.

Haz ejecutable el script si el sistema de archivos no conserva el bit de ejecución:

```bash
chmod +x log_rotation_s3/log_rotation_s3.sh
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
./log_rotation_s3/log_rotation_s3.sh
```

Programa el comando con cron o con el scheduler de tu entorno. Una ejecución diaria suele ser suficiente; la decisión de rotar sigue dependiendo del umbral y del día semanal configurados. Los mensajes se guardan en `/tmp/log_rotation_YYYYMMDD.log`.

Para aplicar expiración real a los objetos archivados, configura una política de ciclo de vida en el bucket S3. `RETENTION_DAYS` por sí sola no elimina objetos.

### Permisos AWS

La identidad usada por AWS CLI necesita `s3:PutObject` sobre el prefijo de destino. Si se usa un perfil distinto al predeterminado, configura `AWS_PROFILE` antes de ejecutar el script.

### Pruebas

Ejecuta las pruebas desde la raíz del repositorio. Usan un directorio temporal y un comando `aws` simulado; no necesitan credenciales ni recursos AWS:

```bash
python3 log_rotation_s3/test_scripts.py
```

## Backup selectivo de RDS

Archivos: `mysql_table_backup/bd_table_backup.sh` y `mysql_table_backup/setup_bd_backup.yml`.

El playbook prepara un agente Jenkins Linux basado en Debian/Ubuntu: instala AWS CLI, `jq` y un cliente compatible con MySQL (`mysqldump`; según la distribución puede ser MariaDB), crea `/var/backups/rds`, instala el script y programa una purga diaria a las 03:00. Los archivos con al menos siete días completos se eliminan; la ejecución diaria puede hacer que permanezcan localmente hasta casi ocho días. El backup se ejecuta bajo demanda desde un stage de Jenkins y produce un dump comprimido de las tablas indicadas.

### Requisitos y configuración

- Un agente Jenkins Debian/Ubuntu con Ansible instalado en el controlador que ejecuta el playbook, inventario con el grupo `jenkins_agents` y un usuario existente llamado `jenkins`.
- Conectividad de red desde el agente al endpoint reader de RDS/Aurora MySQL y permisos de Security Group para MySQL (normalmente TCP 3306).
- Un rol de instancia o credenciales AWS disponibles para el usuario `jenkins`, con `secretsmanager:GetSecretValue` sobre el secreto. Si usa una clave KMS administrada por el cliente, también requiere `kms:Decrypt` sobre esa clave.
- Un secreto JSON de Secrets Manager con las claves `username`, `password`, `reader_endpoint` y `dbname`.
- El playbook usa `/var/backups/rds`; si se cambia `backup_dir`, debe coincidir con `BACKUP_DIR` usado al ejecutar el script.

Despliega la configuración desde la raíz del repositorio (ajusta la ruta del inventario):

```bash
ansible-playbook -i /path/to/inventory mysql_table_backup/setup_bd_backup.yml
```

El script requiere estas variables de entorno y falla antes del dump si falta alguna, una dependencia o un campo del secreto:

| Variable | Ejemplo | Descripción |
| --- | --- | --- |
| `SECRET_ID` | `production/rds/credentials` | Nombre o ARN del secreto de Secrets Manager |
| `REGION` | `us-east-1` | Región del secreto |
| `BACKUP_DIR` | `/var/backups/rds` | Directorio local, existente y escribible |
| `DB_TABLES` | `usuarios transacciones facturacion` | Tablas separadas por espacios |

En Jenkins, invoca el script después de verificar el agente y antes del despliegue. El agente debe obtener las credenciales AWS mediante su rol, no mediante claves incrustadas en el pipeline:

```groovy
stage('Backup tablas críticas') {
   steps {
      sh '''
         SECRET_ID=production/rds/credentials \
         REGION=us-east-1 \
         BACKUP_DIR=/var/backups/rds \
         DB_TABLES="usuarios transacciones facturacion" \
         /usr/local/bin/db_table_backup.sh
      '''
   }
}
```

El artefacto queda como `db_business_tables_<fecha>_<pid>.sql.gz` en el agente; este flujo no lo copia a S3 ni a otro almacenamiento durable. Para restaurar un archivo aprobado sobre el endpoint writer y la base de datos destino, el usuario MySQL necesita permisos para crear y modificar las tablas incluidas:

```bash
BACKUP_FILE=/var/backups/rds/db_business_tables_TIMESTAMP_PID.sql.gz
WRITER_ENDPOINT=your-writer-endpoint
RESTORE_USER=restore_user
DATABASE=your_database
gzip -dc "$BACKUP_FILE" | mysql -h "$WRITER_ENDPOINT" -u "$RESTORE_USER" -p "$DATABASE"
```

### Límites operativos

- Está dirigido a RDS MySQL/Aurora MySQL, no a PostgreSQL ni a servidores MariaDB. El script usa `mysqldump` y activa `--set-gtid-purged=OFF` solo cuando el cliente anuncia esa opción.
- `--single-transaction` da una vista consistente para tablas InnoDB mientras no se ejecuten cambios DDL concurrentes; motores no transaccionales no tienen esa garantía.
- Se consulta el reader endpoint, por lo que la réplica puede ir atrasada respecto del writer. Para un backup previo a un despliegue, confirma que ese retraso sea aceptable.
- Es un dump lógico de las tablas listadas, no una instantánea de RDS ni un rollback automático. La restauración puede reemplazar las tablas incluidas y requerir orden o coordinación por claves foráneas y cambios de esquema.
- El respaldo contiene datos sensibles. Protege el host y el directorio, limita quién puede restaurarlo y considera cifrado/almacenamiento externo si se necesita durabilidad o recuperación ante pérdida del agente.

## Programación de instancias EC2

Hay dos modalidades excluyentes para elegir las instancias objetivo. En ambas se despliega una Lambda para iniciar/detener instancias y se crean dos reglas programadas de EventBridge: una con `{"detail":{"accion":"stop"}}` y otra con `{"detail":{"accion":"start"}}`. Ajusta los horarios a tu jornada y a UTC.

Las Lambdas usan el runtime Python de AWS y `boto3`, disponible en el entorno Lambda. Empaqueta el archivo de la modalidad elegida en un ZIP y despliega una función con el handler indicado. Asigna a la función un rol de ejecución que permita escribir logs en CloudWatch y realizar las acciones EC2/DynamoDB correspondientes.

Ambos schedulers comparten los requisitos de Python 3.8 o superior, `boto3`, AWS CLI, credenciales válidas y región configurada. Compruébalos una vez:

```bash
./ec2_scheduler/setup.sh
```

Cada modalidad tiene además un setup de solo lectura que valida acceso al servicio AWS requerido.

#### Dependencias para desarrollo local

Las dependencias compartidas de los schedulers están declaradas en `ec2_scheduler/requirements.txt`. Instálalas en un entorno virtual antes de ejecutar o importar localmente los schedulers:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r ec2_scheduler/requirements.txt
./ec2_scheduler/setup.sh
```

Las pruebas usan `unittest` y mocks de los servicios AWS, por lo que no necesitan instalar `boto3`. Los paquetes Lambda descritos aquí incluyen el código de la función y usan el `boto3` provisto por el runtime de AWS; el archivo de requisitos es para ejecución local.

### Opción A: selección por tags

Archivo: `ec2_scheduler/for_tags/ec2_scheduler_tags.py`
Handler: `ec2_scheduler_tags.lambda_handler`

La Lambda busca instancias `running` para detener o `stopped` para iniciar y filtra por la clave y los valores de tag configurados.

Valida los requisitos específicos de EC2 y ejecuta las pruebas aisladas:

```bash
./ec2_scheduler/for_tags/setup_tags.sh
python3 ec2_scheduler/for_tags/test_tags.py
```

Las pruebas usan respuestas EC2 y CloudWatch simuladas; no llaman a AWS.

1. Empaqueta el código:

   ```bash
   cd ec2_scheduler/for_tags
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

- `ec2_scheduler/for_dynamodb/ec2_scheduler_dynamo.py`: inicia y detiene instancias registradas.
- `ec2_scheduler/for_dynamodb/ec2_auto_register.py`: registra instancias nuevas cuando se lanzan.

#### 1. Crear la tabla

Crea una tabla DynamoDB con clave de partición `InstanceId` de tipo `String`, sin clave de ordenación. El nombre predeterminado es `ControlHorariosEC2`.

Comprueba acceso a la tabla y a EC2 antes de desplegar:

```bash
./ec2_scheduler/for_dynamodb/setup_dynamo.sh
```

#### 2. Desplegar las funciones

Empaqueta cada archivo desde su directorio:

```bash
cd ec2_scheduler/for_dynamodb
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
python3 ec2_scheduler/for_dynamodb/test_dynamo.py
```

Las pruebas mockean las respuestas de DynamoDB, EC2 y CloudWatch.

### Prueba y observabilidad

Antes de habilitar las reglas programadas, invoca la Lambda con una acción controlada y confirma el resultado. Las funciones publican logs en CloudWatch Logs; las funciones scheduler también envían métricas a CloudWatch. Verifica que la selección de instancias sea correcta antes de permitir operaciones sobre recursos de producción.

## Monitoring de instancias EC2

La carpeta `monitoring/` levanta Prometheus y Grafana con Docker Compose. Prometheus recoge métricas de Node Exporter y Grafana aprovisiona un dashboard de CPU, RAM, disco y tráfico de red, además de alertas por CPU, RAM y disco superiores al 85% durante 5 minutos. El tráfico de red se muestra en bytes por segundo y no genera alertas porcentuales porque no se configura una capacidad de enlace de referencia.

### Requisitos y configuración

- Docker Engine con el plugin de Docker Compose.
- Instancias Linux accesibles por red desde el host de Prometheus e inventario Ansible para desplegar Node Exporter.
- Reglas de Security Group/NACL que permitan TCP 9100 desde el host de Prometheus a las instancias monitorizadas. No expongas el puerto 9100 a Internet.
- Un servidor SMTP y una dirección de correo de destino.

Desde el directorio `monitoring`, crea el archivo local de configuración y sustituye todos los valores de ejemplo, especialmente contraseñas, credenciales SMTP, destinatario, targets y entorno:

```bash
cd monitoring
cp .env.example .env
```

`PROMETHEUS_TARGETS` es una lista separada por comas de `host:puerto` (por ejemplo, IPs privadas o nombres DNS resolubles desde el contenedor). `ENVIRONMENT` etiqueta las series para distinguir entornos.

### Despliegue

Ejecuta el playbook desde `monitoring/` con el inventario de las instancias objetivo:

```bash
ansible-playbook -i /path/to/inventory ansible/install_node_exporter.yml
```

La arquitectura se detecta automáticamente para `x86_64` y `aarch64` (Node Exporter `amd64` y `arm64`). Inicia los contenedores:

```bash
docker compose up -d
```

Grafana queda disponible en `http://localhost:3000` (o el puerto definido en `GRAFANA_PORT`; credenciales definidas en `.env`) y Prometheus en `http://localhost:9090` (o el puerto de `PROMETHEUS_PORT`). Verifica en Prometheus que todos los targets estén `UP`, y en Grafana que el dashboard aparezca en la carpeta `Infrastructure`. Para probar correo, confirma que el servidor SMTP permita el envío y que `ALERT_EMAIL_TO` sea correcto.

Los puertos publicados por Compose escuchan en todas las interfaces por defecto. Limita el acceso a Grafana y Prometheus mediante firewall o security groups; si solo deben ser accesibles localmente, enlázalos a `127.0.0.1` o ponlos detrás de un proxy autenticado.

## Estructura del repositorio

```
sre-sysadmin-toolkit/
├── README.md
├── .gitignore
├── big-log-reader/
│   └── big_log_file_reader.py
├── ec2_scheduler/
│   ├── requirements.txt
│   ├── setup.sh
│   ├── for_dynamodb/
│   │   ├── ec2_auto_register.py
│   │   ├── ec2_scheduler_dynamo.py
│   │   ├── setup_dynamo.sh
│   │   └── test_dynamo.py
│   └── for_tags/
│       ├── ec2_scheduler_tags.py
│       ├── setup_tags.sh
│       └── test_tags.py
├── log_rotation_s3/
│   ├── log_rotation_s3.sh
│   ├── setup.sh
│   └── test_scripts.py
├── monitoring/
│   ├── ansible/
│   ├── grafana/
│   └── prometheus/
└── mysql_table_backup/
   ├── bd_table_backup.sh
   └── setup_bd_backup.yml
```
