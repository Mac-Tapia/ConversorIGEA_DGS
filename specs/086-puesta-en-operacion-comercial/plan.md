# Plan — Spec 086

P03 del cierre de producción (2026-11-07): `tools/verificar_entrega_integral.py`
consolida las puertas de 065:RF-24, frontend y ML sin equiparar una regresión
aprobada con RF-46. Los ensayos nativos, de instalación, interrupción y tercero
conservan su evidencia y aceptación independientes; no se certifican por el runner.

Lee: `docs/constitution.md`, 058, 062, 065, 081. Las revisiones que lo fundamentan son de `f50146e8` y solo leyeron código: cada hallazgo se
reproduce antes de corregirlo. Las licencias son señales para una asesoría, no conclusiones.

## Orden y por qué

| Fase | Qué | Por qué en este orden | Puerta de salida |
| --- | --- | --- | --- |
| F0 | Decidir e integrar | Sin congelar, las corridas prueban otro código; hoy hay ramas entregadas sin integrar | `main` con todo lo entregado y suite sin omitidas |
| F1 | Datos que no se pierden | Hay riesgo real hoy, y renombrar depende de esto | Prueba de corte y de unidad ausente |
| F2 | Renombrar la carpeta | Depende de F1; más fácil con rutas relativas e identidad estable | Web con los mismos espacios y suite |
| F3 | Informes veraces, seguridad y edición de producto | El fallo más grave es un informe con datos viejos | Pruebas negativas |
| F4 | Universal | Debe estar antes de empaquetar | Perfil ficticio de punta a punta sin DIgSILENT |
| F5 | Instalador y soporte | Empaqueta lo anterior | Instalación en una máquina limpia |
| F6 | Corridas reales R1–R6 sobre el candidato congelado | Son la aceptación | Evidencia por corrida |
| F7 | Aceptación final y v1.0 | Cierre | Equipo limpio, otra empresa, corte |

Las decisiones legales (D3, D7) corren en paralelo desde F0, y deben cerrarse antes de entregar a nadie. D3 no espera: el repositorio es público hoy.

## Trabajo en paralelo

En serie por lo que comparten: `web/app.py`, `web/services.py` y `workspace.py`. Sin chocar entre sí: `v1/datos`, `v1/informes` y
`v1/universal` tocan zonas distintas de `services.py`, por lo que se integran de una en una. `v1/instalador` puede ir en paralelo salvo en
`requirements`. Una sola suite completa, la del integrador; los agentes prueban lo que tocan. DIgSILENT, en serie, por licencia.

## F0: integrar

| Parte | Cubre |
| --- | --- |
| `feat/decisiones-usuario`, `entrega/042-doble-terna`, `entrega/083-calibracion` y revisar `fix/acopladores-con-fases` | RF-45 |
| Acordar con las otras sesiones una ventana sin entregas | RF-45 |
| Aplicar el modelo provisional con `tools/asistente_modelo_provisional.py poner` tras reiniciar | 085 T7 |

Al cerrar F0, las ramas ya integradas se archivan en un `git bundle`, con orden del usuario, y las 10 ramas locales que aún llevan
`referencia/NA205.dgs` en su historial no se suben nunca: un push las publicaría de nuevo.

## F1: datos

| Parte | Cubre | Encaje |
| --- | --- | --- |
| `fsync` y `.bak` | RF-1, RF-2 | `util.write_json_atomic`, `almacen.anotar` |
| `load` conserva y avisa; migraciones | RF-3, RF-4, RF-5 | `web/workspace.py:239,267-300` |
| Rutas relativas | RF-6 | `workspace.json`, `conversiones.json`, con migración |
| Identidad estable | RF-7 | `runtime_paths.py:67-69`, un fichero de ID en la raíz de datos |
| Temporal junto al destino | RF-8 | `runtime_paths.py:52-58`, `util.py:37` |
| Diario de trabajos | RF-9 | `web/jobs.py:484` |
| Copia y restauración | RF-10, RF-47 | herramienta nueva, reutilizando `retencion.py` para saber qué es valioso |

Pruebas: matar un proceso a mitad de un guardado; unidad ausente al arrancar; JSON truncado; versión futura; ruta UNC o una segunda unidad;
mover la carpeta entera y que los espacios sigan.

## F2: renombrar

Procedimiento completo en `tasks.md` (T9). Trampa: `requirements*.txt` no incluye torch ni transformers, así que **`.venv` se repara en sitio,
no se rehace**. Se ensaya antes sobre una copia de dos o tres espacios. Con F1 hecha, desaparecen sus pasos más peligrosos.

## F3: veracidad, seguridad y producto

| Parte | Cubre | Encaje |
| --- | --- | --- |
| Informe ligado al `token` de la corrida | RF-11, RF-12 | `services.py:8183,7467-7477,7206,8190` |
| «Caso base» al retomar y su huella | RF-13, RF-14 | `sistema_web.py:284,306,440-454`, `comprobacion_flujo.py:120-122` |
| Edición de producto | RF-15, RF-16 | `web/__main__.py:368`, `vigilancia.py:151,295,337`, `Asistente.tsx:279`, `EquipoAsistente.tsx:32`, `GemeloPIDE.tsx` |
| Host, Origin, token, 0.0.0.0 | RF-17 a RF-20 | `web/app.py:693,1276`, `web/__main__.py:339` y el lanzador; el frontend añade el token |
| Leaflet propio y CSP | RF-21 | `preview.py:293`, `app.py:1334` |
| Sin salida por defecto | RF-22 | `asistente/internet.py`, trazado por OSRM, teselas del mapa, `reranker.py:83` |
| Tareas por efecto | RF-23, RF-24 | las tareas del asistente, hoy 16 sin confirmación |
| Guiones y reintentos | RF-25, RF-26 | `app.py:2120` |
| Sin GPU | RF-27 | `temporal.py:388`, `services.py:5412` |

Decisión: token por arranque en lugar de usuarios, porque D2 es un puesto local. Si D2 cambia, entran usuarios y roles y esta fase crece.

## F4: universal

| Parte | Cubre | Encaje |
| --- | --- | --- |
| Moneda | RF-28 | `informe_docx.py:1143`, `InformesPF.tsx:446` |
| Web sin casos | RF-29 | `Asistente.tsx:167,265`, `DemandaMedida.tsx:613,645` |
| Esquema y `validar-perfil`, guía | RF-30 | `perfil_empresa.py:31`, `docs/PERFIL_EMPRESA.md` |
| Plantillas neutras | RF-31 | `informe_docx.py:76-78` y los modelos de `output/` |
| Perfiles y lista de términos | RF-32, RF-33 | fuera de la entrega `config/perfiles/electro_dunas*`; `config/vnr_dgs_profile.json:5` |
| Sin pesos ajenos | RF-34 | lista de lo que entra en el paquete |
| Valores por defecto | RF-35 | una búsqueda de los valores fijos, al empezar la fase |

Se prueba con un perfil ficticio de una empresa inventada solo en la parte que no toca DIgSILENT: la regla de no probar DIgSILENT con datos
inventados se mantiene.

## F5: instalador

Inno Setup con Python 3.12 embebido, wheels con hash, `dist` precompilado, programa y datos separados, núcleo sin torch y complemento de IA.
Requiere trasladar a datos del paquete lo que hoy se lee del checkout (`pyproject.toml:22,98`, `powerfactory_env.py:20`, `services.py:747`):
es el trabajo más delicado de la fase. SBOM y `pip-audit` en cada candidata. El lanzador `run_gui.bat:11,19,40` deja de instalar desde internet.

## F6: corridas reales

Con el candidato congelado, en serie, por la web, con proyectos de prueba nuevos. Antes: un espacio nuevo por fuente y revisar que 005:RF-22
no borre una versión anterior de un proyecto. Cada fallo real vuelve a F3, entra en `docs/regresiones/` y la corrida se repite.

Las corridas R1 a R6 cierran 33 de las 53 tareas de DIgSILENT abiertas; otras 15 no hacen falta para la 1.0. El detalle está en `tasks.md`.

## Estrategia de prueba

Pruebas sintéticas en cada fase, una suite completa sin omitidas al cerrar cada fase, las dos líneas base, el determinismo y las dos
disposiciones si se toca el lector. El navegador real para la web. Nada se da por aceptado sin DIgSILENT real.

## Riesgos

- Las corridas reales suelen destapar fallos: el plazo no se puede prometer.
- F5 puede obligar a mover ficheros que hoy se leen por ruta: se hace con la línea base en cada paso.
- D7 puede cambiar qué se entrega (`mmarco`, datos de entrenamiento, redistribuir CUDA).
- Sesiones que escriben en `main`: la ventana de F0 y F2 necesita su acuerdo.

Corrección de empaquetado (2026-11-08, RF-36/39): `frontend/licencias` conserva textos
extraídos de los tarballs cuya integridad coincide con el lock de npm. El constructor
rechaza versiones, huellas o textos ausentes y copia los avisos íntegros tanto a la
rueda como al candidato. Incluye transitivas de producción; las herramientas de
desarrollo siguen fuera del inventario entregado. Esto no cierra instalación,
actualización/reversión ni corridas nativas de T40/T32.

Ampliación autorizada P01/P22 (2026-11-08, RF-37/39/44): el mismo constructor
`complemento-ia` admite `--capacidades integrales`, además de inferencia. Toma
todos los extras declarados salvo `dev` y los cuatro requisitos de motores,
MADRL, MCP y drivers; calcula el cierre con los markers/extras de las ruedas,
fijado al freeze del entorno probado. No transforma paquetes instalados en
ruedas. Acepta varias caches existentes para evitar otra copia intermedia.
Exige procedencia URL/commit/huella para Git y URL/huella para CUDA; verifica
ABI, Python, restricciones, coincidencia con el núcleo y licencias incluidas.
Una segunda puerta usa pip offline con `--dry-run --ignore-installed
--require-hashes` y los extras originales resueltos, sin instalar ni activar
modelos. El manifiesto distingue capacidades de inferencia e integrales y
mantiene `proyecto_completo=false`: cobertura de dependencias no cierra T40,
T32/T41 ni demuestra aceptación científica o eléctrica.
Cuando una rueda omite los avisos del titular, `--licencias-suplementarias`
acepta únicamente un inventario de textos del origen versionado, ligado a la
versión y huella de la rueda, URL/huella del origen y ruta/huella de cada texto.
Conserva estos recibos y textos en el complemento, sin modificar la rueda ni
deducir permisos de una etiqueta automática. Sin ese material el cierre falla.

Complemento separado (RF-37/39): el constructor resuelve solo ruedas de inferencia
desde una caché explícita, respetando las versiones del núcleo. Produce su propio
lock por SHA-256, inventario, avisos y manifiesto verificable sin incluir pesos ni
dependencias de entrenamiento. Construirlo no activa modelos ni modifica la
instalación. La aceptación exige instalarlo con el Python entregado y reabrir los
modelos; la descarga o el inventario no cierran T40.

El contenedor Inno debe esperar al instalador Python y propagar su fallo mediante
GetCustomSetupExitCode, además de comprobar el puntero de versión y el intérprete
instalado. Una carpeta preexistente no acredita éxito. El ensayo nativo inyecta
retorno7 y comprueba retorno no cero, incluso con esa carpeta; un caso positivo
comprueba retorno0 con versión correcta. El modo silencioso registra el fallo sin
un diálogo que deje bloqueada la automatización.

Los hijos Python del instalador usan también PYTHONSAFEPATH, como los lanzadores
entregados, para que pip/doctor no importen módulos desde su directorio de trabajo.
Se mantiene el PYTHONPATH explícito de la rueda de pip o de PowerFactory. La prueba
inyecta un json.py en cwd y exige que no se ejecute; doctor no se modifica para
ocultar una ruta ajena.

Copia completa de rutas explícitas (RF-38/47): se incluyen las raíces de asistente
y gemelo y el archivo de perfil configurados fuera de web/config. Un manifiesto v2
distingue archivos, directorios y la configuración que se restaura por archivo;
el lector nuevo conserva compatibilidad con copias v1. La reversión emplea el
lector de la versión actual antes de cambiar el puntero al programa anterior.
Se preparan y verifican todos los destinos antes de cambiarlos, con recuperación
de los originales si falla un cambio intermedio. Se rechazan solapamientos
ambiguos y se conservan datos posteriores apartados, sin seguir enlaces.
