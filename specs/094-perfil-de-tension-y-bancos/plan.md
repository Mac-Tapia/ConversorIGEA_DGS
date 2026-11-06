# Plan 094 — Perfil de tensión y bancos según el perfil

## Dónde

- `src/convertersmartgrid/perfil_tension.py` (nuevo, puro): de un grafo con tensiones (el de `digital_twin`) arma el
  perfil de cada alimentador —barras de media, distancia por el camino eléctrico desde la cabecera, tensión— y las
  ubicaciones candidatas por caída igual, por 2i/(2n+1) y un banco por tramo, con la separación mínima (RF-1, RF-4,
  RF-6). Añade módulos uno a uno con el oráculo hasta el objetivo o la parada de RF-9 (RF-8, RF-9).
- `tools/ajuste_cabecera_pf.py`: al terminar la calibración, lee en «Sin proyecto» las tensiones de media y el grafo
  (la misma lectura que `digital_twin_snapshot_pf.py`) y escribe el perfil en su informe (RF-1), al final del flujo del conversor (cuadre de P y
  luego recalibración de P y Q, 035), con los bancos existentes en servicio; si queda
  AVISO_KVAR, el perfil lleva el aviso y el desvío (RF-10, RF-11). En «Con proyecto» no se cuadra nada: el perfil y
  los bancos se juzgan con lo que da DIgSILENT con cargas y obras (RF-12).
- `src/convertersmartgrid/web/services.py`: guarda el perfil con la calibración (RF-2); la escalera y el déficit previo
  toman las candidatas de banco de `perfil_tension` en vez de solo la barra de la carga (RF-4, RF-5); la confirmación en
  DIgSILENT y el valle siguen como están (RF-7).
- `frontend/src/` y `informes.py`: el gráfico del perfil por alimentador, con el límite (RF-3).

## Decisiones

- El perfil se calcula una vez, en la calibración, y los estudios lo reutilizan: así no se lee DIgSILENT dos veces y la
  ubicación sale del mismo estado que se calibró. Descartado: calcularlo en cada estudio.
- Distancia por el camino eléctrico, no en línea recta: dos barras cercanas por GPS pueden estar en ramales distintos.

## Pruebas

- `tests/test_perfil_tension.py`: perfil de una red sintética sorteada (troncal y ramales de tamaño variable): distancias,
  orden, reglas de ubicación, separación mínima, parada por objetivo, por mejora y por valle.
- Guion con el doble de DIgSILENT: el informe de la calibración trae el perfil.
- Web: el perfil se guarda y la escalera lo usa; el gráfico, en el navegador real.
