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
| `src/convertersmartgrid/web/services.py` | `_dgs_aceptados`, `_red_de_la_fuente_del_plan` (tramos, abiertos y fecha de la importación) en el plan de la calibración y del escaneo | 14 |
| `tests/fake_pf.py` | `App.topologia_viva`: el `ElmFeeder` sigue lo que está en servicio y cerrado desde su cubículo, sin entrar por la cabecera de otro | pruebas |
| T7: `transferencia_operador.py` | `red_del_dgs` (barras de cada rama por sus `StaCubic`), `frente_a_la_fuente` (particiones por la cadena de ramas y barras nuevas; lo demás nuevo, enlace del operador); en `tools/transferencia_operador_pf.py`, `red_de_la_fuente` lee `dgs_fuente` y `_por_ruta` busca por nombre completo; la web pasa `dgs_fuente` y la fecha del sello | 14, 16 a 19 |
| T8: `obras_integrales.variantes_por_enlace`; `optimizacion_oraculo` (la obra «maniobra» en el grafo, `EspacioConObra`, `transferencias_con_oraculo`); `obras_pf` (clase «maniobra»: validación, plan y persistencia en el escenario); `tools/obras_pf.py` (`enlaces_existentes` en `--escalera-datos`, `construir_maniobra`, `cerrar_anotado` y su restitución, `_gps_por_la_red`); `escalera_optima.grupo_economico`; `services` (`_preparar_oraculo`, `_variantes_de_traspaso`, `obras_escalera`, `escalera_por_alimentador`) | 20 a 27 |
| T9: `tools/obras_pf.py` (`sin_cambio`, «no aplicada» en `evaluar`, `bajas` en `--escalera-datos`); `tools/digital_twin_snapshot_pf.py` (`u_medida`); `optimizacion_oraculo.Oraculo` (corrección por barra); `services` (`_bajas_sin_cargas`, `_escalera_sin_cargas`, el desvío y la tabla); `tests/fake_pf.py` (una obra activa alivia la caída de su alimentador) | 28 a 30 |
| T10: `escalera_optima` (`_por_varios_caminos`, `Variante.caminos`, `no_aguanta`, costos de sección y terna); `tools/obras_pf.py` (`_activar_en_el_flujo`, `restituir_el_flujo`, el regulador sin efecto); `services` (`_huella_de_la_medida`, `_medidas_ya_hechas`, `_guardar_medidas`) | 31 a 35 |
| T11: `escalera_optima` (`elegir` con `largo_plazo`, `REGLA_DE_PLAZOS`, `alternativas` con su plazo, `factor_terna_sin_capex`); `tools/obras_pf.py` (`_ldf_del_caso`, `anotar_valor`, `_otras_tomas`, `restituir_valores`, `con_variante` con `aplicar` dentro del `try`, `huella_de_la_red`, `ya_medidas` en `evaluar`, el alcance de cada una que cumple, `retirar_obras` con `operacion_de_obras`); `services` (`_comparar_y_cambiar`, `_obras_que_no_aguantan`, la operación de la obra aplicada, `ya_medidas`); `informes.filas_alternativas_escalera` (Mínima de media y Plazo); `frontend/src/alternativas.ts` y `CargasTab.tsx` | 32, 34 a 37 |
| T12: `services` (`_obras_a_comparar`, `_decidir_sustitucion`, `_sustituir`, `_reponer_obra`, `_retirar_obras` por nombres, el origen y la elección en `registrar_obra_aplicada` y `obras_ejecutar`, `_huella_de_la_eleccion`, `apartar_obras` y `conservar` en `obras_escalera`); `tools/obras_pf.py` (`retirar_obras` con `variaciones`, `_reguladores_activos`, `anotar_valores`, `TOMAS_AUTOMATICAS`, `_apartar_cargas_de` con `obras`, la huella con `_de_tipo` y el escenario, `probados`); `escalera_optima` (`contiene`, `cuando_hace_falta`, `_factor_terna`) | 32, 34 a 37 |
| T13: `tools/obras_pf.py` (`sustituir`, `deshacer_sustitucion`, `_recuperar_especiales`, `anotar_apartadas`, `_diario`, `deshacer_operacion`, `rehacer_operacion`, `_guardar_original`, `restituir_flujo_original`, `ACCIONES_ESPECIALES`, la huella por alimentador); `services` (`_evidencia_de_escalera`, `_medir_la_vieja`, `_fila_de_la_vieja`, `_decidir_sustitucion` con `ok`, `_sustituir` sin borrar antes, `sustituir` y `huellas` en `obras_escalera` y `obras_ejecutar`, las rondas de conjunto) | 34, 36 |

## Decisiones

- **Corregir el oráculo con DIgSILENT, barra por barra (T9).** El grafo se lee con el flujo hecho; la caída de cada
  barra se escala a la medida. Descartado: resolver el flujo desequilibrado en el oráculo, que pide las fases de cada
  carga y su conexión, que el grafo no trae. La corrección conserva el orden de las obras y corrige el sesgo donde está.
- **Lo que no se aplicó no se mide.** Una obra inactiva en «Con proyecto» o sin efecto alguno se marca «no aplicada»;
  el doble de pruebas alivia la caída del alimentador con una obra activa, para que esa comprobación no dé por no
  aplicadas las obras de las pruebas de siempre.

- **La transferencia por enlace existente, como una variante más del oráculo (T8).** El oráculo ya juzga la
  topología (`con_set_nueva` abre ramas): la maniobra es abrir una rama y cerrar el enlace en el mismo grafo. Así entra
  en `elegir_para_k` con los sorteos y en `a_confirmar`, y DIgSILENT confirma solo las mejores (087:RF-39, RF-40).
  Descartado: una etapa aparte que recorriera las maniobras una a una en DIgSILENT.
- **Combinar con la escalera.** Sobre la topología de las mejores transferencias se repiten las variantes de bancos de
  la escalera y la bayesiana del espacio del alimentador (`EspacioConObra`, la misma búsqueda con la transferencia
  delante); compiten por costo. Las transferencias por enlace nuevo (087) no las calcula el oráculo: siguen midiéndose
  en DIgSILENT, ahora antes del nivel.
- **Grupo económico.** La transferencia va con los bancos (042:RF-56), antes que la sección y la terna.
- **Cerrar con registro.** El enlace que se cierra se anota como lo que se abre (`cerrar_anotado`, con `accion:
  cerrar`), y al restituir se vuelve a abrir. La obra solo toca el escenario: su variación queda vacía y la
  comprobación de persistencia (048:RF-9) no la da por perdida.

- **Comparar con el DGS rama por rama (T7).** Por solo los nombres de los tramos, la mitad nueva de una partición
  parecía un tramo nuevo que abrir y un acoplador nuevo no se veía. Con las barras de cada rama en el DGS, una partición
  (la rama del DGS con otras barras más la cadena nueva que vuelve a unir las originales) es la rama de la fuente, y lo
  abierto en ella es el punto del operador. La cadena solo avanza por barras nuevas: un acoplador nuevo entre barras
  del DGS no se confunde con una partición. Descartado: depender de `abiertos_dgs`, que el DGS del conversor no trae.

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
