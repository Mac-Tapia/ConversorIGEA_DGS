---
name: igea-dgs-frontend
description: >-
  Guides work on the Conversor IGEA-DGS desktop UI (Tkinter gui.py, run_gui.bat).
  Use when editing the graphical interface, UX, threading, progress feedback,
  path pickers, packaging for end users, or production hardening of the GUI.
---

# IGEA-DGS Frontend (GUI de escritorio)

## Alcance

Este skill aplica solo a este repo. El “frontend” es la GUI Tkinter (`src/igea_dgs/gui.py`) y el launcher `run_gui.bat`. No hay web/React.

## Principios UX

1. **Tres TXT obligatorios:** RED, CARGA, BD_Equipo (catálogo TXT, no SQL).
2. **Flujo:** elegir archivos → listar alimentadores → seleccionar → Convertir a DGS.
3. **Geografía:** por defecto ON; si falta `pyproj`, mensaje accionable o permitir desactivar GPS.
4. **Vista previa / Excel / TSV:** checkboxes opcionales; preview exige geografía ON; Excel exige `[xlsx]`.
5. **Modo estricto:** checkbox ON por defecto (alineado con el motor).
6. **Feedback:** estado + registro (log); nunca dejar la UI congelada en cargas/conversiones largas.

## Checklist producción (GUI)

- [ ] Operaciones largas (leer TXT, convertir lote) en **hilo daemon**; UI solo vía `root.after`
- [ ] `_busy` deshabilita Convertir **y** Cargar / controles de entrada relevantes
- [ ] Progreso por alimentador (N de M) usando callback del backend
- [ ] Validar archivos existen; crear carpeta de salida si falta
- [ ] Aliases: si hay ruta, debe ser archivo JSON legible
- [ ] Errores: diálogo corto + detalle completo en el Registro
- [ ] Persistir últimas rutas (session) en `%LOCALAPPDATA%/igea-dgs/gui_state.json` (Windows) o `~/.igea-dgs/`
- [ ] `run_gui.bat`: preferir `.venv`, instalar `-e .` **sin** `[dev]` para usuarios finales
- [ ] No importar Tk dentro del motor (`batch`/`model`/…)

## Patrones

```python
def worker():
    try:
        result = convert_selection(..., on_progress=lambda nid, i, n: 
            self.root.after(0, lambda: self.status.set(f'{i}/{n} {nid}')))
        self.root.after(0, lambda: self._on_done(True, result))
    except Exception:
        tb = traceback.format_exc()
        self.root.after(0, lambda: self._on_done(False, tb))

threading.Thread(target=worker, daemon=True).start()
```

## Anti-patrones

- Llamar `convert_selection` o parsear RED en el hilo principal
- Mostrar solo traceback crudo en `messagebox` sin resumen
- Acoplar `tkinter` en `batch.py`
- Instalar pytest (`[dev]`) en el launcher de producción

## Archivos clave

- `src/igea_dgs/gui.py` — UI
- `run_gui.bat` — entrada Windows
- Entry point: `igea-dgs-gui` / `python -m igea_dgs.gui`
