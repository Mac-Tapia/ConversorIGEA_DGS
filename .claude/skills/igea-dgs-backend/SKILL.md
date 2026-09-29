---
name: igea-dgs-backend
description: >-
  Reglas y checklist del motor de conversión IGEA/CYMDIST TXT → DIgSILENT DGS y de su
  API web. Usar al editar src/igea_dgs/*.py (salvo gui.py), src/igea_dgs/web/, el CLI,
  el lote multi-alimentador, el lector de TXT, la validación, el rendimiento o la
  escala (10, 50, 200+ alimentadores), y al evaluar o endurecer el backend.
---

# IGEA-DGS Backend (motor + API)

## Alcance

El «backend» es el motor Python, el CLI y la API web. La interfaz Tkinter (`gui.py`)
es heredada; la principal es la web (`src/igea_dgs/web/` + `frontend/`).

| Capa | Módulos | Rol |
| ---- | ------- | --- |
| Entrada | `dataset.py`, `access.py`, `identify.py` | Una lectura de RED / CARGA / BD_Equipo (TXT) o `.mdb`. Reconoce cada TXT por su contenido, no por su nombre |
| Índices | `CymdistDataset.*_by_feeder`, `intermediate_by_section` | Agrupan las tablas una vez por lote |
| Modelo | `model.py`, `catalog*.py` | Modelo aislado por alimentador; correcciones de catálogo |
| Salida | `dgs.py`, `geography.py`, `validate.py`, `export_tables.py`, `preview.py` | DGS determinista, GPS, validación estricta |
| Lote | `batch.py` | Multi-alimentador, publicación atómica, `batch_manifest.json`, `workers` |
| Red unida | `combine.py`, `puentes.py`, `studies.py` | Grid única con los N alimentadores; estudios |
| Borde | `cli.py`, `web/app.py`, `web/jobs.py`, `web/services.py`, `web/workspace.py` | CLI; API FastAPI + WebSocket; cola de trabajos con carriles `engine` y `powerfactory` |

## Reglas de dominio (no romper)

1. **Sin DGS de referencia en runtime.** `NA205.dgs` es solo para desarrollo.
2. **Modo estricto por defecto.** No inventar tipos `DEFAULT`; los alias solo vienen de un JSON del usuario.
3. **Independencia por alimentador.** Un fallo no invalida a los demás; el manifiesto dice OK/FAIL de cada uno.
4. **Determinismo.** Misma entrada + perfil + alias → mismo DGS **byte a byte**, en serie o en paralelo. El manifiesto sigue el orden de la selección, no el orden en que acaban los procesos.
5. **Geografía opcional.** `include_geography=False` funciona sin `pyproj`.
6. **Dos disposiciones de export.** CYMDIST da la misma red de dos formas («reducida» y «completa»). Tres de sus cinco diferencias no fallan: producen un modelo que converge con números falsos. Todo cambio en el lector se prueba con `ExportSpec(layout='completo')` además del de referencia.
7. **Publicación atómica.** Se escribe en `.igea-stage-<alimentador>` y se publica con `os.replace` solo si todo validó. Una cancelación nunca deja un `.dgs` a medias.

## Reglas del proyecto (siempre)

Toda conversión pasa por `reglas.py`: `preparar_dataset` (coordenadas por el grafo,
catálogo del proyecto) y `aplicar_reglas` (puentes `DEFAULT` ≤ 10 m fundidos, trafomix
`M…` excluidos, SED sobrecargadas redimensionadas, hoja a medida a escala real por
defecto, formatos A0–A4 solo explícitos, todo dibujado) y
`auditar_completitud` (un alimentador que pierde elementos no es «ok»). Las usan
`convert_selection`, `convert_group`, la web, el CLI y la GUI. Si añade una vía nueva,
llame a estas funciones; no copie la lógica. `SIN_REGLAS` solo para pruebas de fidelidad
literal a la entrada.

## Escala: el número de alimentadores no está fijado

Una entrega puede traer 10, 50, 200 o cualquier otro número de alimentadores, de tamaños muy
desiguales. Ningún número está grabado en el motor ni en las pruebas.

- **Prohibido recorrer una tabla completa por alimentador** (O(F·N)). Para lo que es de un
  alimentador se usan los índices del dataset: `customer_loads_by_feeder`,
  `switching_by_feeder` e `intermediate_by_section`. Si una tabla nueva hace falta por
  alimentador, se añade su índice como `cached_property`, conservando el orden de lectura.
  `TestNoFullTableScanPerFeeder` lo vigila de forma determinista: envenena las tablas
  completas y exige que la conversión funcione igual.
- **Paralelismo por procesos, no por hilos.** El motor es CPU pura: con hilos, el GIL no
  deja ganar nada. `convert_selection(..., workers=N)` reparte los alimentadores en un
  `ProcessPoolExecutor`; el dataset viaja **una vez por proceso** (`_init_worker`), no una
  vez por alimentador. `workers=0` es automático, con tope `AUTO_WORKERS_MAX`. Ese tope
  sale de una medición (96 alimentadores: 1 proceso 13,7 s, 4 procesos 4,8 s, 8 procesos
  8,0 s); si cambia el hardware, se vuelve a medir antes de cambiarlo.
- Lo que se ejecuta en un proceso hijo tiene que ser serializable con pickle y no puede
  depender de estado global del proceso padre.
- Los puntos de entrada ejecutables necesitan `if __name__ == '__main__':`. En Windows los
  procesos hijos vuelven a importar el módulo principal, y sin la guarda el pool se cuelga.

## Asíncrono: la API no bloquea

- Nada largo se ejecuta dentro de una petición HTTP. Se encola con
  `JobManager.submit(..., lane=...)` y el navegador sigue el avance por WebSocket, con
  eventos numerados (`EventLog.since(seq)`): al reconectar no se pierde ni se duplica nada.
- Carril `engine` para el motor y carril `powerfactory` para DIgSILENT. **Un solo proceso
  puede tener el motor de PowerFactory**, así que ese carril es estrictamente serie.
- La cancelación es cooperativa, con `threading.Event`: se comprueba entre alimentadores y
  nunca a mitad de uno.
- Si hiciera falta repartir el trabajo entre máquinas, se sustituye `web/jobs.py` (por
  Redis/RQ, por ejemplo) sin tocar las rutas de la API.

## Checklist (al tocar el motor, el CLI o la API)

- [ ] Rutas de entrada validadas antes de parsear; cada TXT comprobado por su contenido
- [ ] Códigos de salida del CLI: `0` OK, `2` fallos de conversión, `1` error de uso o de E/S
- [ ] Errores de usuario claros, en español; sin traza de pila salvo en el Registro de trabajos
- [ ] `batch_manifest.json` escrito siempre, también al cancelar o si algo revienta
- [ ] Sin recorridos completos de tablas por alimentador (ver Escala)
- [ ] Salida idéntica con `workers=1` y `workers>1` (`TestParallelWorkers`)
- [ ] Pruebas con exports sintéticos **sorteados** (`ExportSpec(seed=...)`), no solo con tamaños fijos
- [ ] Probadas las dos disposiciones de export
- [ ] Sin secretos ni rutas absolutas de la máquina en el código

## Pruebas

```bash
# Rápidas, sin datos reales (sintéticos):
.venv/Scripts/python.exe -m pytest -q tests/test_flexibility_and_scale.py tests/test_export_layouts.py

# Suite completa con los TXT reales. Van las tres variables, porque IGEA_TXT_DIR no
# resuelve los nombres con paréntesis:
IGEA_RED="referencia/RED_030826(1).txt" \
IGEA_LOADS="referencia/CARGA_030826(1).txt" \
IGEA_EQUIPMENT="referencia/BD_Equipo_V261124 (1)(1).txt" \
.venv/Scripts/python.exe -m pytest -q

# Repetir un sorteo que falló (la semilla aparece en el mensaje de fallo):
IGEA_SCALE_SEED=<semilla> .venv/Scripts/python.exe -m pytest -q tests/test_flexibility_and_scale.py
```

Las pruebas de escala se sortean: número de alimentadores, tamaño de cada uno y
disposición. Una prueba de tiempos con datos pequeños **no** detecta un O(F·N), porque el
coste lineal de escribir lo tapa. Para eso está la guarda determinista.

## Patrones preferidos

```python
# Progreso desacoplado: la GUI, la web y el CLI pasan un callable.
convert_selection(ds, sel, out, on_progress=cb, cancel=event, workers=0)
```

```python
# Índice por alimentador, construido una vez por lote.
@cached_property
def algo_by_feeder(self) -> dict[str, tuple[...]]:
    ...
```

## Anti-patrones

- `for row in dataset.<tabla>: if owner(row) != network_id: continue` dentro del bucle de alimentadores
- Fijar 96 (o cualquier otro número) de alimentadores en el código o en las pruebas
- Hilos para trabajo CPU del motor; procesos para PowerFactory (solo admite uno)
- Capturar `Exception` y callarla en el motor (en el borde CLI/web sí se captura, y se informa)
- Hacer trabajo largo dentro de un endpoint de FastAPI

## Empaquetado

- Python **3.12 exacto** (`powerfactory.pyd` de PF 2024 solo carga en 3.12)
- Extras: `[geo]`, `[xlsx]`, `[access]`, `[validate]`, `[preview]`, `[web]`, `[all]`, `[dev]`
- Scripts: `igea-dgs`, `igea-dgs-gui`, `igea-dgs-web`

## Referencias

- `docs/superpowers/specs/2026-09-10-universal-igea-dgs-engine-design.md`
- `docs/POWERFACTORY_ACCEPTANCE.md`, `docs/MANUAL_COMANDOS.md`
