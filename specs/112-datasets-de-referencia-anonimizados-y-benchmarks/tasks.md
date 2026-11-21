# Tareas — Spec 112

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar. De `pronostico_demanda.py` solo
se lee su salida, con una excepción acotada, la de la T5 (aclaración de RF-11): el campo opcional `Exogenas.meses` y
`_mes_de`, que sin el campo dejan el 089 igual que antes. Ningún dato de la distribuidora entra en `tests/`.

- [x] T1. Patrones de privacidad en `privacidad.py` del núcleo; `web/soporte.py` los importa sin cambiar su
      comportamiento. (RF-2, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_instalacion_programa.py tests/test_benchmarks_seudonimos.py`
      en verde (las pruebas de 086:RF-42 sin tocar).
      Evidencia (2026-11-15, R1: 112T6-v2 rebasada a e182c823): humo sin pytest `D:/csg/PM_IMPL/112/R1/humo_verde.log`
      (68 passed, la red real con las tres `CSG_*` incluida) y rojo `rojo_humo.log` (42 F por aserción, rojo=VALIDO);
      el verde con pytest de `lista.txt` de R1 lo corre el carril.
- [x] T2. Seudónimos: permutación sorteada por tipo de identificador, coherente entre RED, CARGA y BD_Equipo;
      coordenadas a un origen neutro con giro sorteado; el mapa nunca se escribe; misma semilla, mismos bytes. (RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_seudonimos.py` en verde.
      Evidencia (2026-11-15, R1: 112T6-v2 rebasada a e182c823): humo sin pytest `D:/csg/PM_IMPL/112/R1/humo_verde.log`
      (68 passed, la red real con las tres `CSG_*` incluida) y rojo `rojo_humo.log` (42 F por aserción, rojo=VALIDO);
      el verde con pytest de `lista.txt` de R1 lo corre el carril.
- [x] T3. Redes: lista cerrada de secciones y columnas, escritura del trío TXT en las dos disposiciones, BD_Equipo con
      los parámetros resueltos, perfil neutro, columnas de texto libre fuera; generación sin red. (RF-1, RF-3, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_redes.py` en verde, con `ExportSpec`
      sorteado, `layout='reducido'` y `'completo'`, dos perfiles y un solo alimentador.
      Evidencia (2026-11-15, R1: 112T6-v2 rebasada a e182c823): humo sin pytest `D:/csg/PM_IMPL/112/R1/humo_verde.log`
      (68 passed, la red real con las tres `CSG_*` incluida) y rojo `rojo_humo.log` (42 F por aserción, rojo=VALIDO);
      el verde con pytest de `lista.txt` de R1 lo corre el carril.
- [x] T4. Reproducción del estudio con `reglas` y `oraculo.validar`/`validar_unida`: tensiones, cargas, recuento y
      veredicto dentro de la tolerancia declarada (por defecto 0,005 p.u. y 1 %); si no, no se emite y dice qué
      magnitud y qué elemento. (RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_redes.py -k reproduce` en verde en al
      menos dos redes sintéticas distintas, y con las tres variables `CSG_*` en la red real (salida en `tmp_path`).
      Evidencia (2026-11-15, R1: 112T6-v2 rebasada a e182c823): humo sin pytest `D:/csg/PM_IMPL/112/R1/humo_verde.log`
      (68 passed, la red real con las tres `CSG_*` incluida) y rojo `rojo_humo.log` (42 F por aserción, rojo=VALIDO);
      el verde con pytest de `lista.txt` de R1 lo corre el carril.
- [x] T5. Series del 089: identificador nuevo, escala sorteada, semanas completas desplazadas, exógenas como columnas,
      potencia en bandas, CSV determinista; WAPE y MASE de los métodos de base iguales dentro del 1 %. (RF-3, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_series.py` en verde, con series
      sintéticas y sin GPU.
      Evidencia (2026-11-15, R1: 112T6-v2 rebasada a e182c823): humo sin pytest `D:/csg/PM_IMPL/112/R1/humo_verde.log`
      (68 passed, la red real con las tres `CSG_*` incluida) y rojo `rojo_humo.log` (42 F por aserción, rojo=VALIDO);
      el verde con pytest de `lista.txt` de R1 lo corre el carril.
- [x] T6. Control de reidentificación y prueba negativa con fugas plantadas: identificador, coordenada, cliente, término
      del perfil, fecha, secuencia de valores, fragmento de informe y fichero de más; cada una rechazada con su clase.
      (RF-4, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_reidentificacion.py` en verde.
      Evidencia (2026-11-15, R1: 112T6-v2 rebasada a e182c823): humo sin pytest `D:/csg/PM_IMPL/112/R1/humo_verde.log`
      (68 passed, la red real con las tres `CSG_*` incluida) y rojo `rojo_humo.log` (42 F por aserción, rojo=VALIDO);
      el verde con pytest de `lista.txt` de R1 lo corre el carril.
      Límite conocido hasta la T7: con un origen a
      menos de 50 km del origen neutro, el control de coordenadas rechaza también el benchmark limpio (lo prudente); la
      T7 elige un origen neutro lejos del original.
- [x] T7. Manifiesto y emisión atómica: huella del origen, versión, semilla, transformaciones, columnas omitidas,
      tolerancia con su fuente, métricas de referencia y huella de cada fichero; nada a medias si algo falla. (RF-1, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_redes.py tests/test_benchmarks_series.py -k manifiesto`
      en verde, con la generación repetida dos veces y las mismas huellas.
      Evidencia (2026-11-15, R4): humo sin pytest `D:/csg/PM_IMPL/112/R4/humo_verde.log` (`test_benchmarks_redes.py` y
      `test_benchmarks_series.py` enteros, con `-k manifiesto` dentro y la generación repetida dos veces con las mismas
      huellas) y rojo `rojo_humo.log` (7 F por aserción, rojo=VALIDO); el verde con pytest de `lista.txt` de R4 lo corre
      el carril. Resuelve el límite de coordenadas de la T6: el origen neutro se elige de una lista fija, a más de 100
      km del original.
- [x] T8. Cohortes por empresa (una fuera) y por tiempo con franja de separación, por componente conexo de alimentadores
      y clientes, validadas con `particionar_registros`; con una sola empresa, la frase de que la generalización no está
      demostrada. (RF-6, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_cohortes.py` en verde, con dos empresas
      sintéticas, un cliente transferido y el caso de una sola empresa.
      Evidencia (2026-11-15, R6): humo sin pytest `D:/csg/PM_IMPL/112/R6/humo_verde.log` (`test_benchmarks_cohortes.py`
      entero: 9 passed, con dos empresas sintéticas, un cliente transferido y una sola empresa) y rojo `rojo_humo.log`
      (9 F por aserción, rojo=VALIDO); el verde con pytest de `lista.txt` de R6 lo corre el carril.
- [x] T9. Sellado de la prueba antes de elegir modelo (apertura exclusiva, huella en el manifiesto, rechazo si cambia) e
      informe publicado con todos los resultados, también los negativos. (RF-7, RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_evaluacion.py` en verde.
      Evidencia (2026-11-15, R7): humo sin pytest `D:/csg/PM_IMPL/112/R7/humo_verde.log`
      (`test_benchmarks_evaluacion.py` entero: 5 passed) y rojo `rojo_humo.log` (5 F por aserción, rojo=VALIDO); el
      verde con pytest de `lista.txt` de R7 lo corre el carril.
- [x] T10. Herramienta `tools/benchmark_anonimo.py` con `--help` sin DIgSILENT, alta en `CODIGO_FUENTE.md` con la spec
      112. (RF-1)
      Hecho cuando: `.venv/Scripts/python.exe tools/benchmark_anonimo.py --help` sale con 0 y las pruebas del inventario
      (spec 009) en verde.
      Evidencia (2026-11-15, R8): `tools/benchmark_anonimo.py --help` rc=0 sin DIgSILENT; humo sin pytest
      `D:/csg/PM_IMPL/112/R8/humo_verde.log` (`test_benchmark_anonimo.py`: 3 passed, con un benchmark sintético emitido
      de punta a punta y la semilla en `--carpeta-semilla`) y rojo `rojo_humo.log` (3 F por aserción, rojo=VALIDO);
      `test_inventario.py` con pytest va en `lista.txt` de R8 y lo corre el carril.
- [x] T12. Semilla secreta: la de los seudónimos se guarda solo en el equipo (fuera del destino del benchmark), y el
      manifiesto lleva la pública `sha256("publica:" + semilla)`, de la que no se vuelve a la secreta. Rojo: un
      manifiesto que contiene la semilla de los seudónimos, o una cadena que con ella rehace el mapa, se rechaza. (RF-5,
      RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_reidentificacion.py -k semilla` en verde.
      Evidencia (2026-11-15, R3): humo sin pytest `D:/csg/PM_IMPL/112/R3/humo_verde.log`
      (`test_benchmarks_reidentificacion.py` entero, con `-k semilla` dentro) y rojo `rojo_humo.log` (6 F por aserción,
      rojo=VALIDO); el verde con pytest de `lista.txt` de R3 lo corre el carril.
- [x] T13. Geometría y publicación (aclaración de RF-13 y RF-14): coordenadas de un trazado sintético por el grafo y
      longitudes perturbadas (±5 % por defecto, recortado a la tolerancia de T4) para el benchmark de uso local. Control del
      atacante: emparejar las longitudes ordenadas dentro del margen declarado; con un 50 % o más de los tramos emparejados,
      «identificado», y entonces ese benchmark se marca `uso_local` y `publicar` lo rechaza. El publicable sale de
      `ExportSpec` con las estadísticas agregadas del origen (recuentos y percentiles), sin un solo tramo real. (RF-13,
      RF-14, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_reidentificacion.py -k geometria
      tests/test_benchmarks_sintetico.py` en verde (el generador movido a `benchmarks/sintetico.py` da los mismos bytes), con: la red real perturbada identificada y rechazada para publicar (rojo de un «publicar» que la dejaba
      pasar); la sintética por estadísticas no identificada; y dos redes de uso local reproducidas dentro de la tolerancia.
      Además, un origen con menos de 5 alimentadores o de 500 tramos se agrupa o, si no llega, no se emite (con su prueba
      negativa), y un mínimo pedido por debajo del de la spec se rechaza.
      Evidencia (2026-11-15, R5): humo sin pytest `D:/csg/PM_IMPL/112/R5/humo_verde.log`
      (`test_benchmarks_reidentificacion.py` y `test_benchmarks_sintetico.py` enteros) y rojo `rojo_humo.log` (21 F por
      aserción, rojo=VALIDO); el verde con pytest de `lista.txt` de R5 lo corre el carril. Los tramos de código de
      puente se perturban solo si ni con −a cruzan su umbral, y el publicable genera los tamaños sin sorteo (redondeo
      hacia arriba) para no quedarse por debajo del agregado.
- [x] T14. Cuadre contra la geometría pública: el control de RF-14 también compara el benchmark con la red publicada de
      la misma empresa en el VNR-GIS de Osinergmin (ICP sobre los vértices y la huella de longitudes) y declara cuántos
      alimentadores se identifican. La descarga es bajo demanda y por empresa (`tools/vnr_publico_empresa.py`, de lo
      publicado por Osinergmin), a una carpeta fuera del programa y de sus datos, sin fuga al corpus; la descarga real
      la hace el operador, nunca la suite. (RF-14)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_reidentificacion.py -k publica` en
      verde con una geometría «pública» sintética y sin red (salida en `tmp_path`, nada en `tests/`), y
      `tools/vnr_publico_empresa.py --help` sale con 0. El cuadre con la geometría real de una empresa queda como
      evidencia de la ejecución del operador, fuera de la suite.
      Evidencia (2026-11-15, R9): humo sin pytest `D:/csg/PM_IMPL/112/R9/humo_verde.log`
      (`test_benchmarks_reidentificacion.py` entero, con `-k publica` dentro: ICP de una red girada que cuadra y del
      trazado que no, plan de descarga sin red con el destino fuera del programa, y el manifiesto con
      `identificados_publica`) y rojo `rojo_humo.log` (3 F por aserción, rojo=VALIDO); `tools/vnr_publico_empresa.py
      --help` rc=0. La descarga real de una empresa la hace el operador (b3), fuera de la suite.
- [x] T11. Validación: cada RF citado por al menos una prueba y en verde. (RF-1 a RF-14)
      Hecho cuando: `grep -rnoE "112:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-14 y la suite completa con las tres
      variables `CSG_*` está en verde.
      Avance (2026-11-15, R10): el grep lista RF-1 a RF-14, cada uno citado por al menos una prueba
      (`D:/csg/PM_IMPL/112/R10/validacion_rf.txt`), y las pruebas de la 112 pasan en el humo sin pytest
      (`D:/csg/PM_IMPL/112/R10/humo_verde_final.log`); falta la suite completa con las tres `CSG_*`, que corre el carril.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: las del criterio.
- [x] T15. Dejar una empresa fuera cada vez (Plan Maestro PM-17): el bucle de pliegues en el dominio
      (`dominio/benchmarks/interempresa.py`, sin E/S), el catálogo de fichas de la conversión VNR y la forma semanal del
      pronóstico en su adaptador (`adaptadores/benchmarks/interempresa.py`), el informe JSON atómico y
      `tools/interempresa_loco.py` con `--help` sin DIgSILENT. (RF-15, RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_interempresa.py` en verde, con las
      empresas sintéticas «Empresa A», «Empresa B» y «Empresa C» (y una cuarta que no generaliza), el caso de dos
      empresas «NO DEMOSTRADA», el ajuste que nunca ve la retenida y el informe sin el nombre de ninguna carpeta.
      Evidencia (2026-11-20, MEJ13 de d8): rojo sobre el árbol base c4326366 sin el cambio, 14 F por aserción
      (`D:/csg/PM_IMPL/MEJ13_INTEREMPRESA/rojo_20261120_180112.log`); verde de la selección de la puerta y sus
      estructurales (`verde_*.log` de la misma carpeta, con su `.pruebas`). La prueba del pronóstico fija un margen
      del 25 %: con 20 semillas, la misma forma da como mucho 1,12 veces el WAPE de la base y la invertida, 14,9.
- [ ] T16. Corrida real con los paquetes públicos de Osinergmin: el operador baja el paquete VNR-GIS vigente de al menos
      tres empresas con `tools/vnr_publico_empresa.py` a una carpeta fuera del programa, saca su trío con
      `vnr-etl convert --format cymdist` y corre `tools/interempresa_loco.py vnr`; el pronóstico, con los benchmarks de
      series de al menos tres empresas. Es una corrida aparte, fuera de la suite. (RF-15, RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: el informe de cada tarea queda fuera del repositorio con su veredicto, y su ruta y su veredicto
      (también «NO DEMOSTRADA», que se publica igual, RF-8) se anotan aquí.
- [x] T17. Medición de escala de la web: `tools/benchmark_escala_web.py` con `--help` sin DIgSILENT, redes sintéticas de
      10, 50 y 200 alimentadores con la misma semilla, cada tamaño en un proceso propio, carga de la red, p50 y p95 de las
      peticiones de la pantalla con la primera aparte, tamaño de cada respuesta, memoria pico con psutil y la revisión del
      código; el dibujo, «no medido» con su motivo. Alta en `CODIGO_FUENTE.md` y en `docs/MANUAL_COMANDOS.md`. (RF-20,
      RF-21)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_escala_web.py tests/test_inventario.py`
      en verde (la prueba rápida, con 10 alimentadores).
      Evidencia (2026-11-20, MEJ12 de d8, sobre c4326366 + MEJ13): rojo sin la herramienta, 5 F por aserción
      (`D:/csg/PM_IMPL/MEJ12_ESCALA/rojo_d23600bf.log`); verde de las nuevas con sus vecinas y las estructurales, 461
      passed, 0 omitidas (`D:/csg/PM_IMPL/MEJ12_ESCALA/verde_enfocado.log`).
- [ ] T18. Corrida de escala con 10, 50 y 200 alimentadores y 30 repeticiones, aparte de la suite, con la máquina sin otra
      corrida pesada: `.venv/Scripts/python.exe tools/benchmark_escala_web.py --salida <carpeta de evidencias>/escala.json`.
      (RF-20)
      Hecho cuando: el JSON tiene los tres tamaños con su commit y `cambios_sin_registrar` falso, y su registro queda
      junto a él.
- [ ] T19. Dibujo de la pantalla con las mismas redes sintéticas, en navegador real (Playwright con Edge, web propia en un
      puerto libre, nunca 8765 ni 8766). Guion: (1) generar el trío con `ExportSpec(feeders=N, seed=112, size_cycle=10)`
      para N = 10, 50 y 200; (2) arrancar la web con su lanzador en una carpeta de datos temporal y sin perfil de empresa;
      (3) crear el espacio, subir las tres casillas y cargar la red; (4) medir con `performance.mark` y
      `PerformanceObserver` el tiempo desde la respuesta de `feeders` hasta que la tabla muestra su última fila, y el
      del plano; (5) 10 repeticiones por tamaño, p50 y p95, con el commit; (6) guardar el JSON junto al de la T18. (RF-21)
      Hecho cuando: hay un JSON por tamaño con p50 y p95 del dibujo y su commit, y el resultado de la T18 enlaza a él.
