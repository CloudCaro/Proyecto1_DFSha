# DFSha – Sistema de Archivos Distribuidos

**Proyecto 1 – Sistemas Distribuidos**

DFSha es un sistema de archivos distribuidos desarrollado como proyecto académico para la asignatura de Sistemas Distribuidos. Su propósito es permitir el almacenamiento, organización, consulta y recuperación de archivos mediante una arquitectura distribuida que utiliza un nodo central de coordinación y múltiples nodos de almacenamiento.

El sistema implementa particionamiento de archivos, replicación de bloques, gestión de metadatos, control de concurrencia y mecanismos de seguridad para proteger la información almacenada.

---

## 1. Arquitectura del sistema

DFSha utiliza una arquitectura cliente-servidor compuesta por los siguientes elementos:

- **Cliente:** interfaz de línea de comandos (CLI) desde la cual los usuarios ejecutan las operaciones del sistema.
- **NameNode:** componente central encargado de gestionar los metadatos, autenticar usuarios, coordinar las operaciones y administrar la distribución de bloques.
- **DataNodes:** nodos encargados de almacenar físicamente los bloques de información y atender las solicitudes coordinadas por el NameNode.

La implementación utiliza Docker Compose para desplegar cuatro servicios independientes:

| Componente | Función |
|---|---|
| NameNode | Coordinación y administración de metadatos. |
| DataNode 1 | Almacenamiento de bloques y réplicas. |
| DataNode 2 | Almacenamiento de bloques y réplicas. |
| DataNode 3 | Almacenamiento de bloques y réplicas. |

### Características principales

- Particionamiento de archivos en bloques de **4 MiB**.
- Factor de replicación de **2**.
- Distribución de bloques entre diferentes DataNodes.
- Gestión de metadatos mediante SQLite.
- Comunicación entre componentes mediante HTTP y API REST.
- Verificación de integridad mediante SHA-256.
- Cifrado de bloques en reposo mediante AES-256-GCM.
- Autenticación mediante JWT y almacenamiento de contraseñas con bcrypt.
- Control de concurrencia mediante bloqueos exclusivos.
- Detección de disponibilidad de DataNodes mediante heartbeats.
- Recuperación de réplicas para bloques con redundancia insuficiente.

---

## 2. Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| Python 3.12 | Lenguaje de programación. |
| FastAPI | Implementación de los servicios y API REST. |
| Uvicorn | Servidor de aplicaciones. |
| SQLite | Almacenamiento de metadatos. |
| SQLAlchemy | Gestión de persistencia y modelos de datos. |
| Docker | Contenedorización de los servicios. |
| Docker Compose | Despliegue y administración de los contenedores. |
| HTTPX / Requests | Comunicación entre componentes. |
| PyJWT | Gestión de tokens de autenticación. |
| bcrypt | Protección de contraseñas. |
| Cryptography | Cifrado AES-256-GCM. |
| SHA-256 | Verificación de integridad de los bloques y archivos. |

---

## 3. Estructura del repositorio

```text
Proyecto1_DFSha/
│
├── client/
│   ├── commands.py
│   ├── main.py
│   ├── file_manager.py
│   ├── block_manager.py
│   ├── namenode_client.py
│   ├── datanode_client.py
│   └── security.py
│
├── namenode/
│   ├── app/
│   │   ├── routes/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── metadata.py
│   │   ├── models.py
│   │   ├── replication.py
│   │   ├── scheduler.py
│   │   └── security.py
│   └── Dockerfile
│
├── datanode/
│   ├── app/
│   │   ├── config.py
│   │   ├── heartbeat.py
│   │   ├── main.py
│   │   ├── routes.py
│   │   └── storage.py
│   └── Dockerfile
│
├── test/
│   ├── test_datanode.py
│   └── test_scheduler.py
│
├── storage/
│   ├── DN1/
│   ├── DN2/
│   └── DN3/
│
├── docker-compose.yml
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 4. Requisitos previos

Para ejecutar el proyecto se requiere:

- Python 3.12.
- Docker.
- Docker Compose.
- Git.
- Una terminal compatible con los comandos del sistema operativo.

Se recomienda utilizar Docker Desktop en Windows o Docker Engine y Docker Compose en Linux.

---

## 5. Instalación y configuración

### 5.1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd Proyecto1_DFSha
```

### 5.2. Crear las carpetas de almacenamiento

Se deben crear los directorios correspondientes a los tres DataNodes:

```bash
mkdir -p storage/DN1 storage/DN2 storage/DN3
```

También se debe preparar el archivo de base de datos del NameNode:

```bash
mkdir -p namenode
touch namenode/dfsha.db
```

### 5.3. Configurar las variables de entorno

El proyecto utiliza un archivo `.env` ubicado en la raíz del repositorio para almacenar las claves necesarias para la autenticación y el cifrado.

Crear el archivo `.env` con las siguientes variables:

```env
JWT_SECRET_KEY=CLAVE_SECRETA_JWT
AES_KEY=CLAVE_AES_EN_BASE64
```

Ambas claves deben generarse de forma segura:

- `JWT_SECRET_KEY`: clave secreta utilizada para firmar los tokens JWT.
- `AES_KEY`: clave de 32 bytes codificada en Base64, utilizada para el cifrado AES-256-GCM.

Para generar automáticamente ambas claves mediante Python, ejecutar desde la raíz del proyecto:

```bash
python -c "import secrets,base64,pathlib; p=pathlib.Path('.env'); p.exists() or p.write_text('JWT_SECRET_KEY='+secrets.token_urlsafe(48)+'\nAES_KEY='+base64.b64encode(secrets.token_bytes(32)).decode()+'\n')"
```

Este comando crea el archivo únicamente si todavía no existe.

**Importante:** el archivo `.env` contiene información sensible. No debe publicarse en GitHub ni compartirse públicamente. Cada entorno debe utilizar sus propias claves. Si se cambian las claves después de almacenar información, se deben considerar los datos cifrados existentes antes de realizar el cambio.

---

## 6. Ejecución del sistema

### 6.1. Construir y levantar los servicios

Desde la raíz del repositorio, ejecutar:

```bash
docker compose up -d --build
```

Este comando construye las imágenes y levanta los cuatro contenedores:

- `dfsha-namenode`
- `dfsha-dn1`
- `dfsha-dn2`
- `dfsha-dn3`

### 6.2. Verificar el estado de los contenedores

```bash
docker compose ps
```

Los servicios deben aparecer en estado `Up`.

Para consultar los registros de ejecución:

```bash
docker compose logs -f
```

Para consultar los registros de un servicio específico:

```bash
docker compose logs -f namenode
```

### 6.3. Verificar el NameNode

Una vez iniciado el sistema, la documentación interactiva de la API REST puede consultarse desde un navegador:

```text
http://localhost:8000/docs
```

También se puede comprobar el estado de los DataNodes mediante el endpoint:

```text
http://localhost:8000/datanodes/
```

---

## 7. Ejecución del cliente

El cliente funciona mediante una interfaz de línea de comandos.

Antes de iniciarlo, se debe configurar la dirección del NameNode.

**En Windows PowerShell:**

```powershell
$env:NAMENODE_URL = "http://localhost:8000"
```

**En Linux o macOS:**

```bash
export NAMENODE_URL="http://localhost:8000"
```

Después, desde la raíz del repositorio, ejecutar:

```bash
python -m client.main
```

El cliente mostrará el nombre del sistema, la dirección del NameNode y el indicador de comandos:

```text
DFSha>
```

Si el cliente se ejecuta desde otro equipo, se debe reemplazar `localhost` por la dirección IP o el nombre de host del equipo donde se encuentra desplegado el NameNode.

---

## 8. Comandos disponibles

El sistema proporciona las siguientes operaciones mediante la CLI:

| Comando | Descripción |
|---|---|
| `help` | Muestra los comandos disponibles. |
| `register <usuario> <contraseña>` | Registra un usuario. |
| `login <usuario> <contraseña>` | Inicia sesión. |
| `logout` | Cierra la sesión. |
| `ls` | Lista los archivos y directorios disponibles para el usuario. |
| `cd <ruta>` | Cambia el directorio actual. |
| `mkdir <nombre>` | Crea un directorio. |
| `rmdir <directory_id>` | Elimina un directorio mediante su identificador. |
| `put <ruta_local>` | Sube un archivo al sistema distribuido. |
| `get <file_id> [destino]` | Recupera un archivo. |
| `rm <file_id>` | Elimina un archivo mediante su identificador. |
| `open <file_id> <r\|w>` | Abre un archivo en modo lectura o escritura. |
| `lock` | Adquiere el bloqueo exclusivo del archivo abierto. |
| `unlock` | Libera el bloqueo del archivo. |
| `write <ruta_local>` | Reemplaza el contenido del archivo distribuido utilizando un archivo local. |
| `read [offset] [length]` | Lee el contenido del archivo abierto, indicando opcionalmente el desplazamiento y la longitud. |
| `close` | Cierra la sesión de acceso al archivo. |
| `exit` | Finaliza el cliente. |

### Ejemplo de uso

```text
register usuario1 contraseña
login usuario1 contraseña

mkdir documentos
ls

put archivo.txt
get 1 archivo_recuperado.txt

open 1 r
read
close

exit
```

Para realizar una escritura:

```text
open 1 w
lock
write archivo_actualizado.txt
close
```

La operación `write` utiliza un archivo local como fuente y reemplaza completamente el contenido del archivo distribuido. No implementa edición parcial ni anexado de contenido.

Los bloqueos son exclusivos y tienen un tiempo de expiración de 30 segundos. Se recomienda liberar el bloqueo explícitamente cuando se termine la operación.

---

## 9. Pruebas

El proyecto contempla pruebas orientadas a verificar el funcionamiento de sus principales componentes y requisitos:

- Registro y autenticación de usuarios.
- Creación y consulta de directorios.
- Subida y recuperación de archivos.
- Particionamiento de archivos en bloques.
- Verificación de integridad mediante SHA-256.
- Replicación de bloques entre DataNodes.
- Operaciones OPEN, READ, WRITE y CLOSE.
- Control de concurrencia mediante bloqueos exclusivos.
- Detección de indisponibilidad de DataNodes.
- Recuperación de réplicas.
- Protección de acceso entre usuarios.
- Verificación del almacenamiento cifrado.

Los archivos de pruebas automatizadas se encuentran en el directorio `test/`.

Para ejecutar las pruebas disponibles:

```bash
python -m pytest test/ -v
```

---

## 10. Despliegue y consideraciones de seguridad

Los servicios se ejecutan en contenedores Docker conectados mediante una red virtual tipo bridge.

La configuración contempla los siguientes puertos:

| Servicio | Puerto interno |
|---|---:|
| NameNode | 8000 |
| DataNode 1 | 8001 |
| DataNode 2 | 8001 |
| DataNode 3 | 8001 |

En el archivo Docker Compose se definen las publicaciones de puertos correspondientes para cada servicio.

**Consideraciones importantes:**

- La comunicación entre servicios utiliza HTTP.
- La implementación cifra los bloques almacenados mediante AES-256-GCM.
- Las contraseñas se protegen mediante bcrypt.
- Los tokens de autenticación se gestionan mediante JWT.
- La integridad de los archivos se verifica mediante SHA-256.
- La configuración actual no implementa TLS para cifrar las comunicaciones en tránsito.
- Los DataNodes no cuentan con redundancia física independiente cuando todos se despliegan sobre una misma máquina virtual.

En un despliegue real, los puertos de los DataNodes deben restringirse mediante las reglas de firewall y no exponerse innecesariamente a redes públicas.

---

## 11. Limitaciones y oportunidades de mejora

Aunque DFSha implementa las funcionalidades principales de un sistema de archivos distribuido, se identifican las siguientes limitaciones:

1. **NameNode único:** el sistema utiliza un único nodo de coordinación, por lo que representa un punto único de fallo.
2. **Infraestructura:** los cuatro servicios se despliegan sobre una misma máquina virtual, por lo que una falla de infraestructura puede afectar a todos los componentes.
3. **Comunicación segura:** no se implementó TLS para proteger las comunicaciones en tránsito.
4. **Operación WRITE:** la escritura permite reemplazar completamente el contenido del archivo, pero no contempla modificaciones parciales ni operaciones de anexado.

Estas limitaciones representan oportunidades de mejora para futuras versiones, especialmente en términos de alta disponibilidad, seguridad de las comunicaciones y escalabilidad de la infraestructura.

---

## 12. Contribuciones del equipo

El proyecto fue desarrollado de manera colaborativa. Las contribuciones individuales pueden identificarse mediante el historial de commits del repositorio y los cambios asociados a cada integrante.

---

## 13. Detener los servicios

Para detener los contenedores sin eliminar los datos almacenados:

```bash
docker compose stop
```

Para volver a iniciarlos:

```bash
docker compose start
```

Para consultar el estado:

```bash
docker compose ps
```

**Importante:** los datos de almacenamiento y la base de datos contienen información persistente. No se deben eliminar los directorios `storage/` ni la base de datos `namenode/dfsha.db` si se desea conservar los archivos y metadatos existentes.

---

## 14. Información académica

**Proyecto:** DFSha – Sistema de Archivos Distribuidos  
**Asignatura:** Sistemas Distribuidos  
**Tipo de entrega:** Proyecto 1  
**Año:** 2026

Este proyecto se desarrolló con fines académicos como ejercicio de aplicación de conceptos de sistemas distribuidos, almacenamiento, replicación, coordinación, concurrencia y seguridad.
