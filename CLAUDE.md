# Conversor IGEA/CYMDIST → DIgSILENT PowerFactory DGS

Convierte los TXT que exporta IGEA/CYMDIST (RED, CARGA, BD_Equipo) en ficheros `.dgs`
que se importan en PowerFactory, un alimentador por fichero o todos en una red unida.

## Entorno

- Python **3.12 exacto**, en `.venv` (`.venv/Scripts/python.exe`). La API de PowerFactory 2024 solo carga en 3.12.
- Instalación: `pip install -r requirements-dev.txt`. La web necesita compilar el front una vez: `cd frontend && npm install && npm run build`.
- Web: `run_gui.bat` o `igea-dgs-web`. CLI: `igea-dgs convert --red ... --loads ... --equipment ... --all --out-dir out --workers 0`.

## Skills del proyecto

- `.claude/skills/igea-dgs-backend/SKILL.md`: reglas del motor, la escala y la API. **Léelo antes de tocar `src/igea_dgs/`.**
- `.claude/skills/igea-dgs-frontend/SKILL.md`: UX y checklist de la interfaz web (React en `frontend/`). Léelo antes de tocar `frontend/src/` o `src/igea_dgs/web/`.
- Las copias de `.cursor/skills/` son solo punteros a estas: el texto vigente es uno.

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
nodos están numerados de otra forma. Por eso, con las cinco variables a la vez,
`test_feeder_pa217.py` y `test_feeder_sl143.py` dan 10 fallos que no son del código:
comparan el mismo alimentador por las dos vías. Ejecute `tests/test_access_input.py`
por separado, o use un TXT y una `.mdb` de la misma exportación.

## Reglas que más se rompen

- El número de alimentadores es variable (10, 50, 200…): nada de recorrer una tabla entera por alimentador, y nada de tamaños fijos en las pruebas. Ver la sección «Escala» del skill.
- Dos disposiciones de export (reducida y completa): todo cambio en el lector se prueba con las dos.
- Determinismo: el DGS es idéntico byte a byte con `workers=1` y con `workers>1`.
- Idioma: código, comentarios, mensajes y commits en español, con el estilo de los existentes. Los comentarios explican **por qué**, con el caso real que lo motivó.
- Los TXT de `referencia/` y `D:\BaseDatosElectroDunas` son datos de la distribuidora: nunca se publican ni se suben.
