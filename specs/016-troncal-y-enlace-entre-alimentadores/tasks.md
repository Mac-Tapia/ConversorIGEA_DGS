# Tareas — Spec 016

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Estado: aprobado (2026-10-14) · Fecha: 2026-10-14

Preparación

- [x] T1. Confirmar en el manual de la API de PF 2024 (`Help/PythonReference_en.pdf`) si
      hay un método para partir una línea, y cómo se escriben `GPScoords` de un `ElmLne` y
      `on_off` de un `StaSwitch` dentro de una variación. Sonda en DIgSILENT sobre una
      copia de un proyecto ya importado, borrada al terminar. (RF-16 a RF-19, RF-36)
      Hecho cuando: el plan dice el método que se usa con su referencia, o que se hace la
      copia manual.
- [x] T2. `fake_pf`: `Application.SplitLine` como en DIgSILENT (ver la T1 en el plan),
      `GPScoords` y `StaSwitch` en variaciones. (base de T6 a T9)
      Hecho cuando: `pytest -q tests/test_fake_pf_variaciones.py` en verde, y la suite
      entera en verde.
      Hecha el 2026-10-14: 22 en verde; suite sintética 1.717 en verde. Fallan las dos
      de `test_linea_base_001.py` (94 DGS distintos de la línea base), que no usan
      `fake_pf`: vienen de los cambios sin confirmar de `src/igea_dgs/dgs.py` en la rama.
      Las líneas de `fake_pf.proyecto` tienen ahora `dline` = 1 km (lo que ya suponía la
      confiabilidad de la 012) y `GPScoords` de barra a barra.

Lógica sin DIgSILENT

- [x] T3. `src/igea_dgs/troncal.py`: `Red`, `troncal`, `aguas_abajo`. Entra en
      `CODIGO_FUENTE.md`. (RF-1 a RF-5, RF-64)
      Hecho cuando: `pytest -q tests/test_troncal.py tests/test_inventario.py` en verde, y
      con las tres `IGEA_*` IN111 da 71 tramos y 13,58 km.
      Hecha el 2026-10-15: 106 en verde. El árbol es el de los caminos más cortos en
      metros (IN111 tiene tres anillos cerrados); la spec y el plan, corregidos.
- [x] T4. `troncal.py`: `punto_mas_cercano`, `punto_en_troncal`, `partir` y
      `extremos_del_enlace` con la rejilla. (RF-15, RF-18, RF-20, RF-27, RF-28, RF-45,
      RF-67)
      Hecho cuando: `pytest -q tests/test_troncal.py` en verde.
      Hecha el 2026-10-15: 177 en verde. Con los TXT, el enlace va del nodo `15232` de la
      troncal de TA225 al 47,4 % de `SEC_1091_1055021` de la de IN111: 3.626 m.
- [x] T5. `src/igea_dgs/obras_pf.py`: casos (Sin proyecto implica Con proyecto), clases
      `enlace` y `migracion`, sección con toda la troncal y tipo de cable, simulación de
      cada una. (RF-6 a RF-9, RF-11, RF-13, RF-14, RF-23 a RF-25, RF-31, RF-38, RF-39,
      RF-41, RF-51 a RF-53, RF-59, RF-61, RF-65, RF-66)
      Hecho cuando: `pytest -q tests/test_obras_pf.py tests/test_obras_pf_016.py` en verde.
      Hecha el 2026-10-15: 34 nuevas en `tests/test_obras_pf_016.py`. Las pruebas de la 011
      que pedían una obra solo en «Sin proyecto» piden ahora los dos casos (016:RF-13).
      `construir_seccion` del guion toma el tipo de cada tramo (los cables, el suyo).

Guiones de DIgSILENT

- [x] T6. `partir_tramo` y `leer_red` en `tools/cargas_pf.py` (el módulo común de los
      guiones); las obras usan la troncal de `troncal.py`, el N-1 y la transferencia no.
      (RF-2, RF-10, RF-16, RF-17, RF-19, RF-21, RF-22)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py tests/test_estudios_pf_guion.py`
      en verde.
      Hecha el 2026-10-15: 7 nuevas en `tests/test_obras_pf_guion_016.py`. Las pruebas de
      troncal de la 011 usan ahora la del camino más largo, con una derivación de 0,5 km
      que no es troncal, y comprueban que `ComBbone` no se ejecuta.
- [x] T7. `construir_enlace`. (RF-26, RF-29, RF-30, RF-32 a RF-37, RF-40, RF-42, RF-43,
      RF-62)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py` en verde.
      Hecha el 2026-10-15: 8 nuevas en `tests/test_obras_pf_guion_016.py`. El doble de
      DIgSILENT corta ahora el alimentador en un interruptor abierto, como DIgSILENT: si
      no, el enlace abierto metía las barras de uno en el otro. RF-32 avisa también con
      una barra indicada, con su tensión.
- [x] T8. `construir_migracion`. (RF-54 a RF-58, RF-60)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py` en verde.
      Hecha el 2026-10-15: 4 nuevas en `tests/test_obras_pf_guion_016.py`. La parte que
      pasa se calcula al construir la obra, con la red de «Con proyecto»: si un enlace de
      la misma tanda partió un tramo de esa parte, la mitad nueva también se migra y se
      avisa.
- [x] T9. Orden de casos: obras de «Sin proyecto» activas también en «Con proyecto», que
      se crea después si no existe. (RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py tests/test_casos_pf*.py` en
      verde.
      Hecha el 2026-10-15: 2 nuevas en `tests/test_obras_pf_guion_016.py`. Sin «Con
      proyecto», el guion aplica primero las obras de «Sin proyecto», crea «Con proyecto»
      con `casos_pf.crear_con_proyecto` (la misma copia que la preparación de los casos),
      comprueba allí el flujo de cada una y aplica después las de solo «Con proyecto».
- [x] T10. `tools/cargas_pf.py`: conexión en la troncal, partiendo el tramo en la
      variación de cada carga, en orden de fracción; `minima_m` en el plan. (RF-45 a
      RF-50)
      Hecho cuando: `pytest -q tests/test_cargas_pf*.py` en verde.
      Hecha el 2026-10-15: 10 nuevas en `tests/test_cargas_pf_guion_016.py`. RF-47 se hace
      como dice la spec y no como preveía el plan (ver el plan): cada carga parte el tramo
      original en su variación, porque se mide sola (007:RF-12); dos en el mismo tramo se
      avisan. Sin ElmFeeder o sin cabecera no hay troncal y se usa la barra más cercana.
- [x] T11. `tools/transferencia_pf.py`: no cerrar un enlace entre tensiones distintas.
      (RF-63)
      Hecho cuando: `pytest -q tests/test_transferencia_pf*.py` en verde.

Web
      Hecha el 2026-10-15: 1 nueva en `tests/test_transferencia_pf_guion.py`. El informe
      lista los enlaces sin calcular en `sin_calcular`; si solo hay de esos, no dice «sin
      punto de enlace» (011:RF-107) sino por qué no se calculan.
- [x] T12. API y `ObrasPF.tsx`: clases nuevas, «toda la troncal», tipo de cable, nodo,
      distancia mínima, solo «Con proyecto» en las dos clases nuevas; `CargasTab.tsx`:
      distancia mínima. `npm run build`. (RF-68 a RF-73)
      Hecho cuando: `pytest -q tests/test_obras_pf_web.py tests/test_cargas_pf_web.py
      tests/test_obras_estudios_front.py` en verde y el front compila.

Cierre
      Hecha el 2026-10-15: `tests/test_obras_web_016.py` (6). La API valida las obras nuevas
      con `validar_obra`; `lote/plan` recibe `minima_m` (422 si es negativa). En el formulario,
      al marcar «Sin proyecto» se marca también «Con proyecto».
- [x] T13. Anotar 007 (RF-24, RF-28, RF-30, RF-31) y 011 (RF-57, RF-87) con el cambio de
      esta spec; `CODIGO_FUENTE.md` al día.
      Hecho cuando: `grep -rnoE "016:RF-[0-9]+" tests | sort -u` cubre los 73 RF y la
      suite entera está en verde con las tres `IGEA_*`.
      Hecha el 2026-10-15: anotados 007:RF-24, RF-28, RF-30, RF-31 y 011:RF-57, RF-87. Los
      73 RF citados; RF-44 también con una prueba del doble (el enlace de la obra es una
      línea con seccionador abierto), además de la de DIgSILENT de la T14.
- [x] T14. Prueba en DIgSILENT con el proyecto de IN111 y TA225: toda la troncal de IN111
      a 120 mm² en «Sin proyecto» y «Con proyecto»; el enlace abierto solo en «Con
      proyecto», partiendo un tramo de cada troncal; la migración a 22,9 kV desde el nodo
      que indique el operador; y la transferencia de IN111 a TA225 por el enlace.
      (RF-44 y los criterios de finalización)
      Hecho cuando: el informe de cada paso converge, o se anota por qué no, y el usuario
      lo da por bueno.
      Avance del 2026-10-15 (desde la web, proyecto 20261015-170359_IGEA_IN111_TA225):
      nueve cargas nuevas en TA225, enlace a 22,9 kV, migración de IN111 desde el nodo
      del enlace (que lo cierra, RF-80) y segunda terna en siete tramos sobrecargados de
      TA225: «Con proyecto» converge, tramo más cargado 98,1 %. Salieron RF-74 a RF-80.
      La transferencia no aplica tras la migración (la parte que pasa ya no cuelga de
      IN111). Cerrada el 2026-10-16: el usuario aclaró que la sección de la troncal de
      IN111 era solo actualizar lo existente.

- [x] T15. Trazado del enlace por la vía: `vias.py` con pruebas que inyectan la respuesta
      de OSRM (ruta, sin ruta, error de red, extremo lejos de la vía, sin perfil), el
      enlace en `obras_pf.py` con su trazado y el perfil de Electro Dunas con `vias`.
      (RF-81 a RF-87)
      Hecho cuando: las pruebas que citan 016:RF-81 a RF-87 pasan y un enlace en DIgSILENT
      sale con el trazado de la vía.
      Hecho el 2026-10-16: enlace TA225-IN111 por la vía, 6,27 km y 140 vértices (3,62 km en
      recta), 9,4 m fuera de vía; «Con proyecto» converge con la migración, las nueve
      cargas y la segunda terna en siete tramos (máximo 98,1 %).
- [x] T16. Cable hasta la carga nueva solo a más de 25 m del nodo de media; a menos, la SED
      cuelga del nodo. `con_cable` en `tools/cargas_pf.py`, en la resolución, al crear, en la
      simulación y en el informe. (RF-88)
      Hecho cuando: las pruebas que citan 016:RF-88 pasan y una carga de PN107 en DIgSILENT
      sale con su nodo y, según la distancia, con o sin cable.
      Código hecho el 2026-10-16 (las pruebas de 016:RF-88 pasan); la prueba en DIgSILENT con PN107 pasa a T18 (033, 2026-10-29).
- [x] T17. Dibujar en el diagrama lo que crean las cargas y las obras sin símbolo
      (`Diagrama.completar` en `tools/cargas_pf.py`, al final de cargas y de obras). (RF-89)
      Hecho cuando: las pruebas que citan 016:RF-89 pasan y el enlace de IN111 + TA225 se ve.
      Hecho el 2026-10-16: en IN111 + TA225 se dibujaron el enlace (140 vértices, extremos
      en 15232 y ENLACE_C_IN111(2)), las seis mitades partidas y sus seis nodos; las cargas
      IC_9 a IC_17 están en el punto del Excel (0,0 m); «Con proyecto» converge.
- [ ] T18. [DIgSILENT] Carga nueva de PN107 con y sin cable según la distancia a su nodo de
      media. (RF-88)
      Hecho cuando: en DIgSILENT una carga de PN107 sale con su nodo y, según la distancia,
      con o sin cable.
