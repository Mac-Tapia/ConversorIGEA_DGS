---
name: igea-dgs-frontend
description: >-
  Reglas de UX y checklist de la interfaz web del conversor IGEA-DGS (React + TypeScript
  en frontend/, servida por la API FastAPI de src/igea_dgs/web/). Usar al editar
  frontend/src/**, al añadir una opción o un botón que llame a la API, al tocar el
  Registro, el progreso o la cancelación, y al evaluar la interfaz. La GUI Tkinter
  (gui.py) es heredada.
---

# IGEA-DGS Frontend (interfaz web)

## Alcance

| Pieza | Dónde | Rol |
| ----- | ----- | --- |
| Estado | `src/useWorkspace.ts`, `src/context.tsx` | Espacio de trabajo, Registro en vivo por WebSocket, trabajos |
| Cliente | `src/api.ts`, `src/types.ts` | `fetch` tipado; `ApiError` con el `detail` del servidor |
| Paneles | `src/components/*.tsx` | Entradas, Opciones, Alimentadores, Módulos, Registro, barra de trabajos |
| Estilo | `src/styles.css` | Tokens en `:root`, modo oscuro con `prefers-color-scheme` |
| Servidor | `src/igea_dgs/web/` | La API sirve `frontend/dist`; ver el skill `igea-dgs-backend` |

`run_gui.bat` abre la web. La interfaz de escritorio (`gui.py`, `run_gui_escritorio.bat`)
está heredada: solo se corrige, no recibe funciones nuevas.

## Principios de UX

1. **Flujo:** subir o asignar RED, CARGA y BD_Equipo (o una `.mdb`) → Cargar → elegir alimentadores → Convertir → descargar. Cada TXT se reconoce **por su contenido**: si está en la casilla equivocada, se avisa en ella.
2. **Nada largo bloquea la página.** Cargar, convertir y hablar con PowerFactory son **trabajos** (`startJob`). El botón inicia el trabajo, y el progreso y el Registro llegan por WebSocket.
3. **Feedback siempre visible:** progreso N/M, estado de cada alimentador en la tabla, Registro con cada línea del motor. Un error de usuario se muestra con el `detail` del servidor, no como «Error 500».
4. **Bloqueo coherente:** mientras corre un trabajo del carril `engine`, se desactivan las entradas y opciones que lo invalidarían (`locked = Boolean(active.engine)`). El carril `powerfactory` bloquea solo lo suyo.
5. **Cancelar dice la verdad:** no se empieza ningún alimentador más; los que están en marcha terminan y se conservan. Ningún DGS queda a medias. No prometer «se descarta» (ver la prueba `test_cancelar_en_serie_termina_el_alimentador_en_marcha`).
6. **El número de alimentadores es variable** (10, 50, 200…): la tabla filtra, ordena y admite selección con Mayús. Nada de listas fijas ni de textos con «96».
7. **Opciones con consecuencias explicadas:** si una casilla depende de otra (vista previa ↔ georreferenciación) o de una capacidad del servidor (`health.capabilities`), se desactiva y dice por qué. El selector de procesos explica que más no siempre es más rápido.

## Checklist (al tocar la web)

- [ ] Una opción nueva existe en los cuatro sitios: `DEFAULT_OPTIONS` (workspace.py), `OptionsIn` con su validación (app.py), `Options` (types.ts) y el panel
- [ ] Valores fuera de rango rechazados por la API (422), no solo ocultos en la interfaz
- [ ] Todo lo que tarda más de un segundo va como trabajo, con progreso y cancelable
- [ ] Botones desactivados mientras su trabajo corre; sin doble envío
- [ ] Textos en español, sin tecnicismos del motor; el detalle técnico va al Registro
- [ ] Funciona sin `localStorage` (navegación privada): todo acceso va en `try/catch`
- [ ] Modo claro y oscuro, usando tokens y sin colores fijos
- [ ] `npx tsc --noEmit -p frontend` sin errores y `npm run build` correcto
- [ ] Prueba de API en `tests/test_web_api.py` para cada endpoint u opción nueva

## Patrones

```tsx
// Una acción larga: trabajo en cola, nunca await dentro del clic esperando el resultado.
const convert = () => startJob(() => api.convert(ws.id, { all: true }));
```

```tsx
// Guardar una opción: la API valida y devuelve el espacio actualizado.
const save = async (patch: Partial<Options>) => {
  const r = await run(() => api.setOptions(ws.id, patch));
  if (r) setWs(r);
};
```

## Anti-patrones

- Llamar desde un endpoint al motor de forma síncrona: bloquea el servidor para todos
- Sondear el estado con `setInterval` cuando ya existe el WebSocket con `since`
- Duplicar en el front reglas que decide el servidor (qué CRS vale, qué casilla es cuál)
- Mostrar una traza de pila en un diálogo

## Desarrollo

```bash
cd frontend && npm install
npm run dev            # Vite con proxy a la API en :8765
npm run build          # genera frontend/dist, que sirve igea-dgs-web
.venv/Scripts/python.exe -m pytest -q tests/test_web_api.py
```
