# Documentación Detallada de Endpoints de la API ConneSkills

Este documento describe en detalle el flujo de ejecución de cada endpoint de la API de ConneSkills, basado en el análisis del código fuente. Cada sección explica paso a paso qué sucede cuando se invoca cada endpoint.

---

## 1. Endpoints de Gestión de Servicios (`/api/v1/services`)

### 1.1 `GET /api/v1/services` - Listar Servicios

**Propósito**: Obtener una lista de todos los servicios desplegados en Cloud Run, con capacidad de filtrado por diferentes criterios.

**Flujo de Ejecución**:

1. El endpoint recibe parámetros de consulta opcionales: `status` (estado del servicio), `type` (tipo de servicio), `category` (categoría: managed, external, customer), `customer` (prefijo del cliente), `limit` (límite de resultados), `offset` (para paginación), y `region` (región de GCP).

2. Si se proporcionan parámetros `category` o `customer`, el sistema utiliza el `ServiceRegistry` para obtener los servicios. Este registry consulta tanto los servicios de Cloud Run como los servicios externos registrados en Supabase.

3. Si no se proporcionan filtros de categoría o cliente, el sistema utiliza el `GCloudChecker` para listar servicios directamente desde Cloud Run.

4. Los servicios se transforman al formato `ServiceSummary` que incluye: nombre, tipo, estado, URL, timestamps de creación y actualización.

5. Se aplica la paginación según los parámetros `limit` y `offset`.

6. El sistema retorna un objeto `ServiceList` que contiene el array de servicios, el total de servicios disponibles, el límite usado y el offset aplicado.

**Casos de uso**: Consultar todos los servicios desplegados, filtrar por cliente específico, buscar servicios por estado (Running, Deploying, etc.), o por categoría (managed para servicios core, customer para servicios de clientes, external para servicios externos).

---

### 1.2 `POST /api/v1/services/deploy` - Desplegar Servicio

**Propósito**: Crear o actualizar un servicio en Google Cloud Run de forma directa, sin usar Terraform.

**Flujo de Ejecución**:

1. El endpoint recibe un objeto `ServiceDeployRequest` que contiene la configuración del servicio, incluyendo: nombre del servicio, configuración de Cloud Run (imagen, puerto, CPU, memoria, instancias), variables de entorno, secretos, y configuración de acceso.

2. Se extrae el nombre del servicio de la solicitud. Si no se proporciona, se retorna un error 400.

3. El sistema crea un trabajo (job) en Redis mediante el `job_manager` con la operación "deploy", el nombre del servicio, y la configuración completa. Esto retorna un `job_id` único.

4. Se programa la ejecución del deployment en background mediante `BackgroundTasks` de FastAPI, invocando la función `execute_direct_deployment`.

5. El trabajo de deployment (`execute_direct_deployment` en `direct_deployment.py`) realiza lo siguiente:
   - Conecta con Redis para actualizar el estado del job.
   - Verifica si el servicio ya existe en Cloud Run mediante el método `service_exists` del cliente de Cloud Run.
   - Si existe, llama a `update_service` para actualizar la configuración existente.
   - Si no existe, llama a `create_service` para crear el nuevo servicio.
   - En ambos casos, se configuran: imagen Docker, puerto, CPU, memoria, variables de entorno, secretos, escalado (instancias mínimas y máximas), cuenta de servicio, y políticas IAM (acceso público o privado).
   - El sistema aplica políticas IAM: si `allow_public_access` es true, permite acceso público mediante `allUsers`; de lo contrario, aplica política privada que permite acceso solo al dominio `conneskills.com` y a la cuenta de servicio `ai-agent-onboarding`.

6. Una vez completado el deployment, el servicio se persiste en Supabase mediante `SupabaseClient.upsert_service`, asociándolo al cliente correspondiente si aplica.

7. El endpoint retorna un `JobResponse` con el `job_id`, estado "queued", nombre del servicio, operación, timestamp de creación y tiempo estimado de 2-3 minutos.

**Consideraciones**: El deployment es asíncrono. El cliente debe polling el endpoint de jobs para conocer el estado final del deployment.

---

### 1.3 `GET /api/v1/services/{service_name}` - Obtener Información de Servicio

**Propósito**: Obtener información básica de un servicio específico desplegado en Cloud Run.

**Flujo de Ejecución**:

1. El endpoint recibe el `service_name` como parámetro de path y opcionalmente la `region` como query parameter.

2. Utiliza el `GCloudChecker` para obtener los detalles del servicio desde Cloud Run mediante el API de GCP.

3. Si el servicio no existe, retorna error 404.

4. El sistema extrae los metadatos del servicio: nombre, estado (basado en si tiene URL asignada), URL del servicio, región, y timestamps.

5. Retorna un objeto `ServiceInfo` con la información procesada.

---

### 1.4 `GET /api/v1/services/{service_name}/details` - Obtener Detalles Completos

**Propósito**: Obtener la configuración completa y detallada de un servicio, incluyendo variables de entorno, recursos, y el JSON raw de la respuesta de GCP.

**Flujo de Ejecución**:

1. Similar al endpoint anterior, pero con profundidad de análisis mayor.

2. Obtiene el servicio desde Cloud Run y extrae información adicional del spec y template:
   - Imagen Docker usada
   - Recursos asignados (CPU, memoria)
   - Configuración de escalado (containerConcurrency, traffic percent)
   - Variables de entorno (tanto regulares como de secretos)
   - Cuenta de servicio utilizada

3. Transforma toda esta información en un objeto `ServiceDetails` que incluye:
   - Datos básicos del servicio
   - Diccionario de variables de entorno
   - Configuración de recursos
   - JSON completo de la respuesta de GCP en el campo `raw`

**Casos de uso**: Depuración, auditoría de configuración, verificación de secretos montados en el servicio.

---

### 1.5 `GET /api/v1/services/{service_name}/logs` - Obtener Logs

**Propósito**: Retrieve los logs de un servicio específico desde Cloud Logging.

**Flujo de Ejecución**:

1. El endpoint recibe el `service_name`, `region` (opcional, default us-central1), y `limit` (número de líneas, default 100, máximo 1000).

2. Utiliza el `GCloudChecker` para obtener los logs mediante Cloud Logging API.

3. Transforma cada entrada de log en un objeto `LogEntry` que incluye: timestamp, severity (INFO, ERROR, WARNING, etc.), mensaje, y recurso asociado.

4. Retorna un objeto `ServiceLogs` con el nombre del servicio, total de entradas, y array de logs.

---

### 1.6 `PUT /api/v1/services/{service_name}` - Actualizar Servicio

**Propósito**: Actualizar la configuración de un servicio existente en Cloud Run.

**Flujo de Ejecución**:

1. El endpoint valida que el nombre del servicio en el path coincida con el nombre en el cuerpo de la solicitud.

2. Crea un job similar al de despliegue, pero con operación "update".

3. Ejecuta el mismo flujo de `execute_direct_deployment` en background, que detecta que el servicio ya existe y llama a `update_service` en lugar de `create_service`.

4. La actualización preserva la configuración existente no especificada en la solicitud (merge de variables de entorno, recursos, etc.).

5. Retorna un `JobResponse` con el job_id para seguimiento.

---

### 1.7 `DELETE /api/v1/services/{service_name}` - Eliminar Servicio

**Propósito**: Eliminar un servicio de Cloud Run de forma asíncrona.

**Flujo de Ejecución**:

1. El endpoint recibe el nombre del servicio a eliminar.

2. Crea un job con operación "undeploy" en el job_manager.

3. Ejecuta `execute_direct_undeploy` en background, que:
   - Verifica que el servicio exista
   - Llama al método `delete_service` del cliente de Cloud Run
   - Si la eliminación es exitosa, elimina el registro del servicio de Supabase

4. Retorna el job_id para seguimiento del proceso de eliminación.

---

### 1.8 `POST /api/v1/services/setup-image-build` - Configurar Build de Imagen

**Propósito**: Configurar el pipeline completo de construcción de imágenes Docker desde un repositorio GitHub, incluyendo Artifact Registry, Cloud Build y triggers.

**Flujo de Ejecución**:

1. El endpoint recibe un `ImageBuildRequest` que contiene: `image_name` (nombre de la imagen), `github_repo` (repositorio GitHub), `dockerfile_path` (ruta al Dockerfile), y `cloudbuild_path` (ruta al archivo de configuración de Cloud Build).

2. Crea un job con operación "setup-image-build" en el job_manager.

3. Ejecuta `execute_image_build_setup` en background, que realiza los siguientes pasos:

   **Paso 1 - Clonación del repositorio**:
   - Utiliza `GitUtils.clone_repo` para clonar el repositorio GitHub en un directorio temporal.
   - Verifica que el Dockerfile exista en la ruta especificada.

   **Paso 2 - Artifact Registry**:
   - Verifica si el repositorio de Artifact Registry ya existe mediante `repository_exists`.
   - Si no existe, lo crea con `create_repository`, especificando el formato DOCKER.

   **Paso 3 - Conexión del repositorio**:
   - Verifica si la conexión del repositorio existe en Cloud Build mediante `repository_exists`.
   - Si no existe, la crea con `create_repository_connection`, conectando el repositorio GitHub a GCP.

   **Paso 4 - Generación de cloudbuild.yaml**:
   - Genera automáticamente un archivo `cloudbuild.yaml` con la configuración de build:
     - Step 1: Build de la imagen Docker con tags de SHA del commit y "latest"
     - Step 2: Push de todas las tags a Artifact Registry
   -守护进程将文件写入仓库并通过GitUtils.commit_and_push推送 cambios.

   **Paso 5 - Creación del Trigger**:
   - Verifica si el trigger de Cloud Build ya existe mediante `trigger_exists`.
   - Si no existe, crea un trigger que escucha cambios en la rama main y ejecuta el cloudbuild.yaml.

   **Paso 6 - Build inicial**:
   - Intenta disparar un build inicial mediante `trigger_build`.
   - Si falla, registra una nota de que el trigger funcionará con el próximo push.

4. Retorna el job_id y la información de configuración creada (Artifact Registry URL, nombre del trigger, build_id si aplica).

**Tiempo estimado**: 3-5 minutos para completar toda la configuración.

---

### 1.9 `GET /api/v1/services/{service_name}/status` - Estado del Servicio

**Propósito**: Obtener el estado runtime de un servicio, incluyendo información de salud, instancias y uptime.

**Nota**: Este endpoint actualmente retorna datos mock (hardcodeados) en lugar de datos reales de GCP.

**Flujo de Ejecución**:

1. Busca el servicio en una lista mock interna de servicios.

2. Si encuentra el servicio, retorna un objeto con:
   - Nombre del servicio
   - Estado (basado en el mock)
   - Salud ("healthy")
   - Instancias (active, min, max)
   - Último deployment
   - Uptime

3. Si no encuentra el servicio, retorna error 404.

**Consideración**: Este endpoint debería modificarse para obtener datos reales de Cloud Run en lugar de datos mock.

---

### 1.10 `DELETE /api/v1/services/{service_name}/force` - Eliminación Forzada

**Propósito**: Eliminar un servicio sin validaciones, utilizado principalmente para limpieza de pruebas.

**Flujo de Ejecución**:

1. Intenta eliminar el servicio directamente mediante el cliente de Cloud Run.

2. Ignora cualquier error que pueda ocurrir durante la eliminación.

3. Retorna 204 No Content en todos los casos, sin importar si el servicio existía o no.

---

## 2. Endpoints de Servicios Externos (`/api/v1/external-services`)

### 2.1 `POST /api/v1/external-services` - Crear Servicio Externo

**Propósito**: Registrar un nuevo servicio externo (como PostgreSQL, Redis, etc.) en la plataforma, validando que los secretos referenciados existan en GCP Secret Manager.

**Flujo de Ejecución**:

1. El endpoint recibe un `ExternalServiceCreate` que incluye: `name` (nombre del servicio), `type` (tipo de servicio externo: postgres, mysql, redis, qdrant, neo4j, langfuse, supabase, etc.), `url` (URL de conexión), `cloud_console` (enlace a la consola del proveedor), `metadata` (metadatos adicionales), `secret_refs` (referencias a secretos en GCP), y `active` (si está activo).

2. El `ExternalServiceManager` valida que todos los secretos referenciados existan en GCP Secret Manager mediante el método `get_secret`. Si algún secreto no existe, lanza un error 400.

3. Obtiene los valores de los secretos para ejecutar un health check inicial.

4. Construye una configuración con el nombre, URL, valores de secretos y metadatos.

5. Obtiene el template correspondiente al tipo de servicio (PostgresTemplate, RedisTemplate, etc.) mediante `get_template`.

6. Ejecuta el health check del template para verificar la conectividad al servicio externo.

7. Inserta el registro del servicio en la tabla `external_services` de Supabase con todos los datos: nombre, tipo, URL, cloud_console, metadatos, referencias a secretos, estado de salud, timestamp del último health check, y flag de activo.

8. Retorna el `ExternalServiceResponse` con los datos creados incluyendo el ID generado.

**Tipos de servicios soportados**: POSTGRES, MYSQL, REDIS, MONGODB, QDRANT, NEO4J, LANGFUSE, LITELLM, OPENAI, ANTHROPIC, SUPABASE, JIRA.

---

### 2.2 `GET /api/v1/external-services` - Listar Servicios Externos

**Propósito**: Obtener una lista de los servicios externos registrados.

**Flujo de Ejecución**:

1. El endpoint acepta parámetros opcionales: `type` (filtrar por tipo de servicio) y `active_only` (default true, solo servicios activos).

2. Llama al método `list_services` del `ExternalServiceManager` que consulta la tabla `external_services` en Supabase.

3. Aplica los filtros de tipo y actividad si se especifican.

4. Transforma cada resultado en un objeto `ExternalServiceSummary` que contiene solo: id, name, y type.

5. Retorna un array de resúmenes.

---

### 2.3 `GET /api/v1/external-services/{service_id}` - Obtener Servicio Externo

**Propósito**: Obtener los detalles completos de un servicio externo específico.

**Flujo de Ejecución**:

1. Recibe el `service_id` como UUID en el path.

2. Llama al método `get_service` del manager que consulta Supabase por el ID.

3. Si no encuentra el servicio, retorna error 404.

4. Retorna el `ExternalServiceResponse` con todos los campos: id, name, type, url, cloud_console, metadata, secret_refs, active, health_status, last_health_check, timestamps.

---

### 2.4 `GET /api/v1/external-services/name/{name}` - Obtener por Nombre

**Propósito**: Buscar un servicio externo por su nombre en lugar de por ID.

**Flujo de Ejecución**:

1. Recibe el `name` como string en el path.

2. Llama al método `get_service_by_name` que consulta Supabase filtrando por el campo name.

3. Retorna el `ExternalServiceResponse` completo o 404 si no existe.

---

### 2.5 `PUT /api/v1/external-services/{service_id}` - Actualizar Servicio Externo

**Propósito**: Actualizar la configuración de un servicio externo registrado.

**Flujo de Ejecución**:

1. Recibe el `service_id` y un objeto `ExternalServiceUpdate` con los campos a actualizar: cloud_console, url, metadata, secret_refs, active.

2. Si se actualizan los secret_refs, valida que todos los nuevos secretos existan en GCP Secret Manager.

3. Actualiza el registro en Supabase con los campos proporcionados (usan do `model_dump(exclude_unset=True)` para solo actualizar los campos enviados).

4. Retorna el `ExternalServiceResponse` actualizado o 404 si no existe el servicio.

---

### 2.6 `GET /api/v1/external-services/{service_id}/details` - Detalles con Health Check

**Propósito**: Obtener detalles completos de un servicio externo incluyendo un health check en tiempo real.

**Flujo de Ejecución**:

1. Obtiene el servicio de Supabase por ID.

2. Ejecuta un health check en tiempo real mediante el método `health_check` del manager:
   - Obtiene los valores de los secretos asociados.
   - Construye la configuración.
   - Invoca el método `health_check` del template específico (PostgresTemplate, RedisTemplate, etc.).
   - El template intenta conectarse al servicio y verificar su estado.

3. Obtiene las operaciones disponibles para el tipo de servicio mediante `get_available_operations`:
   - Postgres: list_databases, execute_query, list_tables, create_database, drop_database, create_service_database
   - Redis: get_info, get_key, set_key, delete_key, list_keys
   - Qdrant: list_collections
   - Langfuse: list_projects
   - Etc.

4. Retorna un objeto `ExternalServiceDetails` que incluye: todos los datos del servicio, health_status actual, health_message, health_details (información adicional del health check), y available_operations (lista de operaciones disponibles).

---

### 2.7 `DELETE /api/v1/external-services/{service_id}` - Eliminar Servicio Externo

**Propósito**: Eliminar el registro de un servicio externo de la plataforma.

**Flujo de Ejecución**:

1. Recibe el `service_id` a eliminar.

2. Llama al método `delete_service` del manager que ejecuta un DELETE en Supabase.

3. Retorna 204 No Content si la eliminación fue exitosa, o 404 si el servicio no existía.

**Nota**: Este endpoint solo elimina el registro en la base de datos; no elimina el servicio externo real (como la base de datos en Neon), ya que podría estar siendo usado por otros sistemas.

---

### 2.8 `POST /api/v1/external-services/{service_id}/health` - Health Check Bajo Demanda

**Propósito**: Ejecutar un health check manual sobre un servicio externo.

**Flujo de Ejecución**:

1. Recibe el `service_id` del servicio a verificar.

2. Ejecuta el método `health_check` del manager (mismo proceso que en el endpoint de detalles).

3. Actualiza el estado de salud y el timestamp del último check en la base de datos.

4. Retorna el `HealthCheckResult` con: service_name, status (healthy/unhealthy/unknown), message, details, y checked_at.

---

### 2.9 `POST /api/v1/external-services/{service_id}/operations/{operation}` - Ejecutar Operación

**Propósito**: Ejecutar operaciones específicas del tipo de servicio externo, como crear bases de datos, ejecutar queries, etc.

**Flujo de Ejecución**:

1. Recibe el `service_id`, el nombre de la `operation` a ejecutar, y opcionalmente `params` (parámetros específicos de la operación).

2. Obtiene el servicio de Supabase y los valores de sus secretos.

3. Construye la configuración del template.

4. Invoca el método `execute_operation` del template correspondiente con la operación y parámetros.

5. Retorna el resultado de la operación específica.

**Ejemplos de operaciones**:
- Postgres: `create_database`, `drop_database`, `list_databases`, `execute_query`, `create_service_database`
- Redis: `get_key`, `set_key`, `delete_key`, `list_keys`
- MySQL: `create_database`, `drop_database`, `list_databases`, `execute_query`
- Qdrant: `list_collections`
- Neo4j: `execute_query`

---

### 2.10 `POST /api/v1/external-services/{service_id}/create_service_database` - Crear Base de Datos para Servicio

**Propósito**: Crear una base de datos dedicada para un servicio específico, con su propio usuario y contraseña, y almacenar las credenciales como secretos en GCP.

**Flujo de Ejecución**:

1. El endpoint recibe: `service_id` (ID del servicio PostgreSQL externo), `db_name` (nombre de la base de datos a crear), `service_name` (nombre del servicio que usará la DB), `customer_id` (opcional, UUID del cliente), y `password` (opcional, contraseña).

2. Crea un job con operación "create_service_database" en el job_manager.

3. Ejecuta `execute_create_service_database` en background que realiza:

   **Fase 1 - Validación y generación de credenciales**:
   - Si se proporciona customer_id, obtiene el prefijo del cliente de Supabase.
   - Si no se proporciona password, genera uno aleatorio de 16 caracteres.

   **Fase 2 - Creación de base de datos y usuario**:
   - Ejecuta la operación `create_service_database` en el template de PostgreSQL:
     - Crea la base de datos con el nombre especificado.
     - Crea un usuario con el mismo nombre que la base de datos.
     - Asigna la contraseña proporcionada.
     - Otorga todos los privilegios de la base de datos al usuario.
     - Concede permisos sobre el schema public.

   **Fase 3 - Extracción de host y construcción de cadena de conexión**:
   - Extrae el host de la URL del servicio externo usando regex.
   - Construye la cadena de conexión: `postgresql://{db_name}:{password}@{host}/{db_name}`.

   **Fase 4 - Creación de secretos en GCP**:
   - Determina el scope del secreto: GLOBAL si es para servicio core (sin customer_id), CUSTOMER si es para servicio de cliente.
   - Crea un secreto con la contraseña: `{service_name}-password` (core) o `{prefix}-{service_name}-password` (customer).
   - Crea un secreto con la cadena de conexión completa: `{service_name}-connection-string` (core) o `{prefix}-{service_name}-connection-string` (customer).

4. Completa el job con el resultado que incluye: database name, username, nombres de los secretos creados, y la cadena de conexión.

5. Retorna el job_id para seguimiento.

**Casos de uso**: Crear bases de datos dedicadas para servicios como Phoenix, Litellm, ZenML, o cualquier servicio que requiera PostgreSQL.

---

## 3. Endpoints de Gestión de Clientes (`/api/v1/customers`)

### 3.1 `POST /api/v1/customers` - Crear Cliente

**Propósito**: Crear un nuevo cliente en la plataforma, con opción de aprovisionar automáticamente portales de Jira, usuarios de LiteLLM, y servidores ZenML.

**Flujo de Ejecución**:

1. El endpoint recibe un objeto `CustomerCreate` que incluye:
   - `prefix`: Identificador único del cliente (ej: "acme", "globex")
   - `name`: Nombre descriptivo del cliente
   - `email`: Email del administrador del cliente
   - `create_jira_portal`: Boolean para crear proyecto Jira
   - `create_litellm`: Boolean para crear usuario y API key en LiteLLM
   - `create_zenml`: Boolean para desplegar servidor ZenML dedicado
   - `zenml_organization_id`: ID de organización ZenML (opcional)

2. Llama a `create_customer_with_portal` que:

   **Fase 1 - Creación del registro del cliente**:
   - Crea el registro del cliente en Supabase mediante `SupabaseClient.create_customer`.
   - Genera un UUID único para el cliente.

   **Fase 2 - Creación de jobs de provisioning**:
   - Si `create_jira_portal` es true: crea un job con operación "jira_provision".
   - Si `create_litellm` es true: crea un job con operación "litellm_provision".
   - Si `create_zenml` es true: crea un job con operación "zenml_provision".

3. Añade los jobs como tareas en background de FastAPI:
   - `execute_jira_provisioning`: Crea proyecto Jira, configura Service Desk, crea request types.
   - `execute_litellm_provisioning`: Crea usuario en LiteLLM, genera API key, almacena como secreto.
   - `execute_zenml_provisioning`: Crea base de datos en Aiven MySQL, despliega ZenML en Cloud Run, crea secretos.

4. Retorna la información del cliente creado más los IDs de los jobs de provisioning iniciados.

**Nota**: Los tres procesos de provisioning son asíncronos y se ejecutan en background. El cliente debe esperar a que completen o consultar el estado de los jobs.

---

### 3.2 `GET /api/v1/customers` - Listar Clientes

**Propósito**: Obtener una lista de todos los clientes registrados.

**Flujo de Ejecución**:

1. Acepta un parámetro opcional `active_only` (default false) para filtrar clientes activos.

2. Llama a `SupabaseClient.list_customers` que consulta la tabla `customers` en Supabase.

3. Retorna un array de objetos `CustomerResponse` con todos los campos del cliente: id, prefix, name, email, jira_project_key, jira_project_id, jira_sd_id, jira_group_id, litellm_user_id, litellm_api_key_secret, zenml_workspace_id, zenml_workspace_url, zenml_credentials_secret, timestamps.

---

### 3.3 `GET /api/v1/customers/{customer_id}` - Obtener Cliente por ID

**Propósito**: Obtener los detalles de un cliente específico.

**Flujo de Ejecución**:

1. Recibe el `customer_id` como UUID.

2. Llama a `SupabaseClient.get_customer` que consulta Supabase por ID.

3. Si no encuentra el cliente, retorna error 404.

4. Retorna el objeto `CustomerResponse` completo.

---

### 3.4 `GET /api/v1/customers/prefix/{prefix}` - Obtener Cliente por Prefijo

**Propósito**: Buscar un cliente por su prefijo único.

**Flujo de Ejecución**:

1. Recibe el `prefix` como string en el path.

2. Llama a `SupabaseClient.get_customer_by_prefix` que consulta Supabase filtrando por el campo prefix.

3. Retorna el `CustomerResponse` o 404 si no existe.

---

### 3.5 `GET /api/v1/customers/{customer_id}/portal` - Obtener Información del Portal Jira

**Propósito**: Obtener la información del portal de Jira Service Desk asociado a un cliente.

**Flujo de Ejecución**:

1. Recibe el `customer_id` del cliente.

2. Obtiene el cliente de Supabase para verificar si tiene un Jira SD configurado (campo `jira_sd_id`).

3. Si el cliente no tiene portal Jira, retorna error 404.

4. Construye la URL del portal usando la configuración de Jira: `{JIRA_BASE_URL}/servicedesk/customer/portal/{jira_sd_id}`.

5. Retorna un objeto con: customer_id, jira_project_key, jira_sd_id, y portal_url.

---

### 3.6 `GET /api/v1/customers/{customer_id}/services` - Obtener Servicios del Cliente

**Propósito**: Listar todos los servicios desplegados que pertenecen a un cliente específico.

**Flujo de Ejecución**:

1. Recibe el `customer_id` del cliente.

2. Obtiene el cliente para pre verificar sufijo.

3. Llama a `SupabaseClient.get_services_by_customer` que filtra los servicios por el customer_id en Supabase.

4. Retorna un objeto con: customer_id y array de servicios asociados.

---

### 3.7 `PUT /api/v1/customers/{customer_id}` - Actualizar Cliente

**Propósito**: Actualizar la información de un cliente existente.

**Flujo de Ejecución**:

1. Recibe el `customer_id` y un objeto `CustomerUpdate` con los campos a actualizar.

2. Los campos actualizables incluyen: name, email, jira_project_key, jira_project_id, jira_sd_id, jira_group_id, litellm_user_id, litellm_api_key_secret, zenml_workspace_id, zenml_workspace_url, zenml_credentials_secret.

3. Llama a `SupabaseClient.update_customer` que ejecuta el UPDATE en Supabase.

4. Retorna el `CustomerResponse` actualizado o 404 si el cliente no existe.

---

### 3.8 `DELETE /api/v1/customers/{customer_id}` - Eliminar Cliente

**Propósito**: Eliminar un cliente y todos los recursos asociados (proyecto Jira, usuario LiteLLM, servicio ZenML, secretos).

**Flujo de Ejecución**:

1. Obtiene el cliente de Supabase para identificar los recursos aprovisionados.

2. **Eliminación de proyecto Jira** (si existe):
   - Si el cliente tiene `jira_project_key`, usa el `JiraClient` para eliminar el proyecto Jira.

3. **Eliminación de usuario LiteLLM** (si existe):
   - Si el cliente tiene `litellm_user_id`, usa el `LiteLLMClient` para eliminar el usuario de LiteLLM.

4. **Eliminación de servicio ZenML** (si existe):
   - Si el cliente tiene `zenml_workspace_id`, usa el cliente de Cloud Run para eliminar el servicio ZenML de Cloud Run.

5. **Eliminación de secretos**:
   - Elimina el secreto de API key de LiteLLM.
   - Elimina el secreto de credenciales de ZenML.
   - Elimina el secreto de contraseña de admin de ZenML.

6. **Eliminación del registro del cliente**:
   - Ejecuta `SupabaseClient.delete_customer` para eliminar el registro.

7. Retorna 204 No Content si todo fue exitoso.

---

## 4. Endpoints de Gestión de Agentes (`/api/v1/agents`)

### 4.1 `POST /api/v1/agents/deploy` - Desplegar Agente

**Propósito**: Desplegar un agente de IA como servicio en Cloud Run para un cliente específico.

**Flujo de Ejecución**:

1. El endpoint recibe un `AgentDeployRequest` que incluye:
   - `customer_id`: UUID del cliente que poseerá el agente
   - `agent_name`: Nombre del agente (ej: "researcher", "assistant")
   - `prompt_ref`: Referencia al prompt en LiteLLM
   - `image`: Imagen Docker del agente
   - `default_model`: Modelo de IA por defecto (ej: "gpt-4o", "claude-3-5-sonnet-20241022")
   - `cpu`: CPU dedicado (default "1")
   - `memory`: Memoria (default "512Mi")
   - `port`: Puerto del contenedor (default 9100)
   - `min_instances`: Instancias mínimas
   - `max_instances`: Instancias máximas
   - `allow_public_access`: Si el agente será accesible públicamente

2. El flujo en `agent_deployment.py` realiza las siguientes validaciones y operaciones:

   **Fase 1 - Validación del cliente**:
   - Verifica que el cliente exista en Supabase.
   - Obtiene el prefijo del cliente.
   - Obtiene el litellm_user_id del cliente.

   **Fase 2 - Generación del nombre del servicio**:
   - Construye el nombre del servicio en formato: `{prefix}-{agent_name}` (ej: "acme-researcher").

   **Fase 3 - Verificar que no exista**:
   - Consulta Cloud Run para verificar que el servicio no exista previamente.
   - Si existe, retorna error 409 (conflicto).

   **Fase 4 - Validar referencia del prompt**:
   - Llama a `litellm_client.get_prompt(prompt_ref)` para verificar que el prompt exista en LiteLLM.
   - Si no existe, retorna error 400.

   **Fase 5 - Obtener o crear API key en LiteLLM**:
   - Busca una API key existente para el agente en el usuario de LiteLLM del cliente.
   - Si no existe, genera una nueva API key mediante `litellm_client.generate_api_key` con alias `{prefix}-{agent_name}`.

   **Fase 6 - Crear secreto en GCP**:
   - Crea un secreto en GCP Secret Manager con la API key: `{prefix}-{agent_name}-litellm-key`.
   - Si el secreto ya existe, actualiza su valor.

   **Fase 7 - Construir variables de entorno**:
   - AGENT_NAME: Nombre del agente
   - AGENT_ROLE: Rol del agente
   - PROMPT_REF: Referencia al prompt
   - DEFAULT_MODEL: Modelo por defecto
   - LITELLM_URL: URL de LiteLLM (https://litellm.conneskills.com)
   - AGENT_PORT: Puerto del contenedor

   **Fase 8 - Desplegar en Cloud Run**:
   - Utiliza el cliente de Cloud Run para crear el servicio:
     - Monta el secreto de API key de LiteLLM como variable de entorno.
     - Configura CPU, memoria, escalado.
     - Aplica políticas IAM según allow_public_access.
     - Usa la cuenta de servicio `ai-agent-onboarding@{project}.iam.gserviceaccount.com`.

   **Fase 9 - Obtener URL del servicio**:
   - Recupera la URL pública del servicio desplegado.

3. Retorna un `AgentResponse` con: service_name, service_url, status (RUNNING), agent_name, customer_id, y message de éxito.

**Consideraciones importantes**:
- Este flujo NO registra el agente en un "cs-agent-registry" como se mencionó en la descripción conceptual.
- El agente NO se registra como modelo en LiteLLM.
- El agente NO hace GET/PATCH a ningún registry al iniciar.

---

### 4.2 `GET /api/v1/agents/prompts` - Listar Prompts Disponibles

**Propósito**: Obtener la lista de prompts disponibles en LiteLLM para validar referencias antes del deployment.

**Flujo de Ejecución**:

1. El endpoint usa el `LiteLLMClient` para llamar a la API de LiteLLM.

2. Invoca el método `list_prompts` que hace un GET a `/prompts/list` en el proxy de LiteLLM.

3. Retorna un array de objetos con los prompts disponibles.

**Casos de uso**: Antes de desplegar un agente, el cliente puede consultar qué prompts están disponibles para usar como `prompt_ref`.

---

### 4.3 `GET /api/v1/agents/{service_name}` - Obtener Agente

**Propósito**: Obtener los detalles de un agente desplegado.

**Flujo de Ejecución**:

1. Recibe el `service_name` del agente en el path.

2. Consulta Cloud Run para obtener los detalles del servicio.

3. Si no existe, retorna error 404.

4. Extrae el nombre del agente del nombre del servicio (quitando el prefijo del cliente).

5. Retorna un `AgentResponse` con: service_name, service_url, status, agent_name, customer_id (usando un UUID placeholder ya que no se persiste en el deployment).

---

### 4.4 `DELETE /api/v1/agents/{service_name}` - Eliminar Agente

**Propósito**: Eliminar un agente desplegado.

**Flujo de Ejecución**:

1. Recibe el `service_name` del agente a eliminar.

2. Intenta eliminar el servicio de Cloud Run.

3. Retorna 204 No Content si fue exitoso, o 500 si falló.

**Nota**: Este endpoint no elimina el secreto asociado ni la API key en LiteLLM. Debería implementarse cleanup de estos recursos.

---

## 5. Endpoints de Gestión de Secretos (`/api/v1/secrets`)

### 5.1 `POST /api/v1/secrets` - Crear Secreto

**Propósito**: Crear un nuevo secreto en GCP Secret Manager.

**Flujo de Ejecución**:

1. El endpoint recibe un `SecretCreateRequest` que incluye:
   - `scope`: Enum (GLOBAL, EXTERNAL, CUSTOMER, MANAGED)
   - `key`: Nombre del secreto (patrón: ^[a-z0-9-]+$)
   - `value`: Valor del secreto
   - `customer`: Prefijo del cliente (requerido si scope es CUSTOMER)
   - `service`: Nombre del servicio (requerido si scope es EXTERNAL o MANAGED)

2. El modelo valida que:
   - Si scope es CUSTOMER, debe proporcionar customer.
   - Si scope es EXTERNAL o MANAGED, debe proporcionar service.

3. El `gcp_secret_manager.create_secret`:
   - Construye el nombre completo del secreto según el scope y parámetros:
     - GLOBAL: `{key}`
     - CUSTOMER: `{customer}-{key}`
     - EXTERNAL: `external-{service}-{key}`
     - MANAGED: `managed-{service}-{key}`
   - Crea el secreto en GCP Secret Manager.
   - Añade la primera versión con el valor.
   - Retorna metadatos del secreto creado.

4. Retorna un `SecretResponse` con: name, scope, labels, created_at, updated_at.

---

### 5.2 `GET /api/v1/secrets` - Listar Secretos

**Propósito**: Listar secretos con filtros opcionales.

**Flujo de Ejecución**:

1. Acepta parámetros de filtro:
   - `scope`: Filtrar por scope (global, external, customer, managed)
   - `customer`: Filtrar por prefijo de cliente
   - `service`: Filtrar por nombre de servicio

2. Llama a `gcp_secret_manager.list_secrets` que:
   - Lista todos los secretos del proyecto en GCP Secret Manager.
   - Filtra según los parámetros proporcionados.

3. Retorna un array de `SecretResponse`.

---

### 5.3 `GET /api/v1/secrets/{secret_name}` - Obtener Metadatos del Secreto

**Propósito**: Obtener los metadatos de un secreto específico sin revelar su valor.

**Flujo de Ejecución**:

1. Recibe el `secret_name` en el path.

2. Llama a `gcp_secret_manager.get_secret` que consulta GCP Secret Manager.

3. Si no existe, retorna error 404.

4. Retorna `SecretResponse` (sin el valor).

---

### 5.4 `GET /api/v1/secrets/{secret_name}/value` - Obtener Valor del Secreto

**Propósito**: Obtener el valor actual de un secreto.

**Flujo de Ejecución**:

1. Recibe el `secret_name` en el path.

2. Llama a `gcp_secret_manager.get_secret_value` que:
   - Accede a la versión "latest" del secreto.
   - Retorna el valor desencriptado.

3. Si no existe, retorna error 404.

4. Retorna `SecretValueResponse` con: name y value.

**Advertencia**: Este endpoint expone el valor del secreto. Debe protegerse appropriately en producción.

---

### 5.5 `PUT /api/v1/secrets/{secret_name}` - Actualizar Secreto

**Propósito**: Actualizar el valor de un secreto existente.

**Flujo de Ejecución**:

1. Recibe el `secret_name` y un `SecretUpdateRequest` con el nuevo `value`.

2. Verifica que el secreto exista mediante `get_secret`.

3. Añade una nueva versión del secreto con el nuevo valor mediante `update_secret`.

4. Retorna el `SecretResponse` actualizado.

---

### 5.6 `DELETE /api/v1/secrets/{secret_name}` - Eliminar Secreto

**Propósito**: Eliminar un secreto de GCP Secret Manager.

**Flujo de Ejecución**:

1. Recibe el `secret_name` a eliminar.

2. Llama a `gcp_secret_manager.delete_secret` que elimina el secreto y todas sus versiones.

3. Retorna 204 No Content si fue exitoso, o 404 si no existía.

---

## 6. Endpoints de Gestión de Trabajos (`/api/v1/jobs`)

### 6.1 `GET /api/v1/jobs/{job_id}` - Obtener Estado del Trabajo

**Propósito**: Consultar el estado de un trabajo asíncrono (deployment, provisioning, etc.).

**Flujo de Ejecución**:

1. Recibe el `job_id` del trabajo a consultar.

2. Llama a `job_manager.get_job` que recupera el trabajo de Redis.

3. Si no existe, retorna error 404.

4. Calcula la duración del trabajo si ya completó (diferencia entre completed_at y started_at).

5. Retorna un objeto con:
   - job_id, status, operation, service_name
   - progress (porcentaje), current_phase
   - timestamps: started_at, completed_at, created_at
   - duration (en segundos si completó)
   - result (datos de resultado si completó)
   - error (mensaje de error si falló)
   - logs_url (enlace a los logs del job)

---

### 6.2 `GET /api/v1/jobs/{job_id}/logs` - Obtener Logs del Trabajo

**Propósito**: Obtener los logs de un trabajo específico.

**Flujo de Ejecución**:

1. Recibe el `job_id` y opcionalmente `lines` (número de líneas, default 100, max 10000).

2. Recupera el trabajo de Redis.

3. Si no existe, retorna error 404.

4. Retorna las últimas N líneas de los logs almacenados en el trabajo.

5. El formato de cada entrada de log incluye timestamp ISO: `[2026-02-19T10:30:00] Mensaje de log`.

---

### 6.3 `POST /api/v1/jobs/{job_id}/cancel` - Cancelar Trabajo

**Propósito**: Cancelar un trabajo que está en ejecución.

**Flujo de Ejecución**:

1. Recibe el `job_id` del trabajo a cancelar.

2. Verifica que el trabajo exista y no esté ya completado o fallido.

3. Actualiza el estado del trabajo a CANCELLED.

4. Retorna confirmación del cancelado.

**Nota**: La cancelación efectiva depende de si la tarea en background está implementada para respetar señales de cancelación.

---

### 6.4 `GET /api/v1/jobs` - Listar Trabajos

**Propósito**: Listar trabajos con filtros opcionales.

**Flujo de Ejecución**:

1. Acepta parámetros de filtro:
   - `service_name`: Filtrar por nombre de servicio
   - `status`: Filtrar por estado (queued, running, completed, failed, cancelled)
   - `limit`: Límite de resultados (default 50, max 100)

2. Llama a `job_manager.list_jobs` que:
   - Escanea todas las claves de jobs en Redis.
   - Aplica los filtros proporcionados.
   - Ordena por created_at descendente.
   - Limita los resultados.

3. Retorna un objeto con: array de jobs (con campos seleccionados) y total.

---

## 7. Resumen de Endpoints por Categoría

| Categoría | Endpoint | Método | Propósito |
|-----------|----------|--------|-----------|
| **Servicios** | /services | GET | Listar servicios |
| | /services/deploy | POST | Desplegar servicio |
| | /services/{name} | GET | Obtener servicio |
| | /services/{name}/details | GET | Obtener detalles completos |
| | /services/{name}/logs | GET | Obtener logs |
| | /services/{name} | PUT | Actualizar servicio |
| | /services/{name} | DELETE | Eliminar servicio |
| | /services/setup-image-build | POST | Configurar build de imagen |
| | /services/{name}/status | GET | Obtener estado runtime |
| | /services/{name}/force | DELETE | Eliminación forzada |
| **Servicios Externos** | /external-services | POST | Crear servicio externo |
| | /external-services | GET | Listar servicios externos |
| | /external-services/{id} | GET | Obtener servicio externo |
| | /external-services/name/{name} | GET | Obtener por nombre |
| | /external-services/{id} | PUT | Actualizar servicio |
| | /external-services/{id}/details | GET | Detalles con health check |
| | /external-services/{id} | DELETE | Eliminar servicio |
| | /external-services/{id}/health | POST | Health check bajo demanda |
| | /external-services/{id}/operations/{op} | POST | Ejecutar operación |
| | /external-services/{id}/create_service_database | POST | Crear base de datos |
| **Clientes** | /customers | POST | Crear cliente |
| | /customers | GET | Listar clientes |
| | /customers/{id} | GET | Obtener cliente |
| | /customers/prefix/{prefix} | GET | Obtener por prefijo |
| | /customers/{id}/portal | GET | Info del portal Jira |
| | /customers/{id}/services | GET | Servicios del cliente |
| | /customers/{id} | PUT | Actualizar cliente |
| | /customers/{id} | DELETE | Eliminar cliente |
| **Agentes** | /agents/deploy | POST | Desplegar agente |
| | /agents/prompts | GET | Listar prompts |
| | /agents/{service_name} | GET | Obtener agente |
| | /agents/{service_name} | DELETE | Eliminar agente |
| **Secretos** | /secrets | POST | Crear secreto |
| | /secrets | GET | Listar secretos |
| | /secrets/{name} | GET | Obtener metadatos |
| | /secrets/{name}/value | GET | Obtener valor |
| | /secrets/{name} | PUT | Actualizar secreto |
| | /secrets/{name} | DELETE | Eliminar secreto |
| **Trabajos** | /jobs/{id} | GET | Obtener estado |
| | /jobs/{id}/logs | GET | Obtener logs |
| | /jobs/{id}/cancel | POST | Cancelar trabajo |
| | /jobs | GET | Listar trabajos |

---

*Documento generado el 19 de febrero de 2026*
*Proyecto: ConneSkills AI Platform API*
