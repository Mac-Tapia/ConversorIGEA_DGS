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

- [ ] T3. `src/igea_dgs/datos_empresa.py`: leer el libro, validar hojas, filas, columnas y
      unidades, clases que faltan, fila por tipo que sustituye a la de su clase,
      telemandados, anualidad de los bancos y plantilla descargable. (RF-6 a RF-18,
      RF-62 a RF-66)
      Hecho cuando: `pytest -q tests/test_datos_empresa.py` en verde.
- [ ] T4. Catálogo: estudios `reconectadores`, `alojamiento` y `curvas_pv` en
      `studies.py`; `fiabilidad` y `condensadores` pasan a depender del libro cargado; los
      cinco, ofrecidos en `estudios_pf.estudios_ofrecidos` solo con libro (los que lo
      necesitan) y licencia. (RF-1, RF-4, RF-19)
      Hecho cuando: `pytest -q tests/test_estudios_pf.py tests/test_studies*.py` en verde.
- [ ] T5. `src/igea_dgs/estudios_red_pf.py`: índices por alimentador a partir de los de
      cada carga, CAIDI, ENS total y diferencias, aportes ordenados, capacidad mínima y
      máxima por alimentador, margen PV, informe de bancos, comprobación de estado y filas
      de los ficheros. (RF-25, RF-30 a RF-33, RF-39, RF-47 a RF-49, RF-52, RF-56, RF-57,
      RF-59 a RF-61, RF-67, RF-68)
      Hecho cuando: `pytest -q tests/test_estudios_red_pf.py` en verde.

Capacidad (sin dependencias de la 011 pendientes)

- [ ] T6. `tools/capacidad_pf.py` y sus claves en `tools/estudios_pf.py`: capacidad de
      alojamiento nodo a nodo y conjunta, curvas PV con y sin contingencias, y
      condensadores en una variación temporal; comprobación de estado al terminar; nodos
      sin carga conectada. (RF-2, RF-72,
      RF-41 a RF-46, RF-50 a RF-57, RF-60, RF-61)
      Hecho cuando: `pytest -q tests/test_capacidad_pf_guion.py` en verde y las pruebas de
      la 011 siguen en verde.

Confiabilidad (después de la T15a de la 011)

- [ ] T7. `tools/confiabilidad_pf.py --aplicar-datos`: variación «Datos de
      confiabilidad» activa solo en «Sin proyecto» y «Con proyecto», modelos `Sto*` por
      clase y por tipo, `pStoch` en los elementos, equipos de maniobra por clase,
      reemplazo con un libro nuevo, bloqueo sin clases, interruptor de cabecera, aviso de
      un cliente por carga. (RF-20 a RF-27, RF-69, RF-70)
      Hecho cuando: `pytest -q tests/test_confiabilidad_pf_guion.py -k datos` en verde y
      ningún tipo del proyecto falso cambió.
- [ ] T8. Confiabilidad y reconectadores en `tools/confiabilidad_pf.py` y sus claves en
      `tools/estudios_pf.py`: `ComRel3` propio, lectura por carga, aportes, alimentador
      con todo a cero; `ComOpri` con candidatos filtrados, sin cables, objetivo y máximos
      del operador, en una variación temporal que se borra; alimentador sin tensión; hora
      de estudio restituida. (RF-2, RF-28 a RF-39, RF-71)
      Hecho cuando: `pytest -q tests/test_confiabilidad_pf_guion.py` en verde.

Web e interfaz

- [ ] T9. Servicios y API: subir y validar el libro, guardarlo con el proyecto, plantilla,
      trabajo «aplicar datos», opciones de los estudios nuevos en el plan de estudios.
      (RF-5, RF-6, RF-7, RF-20, RF-37)
      Hecho cuando: `pytest -q tests/test_estudios_red_web.py` en verde.
- [ ] T10. Interfaz (leer antes el skill `igea-dgs-frontend`): `DatosEmpresaPF.tsx` con el
      libro, la plantilla y los errores por hoja y fila; los estudios nuevos y sus
      opciones en «4.2 Estudios»; tablas de resultados. (RF-1, RF-7, RF-19, RF-37, RF-45,
      RF-53)
      Hecho cuando: `pytest -q tests/test_estudios_red_front.py` en verde,
      `npx tsc --noEmit -p .` y `npm run build` correctos.
- [ ] T11. Aceptar una propuesta como obra (después de T13, T16 y T17 de la 011): el
      reconectador o el banco propuesto rellena el formulario de su obra. (RF-40, RF-58)
      Hecho cuando: `pytest -q tests/test_estudios_red_web.py tests/test_estudios_red_front.py`
      en verde con las pruebas de aceptar.

Cierre

- [ ] T12. Índice, estado y validación: ficheros nuevos en `CODIGO_FUENTE.md`, las
      herramientas en `docs/MANUAL_COMANDOS.md`, la spec en `CLAUDE.md`, cada RF citado
      por una prueba en verde, suite completa con las tres `IGEA_*`. (Todos)
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde y
      `grep -rnoE "012:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-72.
- [ ] T13. Prueba real en DIgSILENT con dos alimentadores calibrados, una carga nueva y un
      libro de la empresa, a cargo del usuario: índices y ENS por alimentador, un
      reconectador y un banco propuestos y aceptados como obra, capacidad de un nodo y
      curva PV de un alimentador. (Todos)
      Hecho cuando: el usuario confirma los resultados y que el «Caso base» no cambió.
