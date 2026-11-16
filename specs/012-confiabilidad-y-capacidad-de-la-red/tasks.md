# Tareas — Spec 012

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Estado: aprobado (2026-10-11) · Fecha: 2026-10-11

Orden: T1 a T6 no dependen de nada pendiente de la 011. T7 y T8 necesitan la clase de
equipo de la 011 (T15a). T11 y T12 necesitan sus obras y su web (T13, T16, T17).

Preparación

- [x] T1. Añadir `ComOpri`, `ComHostcap` y `ComPvcurves` a la lista de
      `tools/check_pf_license.py` (`ComRel3` y `ComCapo` ya están). Confirmar en el
      manual y en la referencia de Python de PF 2024 lo que el plan deja abierto: nombre
      de las variables de resultado por carga (ACIF, ACIT, LPENS) y si `ElmFeeder` da los
      índices; si hay variable de aporte por elemento tras `ComRelpost`; los valores
      enteros de `ComHostcap.objective`, `ioptLoads` y `ComCapo.iopt_meth`; si
      `ioptUsrLod` restringe las cargas que crecen; y si `DnFr` asignado al elemento va
      por km. (RF-4, RF-30, RF-32, RF-45, RF-46, RF-9)
      Hecho cuando: el plan lista cada punto con su referencia, o dice cuál no existe y
      qué se hace en su lugar; si RF-32 no tiene variable por elemento, el cambio de la
      spec está propuesto con su diff.
- [x] T2. `fake_pf`: modelos `StoTyplne`, `StoTyptrf` y `StoTypbar`; `pStoch` en
      `ElmLne`, `ElmTr2`, `ElmTerm` y `ElmShnt`; atributos de confiabilidad de
      `StaSwitch`/`ElmCoup`; `ComRel3` con resultados por carga sintéticos; `ComRelpost`;
      `ComOpri` que graba en una variación; `ComHostcap.CalcMaxHostedPower`;
      `ComPvcurves` con su `ElmRes` y `FindCriticalBus`; `ComCapo` que instala
      `ElmShnt` y da `TotalLossCost`. (base de D, E y F)
      Hecho cuando: `pytest -q tests/test_fake_pf_variaciones.py` en verde con las pruebas
      nuevas, y la suite entera en verde.

Libro de la empresa y catálogo

- [x] T3. `src/convertersmartgrid/datos_empresa.py`: leer el libro, validar hojas, filas, columnas y
      unidades, clases que faltan, fila por tipo que sustituye a la de su clase,
      telemandados, anualidad de los bancos y plantilla descargable. (RF-6 a RF-18,
      RF-62 a RF-66)
      Hecho cuando: `pytest -q tests/test_datos_empresa.py` en verde.
      Hecho el 2026-10-29: `datos_empresa.py` (fila 1 columnas, fila 2 unidades; moneda la del
      libro, plantilla sin cifras); `tests/test_datos_empresa.py`, 23 en verde.
      Ampliación del 2026-11-14 (aclaraciones de RF-6, RF-8, RF-9, RF-12, RF-19, RF-20, RF-62 y RF-63): el libro
      puede ser el histórico de interrupciones; `historico_interrupciones.py` reconoce sus columnas,
      deriva λ y r con la exposición de la red del espacio, da la cota al 95 % de las clases sin fallas, dice en
      una frase lo que falta en un espacio sin red convertida y deja la procedencia en `Libro.historico`.
      Hecho cuando: `pytest -q tests/test_historico_interrupciones.py tests/test_datos_empresa.py` en
      verde, y con `CSG_INTERRUPCIONES` y la red TXT el histórico real da tasas mayores que cero.
- [x] T4. Catálogo: estudios `reconectadores`, `alojamiento` y `curvas_pv` en
      `studies.py`; `fiabilidad` y `condensadores` pasan a depender del libro cargado; los
      cinco, ofrecidos en `estudios_pf.estudios_ofrecidos` solo con libro (los que lo
      necesitan) y licencia. (RF-1, RF-4, RF-19)
      Hecho cuando: `pytest -q tests/test_estudios_pf.py tests/test_studies*.py` en verde.
      Hecho el 2026-10-29: `reconectadores`, `alojamiento` y `curvas_pv` en `studies.py`; el catálogo
      ofrece los de la 012 según el libro y los módulos rechazados por licencia. 40 en verde.
- [x] T5. `src/convertersmartgrid/estudios_red_pf.py`: índices por alimentador a partir de los de
      cada carga, CAIDI, ENS total y diferencias, aportes ordenados, capacidad mínima y
      máxima por alimentador, margen PV, informe de bancos, comprobación de estado y filas
      de los ficheros. (RF-25, RF-30 a RF-33, RF-39, RF-47 a RF-49, RF-52, RF-56, RF-57,
      RF-59 a RF-61, RF-67, RF-68)
      Hecho cuando: `pytest -q tests/test_estudios_red_pf.py` en verde.
      Hecho el 2026-10-29: `estudios_red_pf.py`; `tests/test_estudios_red_pf.py`, 27 en verde.

Capacidad (sin dependencias de la 011 pendientes)

- [x] T6. `tools/capacidad_pf.py` y sus claves en `tools/estudios_pf.py`: capacidad de
      alojamiento nodo a nodo y conjunta, curvas PV con y sin contingencias, y
      condensadores en una variación temporal; comprobación de estado al terminar; nodos
      sin carga conectada. (RF-2, RF-72,
      RF-41 a RF-46, RF-50 a RF-57, RF-60, RF-61)
      Hecho cuando: `pytest -q tests/test_capacidad_pf_guion.py` en verde y las pruebas de
      la 011 siguen en verde.
      Hecho el 2026-10-29: `tools/capacidad_pf.py` (tiene `main` con `--help`; lo llama
      `estudios_pf.py`); `tests/test_capacidad_pf_guion.py`, 13 en verde, y la 011 en verde.

Confiabilidad (después de la T15a de la 011)

- [x] T7. `tools/confiabilidad_pf.py --aplicar-datos`: variación «Datos de
      confiabilidad» activa solo en «Sin proyecto» y «Con proyecto», modelos `Sto*` por
      clase y por tipo, `pStoch` en los elementos, equipos de maniobra por clase,
      reemplazo con un libro nuevo, bloqueo sin clases, interruptor de cabecera, aviso de
      un cliente por carga. (RF-20 a RF-27, RF-69, RF-70)
      Hecho cuando: `pytest -q tests/test_confiabilidad_pf_guion.py -k datos` en verde y
      ningún tipo del proyecto falso cambió.
      Hecho el 2026-10-29: la clase de cada equipo sale de la entrada cargada (el DGS escribe
      interruptor, reconectador y fusible como `cbk`); sin ella solo los seccionadores, y RF-26
      bloquea. Las tasas de equipos de maniobra no tienen `pStoch` en PF 2024: se dice.
- [x] T8. Confiabilidad y reconectadores en `tools/confiabilidad_pf.py` y sus claves en
      `tools/estudios_pf.py`: `ComRel3` propio, lectura por carga, aportes, alimentador
      con todo a cero; `ComOpri` con candidatos filtrados, sin cables, objetivo y máximos
      del operador, en una variación temporal que se borra; alimentador sin tensión; hora
      de estudio restituida. (RF-2, RF-28 a RF-39, RF-71)
      Hecho cuando: `pytest -q tests/test_confiabilidad_pf_guion.py` en verde.
      Hecho el 2026-10-29: `tests/test_confiabilidad_pf_guion.py`, 24 en verde (con `-k datos`, T7).
      ComOpri: la hora del caso y la etapa que graba se devuelven en el propio guion.

Web e interfaz

- [x] T9. Servicios y API: subir y validar el libro, guardarlo con el proyecto, plantilla,
      trabajo «aplicar datos», opciones de los estudios nuevos en el plan de estudios.
      (RF-5, RF-6, RF-7, RF-20, RF-37)
      Hecho cuando: `pytest -q tests/test_estudios_red_web.py` en verde.
      Hecho el 2026-10-29: rutas `/pf/datos-empresa` (subir, estado, plantilla, aplicar) y
      `/pf/estudios?project=`; `tests/test_estudios_red_web.py` en verde.
- [x] T10. Interfaz (leer antes el skill `convertersmartgrid-frontend`): `DatosEmpresaPF.tsx` con el
      libro, la plantilla y los errores por hoja y fila; los estudios nuevos y sus
      opciones en «4.2 Estudios»; tablas de resultados. (RF-1, RF-7, RF-19, RF-37, RF-45,
      RF-53)
      Hecho cuando: `pytest -q tests/test_estudios_red_front.py` en verde,
      `npx tsc --noEmit -p .` y `npm run build` correctos.
      Hecho el 2026-10-29: `DatosEmpresaPF.tsx` y `EstudiosPF.tsx`; `tsc` y `npm run build` sin
      errores. Por petición del usuario (2026-10-29) la interfaz se prueba funcionando y no con
      pruebas de la fuente: en la web real, catálogo sin libro (alojamiento y PV ofrecidos, los
      otros con lo que falta), plantilla descargada (200, xlsx) y la plantilla sin rellenar
      rechazada con cada hoja, fila y columna.
- [x] T11. Aceptar una propuesta como obra (después de T13, T16 y T17 de la 011): el
      reconectador o el banco propuesto rellena el formulario de su obra. (RF-40, RF-58)
      Hecho cuando: `pytest -q tests/test_estudios_red_web.py tests/test_estudios_red_front.py`
      en verde con las pruebas de aceptar.
      Hecho el 2026-10-29: «Aceptar como obra» crea la obra de 4.1 (`POST /obras`) y refresca el
      espacio; la prueba web acepta cada propuesta por esa API.

Cierre

- [x] T12. Índice, estado y validación: ficheros nuevos en `CODIGO_FUENTE.md`, las
      herramientas en `docs/MANUAL_COMANDOS.md`, la spec en `CLAUDE.md`, cada RF citado
      por una prueba en verde, suite completa con las tres `CSG_*`. (Todos)
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde y
      `grep -rnoE "012:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-72.
      Hecho el 2026-10-29: `CODIGO_FUENTE.md`, `docs/MANUAL_COMANDOS.md`; los 72 RF citados.
      Ampliada el 2026-11-13 con las entradas cargadas desde la web (RF-73 a RF-86):
      `entradas_estudios.py`, `web/entradas_estudios_api.py`, `tools/estudios_entradas_pf.py`,
      `EntradasEstudios.tsx`; `pytest -q tests/test_entradas_estudios.py` en verde y el cortocircuito y
      la cuasi-dinámica ejecutados en una copia de CA101_CHN102 borrada al terminar.
- [x] T13. [DIgSILENT] Prueba real en DIgSILENT con dos alimentadores calibrados, una carga nueva y un
      libro de la empresa, a cargo del usuario: índices y ENS por alimentador, un
      reconectador y un banco propuestos y aceptados como obra, capacidad de un nodo y
      curva PV de un alimentador. (Todos)
      Hecho cuando: el usuario confirma los resultados y que el «Caso base» no cambió.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).

Exposición leída de DIgSILENT (2026-11-14, «convertido o no»)

- [ ] T14. `historico_interrupciones._cifras` y `con_exposicion` (las tasas que da una exposición que
      llega después, con lo contado por alimentador y clase en `historico['base']`),
      `datos_empresa.con_exposicion` y `tools/confiabilidad_pf.py`: `exposicion_del_proyecto` lee km de
      `ElmLne` aérea y de cable, `ElmTr2` y `ElmTerm` de cada `ElmFeeder` y `aplicar_datos` deriva las
      tasas antes de escribir los modelos. (RF-87)
      Hecho cuando: `pytest -q tests/test_historico_interrupciones.py tests/test_confiabilidad_pf_guion.py`
      en verde con `-k exposicion`, y la exposición leída da las mismas tasas que la red convertida.
- [ ] T15. Web: `datos_empresa_aplicar` guarda el libro derivado y la exposición con su origen;
      `resumen` la muestra; la frase de lo que falta antes de aplicar dice que se lee de DIgSILENT
      al aplicar el libro. (RF-88)
      Hecho cuando: `pytest -q tests/test_estudios_red_web.py` en verde.
- [ ] T16. Sin ninguna interrupción de un alimentador del proyecto o sin causa: ni tasas a cero ni
      escritura en el proyecto, y la frase `SIN_TASAS`. (RF-89)
      Hecho cuando: `pytest -q tests/test_historico_interrupciones.py tests/test_confiabilidad_pf_guion.py`
      en verde con `-k "sin_alimentadores or sin_causa"`.
- [ ] T18. Columna del alimentador por su contenido: `historico_interrupciones.elegir_por_contenido`
      (columna llena y de cardinalidad baja, `MAYORIA_ALIMENTADOR`, con la mayoría de los alimentadores,
      `COBERTURA_ALIMENTADOR`, desempate por forma, respaldo por la forma de los valores distintos,
      `FORMA_MINIMA`, `clave_alimentador` = `feeder_short_name` y un conjunto), `_candidatas` en `historico['base']` cuando no hay red, la elección en
      `con_exposicion` y `reconocer_columnas`, los avisos `AVISO_COLUMNA` y el error `frase_sin_columna`
      (y el de empate) en `que_falta` y en el guion con rc=2. (RF-90, RF-91, RF-92)
      Hecho cuando: `pytest -q tests/test_historico_interrupciones.py tests/test_confiabilidad_pf_guion.py
      -k "columna_del_alimentador or columna_casi or sin_titulo_elige or libro_de_toda_la_empresa"` en verde,
      con el empate, el desempate por forma, la columna casi vacía, el umbral de cobertura y el libro de
      40 alimentadores con un proyecto de 3 (aclaraciones de RF-90 y RF-91), y el respaldo por forma: un
      proyecto de 10 con 3 con interrupciones, dos columnas con forma y el 70 % frente al 80 % (aclaraciones
      de RF-91 y RF-92; `-k` con `elige_por_forma or forma_de_alimentador_es_un_error or 70_por_ciento`), y los cuatro ficheros de la confiabilidad y `tests/test_trazabilidad_specs.py`
      en verde.
- [ ] T17. [DIgSILENT] Prueba nativa en la sesión 2 de DIgSILENT, a cargo del usuario: un proyecto sin
      conversión, el histórico real (`CSG_INTERRUPCIONES`) subido a un espacio sin red, «Aplicar el
      libro» desde la web: la exposición leída por alimentador coincide con la longitud y los elementos
      que muestra DIgSILENT, las tasas de línea y transformador son mayores que cero, los modelos
      `CSG012_*` llevan esas tasas, la confiabilidad corre y el «Caso base» no cambia; el aviso dice qué columna
      es la del alimentador y por qué. (RF-87 a RF-92)
      Hecho cuando: el usuario confirma los resultados con el informe del guion.
