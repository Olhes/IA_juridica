# SonarQube local

## Analizar el proyecto

1. En SonarQube, genera un **Project Analysis Token** para `IA-juridica` o usa
   un **User Token** con permiso **Execute Analysis**. Guarda el valor como
   `SONAR_TOKEN` en el archivo privado `backend/.env`; no lo pegues en comandos
   ni lo subas a Git. Una variable de entorno no vacía tiene prioridad.
2. Desde la raíz, ejecuta `pnpm sonar`. En Windows reutiliza el servidor local
   o lo inicia, espera a que esté operativo y lo deja encendido.
3. Abre el [panel de IA-juridica](http://localhost:9000/dashboard?id=IA-juridica).
   Distingue **análisis publicado** de **Quality Gate aprobado**: el servidor
   puede aceptar el informe y rechazar el Gate.

Para arrancar **solo el servidor** en una consola, usa `pnpm sonar:start` y déjala
abierta. El [lanzador de Windows](../scripts/start-sonarqube.ps1) fija la instalación
local y selecciona Java 21 para ese proceso. Comprueba `UP` en
[el estado del servidor](http://localhost:9000/api/system/status).

## Qué se publica

El runner publica solo si pasan Python, Node y React. Sonar importa la ejecución
de pytest y la cobertura Python y frontend, no el número de casos Node/React
ni las puntuaciones del modelo. La configuración vive en
[`pyproject.toml`](../pyproject.toml) (`[tool.sonar]`); el scanner es una
herramienta de desarrollo, no una dependencia de producción.

Para generar solo informes sin token, usa `pnpm test:coverage`. Las rutas
de los informes y los modos con proveedores están en la
[guía de pruebas](../tests/README.md). No compares cobertura global con
cobertura de código nuevo.

## Diagnóstico

| Síntoma | Qué revisar |
|---|---|
| Falta `SONAR_TOKEN` o la credencial se rechaza | Instancia, clave del proyecto, caducidad y permiso. Revisa si una variable de entorno antigua sustituye el valor de `backend/.env`. |
| Servidor inaccesible | Comprueba el estado y los logs `sonar.log`, `web.log` y `es.log` de la instalación. No borres la carpeta `data`. |
| Error de Java al arrancar | Usa `pnpm sonar:start`; no dependas del Java que devuelve `PATH`. |
| `AccessDeniedException` en Windows | Comprueba lectura y recorrido para tu cuenta en la ruta exacta del error. En este equipo ocurrió en `.pytest_cache`, `backend/.pytest_cache` y subcarpetas de `temp/pytest-runs`. El analizador Python puede recorrerlas pese a las exclusiones. No cambies permisos de todo el proyecto. |
| Cobertura en cero | Comprueba que los informes se regeneraron y que el scanner pudo mapear sus rutas desde la raíz. |
| `Missing blame information` | Comprueba historial Git disponible y archivos sin registrar. No desactives SCM para ocultarlo. |
| Quality Gate rechazado | Revisa las condiciones en el panel: no es necesariamente un fallo de carga ni de autenticación. |

## MCP (opcional)

El MCP sirve para consultar SonarQube, no para arrancar el servidor ni sustituir
al scanner. Usa un **User Token** como `SONARQUBE_TOKEN`, distinto de la variable
`SONAR_TOKEN` que lee el runner. No compartas el valor ni lo guardes en archivos
versionados. Consulta los [tipos de token de SonarQube](https://docs.sonarsource.com/sonarqube-server/user-guide/managing-tokens).

- **OpenCode/Herdr:** [opencode.json](../opencode.json) referencia
  `{file:~/.config/opencode/secrets/sonarqube-token.txt}` y configura acceso de
  solo lectura. Guarda únicamente el token en ese archivo personal, con permisos
  restringidos. Reinicia el proceso de OpenCode que usa Herdr y comprueba
  `opencode mcp list`.
- **Codex:** `{file:...}` es sintaxis de OpenCode. En `config.toml`,
  `env_vars = ["SONARQUBE_TOKEN"]` dentro de `[mcp_servers.sonarqube]` pasa la
  variable del proceso que inicia Codex. No actualiza una instancia de escritorio
  ya abierta. Consulta la [configuración de MCP](https://developers.openai.com/codex/mcp/).
