# Tareas — Spec 011

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Estado: aprobado (2026-10-11) · Fecha: 2026-10-11 (obras de mejora añadidas el
mismo día)

Preparación

- [x] T1. Añadir `ComTransfer` y `ComFeedertool` a la lista de `tools/check_pf_license.py`.
      Confirmar en el manual de la API de PF 2024 (`Help/PythonReference_en.pdf`) los
      métodos que el plan da por supuestos, y que `ComFeedertool` se ejecuta desde la API
      con el objeto de enlace en modo de crear tipos: `AddCopy` de casos, escenarios y tipos, `GetGlobalLibrary`, leer la
      biblioteca de otro proyecto sin activarlo, activar un caso, mover un cubículo a
      otra barra, parámetros de entrada de `ComDpl`/`ComPython`. Los atributos ya están
      comprobados en `datascheme.db` (tabla del plan). (RF-1 a RF-11, RF-28, RF-75,
      RF-86, RF-89 a RF-92)
      Hecho cuando: el plan lista cada método con su referencia del manual, o dice cuál no
      existe y qué se hace en su lugar.
- [x] T2. `fake_pf`: casos de estudio con sus variaciones y escenario activos, `AddCopy`,
      `desc`, bibliotecas de tipos del proyecto, global y de otro proyecto, `ElmShnt`,
      `ElmVoltreg`, `StaSwitch`, `ElmRelay`, cubículos que se mueven. (base de todo)
      Hecho cuando: `pytest -q tests/test_fake_pf_variaciones.py` en verde con las pruebas
      nuevas, y la suite entera en verde.

Estudios sobre los tres casos

- [x] T3. `src/igea_dgs/estudios_pf.py`. (RF-23, RF-24, RF-32 a RF-35, RF-37)
      Hecho cuando: `pytest -q tests/test_estudios_pf.py` en verde.
- [x] T4. `tools/casos_pf.py`: los tres casos, escenarios por caso, variaciones por caso,
      ajustes anteriores, caso ajeno, caso activo restaurado. (RF-1 a RF-16, RF-46 a
      RF-50)
      Hecho cuando: `pytest -q tests/test_casos_pf.py` en verde.
- [x] T5. El ajuste y las cargas trabajan en su caso, y el ajuste marca `i_scale`.
      (RF-18, RF-19, RF-51 a RF-55)
      Hecho cuando: `pytest -q tests/test_casos_pf.py tests/test_ajuste_cabecera_guion.py
      tests/test_cargas_pf_guion.py tests/test_cargas_pf_guion_007.py` en verde.
- [x] T6. `tools/estudios_pf.py`, un estudio en un caso. (RF-17, RF-20 a RF-22, RF-26,
      RF-31, RF-33, RF-38, RF-49, RF-68)
      Hecho cuando: `pytest -q tests/test_estudios_pf_guion.py` en verde.
- [x] T7. Contingencias N-1 sobre la troncal. (RF-36, RF-43 a RF-45)
      Hecho cuando: `pytest -q tests/test_estudios_pf_guion.py -k n1` en verde.
- [x] T8. Guiones del operador. (RF-27 a RF-30)
      Hecho cuando: `pytest -q tests/test_estudios_pf_guion.py -k guion` en verde.

Obras de mejora

- [x] T9. Mover el sufijo de tensión de `dgs._type_name` a `naming.py`, sin cambiar el
      DGS. (RF-61)
      Hecho cuando: suite completa en verde con las tres `IGEA_*` y `TestParallelWorkers`
      en verde.
- [x] T10. `src/igea_dgs/obras_pf.py`: modelo y validación de cada obra, nombres de
      variación y de copias, igualdad de tipos, plan de la simulación. (RF-56, RF-59,
      RF-61 a RF-63, RF-69, RF-85)
      Hecho cuando: `pytest -q tests/test_obras_pf.py` en verde.
- [x] T11. `tools/obras_pf.py --bibliotecas`: tipos de los tres orígenes con sus datos,
      barras y tramos de un alimentador, copia de un tipo al proyecto. (RF-88 a RF-94)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py -k biblioteca` en verde.
- [x] T12. Reglas comunes al aplicar: variación por obra, activación por caso, nunca en
      el «Caso base», copia de tipos, flujo por caso, obra que no converge, comprobación
      de «Sin proyecto». (RF-57, RF-58, RF-60, RF-64 a RF-67)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py -k comunes` en verde.
- [x] T13. Banco de condensadores, reconectador y regulador. (RF-71 a RF-76)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py -k "condensador or
      reconectador or regulador"` en verde.
- [x] T14. Sección de cable y terna en la troncal. (RF-77 a RF-80, RF-87)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py -k "seccion or terna"` en
      verde.
- [x] T15. Migración del alimentador a otra tensión: fuente y barra de la cabecera a la
      tensión nueva sin SET, tipos de SED creados en la biblioteca del proyecto con la
      misma baja y potencia, un tipo compartido con otro alimentador que no cambia, y una
      cabecera compartida que se rechaza. (RF-81 a RF-86, RF-96, RF-97, RF-99 a RF-103)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py -k migracion` en verde.

Transferencia de carga

- [x] T15a. El DGS escribe `iUse` del `StaSwitch` (PF 2024 no tiene `aUsage` en
      `StaSwitch`; ver «Métodos de la API comprobados» en el plan) según la clase del
      export (seccionador o seccionalizador), con el valor de «Disconnector» que lea el
      usuario en DIgSILENT. (RF-128)
      Hecho cuando: suite completa en verde con las tres `IGEA_*`, `TestParallelWorkers`
      en verde y una prueba que cita `011:RF-128` con las dos disposiciones de export.
- [x] T15b. `src/igea_dgs/transferencia_pf.py`: pasos, carga transferida, viabilidad,
      máximo por seccionador y por nodo, elemento limitante, filas del fichero. (RF-110 a
      RF-117, RF-121)
      Hecho cuando: `pytest -q tests/test_transferencia_pf.py` en verde.
- [x] T15c. `tools/transferencia_pf.py`: enlaces entre los dos alimentadores, camino por
      `ComBbone`, maniobras paso a paso en los dos sentidos, restitución, sin grabar en
      variación ni escenario. (RF-105 a RF-109, RF-118 a RF-120,
      RF-129)
      Hecho cuando: `pytest -q tests/test_transferencia_pf_guion.py` en verde.
- [x] T15d. Capacidad y margen del enlace: `ComTransfer` por elementos con frontera
      temporal, y la bisección con `ComLdf` cuando no hay licencia o no es viable; las dos
      dan la misma cifra en `fake_pf`. (RF-122 a RF-127)
      Hecho cuando: `pytest -q tests/test_transferencia_pf_guion.py -k capacidad` en verde.

Web

- [x] T16. Servicios y API: obras guardadas en el espacio, bibliotecas, aplicar y simular
      obras, plan y trabajo de estudios, ficheros. (RF-12 a RF-16, RF-25, RF-39 a RF-41,
      RF-95, y el trabajo de las transferencias)
      Hecho cuando: `pytest -q tests/test_estudios_pf_web.py tests/test_obras_pf_web.py`
      en verde.
- [x] T17. Paso «4 · Obras y estudios» (leer antes el skill `igea-dgs-frontend`). (RF-24,
      RF-35, RF-42, RF-70, RF-88 a RF-95, RF-98, RF-104)
      Hecho cuando: `pytest -q tests/test_obras_estudios_front.py` en verde y
      `npx tsc --noEmit -p .` y `npm run build` en `frontend/` correctos.
- [x] T17b. Guiones del operador en la web: listar los DPL y Python del proyecto, y
      ejecutar uno en «Sin proyecto» y en «Con proyecto» con sus parámetros, cada caso en
      su proceso con su límite, siguiendo con el otro caso si uno devuelve error; código
      y ventana de salida por caso; sección en el paso 4.2. Añadida en la validación de
      T18 (2026-10-12): T8 los dejó en el guion y ninguna tarea los llevó a la web.
      (RF-27 a RF-30)
      Hecho cuando: `pytest -q tests/test_estudios_pf_web.py -k guion
      tests/test_obras_estudios_front.py` en verde y `npm run build` correcto.

Cierre

- [x] T18. Índice, estado y validación: ficheros nuevos en `CODIGO_FUENTE.md`, la spec en
      `CLAUDE.md`, cada RF citado por una prueba en verde, suite completa con las tres
      `IGEA_*`. (Todos)
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde y
      `grep -rnoE "011:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-129.
- [ ] T19. [DIgSILENT] Prueba real en DIgSILENT con dos alimentadores calibrados, una carga nueva y
      una obra de cada clase, a cargo del usuario; la migración de tensión, con un
      alimentador que comparte tipos con otro. (Todos)
      Hecho cuando: el usuario confirma los tres casos, las obras, que «Sin proyecto» no
      cambió y los resultados de los estudios.
- [x] T20. Retro (033, 2026-10-29): RF-73b, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-73b)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_obras_pf_guion.py`).
