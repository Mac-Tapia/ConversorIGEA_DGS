# Plan 098 — La transferencia de carga del operador, en la calibración y en las obras

## Módulos

| Fichero | Qué hace | RF |
| --- | --- | --- |
| `src/convertersmartgrid/transferencia_operador.py` (nuevo, puro) | `transferidas`, `zonas_transferidas` (componentes por union-find con las ramas que son de la fuente; lo que no es de la fuente y une la zona a quien la alimenta; camino más corto de abiertos hasta su origen), `texto_de_zona`, `maniobras_abiertas_del_dgs` | 1, 2, 8, 14, 15 |
| `tools/transferencia_operador_pf.py` (nuevo) | Lectura en DIgSILENT (una pasada por las cargas y, si hay transferidas, una por clase de rama, con los fuera de servicio de `netdat`); `RedDeLaFuente`: restituir lo pendiente, desactivar con registro en disco, comprobar que las SED vuelven, restituir con evidencia; `aviso_de_la_medida`; como orden suelta, solo lee | 1 a 9 |
| `tools/ajuste_cabecera_pf.py` | `ejecutar_proyecto` envuelve las tres vías (un alimentador, el proyecto, con bancos que faltan) en `RedDeLaFuente`, con `finally`; `_devolver_la_transferencia` antes de cada `escenario.Save()`; `_anotar_la_transferencia` en los informes | 3 a 8 |
| `tools/escanear_alimentador_pf.py` | `_transferencias`: zonas con bancos y generadores; marca bancos, generadores y tramos nuevos del que recibe | 9 |
| `src/convertersmartgrid/obras_integrales.py` | `con_maniobras` (el acoplador del camino pasa al tramo siguiente como `maniobra_previa`); `candidatos_de_transferencia` y `nodo_de_traslado` solo con maniobra; `nodos_de_traspaso` dice `sin_maniobra`; `variantes` lo avisa | 11, 13 |
| `tools/obras_pf.py` | `maniobra_del_tramo` y la de los acopladores en `tramos_red`; los caminos con `con_maniobras`; `construir_migracion` abre el `StaSwitch` del tramo de entrada con `abrir`; `abrir` y `_con_nombre` llevan el nombre completo del interruptor | 11, 12 |
| `src/convertersmartgrid/web/services.py` | `_dgs_aceptado`, `_red_de_la_fuente_del_plan` (tramos, abiertos y fecha de la importación) en el plan de la calibración y del escaneo | 14 |
| `tests/fake_pf.py` | `App.topologia_viva`: el `ElmFeeder` sigue lo que está en servicio y cerrado desde su cubículo, sin entrar por la cabecera de otro | pruebas |

## Decisiones

- **Desactivar la transferencia, no corregir la medida.** Primero se pensó sumar a X y restar a Y lo transferido en
  cada flujo; el usuario (2026-11-07) pidió calibrar con los alimentadores completos. Así las pérdidas negativas
  desaparecen solas y la medida se compara con la red en que se tomó.
- **Qué se abre.** Solo lo que no es de la fuente (tramo que no venía en el DGS aceptado, o cerrado ahora y abierto en
  el DGS) y lleva, sin volver a pasar por la zona, a lo que cuelga de la cabecera de quien la alimenta. Descartado:
  abrir todo tramo nuevo, porque cortaría SED nuevas del operador que nada tienen que ver.
- **Qué se cierra.** El camino más corto de elementos abiertos que en la fuente estaban cerrados (o sin estado) hasta lo
  que cuelga de la cabecera del origen. Las barras de cabecera se apartan del grafo: varios alimentadores salen de la
  misma barra de SET, y con ella todo quedaría unido.
- **Restituir antes de guardar.** Con la transferencia desactivada, `sin_a_con_proyecto` habría copiado el tramo nuevo
  fuera de servicio a «Con proyecto» (lo de «Sin proyecto» que difiere del «Caso base»). Se restituye antes del
  `escenario.Save()` de la calibración y otra vez en el `finally`.
- **Registro en disco.** Como el de las aperturas de las obras (081:RF-80), al lado y con su mismo formato, pero con el
  valor original de cada atributo: aquí se abre y se cierra a la vez, y restituir es volver al valor, no cerrar.
- **El escenario se guarda tras desactivar**, para que cambiar de caso (la segunda pasada de los bancos, 021:RF-64) no
  dependa de lo que DIgSILENT haga con un escenario con cambios sin guardar; el registro cubre la muerte del proceso.
- **Fecha de la medida.** La transferencia del operador es de después de importar el proyecto: con la medida de un mes
  anterior al de la importación es de antes; del mismo mes o posterior, no se sabe y se avisa.
- **La maniobra de la escalera.** Un `StaSwitch` en un cubículo del tramo de entrada, o un acoplador del camino, que
  `solo_lineas` quitaba: `con_maniobras` lo pasa al tramo siguiente. El interruptor de cubículo se anota con su nombre
  completo porque `SplitLine` los llama a todos «Switch».

## Pruebas

- `tests/test_transferencia_operador.py`, con `fake_pf` y `topologia_viva`: el caso real con cifras parecidas (X
  medido en 6 600 kW, Y en 2 728 kW): sin desactivar, «pérdidas activas negativas en F1 (-1 209,3 kW)»; con la 098,
  cuadran los dos con pérdidas positivas y la transferencia queda como estaba en «Sin proyecto» y «Con proyecto». Una
  excepción a mitad y una orden que muere; tres alimentadores sorteados con una cadena de transferencias; un proyecto
  sin transferencias (nada escrito); la parte pura en dos sentidos, sin estados del DGS, sin nada que abrir y con una
  SED nueva tras la zona; el escaneo; la web; y las obras (barras con maniobra, aviso sin ella, la migración que abre
  el seccionador y restituye solo ese).
- `tests/test_obras_integrales.py`: los caminos de las pruebas de la 087 llevan su seccionador.
