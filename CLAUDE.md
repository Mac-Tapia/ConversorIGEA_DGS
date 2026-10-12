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
- `specs/NNN-<nombre>/{spec,plan,tasks}.md`: una carpeta por funcionalidad. Estado a 2026-10-10:

  | Spec | Estado |
  | --- | --- |
  | 001 reorganización | cumplida |
  | 002 arquitectura por capas | aprobada; plan y tareas escritos el 2026-10-10, **pendientes de aprobar**; T1 (línea base) y T5 (perfil de empresa) adelantadas el 2026-10-12 |
  | 003 | no existe: la citan la 002 y la memoria para lo que queda de la rama `feat/integracion-web-retiro-gui`, tras las capas |
  | 004 cargas en PowerFactory | implementada y validada |
  | 005 carpeta de proyectos PF | implementada; falta la prueba en DIgSILENT (T12) |
  | 006 ajuste a la máxima | implementada; falta la prueba en DIgSILENT (T8): signo y lado de la cabecera |
  | 007 cargas sobre el ajuste | implementada el 2026-10-10 (una variación por carga, base del ajuste, RF-36/37 para varios alimentadores); falta la prueba en DIgSILENT (T11) |
  | 008 pestaña en tres pasos | implementada; falta la prueba en DIgSILENT con dos alimentadores (T7) |
  | 009 inventario del repositorio | implementada |
  | 010 trazado GPS de las líneas | cumplida; probada en DIgSILENT con NA203 + NA205 (574/574 líneas) |
  | 011 estudios y obras de mejora sobre la red calibrada | implementada el 2026-10-12 (129 RF, T1 a T18 y T17b, añadida en la validación para los guiones del operador en la web); falta la prueba en DIgSILENT (T19), con la lista de lo que confirmar en el plan |
  | 012 confiabilidad y capacidad de la red | spec aprobada el 2026-10-11 (72 RF): confiabilidad, reconectadores (`ComOpri`), capacidad de alojamiento, curvas PV y condensadores con los módulos nativos; tasas y costes de un libro Excel de la empresa. Plan y tareas aprobados el mismo día; T1 y T2 hechas (sondas en DIgSILENT real el 2026-10-12, RF-69 a RF-72 nuevos), sigue T3; T7, T8 y T11 dependen de T13, T15a, T16 y T17 de la 011 |

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
silencio y la suite «pasa» sin haber probado nada real. `IGEA_TXT_DIR` no basta.

Para la vía Access (`tests/test_access_input.py`) hacen falta dos bases, porque la red
más reciente no trae catálogo de equipos:
`IGEA_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/260924.mdb"` e
`IGEA_EQUIPMENT_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/BASE JUL25 1.mdb"`.

Esas bases **no** son la misma foto de la red que los TXT de `referencia/` (03/08): los
nodos están numerados de otra forma. Con las cinco variables a la vez la suite pasa
entera (más de 1100 correctas a 2026-10-10; dos de ellas, de la demanda medida, piden además `IGEA_DEMANDA_DIR`): las comparaciones tramo a tramo entre las dos vías
se omiten solas cuando `igea_dgs.huella` dice que no son la misma exportación. Que las
dos vías den el mismo modelo **no** está comprobado hasta tener un TXT y una `.mdb` de la
misma fecha.

## Reglas que más se rompen

- Universal: TXT, MDB y VNR-GIS de cualquier distribuidora. Electro Dunas es un caso de prueba; sus convenciones (CRS `EPSG:32718`, SED `M…`, escala NA205) van en un perfil de empresa, nunca como valor por defecto (constitución P13).
- El número de alimentadores es variable (10, 50, 200…): nada de recorrer una tabla entera por alimentador, y nada de tamaños fijos en las pruebas. Ver la sección «Escala» del skill.
- Dos disposiciones de export (reducida y completa): todo cambio en el lector se prueba con las dos.
- Determinismo: el DGS es idéntico byte a byte con `workers=1` y con `workers>1`.
- Idioma: código, comentarios, mensajes y commits en español, con el estilo de los existentes. Los comentarios explican **por qué**, con el caso real que lo motivó.
- Los TXT de `referencia/` y `D:\BaseDatosElectroDunas` son datos de la distribuidora: nunca se publican ni se suben. Tampoco se envían a un modelo de terceros: `.claude/settings.json` niega leerlos con la herramienta Read. Las pruebas los siguen leyendo por las variables `IGEA_*`.
