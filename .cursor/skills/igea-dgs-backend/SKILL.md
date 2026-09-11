---
name: igea-dgs-backend
description: >-
  Guides work on the IGEA/CYMDIST→DGS conversion engine (dataset, model, dgs,
  validate, geography, batch, CLI). Use when editing src/igea_dgs/*.py (except
  gui.py), CLI, packaging, schema profiles, strict-mode rules, batch manifests,
  or production hardening of the converter core.
---

# IGEA-DGS Backend (motor de conversión)

## Alcance

Este skill aplica solo a este repo. El “backend” es el motor Python + CLI, no un servidor web.

| Módulo | Rol |
| ------ | --- |
| `dataset.py` | Una lectura de RED / CARGA / BD_Equipo |
| `schema.py` + `schemas/*.json` | Perfil DGS versionado (solo tablas/campos) |
| `model.py` | Modelo aislado por alimentador |
| `dgs.py` | Escritura determinista `.dgs` |
| `validate.py` | Validación estricta post-escritura |
| `geography.py` | GPS + diagrama (opcional; requiere `pyproj`) |
| `batch.py` | Multi-feeder + `batch_manifest.json` |
| `cli.py` | `list` / `convert` / `gui` |

## Reglas de dominio (no romper)

1. **Sin DGS de referencia en runtime.** `NA205.dgs` es solo desarrollo; no empaquetar ni parsear en producción.
2. **Modo estricto por defecto.** No inventar tipos `DEFAULT`; aliases solo desde JSON externo del usuario.
3. **Independencia por alimentador.** Un fallo no invalida otros; el manifiesto refleja OK/FAIL.
4. **Determinismo.** Misma entrada + perfil + aliases → mismo DGS.
5. **Geografía opcional.** `--no-geography` / `include_geography=False` debe funcionar sin `pyproj`.

## Checklist producción (backend)

Al tocar el motor o el CLI, verificar:

- [ ] Validar existencia/legibilidad de rutas de entrada antes de parsear
- [ ] Códigos de salida CLI: `0` OK, `2` fallos de conversión, `1` error de uso/IO
- [ ] Errores de usuario claros (español o inglés consistente con el módulo); sin stack traces en stdout salvo `--verbose` si existe
- [ ] `batch_manifest.json` siempre escrito al final del lote
- [ ] Callbacks de progreso opcionales en `convert_selection` (para GUI) sin acoplar a Tk
- [ ] `pyproj` como dependencia de geografía, no bloquear conversión sin GPS
- [ ] Tests en `tests/` para cambios de reglas de conexión/validación
- [ ] No meter secretos ni rutas absolutas de máquina en código

## Patrones preferidos

```python
# Progreso desacoplado (GUI/CLI pueden pasar callable)
def convert_selection(..., on_progress=None):
    for network_id in networks:
        if on_progress:
            on_progress(network_id, index, total)
        ...
```

```python
# CLI: fallar temprano
for label, path in (...):
    if not Path(path).is_file():
        raise SystemExit(f'Missing {label}: {path}')
```

## Empaquetado

- Paquete: `igea-dgs` (`pyproject.toml`), scripts `igea-dgs` / `igea-dgs-gui`
- Extra `dev`: pytest
- Runtime geo: `pyproj` (documentar; idealmente extra `[geo]` si se hace opcional en deps base)
- Usuarios finales: instalar sin `[dev]` (`pip install -e .`)

## Anti-patrones

- Hardcodear aliases desde alimentadores de ejemplo
- Embebidos de datos topológicos en el schema profile
- Capturar `Exception` genérica y silenciar en el motor (sí en borde CLI/GUI)
- Bloquear el event loop de la GUI desde el motor (usar hilos + callbacks)

## Referencias del repo

- Spec: `docs/superpowers/specs/2026-09-10-universal-igea-dgs-engine-design.md`
- Aceptación PF: `docs/POWERFACTORY_ACCEPTANCE.md`
