# SonarQube local

Alcance del repositorio revisado en **v8, 2026-10-06**: la configuración analiza
`backend`, `frontend/src` y `frontend/app` en el proyecto local **`IA-juridica`**.
Importa XML Python y LCOV frontend; los tests se centralizan en `tests/`.
El escáner se mantiene como herramienta opcional de desarrollo: no forma parte
de las dependencias de la aplicación ni se instala con el grupo `dev`.
Los resultados actuales y límites de cobertura están en la [guía única de tests](../tests/README.md);
no se garantiza un Quality Gate aprobado por superar un porcentaje local.

## Ruta rápida

1. Arranca el servidor SonarQube con el comando de la sección siguiente.
2. Espera a que esté operativo en `http://localhost:9000`.
3. Para OpenCode/Herdr, guarda una vez el **User Token** en el archivo personal indicado más abajo y reinicia el proceso de OpenCode.
4. Comprueba el MCP con `opencode mcp list`.
5. Guarda una vez `SONAR_TOKEN` en `backend\.env` y ejecuta `pnpm sonar`: conectar el MCP no sustituye el análisis del escáner.

> **Alcance:** esta guía documenta la instalación local de Windows verificada el 2026-10-05. No instala un servidor nuevo, no configura arranque automático y no contiene credenciales.

## Arrancar el servidor en Windows

La instalación existente está en:

`D:\Installations\sonarqube-26.9.0.129388\sonarqube-26.9.0.129388`

Ejecuta este comando en PowerShell. Selecciona Java 21 para ese arranque, sin cambiar el Java predeterminado del equipo:

```powershell
cmd.exe /d /c 'set SONAR_JAVA_PATH=C:\Herramientas\jdk-21\bin\java.exe&&call D:\Installations\sonarqube-26.9.0.129388\sonarqube-26.9.0.129388\bin\windows-x86-64\StartSonar.bat'
```

Mantén abierta esa consola y espera el mensaje `SonarQube is operational`. Desde otra consola, comprueba:

```powershell
Invoke-RestMethod -Uri 'http://localhost:9000/api/system/status' -TimeoutSec 10
```

El estado debe ser `UP`; después puedes abrir `http://localhost:9000`. El JAR `C:\Herramientas\sonarqube-mcp.jar` es el conector MCP: **no arranca el servidor SonarQube**.

El lanzador utiliza el Java de `PATH` salvo que se especifique `SONAR_JAVA_PATH`. En este equipo se verificó Java 8 como predeterminado, incompatible con las opciones del lanzador; el comando anterior fuerza el ejecutable Java 21 existente. No basta con cambiar `JAVA_HOME`. [Referencia oficial sobre la selección de Java](https://docs.sonarsource.com/sonarqube-server/server-installation/from-zip-file/advanced-setup#adjusting-java-exec-path).

Reutiliza esta instalación para conservar sus datos y proyectos. No borres su carpeta `data` ni levantes otra instancia como solución a un error de conexión. Si no termina de arrancar, revisa `logs\sonar.log`, `logs\web.log` y `logs\es.log` dentro de la instalación. El comando y la selección de Java se verificaron; el estado operativo debe comprobarse en cada arranque.

## Qué token usar

| Uso | Token | Variable que recibe la herramienta |
| --- | --- | --- |
| MCP de SonarQube en OpenCode o Codex | **User Token**, creado en **My Account > Security** | `SONARQUBE_TOKEN` |
| Escáner para analizar `IA-juridica` | **Project Analysis Token** de ese proyecto, preferiblemente | `SONAR_TOKEN` |

La contraseña de inicio de sesión y el texto `admin` no sustituyen un token. El token de análisis de proyecto sirve para ejecutar el escáner, pero no sustituye al User Token del MCP. Un User Token también puede ejecutar análisis si su usuario tiene el permiso correspondiente; no es necesario reutilizarlo para ambos usos. [Tipos y permisos de tokens](https://docs.sonarsource.com/sonarqube-server/user-guide/managing-tokens), [configuración oficial del MCP](https://github.com/SonarSource/sonarqube-mcp-server#manual-setup).

## OpenCode/Herdr: token persistente desde archivo

El `opencode.json` del repositorio configura el MCP con Java `C:\Herramientas\jdk-21\bin\java.exe`, el JAR `C:\Herramientas\sonarqube-mcp.jar` y almacenamiento en `C:\Herramientas\sonarqube-mcp-data`. Limita las herramientas a `issues,rules,sources,measures,quality-gates` y activa el modo de solo lectura. El acceso a fuentes puede mostrar código; comparte esos resultados con cuidado.

### Configuración inicial, una sola vez

1. Crea la carpeta personal `C:\Users\danil\.config\opencode\secrets` si no existe.
2. Crea `sonarqube-token.txt` dentro de esa carpeta. Guarda **únicamente el User Token**, sin comillas, sin `SONARQUBE_TOKEN=` y sin líneas adicionales. No es un archivo `.env`.
3. En las propiedades de seguridad de la carpeta y el archivo, restringe el acceso mediante permisos NTFS a tu usuario y las cuentas administrativas necesarias. No los coloques en Git, carpetas compartidas o sincronizadas.
4. La propiedad `mcp.sonarqube.environment.SONARQUBE_TOKEN` de `opencode.json` debe ser:

   ```json
   "SONARQUBE_TOKEN": "{file:~/.config/opencode/secrets/sonarqube-token.txt}"
   ```

   Es una propiedad dentro del bloque existente, no un archivo JSON completo. Conserva el resto de la configuración. La referencia coincide con el estado de `opencode.json` comprobado el 2026-10-05; el archivo secreto no se crea ni se verifica leyendo su contenido durante esta actualización de documentación.

5. Cierra y vuelve a iniciar el proceso de OpenCode. En Herdr, reinicia la sesión/backend de OpenCode que utiliza el proyecto; abrir otra pestaña conectada al mismo proceso no garantiza que recargue la configuración.
6. Desde la raíz del proyecto, comprueba:

   ```powershell
   opencode mcp list
   ```

OpenCode admite la sustitución nativa `{file:...}`; `~` identifica la carpeta del usuario que ejecuta OpenCode. En otra cuenta o equipo, crea el archivo en su carpeta personal. No se debe asumir que OpenCode carga automáticamente un `.env`. [Documentación de sustitución desde archivos](https://dev.opencode.ai/docs/es/config/#archivos).

### Después de reiniciar la PC

El archivo permanece y OpenCode puede leerlo sin introducir de nuevo el token ni depender de las variables heredadas por Herdr. **El servidor SonarQube debe arrancarse por separado**. El archivo no evita la caducidad o revocación del token: cuando ocurra, genera otro y reemplaza su contenido, luego reinicia OpenCode.

> **Seguridad:** el token está en texto plano, no cifrado. Los permisos NTFS reducen quién puede leerlo, pero no lo protegen frente a programas que ya se ejecutan como tu usuario. No lo pegues en chats, capturas, argumentos ni historial. No publiques salidas de configuración resuelta que puedan incluirlo.

### Alternativa temporal: variable de entorno

Si prefieres no guardar el token en disco, cambia **solo** esa propiedad a `"{env:SONARQUBE_TOKEN}"` y utiliza PowerShell 7:

```powershell
$env:SONARQUBE_TOKEN = Read-Host 'User Token de SonarQube' -MaskInput
try {
    opencode
} finally {
    Remove-Item Env:SONARQUBE_TOKEN -ErrorAction SilentlyContinue
}
```

`$env:...` dura únicamente en ese proceso y sus hijos. Si Herdr ya estaba abierto, no recibirá automáticamente las variables de esta terminal; por eso el archivo es la opción recomendada para ese flujo. Una variable de usuario persistente tampoco actualiza los procesos ya abiertos. El servidor local debe estar activo; SonarQube Community Build no requiere `SONARQUBE_ORG`.

## Codex: no confundir la sintaxis

La referencia `{file:...}` de esta guía es una función de **OpenCode**, no una sintaxis que deba copiarse al TOML de Codex. Para un MCP local en `C:\Users\danil\.codex\config.toml`, la propiedad `env_vars = ["SONARQUBE_TOKEN"]` dentro de `[mcp_servers.sonarqube]` permite pasar la variable del proceso que lo inicia. `env_vars` es una propiedad TOML, **no un comando de PowerShell**. [Documentación oficial de OpenAI sobre MCP](https://developers.openai.com/codex/mcp/).

Si quieres cargar el mismo archivo para una sesión del CLI de Codex, inicia el CLI desde esa misma PowerShell:

```powershell
$tokenPath = Join-Path $HOME '.config\opencode\secrets\sonarqube-token.txt'
$env:SONARQUBE_TOKEN = (Get-Content -LiteralPath $tokenPath -Raw -Encoding UTF8).Trim()
try {
    codex
} finally {
    Remove-Item Env:SONARQUBE_TOKEN -ErrorAction SilentlyContinue
}
```

Esto no actualiza una aplicación Codex de escritorio que ya esté abierta ni implementa su carga automática al iniciar. La configuración persistente del escritorio es un paso separado; no guardes el token literal en un archivo versionado.

## Analizar el proyecto

**Configuración una sola vez:** añade el token de análisis al archivo existente `D:\Web\IA_juridica\backend\.env`, sin reemplazar sus otras variables. Es el único `.env` utilizado para el backend y el scanner; no crees otro en la raíz. Edita el archivo localmente, sin pegar el secreto en la terminal ni en el chat:

```dotenv
SONAR_TOKEN=tu_token_de_analisis
```

El ejemplo es un marcador: debe reemplazarse por el token real. Puedes usar un Project Analysis Token de `IA-juridica` o tu User Token existente si tiene permiso **Execute Analysis**. No cambies el User Token que utiliza el MCP por un token de proyecto.

**En cada ejecución:** desde la raíz, con el servidor operativo:

```powershell
uv sync --frozen --extra dev --group sonar --inexact
pnpm sonar
```

El servidor local debe estar disponible en `http://localhost:9000` y el proyecto debe existir con la clave exacta `IA-juridica`. La configuración del escáner vive en `[tool.sonar]` de `pyproject.toml`; no se necesita un segundo archivo de propiedades. Se analizan `backend`, `frontend/src` y `frontend/app`; `tests` se clasifica por separado. Se excluyen archivos PDF y datos/corpus no ejecutables, además de entornos y artefactos generados; los diagnósticos heredados de `tests/backend/manual/` quedan fuera del análisis automatizado.

`pnpm sonar` lee automáticamente **solo `SONAR_TOKEN`** de `backend\.env` y lo entrega al proceso del escáner, sin mostrarlo ni pasarlo en argumentos. El runner no exporta el resto de secretos del archivo a los tests, no modifica permanentemente las variables del sistema y no necesita reintroducir el token después de reiniciar la PC. Para CI, un `SONAR_TOKEN` no vacío del entorno tiene prioridad sobre el archivo; elimina una variable antigua si quieres usar el valor de `backend\.env`. La ruta se resuelve desde el repositorio, no desde la carpeta actual de la terminal.

`backend\.env` está ignorado por Git y excluido del análisis Sonar, pero sigue siendo texto plano: restringe permisos y no lo compartas ni lo sincronices. Nunca guardes credenciales reales en archivos `.env.example`; `backend\.env.example` incluye únicamente la clave vacía como referencia. Esta carga automática es propia de `pnpm sonar`; **no cambia la configuración de OpenCode/Codex** ni hace que `pysonar` directo lea ese archivo.

### Reconocer tests y cobertura: ejecutar antes del escáner

**SonarQube no ejecuta pytest ni calcula cobertura por sí solo.** Importa cobertura Python, ejecución xUnit Python y cobertura LCOV del frontend generadas en este repositorio. [Cobertura Python](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/test-coverage/python-test-coverage), [resultados de tests](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/test-coverage/test-execution-parameters).

Desde `D:\Web\IA_juridica`:

```powershell
# Solo tests + informes, sin token Sonar ni llamadas a modelos reales
pnpm test:coverage

# Tests + informes + análisis: requiere servidor UP y SONAR_TOKEN en backend/.env
pnpm sonar
```

`pnpm sonar` comprueba primero el token del entorno o de `backend\.env`: si falta, está vacío o el archivo no se puede leer, avisa sin ejecutar tests ni el escáner. Después ejecuta las mismas suites e informes de `test:coverage` y **solo si las tres suites (Python, scripts Node y React) terminan correctamente** lanza el escáner congelado con el grupo sonar. No se reutilizan informes viejos para ocultar tests fallidos. El comando directo `uv run --frozen --group sonar --inexact pysonar` requiere que su proceso reciba `SONAR_TOKEN`; para la lectura automática desde archivo usa `pnpm sonar`.

| Informe | Generador y contenido | Propiedad `[tool.sonar]` |
| --- | --- | --- |
| `coverage.xml` | pytest-cov/Coverage.py: líneas y ramas del backend ejecutadas | `python.coverage.reportPaths` |
| `temp/sonar-reports/pytest.xml` | pytest xUnit: tests ejecutados, fallidos y omitidos, con archivo relativo | `python.xunit.reportPath` |
| `temp/sonar-reports/frontend-coverage/lcov.info` | Vitest/V8: líneas y ramas JS/TS del frontend | `javascript.lcov.reportPaths` |

El comando recoge `tests` mediante `pytest.ini`; también verifica scripts Node y componentes/hooks React. Sonar recibe **ejecución Python y cobertura Python/frontend**, no conteos de tests Node/React ni puntuaciones de DeepEval. El LCOV incluye frontend/src y frontend/app, también archivos sin ejercitar; los E2E no generan ese informe. `pnpm test` sigue siendo el modo rápido sin informes. Las evaluaciones con proveedores siguen siendo opt-in:

```powershell
# Añadir evaluaciones reales al mismo informe (credenciales, red y coste)
pnpm test:coverage --run-model-evals
```

Los tests de modelos reales normalmente aparecen omitidos; eso no mide la calidad del modelo. Todas las suites y la evaluación de calidad se documentan en la [guía única de tests](../tests/README.md#calidad-real-del-modelo).

**Rutas y alcance:** Coverage.py usa rutas relativas y solo código `backend`; las pruebas y los diagnósticos viven fuera de `backend`, bajo `tests/`, y no cuentan como código de producto. No se excluyen módulos de aplicación sin cobertura para elevar artificialmente el porcentaje. Los fixtures `conftest.py` bajo los directorios de tests se clasifican como tests. No se añade un archivo de configuración Sonar adicional: todo sigue en `pyproject.toml`. Los informes son artefactos locales ignorados por Git.

**El 80 % no está garantizado:** la captura corresponde a **New Code**, no a todo el proyecto. Importar cobertura permite medirla; después puede seguir siendo inferior al umbral si los tests no ejercitan las líneas nuevas. Las incidencias nuevas son otra condición del Quality Gate: importar tests no corrige esas incidencias ni baja el umbral. Un fallo de Quality Gate tras el procesamiento no equivale a un fallo de carga.

**Verificación histórica previa a ampliar frontend — 06/10/2026:** `pnpm test:coverage` termina con código 0: 225 tests Python pasan, 3 evaluaciones reales omitidas y 2 xfail temporales conocidos; 15 tests Node pasan. Ambos XML se generan y todas sus rutas resuelven a archivos existentes (71 módulos y 230 casos Python). Cobertura local: **45.62 % de líneas**, **29.01 % de ramas**, aproximadamente **42 % combinado**; no es la medición de New Code del servidor. `pnpm deps:check` pasa. Evidencia local: `temp/sonar-reports/run.log`. La importación autenticada queda pendiente: esta sesión no recibió `SONAR_TOKEN`.

**Corrección posterior de la salida del runner:** las pruebas Node que simulan errores ahora capturan esos mensajes y comprueban su contenido sin imprimir falsos fallos de Python. `pnpm test` vuelve a pasar: 225 Python, 3 skips, 2 xfail y **17 Node**. Los errores reales del runner se siguen mostrando. La ausencia de `SONAR_TOKEN` devuelve código 2 antes de iniciar tests/escáner y no modifica los informes; evidencia `temp/sonar-reports/runner-fix.log`.

## Diagnóstico rápido

### Advertencias de codificación e historial Git

- **Codificación:** el detector de documentos corruptos en `backend/ingestion/pipeline.py` utilizaba literalmente el carácter de reemplazo Unicode U+FFFD. Se expresa ahora como `"\ufffd"`: conserva la detección en los documentos sin incluir ese carácter en el código fuente. Las pruebas comprueban la detección y que el archivo sea UTF-8 válido sin ese literal; no se recodifican ni eliminan textos españoles válidos.
- **Historial Git (`Missing blame information`):** el repositorio tiene historia completa, pero hay fuentes modificadas y archivos nuevos todavía sin commit. Las líneas no registradas no tienen autor ni revisión en el historial. Revisa y registra esos cambios en tus propios commits antes de repetir `pnpm sonar`. No basta con hacer `git add`, no es necesario hacer push y no se debe incluir `backend\.env`, datos ni informes. No se crean commits automáticamente ni se desactiva SCM para esconder la advertencia. [Integración SCM de Sonar](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/scm-integration).

El Quality Gate sigue evaluando cobertura e incidencias: corregir estas advertencias no garantiza que pase.

**Estado de la corrección — 06/10/2026:** se añadieron tres casos de regresión y pasan **228 tests Python y 20 Node** (3 skips y 2 xfail); la suite focalizada de evidencia pasa sus 11 casos usando `pytest -c pytest.ini`. La auditoría de 121 archivos de texto no encuentra UTF-8 inválido ni caracteres U+FFFD literales. Los cachés `.pytest_cache/` quedan ignorados por Git. La comprobación del scanner desde esta sesión sigue bloqueada por permisos de esos cachés: no se afirma una nueva importación ni la desaparición de los avisos en el servidor. La advertencia de historial permanece pendiente de los commits que el usuario decidió realizar personalmente; SCM continúa activo. Evidencia: `temp/sonar-reports/warnings-fix.log` y `temp/sonar-reports/encoding-scan.log`.

**Verificación de lectura desde archivo — 06/10/2026:** la primera ejecución con archivo autenticó correctamente y pasaron 225 tests Python y 20 Node (3 skips y 2 xfail), pero encontró `AccessDeniedException` al recorrer `backend\.pytest_cache`. Después se unificó la configuración en `backend\.env`, conservando las variables previas y eliminando el `.env` raíz creado para el scanner. El error de permisos de ese intento no fue un fallo de token ni de las suites. Evidencia histórica: `temp/sonar-reports/file-token.log`.

**Verificación tras unificar el `.env`:** `pnpm test` vuelve a pasar con 225 Python y 20 Node (3 skips y 2 xfail). Se comprobó la lectura real de `backend\.env` desde otra carpeta y la entrega del token al entorno del scanner mediante un proceso simulado, sin revelar secretos. Esa verificación local no repitió el scanner; la ejecución posterior del usuario sí se procesó, como se detalla a continuación. Evidencia de tests: `temp/sonar-reports/backend-env-tests.log`.

**Último análisis procesado — 06/10/2026, 14:13:55 (Lima):** la tarea `940307f0-e1b7-4182-9e90-50de27590549` terminó con estado `SUCCESS`. Sonar reconoce **225 tests**, **0 fallos**, **0 errores** y **5 omitidos**; cobertura global **40.2 %** y cobertura de código nuevo **68.7 %**. El Quality Gate falla por cobertura nueva inferior al **80 %** y **52 incidencias nuevas** cuando exige 0; duplicación nueva **1.6 %** cumple el máximo del 3 %. La API confirma dos advertencias distintas: codificación de fuentes y ausencia de información Git/blame en 54 archivos. La carga no falla por ellas, pero requieren revisión. El código de salida 1 corresponde al Quality Gate rechazado porque `qualitygate.wait = true`; no hay que reconfigurar el token ni ocultar el resultado desactivando el Gate. [Comportamiento oficial de espera del Quality Gate](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/analysis-parameters/parameters-not-settable-in-ui#quality-gate).

| Síntoma | Qué significa | Qué hacer |
| --- | --- | --- |
| `Missing required properties: sonar.token` o `Falta SONAR_TOKEN` | El scanner no recibió su token, aunque el MCP funcione | Guarda `SONAR_TOKEN` en `backend\.env` y ejecuta `pnpm sonar`; no uses `pysonar` directo esperando que cargue el archivo |
| `No se pudo leer backend/.env` | Archivo inaccesible o formato no legible | Comprueba permisos y formato UTF-8 de `backend\.env`, sin publicar su contenido |
| `Connection refused` / `HttpHostConnectException` en `localhost:9000` | No hay un servidor accesible en esa dirección; no demuestra un problema con el token | Arranca la instalación existente y comprueba `/api/system/status` antes de tocar credenciales |
| `Unrecognized option: --add-exports=...` | La JVM seleccionada no reconoce la opción; en este equipo se comprobó que era Java 8 | Usa el comando de arranque con `SONAR_JAVA_PATH` apuntando al Java 21 existente |
| `Not authorized. Please check server credentials.` | El servidor responde, pero rechaza las credenciales o los permisos | Usa un User Token para MCP; comprueba su caducidad, revocación y permisos sobre `IA-juridica` |
| Archivo del token no encontrado o vacío | OpenCode no puede obtener la credencial del archivo personal | Comprueba ruta, cuenta de Windows, permisos y contenido local; no publiques el token |
| Funciona en terminal, pero no en Herdr | Con `{env:...}`, el proceso de Herdr puede tener un entorno anterior | Usa `{file:...}` y reinicia el proceso de OpenCode que utiliza Herdr |
| `env_vars` no se reconoce como cmdlet | Se pegó una propiedad de configuración en la terminal | Colócala en el TOML de Codex, no la ejecutes como comando |
| Cobertura `0.0%` | No demuestra que no existan tests; puede faltar informe o sus rutas no coincidir | Ejecuta `pnpm test:coverage`, comprueba los XML, luego `pnpm sonar`; revisa importación en el log del escáner |
| XML presente, pero cobertura sigue en cero | Puede ser reporte viejo, raíz distinta o mapeo inválido | Analiza desde la raíz, busca el importador Cobertura y avisos de archivos no resueltos; distingue Overall Code de New Code |

## Comprobación final

- [ ] SonarQube responde con estado `UP` en `http://localhost:9000/api/system/status`.
- [ ] El proyecto tiene la clave exacta `IA-juridica`.
- [ ] OpenCode utiliza el User Token mediante el archivo personal y el MCP aparece conectado.
- [ ] El archivo personal del MCP está fuera del repositorio; `backend\.env` es el único `.env` para backend y scanner y está ignorado por Git. Ambos tienen permisos restringidos.
- [ ] El análisis completo se ejecutó con el escáner y un token autorizado para analizar el proyecto.
- [ ] Los XML y LCOV se generaron después del cambio de código y antes del escáner; se revisaron los logs de importación Cobertura, xUnit y JavaScript/TypeScript LCOV.
- [ ] Se revisaron por separado la carga del análisis, la cobertura y el Quality Gate.
