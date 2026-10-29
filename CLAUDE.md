# Conversor IGEA/CYMDIST → DIgSILENT PowerFactory DGS

Convierte los TXT que exporta IGEA/CYMDIST (RED, CARGA, BD_Equipo) en ficheros `.dgs`
que se importan en PowerFactory, un alimentador por fichero o todos en una red unida.

## Entorno

- Python **3.12 exacto**, en `.venv` (`.venv/Scripts/python.exe`). La API de PowerFactory 2024 solo carga en 3.12.
- Instalación: `pip install -r requirements.txt`; los drivers opcionales de VNR-GIS, aparte con `pip install -r requirements-drivers.txt`. La web necesita compilar el front una vez: `cd frontend && npm install && npm run build`.
- Web: `run_gui.bat` o `igea-dgs-web`. CLI: `igea-dgs convert --red ... --loads ... --equipment ... --all --out-dir out --workers 0`.

## Skills del proyecto

- `.claude/skills/igea-dgs-backend/SKILL.md`: reglas del motor, la escala y la API. **Léelo antes de tocar `src/igea_dgs/`.**
- `.claude/skills/igea-dgs-frontend/SKILL.md`: UX y checklist de la interfaz web (React en `frontend/`). Léelo antes de tocar `frontend/src/` o `src/igea_dgs/web/`.
- `.claude/skills/igea-dgs-spec/SKILL.md`: desarrollo guiado por especificaciones. Toda funcionalidad o reorganización que no sea un arreglo de una línea empieza por `specs/NNN-*/spec.md` (requisitos `RF-n` en EARS), luego plan y tareas; las pruebas citan `NNN:RF-n`.
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
  | 002 Arquitectura por capas y módulos enchufables | aprobada | falta T2, T3, T4, T6, T7, T8, T9, T10, T11, T12 |
  | 003 Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | reservada |  |
  | 004 Cargas en un proyecto existente de DIgSILENT | cumplida |  |
  | 005 Carpeta de proyectos importados en DIgSILENT | implementada | falta T12 |
  | 006 Ajuste de las demandas a la máxima de cabecera | cumplida |  |
  | 007 Cargas nuevas sobre el alimentador ajustado, una variación por carga | implementada | falta T11 |
  | 008 Pestaña «Cargas en DIgSILENT» en tres pasos | implementada | falta T7 |
  | 009 Inventario del repositorio: cada fichero con su módulo y su spec | cumplida |  |
  | 010 Trazado GPS de las líneas | cumplida |  |
  | 011 Estudios y obras de mejora sobre la red calibrada | implementada | falta T19 |
  | 012 Confiabilidad y capacidad de la red calibrada | aprobada | falta T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13 |
  | 013 Mes de análisis y transferencia entre dos alimentadores | aprobada | falta T5, T6, T7, T8 |
  | 014 Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida |  |
  | 015 «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida |  |
  | 016 Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | implementada | falta T18 |
  | 017 Informes de estudio eléctrico y de factibilidad de suministro | aprobada | falta T5, T7, T8, T9, T10, T11, T12, T13, T14, T15, T17 |
  | 018 Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida |  |
  | 019 Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida |  |
  | 020 SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida |  |
  | 021 Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida |  |
  | 022 Red unida por zonal y SET | cumplida |  |
  | 023 VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida |  |
  | 024 PINN como oráculo y gemelo digital de la red calibrada | cumplida |  |
  | 025 Calibración por año de medición | aprobada | falta T15, T21, T22 |
  | 026 Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | implementada | falta T12 |
  | 027 Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | falta T11, T22, T14, T26, T29, T30, T31 |
  | 028 Escaneo del alimentador antes de recalibrar | implementada | falta T6, T11 |
  | 029 Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida |  |
  | 030 Los años del PIDE en casos y escenarios de DIgSILENT | cumplida |  |
  | 031 Proyección econométrica de la demanda con variables exógenas | reservada |  |
  | 032 «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida |  |
  | 033 Trazabilidad y estado de las specs | cumplida |  |
  | 034 Motor base de conversión y contrato universal de fuentes | cumplida |  |

  Las convenciones de cada empresa (CRS de origen, patrón de SED de medición, escala,
  carpeta de DIgSILENT) van en `config/perfil_empresa.json`, local y fuera de git, que
  puede heredar de un perfil de `config/perfiles/` (`{"perfil": "electro_dunas"}`); los
  alias de tipos de línea en `config/line_type_aliases.json`, también local. Sin perfil
  no se supone nada: el CRS se pide y ninguna SED se excluye por su nombre.
- `CODIGO_FUENTE.md` lista cada fichero de `src/`, `tools/` y `frontend/src/` con su spec.
  **Un fichero nuevo entra en el índice en el mismo cambio**: `tests/test_inventario.py`
  (spec 009) falla si falta, si una herramienta no responde a `--help`, si una función de
  `src/` no la usa nada o si una spec con sus tareas hechas tiene un RF sin prueba.
- `docs/superpowers/specs/` y `plans/`, y `docs/DIAGNOSTICO_*.md`, son históricos: no tienen
  requisitos numerados ni casillas al día.

## Pruebas

```bash
.venv/Scripts/python.exe -m pytest -q                      # sintéticas: omiten las de datos reales
IGEA_RED="referencia/RED_030826(1).txt" IGEA_LOADS="referencia/CARGA_030826(1).txt" \
IGEA_EQUIPMENT="referencia/BD_Equipo_V261124 (1)(1).txt" .venv/Scripts/python.exe -m pytest -q
```

Sin las tres variables `IGEA_*`, la mayoría de las pruebas de integración se omiten en
silencio y la suite «pasa» sin haber probado nada real. `IGEA_TXT_DIR` no basta. La suite se da
por buena solo sin ninguna omitida: con las siete variables (las tres de los TXT, las dos
de Access de abajo, `IGEA_DEMANDA_DIR="referencia"` e
`IGEA_VNR_BAK="referencia/Electro Dunas VNRGIS/DAT_VNR/ELDU_VNR_24_APR.bak"`, con SQL Server
Express en marcha, spec 023) y `-rs` pasan todas.

Para la vía Access (`tests/test_access_input.py`) hacen falta dos bases, porque la red
más reciente no trae catálogo de equipos:
`IGEA_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/260924.mdb"` e
`IGEA_EQUIPMENT_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/BASE JUL25 1.mdb"`.

Las fuentes son independientes: un TXT, una `.mdb` o un paquete VNR-GIS se convierten
y se prueban cada uno por su cuenta, sean de la empresa y la fecha que sean. No hay
pruebas que comparen una fuente con otra (se retiraron el 2026-10-14). Con las cinco
variables a la vez la suite pasa entera; solo dos pruebas de la demanda medida piden
además `IGEA_DEMANDA_DIR`.

## Probar en DIgSILENT

- Siempre por la web, como el operador: un sistema eléctrico entero con
  `.venv/Scripts/python.exe tools/sistema_web.py --espacio <id> --zonal Pisco --demanda-dir referencia --periodo 2026-07`
  (convierte, importa y calibra; retoma lo hecho). Nada de guiones del scratchpad que
  repitan la API.
- Tras cambiar `src/igea_dgs/web/` o `src/igea_dgs/*.py` que use la web, reiniciarla: parar
  el proceso del puerto 8765 y abrir el acceso directo «Conversor IGEA-DGS» del escritorio.
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
- Los TXT de `referencia/` y `D:\BaseDatosElectroDunas` son datos de la distribuidora: nunca se publican ni se suben a git. Desde el 2026-10-27 el usuario autoriza leerlos (sin `deny` en `.claude/settings.json`) para diagnosticar; las pruebas los siguen leyendo por las variables `IGEA_*`.
