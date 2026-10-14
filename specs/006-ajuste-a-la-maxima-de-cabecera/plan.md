# Plan — Spec 006

Lee: `docs/constitution.md` y `specs/006-ajuste-a-la-maxima-de-cabecera/spec.md`.

## Contexto técnico

- La demanda medida (spec 004) vive en `src/igea_dgs/demanda_medida.py` y en
  `services.demanda_*`; la máxima es el resultado del trabajo `demanda_cabecera` y el
  cruce por alimentador lo da `services.demanda_clientes(ws, [alimentador])` (RF-43).
- Las cargas en DIgSILENT siguen el patrón plan → guion: `services.cargas_plan` escribe
  un JSON en `ws.plans_dir` y `services.cargas_ejecutar` lanza `tools/cargas_pf.py` en el
  carril `powerfactory`, con un fichero de cancelación y un informe JSON. De ese guion se
  reutilizan `activar_proyecto`, `Alimentadores`, `escribir_carga`, `error_relectura`,
  `foto_carga`, `crear_variacion` y el manejo del escenario activo.
- El kVA de la entrada original (RF-10) sale de `build_feeder_model(ws.dataset, feeder)`:
  `model.seds[i].code` y `design_kva`, como usa `sed_potencia.py`.
- Atributos de DIgSILENT 2024 comprobados en `localisation/en-GB/data.db`: `ElmFeeder.obj_id`
  (cubículo de la cabecera) y `obj_bus` (dirección); `ComLdf.itrlx` (iteraciones de
  Newton), `iStepAdapt` (tamaño del paso), `iopt_lev` (adaptación automática del modelo:
  DIgSILENT baja la dependencia de tensión de las cargas, «msgVDepOn»), `iopt_pq`
  (dependencia de tensión de las cargas).

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Reparto y cuadre, puro y sin DIgSILENT | `src/igea_dgs/ajuste_cabecera.py` (nuevo) | RF-5 a RF-8, RF-11 a RF-14, RF-16 (pasos), RF-18, RF-24 |
| Plan del ajuste en la web | `src/igea_dgs/web/services.py` (`ajuste_plan`, `ajuste_ejecutar`), `app.py` | RF-1 a RF-3, RF-4, RF-9, RF-10, RF-24 |
| Guion en DIgSILENT | `tools/ajuste_cabecera_pf.py` (nuevo) | RF-4, RF-9, RF-10, RF-11, RF-12, RF-15 a RF-22 |
| Interfaz | `frontend/src/components/DemandaMedida.tsx`, `api.ts`, `types.ts` | RF-2, RF-3, RF-20, RF-21, RF-23 |

### `ajuste_cabecera.py`

- `objetivo_de(maxima) -> Objetivo(kw, kvar, fp, medidor)`: RF-1 y RF-3.
- `fijas_de(cruzados) -> dict[sed, (kw, kvar, avisos)]`: suma por SED de la `pot` de sus
  clientes; kVAR = kW × ERI/EA de la suma de sus clientes (RF-6), y con el FP del
  objetivo si falta EA o ERI (RF-7).
- `Reparto`: kW y kVAR por SED, con su origen (`cliente` o `kva`). Las repartidas llevan
  `kp × kVA` y `kq × kVA`: dos factores para todo el alimentador (RF-8).
- `reparto_inicial(objetivo, fijas, kva)`: el que falta sin pérdidas. Si las fijas no
  dejan nada (RF-13), modo «todo escala»: las fijas por un factor `f` y las repartidas
  con `kVA × (ΣkW fijas / ΣkVA fijas) × f`. Si el kVAR que falta es negativo (RF-14), modo
  «solo kW»: `kq = kp × tan φ` del objetivo.
- `Cuadre`: método de la secante sobre `kp` (y sobre `kq` aparte) con lo medido en la
  cabecera; el primer paso supone pérdidas proporcionales (`k ← k × objetivo/medido`).
  `cuadrado(medido)` aplica RF-11 con la tolerancia. Guarda el último reparto que
  convergió.
- `escalera_de_remedios()`: lista ordenada y finita (RF-16): (1) paso a medio camino
  desde el último reparto que convergió, hasta 4 veces; (2) `itrlx` × 3; (3)
  `iStepAdapt` automático; (4) `iopt_lev = 1` y `iopt_pq = 1`. Cada remedio es un dato
  `(nombre, {atributo: valor})`, para que el informe diga qué cambió (RF-17).

### `tools/ajuste_cabecera_pf.py`

1. Activa el proyecto por su ruta y busca el `ElmFeeder` del alimentador; sin él, error
   (caso límite: no hay cabecera que medir).
2. Cargas de SED del alimentador por nombre, como `resolver_demandas` (RF-9).
3. kVA de cada SED: transformadores `ElmTr2` conectados a la barra de la carga
   (`typ_id.strn` × 1000), sumados si hay varios; si no hay, el `kva_entrada` del plan
   (RF-10); si tampoco, error de datos y no se escribe nada (RF-24).
4. Simular: devuelve el reparto inicial por SED, sin variación (RF-20).
5. Aplicar: desactiva el escenario activo, crea la variación (RF-19), escribe el reparto
   con `escribir_carga` y repite flujo → medir cabecera → corregir (RF-12) hasta cuadrar o
   agotar 30 flujos. Lo que entra por la cabecera: `m:Psum:busN` y `m:Qsum:busN` de la rama
   del cubículo `obj_id`, en el lado del cubículo y con el signo de `obj_bus`.
6. Si un flujo no converge: diagnóstico (RF-15) y siguiente remedio (RF-16); los ajustes
   del `ComLdf` se guardan antes y se restituyen al final, porque son del caso de estudio
   del operador y no de la variación. El informe dice cuáles hicieron falta (RF-17).
7. Al acabar sin cuadrar, o al cancelar, vuelve a escribir el último reparto que
   convergió (RF-18, RF-22).

Diagnóstico (RF-15), del último flujo que convergió: barras con `m:u` < 0,5 o sin
resultados (aisladas); transformadores y líneas con `c:loading` > 100 %; la barra de menor
tensión. Sin un flujo convergido, solo las barras sin resultados y los transformadores
cuya carga escrita supera su kVA (el caso de `SE50111` en `sed_potencia.py`).

## Decisiones

- Iteración propia en Python sobre el flujo de DIgSILENT. Descartado: el escalado de
  alimentador del propio DIgSILENT (`ComLdf.iopt_fls`, `ElmFeeder.i_scale`,
  `ElmLod.i_scale`), porque deja el resultado en un factor de escala del flujo y no en la
  demanda de cada carga, no permite acercarse en pasos desde el último reparto que
  convergió (RF-16) y sus atributos de consigna no están comprobados en esta versión.
- Dos factores (`kp`, `kq`) para todas las SED repartidas. Descartado: un factor por SED,
  porque rompería la proporción al kVA de RF-8.
- En «todo escala» (RF-13), la base de las repartidas es su kVA por la utilización media
  de las fijas. Descartado: dejarlas en 0, porque la spec dice «junto con las demás».
- El objetivo lo manda la web desde la máxima mostrada (RF-1: «el mismo valor que muestra
  su tabla») y el servidor lo comprueba contra el resultado del trabajo `demanda_cabecera`.
  Descartado: volver a abrir los libros de cabecera, que pesan cientos de MB.
- Los ajustes del `ComLdf` se restituyen al final. Descartado: dejarlos, porque cambiarían
  los flujos que el operador ejecute después en ese caso de estudio sin que lo sepa.

## Comprobación contra la constitución

- P7: plan en la petición (rápido, sin DIgSILENT); simular y aplicar son trabajos del
  carril `powerfactory`, con progreso por flujo y cancelación por fichero.
- P9: pruebas con libros y proyectos sintéticos (`tests/fake_pf.py`); la prueba en
  DIgSILENT la hace el usuario.
- P10: código, mensajes e informe en español.
- P12: cada RF con su prueba `006:RF-n`.
- P13: ningún código de empresa; la tolerancia y el número de flujos son opciones.
- P2: el reparto es lineal en el número de SED; nada de recorrer el proyecto por SED.

## Estrategia de pruebas

- `tests/test_ajuste_cabecera.py`: reparto y cuadre con una red de juguete cuyas pérdidas
  son cuadráticas en la carga (`pérdidas = a × P²`), y otra que «no converge» por encima de
  un umbral, para la escalera de remedios. Número de SED sorteado.
- `tests/test_ajuste_cabecera_guion.py`: el guion con `tests/fake_pf.py` ampliado con
  `ElmTr2`, cubículo de cabecera y un `ComLdf` simulado que calcula la cabecera con esas
  mismas pérdidas.
- `tests/test_demanda_medida_web.py`: plan del ajuste (RF-1 a RF-3, RF-10, RF-24) y
  trabajo en el carril `powerfactory`.
- Cada prueba cita su requisito: `"""006:RF-n — …"""`.

## Riesgos

- El signo y el lado de `m:Psum` en el cubículo de cabecera: si están al revés, el cuadre
  diverge. Se detecta en la prueba en DIgSILENT (el informe da lo medido en cada flujo).
- Cargas cuyo nombre no es el código de SED: quedan fuera del reparto y el informe las
  lista.
- `iStepAdapt` o `iopt_lev` con otro sentido en otra versión de DIgSILENT: el guion
  comprueba que el atributo existe antes de escribirlo y lo informa si no.

## Curva del registro del medidor (RF-31 a RF-39, cambio del 2026-10-12)

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Curva y reducción, puras | `src/igea_dgs/demanda_medida.py` | RF-31, RF-37, RF-39 |
| Guardar la curva y servirla | `src/igea_dgs/web/services.py`, `workspace.py`, `app.py` | RF-31, RF-35, RF-38, RF-39 |
| Gráfica | `frontend/src/components/CurvaCabecera.tsx` (nuevo), `AjusteCabecera.tsx`, `api.ts`, `types.ts`, `styles.css` | RF-32 a RF-36, RF-38 |

### `demanda_medida.py`

- `maxima_de_registros` ya recorre todos los registros: guarda en `MaximaCabecera.curva`
  la lista ordenada por fecha de `(fecha, kw, kvar)` de los registros con fecha
  `datetime` y kW numérico, y en `fuera_de_curva` cuántos dejó fuera (RF-31, RF-37).
  `to_dict` **no** incluye `curva`: el resultado del trabajo viaja entero al navegador
  por el WebSocket y un año de lecturas de 15 min son ~35 000 registros por medidor.
- `reducir_curva(curva, desde, hasta, max_puntos) -> list`: recorta al tramo y, si
  quedan más de `max_puntos`, parte el tramo en `max_puntos // 2` intervalos de tiempo
  iguales y conserva de cada uno el registro de kW mínimo y el de kW máximo, en su orden
  (RF-39). El registro de la máxima siempre sobrevive: es el máximo de su intervalo.

### Web

- `services.demanda_cabecera` guarda las curvas en `ws.curvas_cabecera[job_id] =
  {medidor: curva}`, en memoria y solo la del último trabajo de máxima del espacio
  (sustituye la anterior), para no acumular cientos de miles de registros.
- `GET /api/workspaces/{wid}/demanda/cabecera/{job_id}/curva?medidor=&desde=&hasta=`
  devuelve `{medidor, inicio, fin, maxima: {fecha, kw}, puntos: [[iso, kw, kvar]],
  total, reducida, fuera_de_curva}`. Sin `desde`/`hasta`, el registro entero (RF-32);
  con ellos, el tramo (RF-35). `max_puntos` = 2 000, fijo en el servidor. 404 si el
  trabajo ya no es el último o el medidor no está; 422 si `desde > hasta`.
- La franja del mes (RF-33) la calcula el front con la fecha de la máxima: no hace falta
  pedirla al servidor.

### `CurvaCabecera.tsx`

- SVG propio, una `polyline` de kW (y otra de kVAR si se activa, RF-36), ejes con
  fechas y kW, un `rect` sombreado del día 1 al último del mes de la máxima (RF-33) y un
  círculo con su etiqueta en el punto de la máxima (RF-34).
- Zoom: arrastrar sobre la gráfica selecciona un tramo y pide ese tramo al servidor;
  «Ver todo» vuelve al registro entero (RF-35). Sin rueda del ratón: en una página que
  hace scroll, la rueda no debe capturarse.
- Selector de medidor si el alimentador tiene varios con curva, por defecto el que da
  el objetivo (RF-38). Aviso con `fuera_de_curva` si es mayor que 0 (RF-37).
- Colores con los tokens de `styles.css` (modo claro y oscuro).
- Va en la caja del ajuste, a todo el ancho, encima de la tabla del objetivo.

### Decisiones

- SVG propio. Descartado: `recharts` (~100 kB comprimidos más en un front de 109 kB) y
  `uPlot` (pinta en canvas, sin tokens CSS para el modo oscuro, y otra dependencia que
  mantener) para una sola línea de 2 000 puntos.
- La curva se guarda al buscar la máxima. Descartado: releerla del libro al dibujar,
  porque abrir un libro de cabecera cuesta segundos y pesa cientos de MB.
- Reducción mín./máx. por intervalo. Descartado: la media diaria, que aplana el pico
  y haría que la máxima marcada no estuviera sobre la línea.
- Mes natural para la franja (RF-33), como se acordó al aprobar la spec.

### Pruebas

- `tests/test_demanda_medida.py`: curva y `fuera_de_curva` desde un libro sintético;
  `reducir_curva` con longitudes sorteadas y la máxima en una posición sorteada, que
  nunca desaparece y no pasa de `max_puntos` (RF-31, RF-37, RF-39).
- `tests/test_demanda_medida_web.py`: endpoint con registro entero y con tramo, 404 y
  422; el resultado del trabajo no lleva la curva (RF-31, RF-32, RF-35, RF-38).
- `tests/test_ajuste_cabecera_web.py` o una prueba de front estática como
  `tests/test_cargas_tres_pasos_front.py`: el componente existe, tiene la franja, la
  marca, el zoom, el kVAR y el selector (RF-32 a RF-36, RF-38).

