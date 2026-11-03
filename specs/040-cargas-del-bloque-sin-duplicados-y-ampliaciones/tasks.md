# Tareas — Spec 040

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Filas repetidas del libro y reconocimiento de ampliaciones en `resolver_nuevas`. (RF-1 a RF-3)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_040.py -k "duplicada or ampliacion_se_reconoce"` en verde.
      Hecho el 2026-10-31: `sed_existentes` y `ampliacion_de`; en `resolver_nuevas`, duplicada por
      alimentador del libro y punto (1 m), luego ampliación (palabra del nombre o 30 m), luego 014.
      Un nombre idéntico a una SED sigue 004:RF-15.
- [x] T2. La ampliación crea solo su carga en la barra de baja y propone el transformador; las
      fichas del perfil en el plan de cargas. (RF-4, RF-5)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_040.py tests/test_cargas_pf_web.py` en verde.
      Hecho el 2026-10-31: `crear_ampliacion` y `transformador_de_la_ampliacion` (reutiliza
      `potencia_efectiva`, `transformadores_de` y `proponer_transformadores` de la calibración);
      `transformadores_sed` en el plan de cargas.
- [x] T3. Eliminar las variaciones de carga nueva que sobran, con los avisos del informe; 014:RF-26
      pasa a RF-7. (RF-6 a RF-9)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_040.py tests/test_cargas_pf_guion_007.py` en verde.
      Hecho el 2026-10-31: `variaciones_que_sobran` y `eliminar_variaciones` (desactivadas en cada
      caso antes de borrar); `eliminadas`/`eliminarian` y `duplicadas` en el informe; 249 pruebas
      de cargas, casos, obras y ajuste en verde.
- [x] T5. Nombres de variación con su alimentador y reconocimiento de las cortadas. (RF-10 a RF-12)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_040.py` en verde.
      Hecho el 2026-10-31: `nombre_de_carga` recorta la SED; `indice_de_cargas_nuevas` da a una
      variación sin alimentador en el nombre el de la SED existente más cercana a su carga, y
      `ejecutar` la renombra al reutilizarla; 252 pruebas de cargas, casos, obras y ajuste en verde.
- [x] T4. [DIgSILENT] NA203 + NA205 cargado de nuevo desde la web. (Todos)
      Hecho cuando: sin la segunda Fundo Luciana ni la segunda YANACA; Cesar Monge, HONGWEN y
      AGROPEX como ampliaciones de SE50324, SE50323 y SE50150; las variaciones que sobraban, eliminadas.
      Hecho el 2026-10-31 desde la web (libro v3, base disco:56e1cbdb77ac): 5 variaciones eliminadas
      (las dos duplicadas y las tres ampliaciones creadas como SED), 3 ampliaciones en SE50150, SE50324 y
      SE50323 con su propuesta de transformador, 1 carga nueva, 31 reutilizadas (15 renombradas con su
      alimentador); «Con proyecto» converge, sin fallos.
- [x] T9. La fila cercana que no cabe en el transformador de la SED es SED nueva. (RF-13)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py` en verde.
