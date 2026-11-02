# Tareas — Spec 063

- [x] T1. Conclusión de factibilidad con los tres casos, función pura. (RF-7, RF-8, RF-9, RF-10, RF-11, RF-13)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py -k conclusion` en verde,
      con medidas sorteadas en las cuatro ramas.
      Hecho el 2026-11-01: `informes.conclusion_factibilidad` y `Conclusion`; la web la devuelve como
      `conclusion_conexion` en el resultado del informe. 7 pruebas sorteadas en verde (semillas 1 a 5).
- [x] T2. Etapas al día antes del flujo de cada caso. (RF-3, RF-4, RF-5)
      Hecho cuando: `pytest -q tests/test_estudios_pf_guion.py tests/test_casos_pf.py` en verde,
      con una etapa posterior a la hora del caso aplicada y avisada.
      Hecho el 2026-11-01: `estudios_pf.ejecutar` llama a `etapas_al_dia` al activar el caso y lo
      avisa; `_optimizador` restituye la hora del caso (011:RF-26); «Con proyecto» sin obras se
      renueva desde la recalibración (037:RF-8). 201 pruebas de estudios, casos y ajuste en verde.
- [x] T3. «Generar informe de factibilidad» prepara, corre los flujos y escribe, en un trabajo. (RF-1, RF-2, RF-6, RF-12)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py` en verde con alimentadores
      sorteados de distinto tamaño, sin pasar por 4.2, y el endpoint en el carril de DIgSILENT.
      Hecho el 2026-11-02: `preparar_flujos_del_informe` (4.2 entero solo para el alimentador) y
      carril `powerfactory`; `test_el_informe_prepara_solo_su_alimentador_sin_pasar_por_4_2` (sorteados) y
      `test_el_boton_prepara_los_casos_y_corre_los_flujos_en_el_mismo_trabajo`.
- [x] T4. Informe Word con estado actual, proyectado sin obras y con proyecto. (RF-7, RF-8, RF-9, RF-10, RF-14, RF-17)
      Hecho cuando: el .docx de la prueba lleva las tres secciones, «de A kW a B kW (+C kW)», y la
      Pcc y las coordenadas en el punto de diseño.
      Verificado el 2026-11-01: pruebas de los tres casos, potencia previa/incremento, NIS y ficha;
      101 pruebas focales de informes/estudios. Informe real de Santa María con tres casos,
      sin campos pendientes y con dictamen desfavorable sustentado en cobertura completa.
- [x] T5. Datos de los PDF: expediente EXP, fecha con su documento, alimentadores leídos. (RF-15, RF-19, RF-20)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py -k documentos` en verde con
      textos sintéticos.
      Hecho el 2026-11-02: `codigo_ficha` aparte del EXP; `fechas` y `alimentadores_leidos` con su
      documento; `test_documentos_exp_codigo_de_ficha_fechas_y_alimentadores` (en
      `tests/test_documentos_solicitud.py`, junto a los textos sintéticos).
- [x] T6. Formulario: potencia actual, incremento, NIS, estructura, Pcc y UTM; aviso de alimentador. (RF-14, RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: `npm --prefix frontend run build` sin errores y la web probada en el navegador real.
      Hecho el 2026-11-02: `npm run build` sin errores y probado en el navegador real (web abierta con el
      acceso directo, SM218, carga de INKA) con los PDF reales del expediente: la carta dio potencia actual
      480 kW, solicitada 1100 kW e «incremento de 620 kW», NIS y EXP; la ficha, código de ficha
      `00229-25` aparte del EXP, Pcc 36 MVA y UTM; la respuesta, la estructura 39533 como código del
      punto de diseño; el botón activo sin pasar por 4.2; consola sin errores. El aviso de alimentador
      (RF-19) no salió porque los PDF dicen SM218, como la carga: en el navegador no se vio; su
      regla la prueba `frontend/test/solicitudLeida.test.mjs` (`npm test`).
- [x] T8. Escalera por escalones: bancos, sección, terna; el primero que cumple. (RF-21, RF-22)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_optimizacion_oraculo.py
      tests/test_informe_factibilidad_un_paso.py` en verde, con variantes sorteadas donde la sección es
      más barata que los bancos y aun así se eligen los bancos si cumplen.
      Hecho el 2026-11-01: `escalera_optima.ORDEN` y `rango`; `elegir`, `buscar_k` y `elegir_para_k`
      ordenan por escalón y luego por costo. 135 pruebas de escalera, oráculo, SET nueva e inventario.
- [x] T9. Optimizar «Con proyecto» solo con las cargas que se evalúan. (RF-23, RF-24)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py -k optimiza` en verde, con
      cargas sorteadas: solo las pedidas llegan a la escalera y un nombre que no está se rechaza.
      Hecho el 2026-11-01: `cargas` en `ObrasIn`, `con_proyecto_optimizar` y `optimizar_con_proyecto`.
- [x] T10. Bancos en la barra existente de la troncal; regulador solo si el perfil lo pide. (RF-25, RF-26)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion.py` en verde, con
      una carga en un NODE_T que recibe variantes de banco en la barra de aguas arriba y sin regulador.
      Hecho el 2026-11-01: `banco_en` en la lectura, `_carga_para_escalera` en la web y el oráculo;
      `escalera.con_regulador` en el perfil.
- [x] T11. Sección escalonada de menor a mayor; bancos del oráculo en la troncal. (RF-25, RF-27)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde, con todas las secciones aptas
      en orden creciente y la menor que cumple elegida.
      Hecho el 2026-11-01: todas las aptas en la escalera y en el espacio del oráculo.
- [x] T12. Mejora de cada escalón en la evaluación y en el informe. (RF-28)
      Hecho cuando: el informe de la evaluación lista bancos, cada sección y terna con la tensión que
      deja cada una.
      Hecho el 2026-11-02: cada variante evaluada lleva `u_cargas` y `u_min_mt`, el Registro y la
      tabla «Obras en escalera» los muestran; `test_cada_variante_dice_la_tension_que_deja`.
- [x] T13. La consigna de la fuente en los cuatro casos. (RF-29)
      Hecho cuando: `pytest -q tests/test_casos_pf.py tests/test_ajuste_cabecera_guion.py` en verde, con
      la consigna de «Sin proyecto» copiada a «Con proyecto» y fijada también en el «Caso base».
      Hecho el 2026-11-01: `casos_pf.OPERACION` copia `ElmXnet.usetp` (014:RF-32) y la calibración la
      fija también en el «Caso base».
- [x] T14. El cambio de sección solo sube de sección. (RF-30)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde, con tramos de distinta sección
      donde solo cambian los de menor corriente nominal que el conductor nuevo.
      Hecho el 2026-11-01: la lectura de la troncal lleva `tipo` e `inom_a`; `_escalon_seccion` filtra.
- [x] T15. Nodos de cada obra en la evaluación y en el informe. (RF-31)
      Hecho cuando: la lectura de la troncal da `desde` y `hasta` de cada tramo y el informe lista el
      nodo de MT de cada banco y los nodos de inicio y fin de cada tramo cambiado.
      Hecho el 2026-11-02: `nodos` (tramo, desde, hasta) en cada obra de sección y terna y
      `escalera_optima.ubicacion`; el Registro y la tabla de la web la dicen;
      `test_cada_obra_dice_su_nodo_de_mt_o_sus_nodos_de_inicio_y_fin`.
- [x] T16. Obras sobre el camino eléctrico de cada carga. (RF-32)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde, con caminos sorteados donde sección
      y terna van sobre el camino de la carga y el banco en su barra de aguas arriba.
      Hecho el 2026-11-01/02: `test_obras_sobre_el_camino_electrico_de_la_carga` (caminos sorteados) y
      `test_banco_en_la_barra_existente_de_la_troncal`.
- [x] T17. Con solución en la máxima no se pasa a otras obras ni a la SET nueva. (RF-33)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde, con variantes que cumplen la
      máxima y no los sorteos: se elige la primera por prioridad y se avisa.
      Hecho el 2026-11-01: `escalera_optima.elegir` con `sin_confirmar_sorteos`.
- [x] T18. Los sorteos miden la red con la obra y la demanda escalada. (RF-28)
      Hecho cuando: una prueba con el doble de DIgSILENT muestra que cada sorteo ve la obra aplicada y
      la demanda escalada (SM218: la tensión de INKA no cambiaba con la demanda).
      Hecho el 2026-11-02: la causa no era la obra sino el escalado. Sonda en una copia de SM218:
      escribir `plini × 0,35` en el escenario dejaba las existentes en 9,1 MW con cualquier factor;
      `scale0 × 0,35` las bajó a 3,2 MW (INKA de 0,921 a 0,960 p.u.). `_Sorteo` escala `scale0`;
      `test_los_sorteos_escalan_solo_las_cargas_existentes_y_se_restituyen` exige que no se
      escriba `plini`. El 94,5 % era el corte de `sortear` tras 11 fallos de 200.
- [x] T19. Más del umbral de carga nueva: SET nueva directa. (RF-34)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py -k umbral` en verde, con cargas
      sorteadas por encima y por debajo del umbral.
      Hecho el 2026-11-01: `con_proyecto_optimizar` y `planificacion.set_nueva_desde_kw` en el perfil.
- [x] T25. Los sorteos y el criterio de la escalera cubren todas las troncales. (RF-39, RF-40)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py -k "troncales or queda_fuera"` en verde.
      Hecho el 2026-11-02: `_cargas_de` usa `cargas_sed`. Las dos pruebas fallaban antes del arreglo.
- [x] T26. Libro de pérdidas en dos hojas y PDF del informe desde la web. (RF-41, RF-42)
      Hecho cuando: `pytest -q tests/test_libro_perdidas_por_sistema.py` en verde.
- [ ] T7. [DIgSILENT] INKA'S BERRIES en SM218 desde la web con un clic. (Todos)
      Hecho cuando: el informe sale del botón de 4.4 sin pasar por 4.2, con los tres casos, y dice lo
      mismo que el informe hecho a mano el 2026-11-01.

- [x] T20. Cobertura del proyecto completo tras trasladar ramas a una SET nueva. (RF-6, RF-9, RF-12)
      Hecho cuando: `pytest -q tests/test_estudios_pf_guion.py -k cobertura` en verde y los seis
      flujos reales guardan barras completas, fuentes, consumos y balance sin omitir COPARA.
      Verificado el 2026-11-01: trabajo web b724419e1494; 809/914/916 barras según el caso,
      sin barras sin resultado. La captura distingue MT, BT y AT y no sustituye los medidores.
- [x] T21. Reproducción del informe desde los seis flujos guardados. (RF-6, RF-7, RF-9, RF-12, RF-14)
      Hecho cuando: `informe_casos_guardados.py --plan PLAN --salida INFORME.docx` conserva los
      hashes, rechaza otro proyecto o cobertura incompleta y entrega Word, JSON y CSV sin huecos.
      Verificado el 2026-11-01 con Santa María, NA205, y pruebas de rechazo; se reutiliza el escritor.
- [x] T22. Planos comparables con problemas y obras en colores/tramas y leyenda. (RF-35)
      Hecho cuando: los tres estados del Word/PDF muestran la red, el punto del cliente,
      problemas de tensión/cargabilidad y las obras diferenciadas; prueba de render y revisión visual.
      Verificado el 2026-11-02: Word/PDF de Santa María con planos nativos y esquema de Cargas
      nuevas sin solución de flujo, identificado sin resultados eléctricos; 35 marcadores y
      anexos de cargas/obras. PDF de 14 páginas revisado, sin huecos.
- [x] T23. Variaciones separadas y demanda completa en la solución COPARA. (RF-36, RF-37)
      Hecho cuando: la relectura nativa verifica cargas previstas, demandas efectivas, variaciones
      de cada carga/obra y sus casos; ambos proyectados incluyen las mismas cargas del bloque.
      La conciliación explícita por fase conserva P/Q nominales y la proporción original entre
      fases; se registran las entradas anteriores y posteriores en las copias de escenarios.
      Verificado el 2026-11-02: 35 cargas nuevas y 35 variaciones de obra; 48,286 MW nominales
      y efectivos en Con proyecto. Las dos referencias proyectadas conservan iguales demandas
      nominales; Cargas nuevas sin obras no converge y no se atribuyen consumos efectivos.
- [x] T24. [DIgSILENT] COPARA con NA203–NA205 en límites y térmica fuera de servicio. (RF-38)
      Hecho cuando: equilibrado y desequilibrado convergen, toda la red cumple, se releen
      variaciones tras reabrir y el informe entrega los resultados sin confundir convergencia y aceptación.
      Aplicación febcc9b41837: informe nativo set_nueva_operacion_37f7270bd40c.json, aceptada y
      persistida, modelo idéntico después de la restitución. Motor anterior cerrado; comprobación
      independiente 0edd2ab893e0, set_nueva_operacion_87ace2d82986.json: ambos flujos conformes,
      0,964209–1,049746 p.u., máximo 98,5597 %, CT fuera de servicio, 35 cargas desde COPARA.
      Word/PDF: output/informes/Informe_Santa_Maria_NA205_COPARA_Verificado.*.
