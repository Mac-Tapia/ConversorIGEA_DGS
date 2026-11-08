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
- [x] T20 [DIgSILENT] Una carga nueva en un ramal monofásico de un proyecto de prueba, importado por la web.
  Hecho cuando: «Con proyecto» converge con la SED monofásica servida y el informe lleva el aviso con sus cifras.
  Verificado 2026-11-07: proyecto nuevo `20261107-233155_CSG_TXT_PE104`, importado por la web desde TXT reales intactos.
  Carga explícitamente sintética PRBFASE_UNO por barra sin coordenadas: transformador de una fase releído,
  baja a 0,914107 p.u. y potencia efectiva 0,099999997 kW para 0,1 kW pedidos. Con proyecto converge.
  Aviso conservado: 10 kVA, 0,1 kW, 0 kvar y corriente calculada de 1,0 A por fase frente a 0,6 A con tres;
  la corriente del aviso se calcula de la potencia declarada y no se presenta como una medición.
  Procesos nuevos 25984/38692/29100, códigos 0 sin avisos: las variaciones persisten en Con proyecto;
  Base/Sin conservan sus JSON completos por bytes. Repetición: cero creadas/una reutilizada; termina en Sin proyecto.
  El ensayo anterior con coordenadas reubicó correctamente a tres fases (RF-8); se conserva, pero no prueba la adaptación.
  Evidencia: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/p12_monofasica_aceptacion.json`.
  Mínima global 0,7759 p.u.: sin aceptación eléctrica de la red, visual, de R2 completo ni de una campaña ML.
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
  Hecho cuando: cada proyecto queda en la carpeta de su empresa, el aviso del supuesto se ve y las lecturas lo encuentran; ningún proyecto existente se ha movido.
  Avance 2026-11-07: campo «Empresa del espacio» implementado en las tres modalidades; conserva los selectores y se bloquea durante trabajos de motor. Guardar vacío envía `null`; la API ahora lo persiste, mientras omitir el campo conserva su valor. Render React, tipos, compilación y contratos/persistencia verificados. Falta la aceptación por navegador con dos empresas y relectura nativa; esta tarea sigue abierta.
- [x] T23. Registro de cada orden, estadística descriptiva, contraste de versiones y fallos repetidos. (RF-71, RF-72, RF-73, RF-74)
      Hecho cuando: `pytest -q tests/test_estadistica_ordenes.py` en verde.
- [x] T25. Una relectura anterior a la importación no rechaza el proyecto recién importado. (RF-75)
      Hecho cuando: `pytest -q tests/test_powerfactory_binding.py -k rf75` en verde.
      Hecho el 2026-11-05: `require_project_binding` compara `accepted_at` con el `native_reread_at` más reciente;
      sin fecha de relectura se compara como antes.
- [x] T26. El vigía de la conexión cubre también `GetCurrentUser`. (RF-76)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py -k rf76` en verde.
      Hecho el 2026-11-05: `conectar` pide el usuario antes de anotar «fin».
- [x] T27. `ntnum` entre los datos de operación que pasan de «Sin proyecto» a «Con proyecto». (RF-77)
      Hecho cuando: `pytest -q tests/test_casos_pf.py -k rf77` en verde.
- [x] T28. `sin_a_con_proyecto` llama a `etapas_al_dia` con «Con proyecto» activo y lo dice en sus avisos. (RF-78)
      Hecho cuando: `pytest -q tests/test_casos_pf.py tests/test_cargas_pf_guion_007.py -k rf78` en verde.
      Del 2026-11-06: en DIgSILENT la llamada de la sincronía llegaba antes de encender las variaciones de «Con proyecto» y no
      adelantaba nada; se llama también en `tools/cargas_pf.py` con todo encendido, antes del flujo de «Con proyecto».
- [x] T29. `connect_powerfactory` de la aceptación conecta con `pf_arnes.conectar` cuando arranca el motor. (RF-79)
      Hecho cuando: `pytest -q tests/test_powerfactory_gate.py -k rf79` en verde.
- [ ] T24. [DIgSILENT] Medir «Con proyecto» de Pisco antes y después de 042:RF-29/RF-30 con `tools/estadistica_ordenes.py --corte`, y bajar la tasa de fallos de `ajuste_cabecera_pf.py` y de la foto del gemelo con sus causas repetidas. (RF-73, RF-74)
      Hecho cuando: el contraste da p < 0,05 en fallos sobre una corrida real.
- [x] T30. Lo que una obra abre se anota antes, se cierra al borrar la variante y se restituye al empezar la orden siguiente;
      comprobación de «Con proyecto» contra «Sin proyecto» al leer la escalera. (RF-80, RF-81, RF-82, RF-83, RF-84, RF-85)
      Hecho cuando: `pytest -q tests/test_obras_aperturas.py` en verde.
      Hecho el 2026-11-07: `tools/obras_pf.py::abrir` (todas las aperturas de las obras, también la entrada de la migración,
      que no se anotaba), `restituir_lo_abierto` en el `finally` de la variante evaluada, `restituir_pendientes` al empezar
      `aplicar`, `evaluar` y `datos_escalera`, y `comprobar_servicio_con_proyecto` en `datos_escalera`. El doble
      (`fake_pf`, `servicio_en_escenario`) guarda `outserv` y `on_off` en el escenario activo y da `ElmTerm.IsEnergized`.
- [ ] T31 [DIgSILENT] Una escalera de «Con proyecto» con transferencia (087:RF-31) cortada a mitad en un proyecto de prueba
      nuevo, y la orden siguiente por la web. (RF-80, RF-82, RF-83)
      Hecho cuando: tras parar el trabajo mientras mide la transferencia, la lectura siguiente de la escalera dice qué cerró
      (081:RF-82 o RF-83), «Con proyecto» queda con 0 barras de media sin tensión, como «Sin proyecto», y el registro de
      aperturas queda vacío.

Avance transversal P21, 2026-11-08: el ensayo de RF-37/RF-39/RF-41 usa procesos reales separados y
una única prueba propia, registra su resultado tras matar el servidor y detecta la muerte real del proceso
de tandas. `tests/test_suite_por_tandas.py` conserva esa reproducción; no es la noche completa de T14.
Las pruebas de trabajos interrumpidos producen el diario mediante JobManager antes de matar el servidor,
sin sembrarlo manualmente para acreditar la caída. El aislamiento de red de `tests/test_seguridad_web.py`
abarca solo procesos Python propios (audit-hook heredado), conversión de TXT sintéticos y reapertura de dos DGS.
No hubo importación/calibración/informe nativo, flujo real sin fase, deriva de Caso base nativa ni corte de
escalera con transferencia: T10/T11/T12/T13/T14/T31 permanecen abiertas, al igual que 086:T33/T36 y 096:T3.
Evidencias y limitaciones: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/paralelo_p21_20261108/HANDOFF.md`.

Corrección de revisión P21 I1–I3: `tests/test_integridad_trabajos.py` incorpora los
fallos reproducidos de cancelación/snapshot, protección de identidades y cadenas antes
de retención, y admisión frente a shutdown. Incluye fallos de escritura sin afirmación
de durabilidad, joins fuera del cerrojo y resultado completo de 8 MiB sin truncamiento.
Los recibos/cortes son de procesos propios y los datos son de contrato; no cierran
T10/T11/T12/T13/T14/T31, 086:T33/T36 ni 096:T3. La corrección conserva fuente y alcance
de la revisión previa. Resultados y corte exacto: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/correccion_revision_p21_20261108/HANDOFF.md`.
