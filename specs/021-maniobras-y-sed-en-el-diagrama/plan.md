# Plan — Spec 021

Lee: `docs/constitution.md` y `specs/021-maniobras-y-sed-en-el-diagrama/spec.md`.

## Contexto técnico

Cuatro bloques independientes, que se pueden entregar por separado y en este orden:

1. **Maniobras de los puentes** (motor, DGS). `src/igea_dgs/puentes.py` decide hoy entre
   fundir y `Coupler`; `src/igea_dgs/dgs.py` escribe los `Coupler` como `ElmCoup`
   (líneas 1214-1236) y los `SwitchingDevice` de `model.devices` como `StaSwitch` en el
   cubículo `line_cubic_fids[(section_id, terminal_side)]` (líneas 1268-1278). El cambio
   es sobre todo en `puentes.py`: un equipo plegado deja de ser `Coupler` y pasa a ser un
   `SwitchingDevice` de la línea vecina, y `dgs.py` ya lo escribe sin tocarlo. El
   trafomix se quita en `src/igea_dgs/trafomix.py`, después de `fundir_puentes`
   (`reglas.aplicar_reglas`); la completitud está en `reglas.auditar_completitud`
   (líneas 210-241).
2. **SED unidas a su barra** (DGS, dibujo). `dgs.py` escribe el triángulo `SecSubProd`
   sobre la barra exterior, sin `IntGrfcon` (líneas 1451-1470). La barra exterior es la
   `NODE_…_SE…` y el `ElmCoup` interno `SW_SE…` la une a la barra de MT de la SED.
3. **Curvas de varios alimentadores** (web). `frontend/src/components/CurvaCabecera.tsx`
   pinta una serie; `AjusteCabecera.tsx` le pasa un medidor inicial y un desplegable.
   La ruta `GET /api/workspaces/{wid}/demanda/cabecera/{job_id}/curva` (`web/app.py:1093`,
   `services.demanda_curva`) devuelve una curva por medidor, y se reutiliza tal cual.
4. **Central térmica** (demanda medida, plan del ajuste, guion de DIgSILENT, web).
   `src/igea_dgs/demanda_medida.py` (lectura y máxima), `src/igea_dgs/ajuste_cabecera.py`
   (objetivo, reparto, cuadre), `src/igea_dgs/web/services.py` (`maximas` en la búsqueda
   de la máxima, `ajuste_plan`), `tools/ajuste_cabecera_pf.py` (crear el generador y
   medir en el flujo), `src/igea_dgs/troncal.py` (`aguas_abajo`), perfil de empresa en
   `src/igea_dgs/perfil_empresa.py`. Carril `powerfactory` para el guion; el cálculo de
   la máxima va en el carril `engine`, como hoy.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Plegar el equipo del puente en el cubículo de la línea vecina | `puentes.py` (`fundir_puentes`: segunda pasada sobre los puentes con equipo; `SwitchingDevice` con `section_id` y `terminal_side` de la línea vecina; unión de las dos barras) | RF-1, RF-2, RF-3, RF-5, RF-6 |
| B. Cubículo ocupado: queda `ElmCoup` | `puentes.py` (conjunto de cubículos ya ocupados por un equipo de la base o por otro plegado, en orden de `section_id`) | RF-4 |
| C. Fusible del trafomix sin destino | `trafomix.py` (tras excluir: `Coupler` cuyo extremo es una barra sin nada más → se quitan los dos; lista de nombres en el informe) | RF-7, RF-8 |
| D. Completitud y reglas | `reglas.py` (`auditar_completitud` suma los quitados de C; `SIN_REGLAS` no pliega) | RF-9, RF-10, RF-11 |
| E. Sonda de la SED en DIgSILENT | guion de sonda en `tools/` (solo sobre una copia de un proyecto importado, borrada al acabar): dos variantes del DGS de una SED y cuál sigue al moverla | duda abierta, RF-12 |
| F. SED unida a su barra | `dgs.py` (bloque de `SecSubProd`), según E | RF-12, RF-13, RF-14 |
| G. Lectores de maniobras | `tools/transferencia_pf.py` (ya lee `StaSwitch` de cubículos: solo prueba), `oraculo.py`, `informes.py` (trecho del conductor) | RF-15, RF-16 |
| H. Gráfica con varias series | `CurvaCabecera.tsx` (lista de series `{clave, etiqueta, color, puntos, máxima}`; leyenda con conmutador; un arrastre común), `AjusteCabecera.tsx` (una serie por grupo con el medidor elegido o el primero), `styles.css` (paleta de series) | RF-17 a RF-24 |
| I. Medidas de la central | `demanda_medida.py`: `CentralTermica` (alimentador, generación, llegada, salida, nodo) y `demanda_con_central(registros…)`: registros comunes, signos por mínimo desbalance, zonas, descarte por 3·IQR, máxima de demanda | RF-28 a RF-34 |
| J. Declaración en la web y el perfil | `web/services.py` (medidores sin alimentador de la red; la máxima con central), `web/app.py` (campos nuevos en la petición de la máxima y en `AjusteIn`), `perfil_empresa.py` (sección `centrales` por alimentador), `AjusteCabecera.tsx` (campo «Central térmica» por alimentador: tres desplegables de medidor y el nodo) | RF-25, RF-26, RF-27 |
| K. Objetivo de dos zonas | `ajuste_cabecera.py`: `Objetivo` con `zonas` opcionales (aguas arriba, aguas abajo, generación P y Q); `cuadrar` con dos factores; `cuadrado` exige las dos | RF-33, RF-40, RF-41, RF-43, RF-45, RF-46 |
| L. Central en DIgSILENT | `tools/ajuste_cabecera_pf.py`: `central_en_sin_proyecto` (crea o reutiliza el `ElmGenstat` marcado como del conversor en el nodo, en «Sin proyecto»; P y Q del registro); zonas con `troncal.aguas_abajo`; medida de la salida y la llegada en los cubículos de la barra de la central; informe | RF-35 a RF-39, RF-42, RF-44 |
| M. Curvas de la central | `services.demanda_curva` sin cambios (una por medidor) + una serie calculada de demanda en el front; marcas de las dos máximas | RF-47, RF-48, RF-49 |

## Decisiones

- **Plegar en `puentes.py`, no en `dgs.py`.** Así el modelo ya sale con el equipo en la
  línea y lo ven igual el DGS, la red unida, el oráculo y los informes. Descartado: decidir
  al escribir el DGS, porque el modelo y el DGS dirían cosas distintas.
- **Plegar del lado de aguas arriba si los dos extremos valen (RF-5).** Es donde la base
  coloca el equipo (`FromNode`) y es determinista. Descartado: el lado de la línea más
  larga, porque depende de longitudes recalculadas con el GPS.
- **Quitar el fusible del trafomix (RF-7), no dejarlo abierto.** Decisión del operador
  (2026-10-17): una maniobra que no lleva a nada no se maniobra. Queda contada en el
  informe para que la completitud siga cuadrando.
- **Sonda antes que código para la SED (parte E).** Lo que hace PowerFactory con un
  `SecSubProd` conectado no está en el manual que tenemos, y una prueba sintética no lo
  dice. Descartado: probar a ciegas en el DGS de producción.
- **Las curvas de varios alimentadores, superpuestas** (decisión del operador). Una
  petición por medidor, en paralelo; sin ruta nueva. Descartado: una ruta que devuelva
  todas, porque la curva de un alimentador que falla no debe tumbar las demás (RF-23).
- **Central como `ElmGenstat` creado en «Sin proyecto»** (decisión del operador). P y Q
  fijas, sin máquina síncrona: lo que se calibra es la demanda. Igual que los bancos
  existentes: el «Caso base» sigue fiel al archivo. Descartado: exigir que exista en el
  proyecto, porque los archivos de IGEA no la traen.
- **Dos zonas** (decisión del operador). La salida (BH1) mide toda la carga de aguas
  abajo, y cabecera + llegada la de aguas arriba: con una sola cifra en cabecera, 9 MW de
  generación esconden dónde está la carga. Descartado: un solo factor a cabecera.
- **Máxima de demanda, no de cabecera** (decisión del operador). En NA205 la máxima de
  cabecera cae con la central parada y no prueba nada de la central.
- **Signos deducidos del balance (RF-29), no por perfil.** Cada medidor exporta con su
  convención; el balance BH4 = BH1 + BH2 la delata registro a registro. Descartado:
  pedir el signo al operador, que no lo sabe sin mirar los datos.

## Comprobación contra la constitución

- 1 Determinismo: plegar recorre los puentes por `section_id`; la creación de la central
  no toca el DGS. Prueba de `workers=1` frente a `workers>1` con NA203 + NA205.
- 2 Escala: el plegado es lineal en puentes; las curvas se piden una por alimentador; nada
  supone un número de alimentadores o de centrales.
- 4 Sin inventar: el generador lleva la P y Q medidas, no un tipo `DEFAULT`.
- 5 Una sola vía: plegado y quitado del trafomix dentro de `aplicar_reglas`.
- 7 Nada largo en HTTP: la máxima con central se calcula en el trabajo de la máxima.
- 9 Datos de la distribuidora: las pruebas con libros reales solo con `IGEA_DEMANDA_DIR`;
  las sintéticas inventan sus series.
- 13 Universal: ningún nombre de medidor o de central en el código; la central de NA205
  solo en el perfil de Electro Dunas.

## Estrategia de pruebas

- `tests/test_puentes.py`: redes sintéticas para cada caso de RF-1 a RF-11 (vecina única,
  dos vecinas, cubículo ocupado, fuente, trafomix muerto); completitud.
- Datos reales (las tres `IGEA_*` y la vía Access): NA203 + NA205 sin barras hechas solo
  de acopladores donde RF-6 aplica; contador del informe; DGS idéntico con
  `workers=1` y `workers>1`; las dos disposiciones del TXT.
- `tests/test_dgs_v2.py`: la SED con lo que decida la sonda (RF-12, RF-13).
- `tests/test_transferencia_pf.py` / `test_estudios_pf_guion.py` con `fake_pf`: un
  seccionador en cubículo cuenta como punto de maniobra (RF-15).
- `tests/test_curva_cabecera_front.py`: fuente del front (series, leyenda, arrastre
  común), como las pruebas de front existentes.
- `tests/test_demanda_medida.py`: series sintéticas con central (signos cambiados,
  desbalance, registros raros, central parada); con `IGEA_DEMANDA_DIR`, el registro de
  NA205 del 2026-08-20 16:45.
- `tests/test_ajuste_cabecera.py` y `test_ajuste_cabecera_guion.py` con `fake_pf`: dos
  factores, generador creado una vez, zona sin escaladas, sin central igual que antes.
- DIgSILENT real al final de cada bloque (memoria: validar en DIgSILENT, no solo la suite).
- Cada prueba cita `021:RF-n`.

## Riesgos

- **Proyectos ya importados con `ElmCoup`**: los guiones (obras, transferencia) siguen
  leyendo los dos modelos; se prueba con `fake_pf` en los dos.
- **Informes de estudio (017)** que nombran barras de puentes que ya no existen: se
  revisa el trecho desde–hasta con CA101.
- **Diagrama**: al fundir barras cambia la posición de los símbolos de maniobra; se mira en
  DIgSILENT con NA203 + NA205.
- **La sonda de la SED puede decir que no hay forma limpia**: entonces RF-12 vuelve a la
  spec con la alternativa medida, antes de tocar `dgs.py`.
- **Central y transferencia (011)**: con el generador en «Sin proyecto», los estudios de
  transferencia de NA205 cambian; se anota en el informe que la central estaba generando.
