# Tareas — Spec 025

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Árbol de libros por año (`libros_por_anio.py`) y periodo `AAAA` en la máxima.
      (RF-1, RF-2, RF-3, RF-7, RF-26, RF-27)
      Hecho cuando: `pytest -q tests/test_libros_por_anio.py` en verde.
      Hecho el 2026-10-23: suite con las siete variables, 2676 pasan, ninguna omitida;
      `libros_de_cabecera` recorre las subcarpetas de año.
- [x] T2. Mes por nombre universal y lista de patrones del perfil; catálogo de clientes sobre
      el árbol con ruta relativa y año. (RF-4, RF-5, RF-6, RF-6b, RF-11)
      Hecho cuando: `pytest -q tests/test_libros_por_anio.py tests/test_demanda_medida.py` en verde.
      Hecho el 2026-10-23: los 21 libros reales (12 de 2025, 9 de 2026) con su mes por la
      regla general, sin patrón; el catálogo publica el año. RF-11 se prueba en T5 (cruce).
- [x] T3. Medidor → hoja por código del alimentador, ambigüedades y libro más reciente del
      año. (RF-12, RF-12b, RF-13, RF-30)
      Hecho cuando: `pytest -q tests/test_libros_por_anio.py` en verde.
      Hecho el 2026-10-23: con los libros reales, los 7 alimentadores de 2025 dan su máxima
      (SI213, PN107, TM105 y PA217 por el código del alimentador, con aviso).
- [x] T4. Índice de cabecera como trabajo (reutiliza por tamaño y fecha, motivo por libro,
      foto recursiva, todo o nada al cancelar); clientes con foto recursiva.
      (RF-28, RF-29, RF-31, RF-32, RF-33)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py` en verde.
      Hecho el 2026-10-23: `POST /demanda/cabecera/indexar` (carril del motor) y
      `tests/test_libros_por_anio_web.py`.
- [x] T5. Búsqueda de la máxima y cruce por periodo con los libros de su año.
      (RF-8, RF-9, RF-10)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py` en verde.
      Hecho el 2026-10-23: también RF-11 (mes sin libro → por kVA, sin bloquear) y RF-29 al
      buscar (un libro roto se salta y se avisa).
- [x] T6. Casos por año en `casos_pf.py` y `ajuste_cabecera_pf.py` (doble `fake_pf`).
      (RF-14, RF-15, RF-16, RF-17, RF-18, RF-21)
      Hecho cuando: `pytest -q tests/test_casos_pf.py tests/test_ajuste_cabecera_pf.py` en verde.
      Hecho el 2026-10-23: `tests/test_casos_por_anio.py` (9) y los guiones de ajuste,
      cargas y obras con `fake_pf` (320) en verde. El año va como parámetro y nunca como
      estado del módulo: el servidor de DIgSILENT conserva `casos_pf` entre órdenes.
- [x] T7. Plan y registro de la calibración por año; migración de `calibraciones`.
      (RF-19, RF-20, RF-24)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py tests/test_ajuste_cabecera.py` en verde.
      Hecho el 2026-10-23: `anio_medicion`, `anio_casos` y `caso` en el plan; registro por
      `<proyecto>@<año>`; `ws.anios_casos` guarda el año de los casos sin año (un proyecto
      calibrado antes se toma del año más reciente de la cabecera, con aviso). No hace
      falta migrar: la clave antigua sigue siendo la de los casos sin año. RF-19 sale de
      RF-15 (copia del «Caso base»), probado en T6.
- [x] T8. Tipos de libro por contenido y `sistema_web.py` sin nombres de carpeta.
      (RF-25, RF-25b, RF-25c)
      Hecho cuando: `pytest -q tests/test_sistema_web.py` en verde y `--help` sin DIgSILENT.
      Hecho el 2026-10-23: `clasificar_carpeta_demanda` mira solo la cabecera de las hojas
      (`nrows`); con `referencia/` reconoce los cuatro en 1,7 s y no se confunde con los
      libros sueltos (CAPEX, pérdidas). `--medidores/--cabecera/--clientes/--suministros`
      mandan sobre lo reconocido.
- [x] T9. Web: selector de año, meses del año, panel de libros por año, dónde dejar un año
      nuevo, año y caso en el resultado. (RF-22, RF-23, RF-24, RF-34, RF-35)
      Hecho cuando: `npm run build` sin errores y prueba de la API del panel en verde.
      Hecho el 2026-10-23: `tsc` y `npm run build` sin errores; `tests/test_libros_por_anio_front.py`.
      La cabecera en carpeta se indexa sola al asignarla, como los clientes.
- [x] T10. Datos reales: 7 alimentadores de 2025 con hoja, 21 libros de clientes con mes,
      suite con las siete variables sin omitidas; `CODIGO_FUENTE.md` y `CLAUDE.md` al día.
      (Todos)
      Hecho cuando: suite completa `-rs` en verde, ninguna omitida.
      Hecho el 2026-10-23: 2750 pasan, ninguna omitida (10 min 19 s).
- [x] T11. DIgSILENT: Chincha, Pisco e Ica con `tools/sistema_web.py --periodo 2025`;
      «Sin proyecto 2025» válido y «Sin proyecto» (2026) con el mismo flujo antes y después.
      (RF-14 a RF-19, RF-24, RF-25)
      Hecho cuando: los tres sistemas calibrados y la comparación anotada aquí.
      Hecho el 2026-10-23, solo los alimentadores que pidió el usuario, cada uno en su
      proyecto y con `--sin-bancos` (los bancos que faltan se crean en la red común):
      Pisco SI213 −0,00 % y PA217 −0,01 %; Chincha PN107 −0,04 % y TM105 −0,00 %; el
      unido IN111 + TA225 (`20261015-170359_IGEA_IN111_TA225`) IN111 −0,89 % y TA225
      −0,08 %; los seis VALIDO, con AVISO_KVAR (sin bancos, la red da menos kVAR que el
      medidor). Foto de cada carga (P, Q, scale0) y del flujo antes y después: «Caso base»,
      «Sin proyecto» y «Con proyecto» de 2026, IGUAL en los cuatro proyectos. IN111 en
      2025 no tiene hojas de sus canales: los dos se leen como IN111 y quedan en una fila.
      El sistema Ica se empezó y se canceló (el usuario lo quería en el unido): dejó un
      «Sin proyecto 2025» en `SISTEMA_ICA`, sin tocar 2026.
- [x] T13. Cargas nuevas y demandas en bloque en los casos del año de su base: el plan
      lleva `anio_casos` sacado del caso de la calibración base; `tools/cargas_pf.py` usa
      los casos de ese año. (RF-36, RF-37, RF-38)
      Hecho cuando: `pytest -q tests/test_casos_por_anio.py tests/test_cargas_pf_guion.py` en
      verde y `NuevosclientesMayoresv1.xlsx` insertado en DIgSILENT sobre los proyectos
      recalibrados con 2025.
      Hecho el 2026-10-23 desde la web, con `anio_casos` 2025 en el plan: Pisco (PI_7 en
      SI213; PI_1, PI_8 a PI_11 en PA217), Chincha (CH_9 en PN107; CH_3, CH_5 y CH_8 en
      TM105) y el unido IN111 + TA225 (sus 9 de TA225), en «Con proyecto 2025»; las demandas
      en «Sin proyecto 2025». Cerrada el 2026-10-24 con las pruebas en verde.
- [x] T14. Obras por año y obras de las cargas reutilizadas; campos de la web habilitados
      para reemplazar. (RF-39 a RF-43)
      Hecho cuando: `pytest -q tests/test_casos_por_anio.py tests/test_libros_por_anio_front.py`
      en verde y el unido IN111 + TA225 converge en «Con proyecto 2025».
      Avance del 2026-10-23: código y pruebas hechos; en DIgSILENT, el unido converge en
      «Con proyecto 2025» con sus 9 cargas de TA225 y las 4 obras de 2026 activadas (RF-42);
      «Con proyecto» (2026), igual. Pisco (PI_1 con PI_8, PA217) y Chincha (CH_3 con CH_5,
      TM105) no convergen juntas; cada carga sola, sí (RF-43, sonda). Falta reiniciar la web
      (obras con año en la API) y la suite completa.
      Cerrada el 2026-10-24: suite con las siete variables, 2770 pasan, ninguna omitida (11 min
      15 s; la cuenta de flujos de 007 suma el de RF-43). Las obras de la escalera del 23 ya
      llegaron con `anio_casos` 2025 por la API.
- [ ] T15. Obras en escalera sobre «Con proyecto <año>» que no converge (RF-44), con la 017
      (T8, T9): bancos, regulador, sección, terna; la primera que converge, en su variación.
      Hecho cuando: Pisco y Chincha convergen en «Con proyecto 2025» y el informe dice la obra.
      Avance del 2026-10-23: `obras_pf.escalera_de_obras` y `POST /pf/obras/escalera` con
      bancos, sección de toda la troncal y terna (sin regulador). En DIgSILENT, con año 2025:
      PA217 converge con la terna (bancos y sección no bastan); TM105, con la sección. Los
      bancos se intentaron en NODE_T_PI_1 y NODE_T_PI_11, nodos que crea la variación de la
      carga; ya se excluyen por el criterio de conexión. Del 2026-10-24: el informe de cargas
      dice qué cargas no convergen juntas y ofrece «Proponer obras en escalera» (antes solo
      por la API). Falta decidir el escalón del regulador que nombra RF-44.
      Comprobado en DIgSILENT el 2026-10-24 (sonda de solo lectura): «Sin proyecto 2025»
      converge y cuadra con la máxima de 2025 en PA217 −0,005 %, SI213 −0,00 %, PN107
      −0,04 %, TM105 −0,00 %, IN111 −0,89 % y TA225 −0,08 % (unido); «Con proyecto 2025»
      converge en los tres con sus cargas y su obra. El regulador no se pudo probar: no hay
      ningún `TypVoltreg` en la biblioteca global ni en los proyectos; hace falta su ficha.
      Del 2026-10-24: sustituida por T17 a T22 (escalera optimizada, RF-44 cambiado).
- [x] T17. Catálogo Eaton VR-32 de 50 Hz y creación de sus `TypVoltreg` en la biblioteca
      global. (RF-59)
      Hecho el 2026-10-24: `catalogo_reguladores.py` y `obras_pf.py --tipos-regulador`; en
      DIgSILENT, 16 tipos (9 de 10 kV, 50 a 668 A; 7 de 22,9 kV, 50 a 500 A) en el proyecto
      `IGEA_Biblioteca_tipos` de la carpeta del usuario (elegido por el usuario: la global no
      deja escribir), creado con `Application.CreateProject`. La obra «regulador» pone ya
      `Un` de unidad monofásica (de fase en estrella) e `In` se muestra en amperios.
      Hecho cuando: prueba con `fake_pf` en verde y los tipos en DIgSILENT.
      Sondas del 2026-10-24: `\Lib` y sus subcarpetas no dejan crear objetos a este usuario
      (`CreateObject` devuelve nada); su carpeta de usuario, sí. Un `TypVoltreg` nuevo trae
      `type`=1, `config`=2, `Un`=7,62 kV, `In`=437 (amperios, no kA como dice
      `RESUMEN_TIPO`), `pcReg`=10 %, `ntapmax`=16.
- [x] T23. «Cargas nuevas <año>»: copia de «Sin proyecto <año>» y de su escenario con las
      variaciones de las cargas nuevas, una a una, solo las que lo dejan converger, sin obras
      ni cambios; las que no, inactivas y con su motivo en la web. (RF-61 a RF-66)
      Hecho cuando: `pytest -q tests/test_casos_por_anio.py` en verde y el caso en DIgSILENT
      en Pisco, Chincha y el unido IN111 + TA225, con 2025, insertando desde la web.
      Hecho el 2026-10-24, insertando `NuevosclientesMayoresv1.xlsx` por la web con la base de
      2025 (las cargas ya existían y se reutilizan). «Cargas nuevas 2025» convergido en los
      tres: Pisco con PI_1, PI_7 y PI_8 (fuera PI_9, PI_10 y PI_11: PA217 ya a 0,647 p.u. y
      72 tramos sobre el 100 %, Newton estancado); Chincha sin CH_5 (TM105 a 0,832 p.u., un
      tramo al 301 %); el unido sin IC_11, IC_12, IC_15 e IC_17 (su línea queda entre 22,9 y
      10 kV sin la migración de IN111, que es obra de «Con proyecto»). De paso, la base de
      las cargas se busca en todas las ejecuciones también sin token: tras reiniciar la web,
      la de Pisco no aparecía. Comprobado en DIgSILENT nativo el mismo día (sonda de solo
      lectura, 25 comprobaciones, 0 fallos): los 16 reguladores con los datos del catálogo,
      los casos de 2025 con su marca, «Cargas nuevas 2025» con su escenario, sin obras y
      convergido, y «Sin proyecto 2025» con la misma calibración.
- [x] T18. Variantes, criterio por sorteo, sorteos con semilla, costo anual y elección,
      puros. (RF-44, RF-49, RF-50, RF-51, RF-53, RF-55 a RF-58, RF-60)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
      Hecho el 2026-10-24: `escalera_optima.py` (18 pruebas); parámetros en el bloque
      `escalera` del perfil (95 %, 200 sorteos, tolerancias 0,005 p.u. y 1 %); sin precio de
      pérdidas ni COyM en el perfil, el costo anual va sin ellos y lo dice.
- [ ] T19. Evaluación en DIgSILENT (`--evaluar`): máxima, sorteos, escenario temporal y
      limpieza. (RF-44b, RF-50, RF-51, RF-52, RF-52b)
      Hecho cuando: prueba con `fake_pf` en verde.
- [ ] T20. Servicio y web: elegir, aplicar la elegida y la tabla de variantes. (RF-54, RF-55)
      Hecho cuando: pruebas de la API y del front en verde y `npm run build`.
- [ ] T21. DIgSILENT: PA217 (Pisco) y TM105 (Chincha) en «Con proyecto 2025» desde la web,
      con la obra elegida en DIgSILENT nativo y «Sin proyecto 2025» calibrado igual que antes.
      Hecho cuando: los dos con su variante elegida o con la más cercana dicha (RF-56).
- [ ] T22. Validación de RF-44 a RF-60 y suite completa sin omitidas.
- [x] T16. Cargas nuevas incompletas e independientes. (RF-45, RF-46, RF-47, RF-48)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py tests/test_cargas_pf_web.py
      tests/test_cargas_pf_guion_016.py tests/test_cargas_tres_pasos_front.py` en verde.
      Hecho el 2026-10-23 (código) y el 2026-10-24 (pruebas de RF-46 en la web y en el plan,
      y de RF-48: cada carga se mide con las variaciones de las demás inactivas).
- [x] T12. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "025:RF-[0-9]+[b-c]?" tests | sort -u` lista todos los RF.
      Hecho el 2026-10-24: los 48 RF (y RF-6b, RF-12b, RF-25b, RF-25c, RF-42b) citados con la
      forma `025:RF-n` que cuenta `test_inventario`; RF-46 y RF-48 con prueba propia nueva.
