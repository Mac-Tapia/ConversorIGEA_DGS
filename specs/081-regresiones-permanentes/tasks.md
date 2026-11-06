# Tareas — Spec 081

- [x] T1 Contrato de fases, regla del banco y preflight. (RF-1 a RF-9)
  Hecho cuando: `pytest -q tests/test_comprobacion_fases.py` en verde.
- [x] T2 Lectura de DIgSILENT tras el flujo y sus fases, sin escribir, con doble. (RF-10 a RF-13)
  Hecho cuando: `pytest -q tests/test_resolver_convergencia.py -k lectura` en verde.
- [x] T3 La lectura del flujo, el «Caso base» y la línea de importación. (RF-14 a RF-16, RF-32)
  Hecho cuando: `pytest -q tests/test_comprobacion_flujo.py -k limpio` en verde.
- [x] T4 Estados `parcial` y `no_converge` del trabajo, y sus consumidores. (RF-17 a RF-24)
  Hecho cuando: `pytest -q tests/test_comprobacion_flujo.py -k trabajo` en verde y `npm run typecheck` sin errores.
- [x] T5 Resolver la no convergencia del «Caso base», con doble. (RF-25 a RF-31)
  Hecho cuando: `pytest -q tests/test_resolver_convergencia.py` en verde.
- [x] T6 Huella del «Caso base», con doble. (RF-33 a RF-36)
  Hecho cuando: `pytest -q tests/test_comprobacion_flujo.py -k huella` en verde.
- [x] T7 Suite por tandas en otro proceso. (RF-37 a RF-41)
  Hecho cuando: `pytest -q tests/test_suite_por_tandas.py` en verde.
- [x] T8 Registro de cierre y las dos vías de cierre. (RF-42 a RF-45)
  Hecho cuando: `pytest -q tests/test_cierre_web.py tests/test_lanzador_web.py` en verde.
- [x] T9 Regresiones y su prueba. (RF-46 a RF-49)
  Hecho cuando: `pytest -q tests/test_regresiones.py` en verde.
- [x] T15 Una carpeta por empresa, con su regla, el vínculo y el aviso. (RF-50 a RF-56)
  Hecho cuando: `pytest -q tests/test_carpeta_por_empresa.py` en verde.
- [x] T17 El oráculo avisa sin impedir importar, y la carpeta mal escrita no da error. (RF-57 a RF-61)
  Hecho cuando: `pytest -q tests/test_oraculo_corrige.py tests/test_preflight_contract.py tests/test_carpeta_pf.py tests/test_carpeta_por_empresa.py` en verde.
- [x] T18 Sin nombres de empresa en la lista negra, y la ayuda del MCP en UTF-8. (RF-62, RF-63)
  Hecho cuando: `pytest -q tests/test_casos_de_prueba.py tests/test_asistente_lectura_local.py` en verde, sin `PYTHONUTF8`.
- [x] T19 Lo nuevo se adapta a las fases de su barra: cargas nuevas, bancos de la calibración y de una obra. (RF-64 a RF-69)
  Hecho cuando: `pytest -q tests/test_fases_de_lo_nuevo.py` en verde, con redes sorteadas.
- [x] T21 El aviso del catálogo subido dice dónde entran sus fichas. (RF-70)
  Hecho cuando: `pytest -q tests/test_aviso_catalogo.py` en verde.
- [ ] T22 [DIgSILENT] El aviso del catálogo en el navegador real, con la web reiniciada y el frente reconstruido; no toca DIgSILENT. (RF-70)
  Hecho cuando: al subir un catálogo, la pantalla y el Registro dan la misma frase, y la confirmación de «Quitar» dice que el DGS no cambia.
- [ ] T20 [DIgSILENT] Una carga nueva en un ramal monofásico de un proyecto de prueba, importado por la web.
  Hecho cuando: «Con proyecto» converge con la SED monofásica servida y el informe lleva el aviso con sus cifras.
- [ ] T10 [DIgSILENT] Resolver en un proyecto de prueba de quien tenga el turno: un acoplador o un banco con más fases que su barra.
  Hecho cuando: importado por la web, el «Caso base» converge en DIgSILENT y su informe lleva la anotación.
- [ ] T11 [DIgSILENT] La lectura real tras el flujo: una SED de una fase en un ramal sin esa fase, sobre una copia de prueba.
  Hecho cuando: el informe cuenta su barra de baja a 0 p.u. y su carga, y sale `CONVERGE_SIN_SERVIR`.
- [ ] T12 [DIgSILENT] La huella real del «Caso base» desde `tools/ajuste_cabecera_pf.py`, con `caso_base_huella` en el informe.
  Hecho cuando: una calibración real da la misma huella antes y después; si no, sale el fallo grave con lo cambiado. Con esto se confirma la causa de (e).
- [ ] T13 [DIgSILENT] Sistema con un alimentador sin converger, por la web y en el navegador.
  Hecho cuando: el trabajo dice `parcial` con la lista en el título y en la calibración, y lo demás sigue calibrado.
- [ ] T14 [DIgSILENT] La suite nocturna real, cerrando la web a mitad, sin DIgSILENT en uso por otra sesión.
  Hecho cuando: la suite termina y registra su resultado; y con el proceso matado, la web avisa de «interrumpida».
- [ ] T16 [DIgSILENT] Dos fuentes de empresas distintas por la web, con un TXT sin empresa y el campo del espacio en el navegador.
  Hecho cuando: cada proyecto queda en la carpeta de su empresa, el aviso del supuesto se ve y las lecturas lo encuentran; ningún proyecto existente se ha movido. Falta el campo en el front: hoy solo por `PUT /api/workspaces/<id>/options`.
- [x] T23. Registro de cada orden, estadística descriptiva, contraste de versiones y fallos repetidos. (RF-71, RF-72, RF-73, RF-74)
      Hecho cuando: `pytest -q tests/test_estadistica_ordenes.py` en verde.
- [x] T25. Una relectura anterior a la importación no rechaza el proyecto recién importado. (RF-75)
      Hecho cuando: `pytest -q tests/test_powerfactory_binding.py -k rf75` en verde.
      Hecho el 2026-11-05: `require_project_binding` compara `accepted_at` con el `native_reread_at` más reciente;
      sin fecha de relectura se compara como antes.
- [x] T26. El vigía de la conexión cubre también `GetCurrentUser`. (RF-76)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py -k rf76` en verde.
      Hecho el 2026-11-05: `conectar` pide el usuario antes de anotar «fin».
- [ ] T24. [DIgSILENT] Medir «Con proyecto» de Pisco antes y después de 042:RF-29/RF-30 con `tools/estadistica_ordenes.py --corte`, y bajar la tasa de fallos de `ajuste_cabecera_pf.py` y de la foto del gemelo con sus causas repetidas. (RF-73, RF-74)
      Hecho cuando: el contraste da p < 0,05 en fallos sobre una corrida real.
