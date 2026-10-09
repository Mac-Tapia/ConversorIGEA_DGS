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
- `specs/NNN-<nombre>/{spec,plan,tasks}.md`: una carpeta por funcionalidad. Specs activas, en este orden: `specs/001-reorganizacion/` y
  `specs/002-arquitectura-por-capas/`, aprobadas el 2026-10-08. La 001 está cumplida; la 002, aún sin plan ni tareas.
  `specs/005-carpeta-de-proyectos-pf/` (aprobada el 2026-10-09): implementada, falta la prueba manual en DIgSILENT (T12).
  La carpeta de DIgSILENT de cada empresa va en `config/perfil_empresa.json`, local y fuera de git.
- `docs/superpowers/specs/` y `plans/` son históricos: no tienen requisitos numerados ni casillas al día.

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
entera (1036 correctas y 20 omitidas a 2026-10-09; dos de ellas, de la demanda medida, piden además `IGEA_DEMANDA_DIR`): las comparaciones tramo a tramo entre las dos vías
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
