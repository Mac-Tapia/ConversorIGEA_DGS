# ConverterSmartGrid → DIgSILENT PowerFactory DGS

Convierte los TXT que exporta CYMDIST (RED, CARGA, BD_Equipo) en ficheros `.dgs`
que se importan en PowerFactory, un alimentador por fichero o todos en una red unida.

## Entorno

- Python **3.12 exacto**, en `.venv` (`.venv/Scripts/python.exe`). La API de PowerFactory 2024 solo carga en 3.12.
- Instalación: `pip install -r requirements.txt`; incluye el cierre de versiones verificado para CPython 3.12/Windows. Los drivers opcionales de VNR-GIS, aparte con `pip install -r requirements-drivers.txt`. Frontend: `cd frontend && npm ci && npm run build`.
- Web: `run_gui.bat` o `convertersmartgrid-web`. CLI: `convertersmartgrid convert --red ... --loads ... --equipment ... --all --out-dir out --workers 0`.

## Skills del proyecto

- `.claude/skills/convertersmartgrid-backend/SKILL.md`: reglas del motor, la escala y la API. **Léelo antes de tocar `src/convertersmartgrid/`.**
- `.claude/skills/convertersmartgrid-frontend/SKILL.md`: UX y checklist de la interfaz web (React en `frontend/`). Léelo antes de tocar `frontend/src/` o `src/convertersmartgrid/web/`.
- `.claude/skills/convertersmartgrid-spec/SKILL.md`: desarrollo guiado por especificaciones. Toda funcionalidad o reorganización que no sea un arreglo de una línea empieza por `specs/NNN-*/spec.md` (requisitos `RF-n` en EARS), luego plan y tareas; las pruebas citan `NNN:RF-n`.
- Las copias de `.cursor/skills/` son solo punteros a estas: el texto vigente es uno.

## Especificaciones

- `docs/constitution.md`: principios innegociables, cada uno con cómo se comprueba.
- `specs/NNN-<nombre>/{spec,plan,tasks}.md`: una carpeta por funcionalidad. El estado de cada spec
  se escribe solo en su línea `Estado:` (borrador, aprobada, implementada, cumplida, reservada o
  retirada); `specs/README.md` lo reúne con sus RF y tareas abiertas y lo genera
  `python tools/estado_specs.py --escribir` (spec 033). Esta tabla debe decir lo mismo: la suite lo
  comprueba. El detalle y la evidencia de cada spec están en sus tareas; la revisión de numeración y
  trazabilidad, en `docs/REVISION_SPECS_2026-10-29.md`; la arquitectura, en `docs/ARQUITECTURA.md`.

  | Spec | Estado | Pendiente |
  | --- | --- | --- |
  | 001 Reorganización: una responsabilidad, un sitio | cumplida |  |
  | 002 Arquitectura por capas y módulos enchufables | aprobada | falta T7, T8, T9, T11, T12 |
  | 003 Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | retirada |  |
  | 004 Cargas en un proyecto existente de DIgSILENT | cumplida |  |
  | 005 Carpeta de proyectos importados en DIgSILENT | cumplida |  |
  | 006 Ajuste de las demandas a la máxima de cabecera | cumplida |  |
  | 007 Cargas nuevas sobre el alimentador ajustado, una variación por carga | cumplida |  |
  | 008 Pestaña «Cargas en DIgSILENT» en tres pasos | cumplida |  |
  | 009 Inventario del repositorio: cada fichero con su módulo y su spec | cumplida |  |
  | 010 Trazado GPS de las líneas | cumplida |  |
  | 011 Estudios y obras de mejora sobre la red calibrada | cumplida |  |
  | 012 Confiabilidad y capacidad de la red calibrada | cumplida |  |
  | 013 Mes de análisis y transferencia entre dos alimentadores | cumplida |  |
  | 014 Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida |  |
  | 015 «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida |  |
  | 016 Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | cumplida |  |
  | 017 Informes de estudio eléctrico y de factibilidad de suministro | cumplida |  |
  | 018 Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida |  |
  | 019 Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida |  |
  | 020 SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida |  |
  | 021 Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida |  |
  | 022 Red unida por zonal y SET | cumplida |  |
  | 023 VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida |  |
  | 024 PINN como oráculo y gemelo digital de la red calibrada | cumplida |  |
  | 025 Calibración por año de medición | aprobada | falta T22 |
  | 026 Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | cumplida |  |
  | 027 Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | falta T11, T26 |
  | 028 Escaneo del alimentador antes de recalibrar | cumplida |  |
  | 029 Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida |  |
  | 030 Los años del PIDE en casos y escenarios de DIgSILENT | cumplida |  |
  | 031 Proyección de la demanda para todos los años del PIDE, con el mejor modelo por métricas | aprobada | falta T4, T5 |
  | 032 «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida |  |
  | 033 Trazabilidad y estado de las specs | cumplida |  |
  | 034 Motor base de conversión y contrato universal de fuentes | cumplida |  |
  | 035 Fijas de la tabla en el instante de la máxima, Q de cabecera con bancos y unidades de DIgSILENT | cumplida |  |
  | 036 Auditoría de raíz y correcciones del arranque | cumplida |  |
  | 037 Caso «Cargas nuevas» en los estudios de la web | cumplida |  |
  | 038 Pertenencia de las SED y notas en la web | cumplida | — |
  | 039 Fijas del máximo del mes o coincidentes con la cabecera | cumplida |  |
  | 040 Cargas del bloque sin duplicados, y ampliaciones de clientes existentes | cumplida |  |
  | 041 Reparto probabilístico de las SED escaladas | cumplida |  |
  | 042 «Con proyecto»: escalera de obras carga a carga y SET nueva para las que no caben | cumplida |  |
  | 043 Consolidación y gobierno de modelos | aprobada | falta T9 |
  | 044 Evaluación causal y verificación completa | cumplida |  |
  | 045 Gemelo físico y contratos PINN/GNN | aprobada | falta T3 |
  | 046 Pronóstico causal multihorizonte | cumplida |  |
  | 047 Asistente estructurado y revisión por roles | aprobada | ver sus tareas |
  | 048 Optimización mixta evolutiva y PNL | cumplida |  |
  | 049 Protecciones nativas y coordinación | cumplida |  |
  | 050 Aprendizaje continuo integrado | aprobada | falta T3b, T4b, T5b |
  | 051 Medición de cabecera en libro ancho: una columna por alimentador | cumplida |  |
  | 052 Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT | cumplida |  |
  | 053 El catálogo de fichas crece con cada código nuevo | cumplida |  |
  | 054 Fases reales en el DGS: tramos y SED monofásicos y bifásicos | cumplida |  |
  | 055 Estructura de sistemas y SET desde la propia fuente, para cualquier empresa | cumplida |  |
  | 056 Nombres y mensajes según la fuente: cada fuente con sus propias palabras | cumplida |  |
  | 057 El «Caso base» llega convergido: el oráculo corrige antes de importar | cumplida |  |
  | 058 ConverterSmartGrid: el proyecto sin el nombre de otra empresa | aprobada | falta T5, T6 |
  | 059 La fuente es la del fichero que se carga, sin valor por defecto | cumplida |  |
  | 060 Correcciones verificables del aprendizaje | cumplida |  |
  | 061 Observación y operación integrada del agente | cumplida | T1–T5 cerradas; evidencia en docs/INTEGRACION_MONITOR_AGENTE_2026-11-01.md |
  | 062 Retención diaria de ejecuciones y temporales | cumplida | T1–T4 verificadas; primera revisión real sin errores |
  | 063 Evaluación de conexión y operación comercial en un paso, para cualquier alimentador | cumplida |  |
  | 064 Arnés de DIgSILENT sin atajos: un turno para todos y estado restituido | cumplida |  |
  | 065 Cierre verificable de la auditoría integral | aprobada | falta T13 |
  | 066 Cada informe con su libro Excel, según el perfil de la empresa | cumplida |  |
  | 067 Asistente operativo: revisión, planes, modelos y tareas que funcionan desde la web | cumplida |  |
  | 068 Dataset real del maestro: órdenes del operador, etiquetas de plata y currículo con su estilo | cumplida |  |
  | 069 Intérprete de órdenes con codificador preentrenado y clase «ninguna» | aprobada | falta T7 |
  | 070 El asistente opera el conversor de punta a punta | implementada | falta T11 |
  | 071 Puertas de los modelos antes de entrenar: PINN en su red, un puntero, sin autoentrenamiento y una guardia de GPU | aprobada | falta T5 |
  | 072 PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio | aprobada | falta T9b, T11, T13, T14 |
  | 073 El número de bancos lo define la tensión en las ventanas de valle | cumplida |  |
  | 074 Piloto MADRL en obras: medir antes de aprender | aprobada | falta T5, T7, T8 |
  | 075 Validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla | cumplida |  |
  | 076 Preguntas de metodología y criterios por entregable, del flujo, de la arquitectura y de la web | cumplida |  |
  | 077 El asistente lee skills, documentos, código y API del proyecto, y un MCP local de solo lectura | cumplida |  |
  | 078 Las señales de convergencia dicen lo que devolvió DIgSILENT, y el asistente importa un grupo ya convertido | cumplida |  |
  | 079 Afinado real del intérprete de órdenes: las últimas capas del codificador junto con sus cabezas | cumplida |  |
  | 080 Acceso directo a los paquetes VNR-GIS de cada distribuidora | cumplida |  |
  | 081 Los fallos reales no se repiten: comprobaciones permanentes, solución con los oráculos y mejora continua | cumplida |  |
  | 082 El oráculo calcula todo lo del modelo, y por fases | cumplida |  |
  | 083 El oráculo antes de calibrar y recalibrar | cumplida |  |
  | 084 Seis reglas del operador pasan de notas a requisitos con prueba | cumplida |  |
  | 085 Órdenes del maestro con grupos apartados, y la puerta de órdenes sin humanas suficientes | cumplida |  |
  | 086 Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta | aprobada | ver sus tareas |
  | 087 Selección de obras con el oráculo, métodos probabilísticos y medición de la mejora | cumplida |  |
  | 088 Q negativa desde el factor de potencia | cumplida |  |
  | 089 Pronóstico de demanda en un módulo: datos vivos, limpieza, tres clases y backtest por método | aprobada | falta T5, T7 |
  | 090 La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo | cumplida |  |
  | 091 De la calibración al estudio, en su orden y sin avisos que engañen | cumplida |  |
  | 092 El «Caso base» de una red reconstruida se verifica con lo que hay en disco | cumplida |  |
  | 093 La sigla de la carga nombra la carga nueva y su variación | cumplida |  |
  | 094 Perfil de tensión en la calibración y bancos ubicados según el perfil | cumplida |  |
  | 095 Escaladas proporcionales a su potencia instalada | cumplida |  |
  | 096 Tras suspender el equipo, la web vuelve sola al último trabajo pendiente | cumplida |  |
  | 097 Vectores multilingües para la búsqueda del asistente | aprobada | falta T3 |
  | 098 La transferencia de carga del operador, en la calibración y en las obras | cumplida |  |
  | 099 Cargas del libro duplicadas por el nombre del cliente | cumplida |  |
  | 100 Aceptación automática por versión, sin tareas pendientes por proyecto | aprobada | falta T1, T2, T3, T4 |
  | 101 La calibración cambia sola los transformadores que impiden converger | implementada | falta T3 |
  | 102 Puerta de calidad: ningún commit ni subida con la suite en rojo | aprobada | falta T4 |

  Las convenciones de cada empresa (CRS de origen, patrón de SED de medición, escala,
  carpeta de DIgSILENT) van en `config/perfil_empresa.json`, local y fuera de git, que
  puede heredar de un perfil de `config/perfiles/` (`{"perfil": "electro_dunas"}`); los
  alias de tipos de línea en `config/line_type_aliases.json`, también local. Sin perfil
  no se supone nada: el CRS se pide y ninguna SED se excluye por su nombre.
- `CODIGO_FUENTE.md` lista cada fichero de `src/`, `tools/` y `frontend/src/` con su spec.
  **Un fichero nuevo entra en el índice en el mismo cambio**: `tests/test_inventario.py`
  (spec 009) falla si falta, si una herramienta no responde a `--help`, si una función de
  `src/` no la usa nada o si una spec con sus tareas hechas tiene un RF sin prueba.
- `docs/ARQUITECTURA_CATALOGO.md` lo genera `tools/generar_arquitectura.py` (spec 090) y no se edita a mano: los ganchos de `.githooks/`
  lo regeneran en cada commit y fusión (`python tools/generar_arquitectura.py --instalar-ganchos`, una vez por clon). Un fichero nuevo
  entra solo; su subsistema se asigna en `docs/architecture/subsistemas.json`.
- `docs/superpowers/specs/` y `plans/`, y `docs/DIAGNOSTICO_*.md`, son históricos: no tienen
  requisitos numerados ni casillas al día.

## Pruebas

```bash
.venv/Scripts/python.exe -m pytest -q                      # sintéticas: omiten las de datos reales
CSG_RED="D:/BaseDatosElectroDunas/referencia_retirada_20261102/RED_030826(1).txt" CSG_LOADS="D:/BaseDatosElectroDunas/referencia_retirada_20261102/CARGA_030826(1).txt" \
CSG_EQUIPMENT="D:/BaseDatosElectroDunas/referencia_retirada_20261102/BD_Equipo_V261124 (1)(1).txt" .venv/Scripts/python.exe -m pytest -q
```

La puerta de calidad (spec 102) lo exige: el gancho `pre-commit` corre las pruebas de gobierno y las del commit, y
`pre-push` la suite completa sin fallidas ni omitidas, con las variables de `config/suite_completa.json` (local, fuera
de git; ejemplo en `config/suite_completa.example.json`). GitHub Actions corre la suite sintética y el frontend.
Se activan una vez por clon con `python tools/generar_arquitectura.py --instalar-ganchos`.

Sin las tres variables `CSG_*`, la mayoría de las pruebas de integración se omiten en
silencio y la suite «pasa» sin haber probado nada real. `CSG_TXT_DIR` no basta. La suite se da
por buena solo sin ninguna omitida: con las nueve variables (las tres de los TXT, las dos
de Access de abajo, `CSG_DEMANDA_DIR="D:/BaseDatosElectroDunas/referencia_retirada_20261102"`,
`CSG_VNR_BAK="D:/BaseDatosElectroDunas/referencia_retirada_20261102/Electro Dunas VNRGIS/DAT_VNR/ELDU_VNR_24_APR.bak"`, con SQL Server
Express en marcha, spec 023, y las dos de los PDF del solicitante, spec 017:
`CSG_SOLICITUD_PDF="D:/BaseDatosElectroDunas/referencia_retirada_20261102/Carta_Sol_Fact_AMPC_480A1000.pdf"` e
`CSG_SOLICITUD_DIR="D:/BaseDatosElectroDunas/referencia_retirada_20261102/ampliaciondecarga"`) y `-rs` pasan todas. El OCR de esas
pruebas usa Tesseract; el idioma `spa` puede ir en `~/.convertersmartgrid/tessdata` (o `CSG_TESSDATA`)
si no se puede escribir en la carpeta de Tesseract.

Las pruebas nativas de las T4 (044, 045, 048, 049) no conectan con DIgSILENT desde pytest (084:RF-21): `tools/aceptacion_nativa.py` hace la corrida real y deja la evidencia con sus huellas, y las pruebas la releen con `CSG_EVIDENCIA_NATIVA=<carpeta>` (fuera de git, con datos de la distribuidora; la vigente, del 2026-11-10 con las relecturas tras retirar la obra, está en `D:/converter/evidencia_nativa/20261110_PE10_t4b`). Sin ella se omiten y la suite no se da por buena.

La prueba del servidor MCP real (spec 077) pide `CSG_MCP_PYTHON`, un intérprete aparte con `requirements-mcp.txt`: el paquete es
opcional y no se instala en `.venv`. Sin ella, esa prueba se omite y la suite no se da por buena.

Para la vía Access (`tests/test_access_input.py`) hacen falta dos bases, porque la red
más reciente no trae catálogo de equipos:
`CSG_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/260924.mdb"` e
`CSG_EQUIPMENT_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/BASE JUL25 1.mdb"`.

Las fuentes son independientes: un TXT, una `.mdb` o un paquete VNR-GIS se convierten
y se prueban cada uno por su cuenta, sean de la empresa y la fecha que sean. No hay
pruebas que comparen una fuente con otra (se retiraron el 2026-10-14). Con las cinco
variables a la vez la suite pasa entera; solo dos pruebas de la demanda medida piden
además `CSG_DEMANDA_DIR`.

## Probar en DIgSILENT

- Siempre por la web, como el operador: un sistema eléctrico entero con
  `.venv/Scripts/python.exe tools/sistema_web.py --espacio <id> --zonal Pisco --demanda-dir D:/BaseDatosElectroDunas/referencia_retirada_20261102 --periodo 2026-07`
  (convierte, importa y calibra; retoma lo hecho). Nada de guiones del scratchpad que
  repitan la API.
- Tras cambiar `src/convertersmartgrid/web/` o `src/convertersmartgrid/*.py` que use la web, reiniciarla: parar
  el proceso del puerto 8765 y abrir el acceso directo «ConverterSmartGrid» del escritorio.
  Los guiones de `tools/` no: el servidor de DIgSILENT los carga de nuevo en cada orden.
- Parar un cliente no para el trabajo de la web: cancelarlo con `POST /api/jobs/<id>/cancel`.
- Una sonda suelta conecta con `pf_arnes.conectar('nombre')`, sin `PYTHONPATH` (019:RF-16);
  si el servidor de la web está ocioso, le pide que se cierre (019:RF-14). Su salida va
  línea a línea (019:RF-15). Solo sobre proyectos importados, nunca con datos inventados.
- En el Bash de esta máquina, un heredoc reduce cada barra invertida doble a una sola: rutas con `/`, `re.escape`
  para las rutas en expresiones, y los ficheros largos con la herramienta de escribir.
- Un flujo que no converge dice lo que informa DIgSILENT en el `historial` del informe:
  leerlo antes de tocar nada (Chincha: TM106 con su factor de escala en 13,7).

## Reglas que más se rompen

- Una fuente por vez: TXT, MDB y VNR-GIS son entradas distintas, de empresas y fechas distintas. Nunca se mezclan en una conversión, una línea base, una prueba, un espacio de la web ni una orden: cada una se carga, se convierte, se prueba y se regenera sola (`linea_base_001.json` del TXT, `linea_base_001_mdb.json` de Access, cada una con su orden). Ninguna prueba compara una con otra y ningún mensaje pide la otra fuente ni la misma fecha.
- Universal: TXT, MDB y VNR-GIS de cualquier distribuidora. Electro Dunas es un caso de prueba; sus convenciones (CRS `EPSG:32718`, SED `M…`, escala NA205) van en un perfil de empresa, nunca como valor por defecto (constitución P13).
- El número de alimentadores es variable (10, 50, 200…): nada de recorrer una tabla entera por alimentador, y nada de tamaños fijos en las pruebas. Ver la sección «Escala» del skill.
- Dos disposiciones de export (reducida y completa): todo cambio en el lector se prueba con las dos.
- Determinismo: el DGS es idéntico byte a byte con `workers=1` y con `workers>1`.
- Idioma: código, comentarios, mensajes y commits en español, con el estilo de los existentes. Los comentarios explican **por qué**, con el caso real que lo motivó.
- Los datos de prueba se retiraron del proyecto el 2026-11-02: están en `D:/BaseDatosElectroDunas/referencia_retirada_20261102` y la web los carga por su ruta; ningún código los lee directamente. Esos ficheros y `D:\BaseDatosElectroDunas` son datos de la distribuidora: nunca se publican ni se suben a git. Desde el 2026-10-27 el usuario autoriza leerlos (sin `deny` en `.claude/settings.json`) para diagnosticar; las pruebas los siguen leyendo por las variables `CSG_*`.
