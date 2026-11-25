# Pseudocódigo de la arquitectura

El recorrido de cada flujo principal del conversor, paso a paso, con la función real que lo hace (090:RF-23). Cada cita
`ruta.py::función` la comprueba `tests/test_arquitectura_c4_al_dia.py`: si la función se renombra o desaparece, la suite la
nombra. `tools/generar_c4.py --escribir` copia estos bloques a la página interactiva (090:RF-24); el de cada vista se abre al
elegirla.

Convenciones: `←` asigna, `para cada` recorre, `si … entonces` decide, `encolar(carril, …)` manda un trabajo a un carril de
`presentacion/web/jobs.py`. Los nombres de los alimentadores nunca son fijos: «cada alimentador» es cada uno de la entrega.

## conversion — De la fuente al DGS validado

```text
web: convertir(espacio, alimentadores)                      src/convertersmartgrid/presentacion/web/services.py::convert
  dataset ← cargar la fuente del espacio (TXT, MDB o VNR-GIS, una sola)
                                                            src/convertersmartgrid/presentacion/web/services.py::load_dataset
  informe ← completar lo que falta con el catálogo y anotar cada supuesto
                                                            src/convertersmartgrid/aplicacion/reglas.py::preparar_dataset
  seleccion ← alimentadores pedidos o todos                 src/convertersmartgrid/aplicacion/batch.py::convert_selection
  procesos ← min(pedidos, alimentadores)                    src/convertersmartgrid/aplicacion/batch.py::resolve_workers
  para cada alimentador, en paralelo y con el mismo resultado byte a byte:
      modelo ← FeederModel de la red de ese alimentador     src/convertersmartgrid/dominio/model.py::build_feeder_model
      modelo ← reglas comunes (fases, puentes, capacidades) src/convertersmartgrid/aplicacion/reglas.py::aplicar_reglas
      auditar que no falte ningún equipo                    src/convertersmartgrid/aplicacion/reglas.py::auditar_completitud
      escribir el DGS con su esquema versionado             src/convertersmartgrid/adaptadores/dgs.py::write_dgs
      validar el DGS escrito; si falla, no se publica       src/convertersmartgrid/adaptadores/validate.py::validate_dgs
  publicar de forma atómica en el espacio, con su manifiesto y sus huellas
```

## powerfactory — Del DGS a DIgSILENT

```text
web: importar(espacio, proyecto)
  encolar(powerfactory, guion)                              src/convertersmartgrid/presentacion/web/jobs.py::JobManager.submit
  el carril lanza el guion como proceso aparte, con plan JSON
                                                            src/convertersmartgrid/presentacion/web/jobs.py::JobContext.run_process
  guion: turno exclusivo de DIgSILENT en la máquina         src/convertersmartgrid/adaptadores/pf_arnes.py::conectar
  preflight consultivo con pandapower: avisa, no omite el DGS
                                                            src/convertersmartgrid/adaptadores/oraculo.py::validar
  importar los DGS fijados, guardar, reabrir y releer      src/convertersmartgrid/presentacion/web/services.py::_importar_dgs_fijados
                                                            tools/powerfactory_acceptance.py::main
  verificar el «Caso base» sin volver a importar: GPS, conectividad, capacidades
                                                            src/convertersmartgrid/presentacion/web/services.py::pf_verificar_base
  informe JSON → el espacio; la web lo presenta con lo que devolvió DIgSILENT
```

## calibracion — Calibración con la máxima coincidente

```text
web: calibrar(proyecto, máximas, medidor, periodo)
  plan ← máxima de cabecera de cada alimentador, fijas y escaladas
                                                            src/convertersmartgrid/presentacion/web/services.py::ajuste_plan
  ejecutar el plan guardado por su token                    src/convertersmartgrid/presentacion/web/services.py::ajuste_ejecutar
    arranque ← tensiones del oráculo antes de calibrar (motor abierto)
                                                            src/convertersmartgrid/adaptadores/oraculo_calibracion.py::arranque_con_oraculo
    encolar(powerfactory, ajuste de cabecera)               src/convertersmartgrid/presentacion/web/services.py::_correr_guion_ajuste
      guion: para cada alimentador
          escalar las cargas hasta la máxima medida, con Q desde el factor de potencia
          si no converge entonces leer el historial de DIgSILENT y cambiar el
              transformador que lo impide (spec 101), nunca aceptar «no converge»
                                                            tools/ajuste_cabecera_pf.py::main
    la verdad de la calibración es la que relee DIgSILENT   src/convertersmartgrid/presentacion/web/services.py::_verdad_de_la_calibracion
  guardar por proyecto y año de medición                    src/convertersmartgrid/presentacion/web/services.py::_guardar_calibracion
```

## con-proyecto — «Con proyecto»: cargas nuevas y obras

```text
web: con_proyecto(proyecto, alimentadores)                  src/convertersmartgrid/presentacion/web/services.py::con_proyecto_optimizar
  con las cargas nuevas de todos los alimentadores activas:
  en un hilo, el oráculo elige la obra de cada alimentador:
      espacio ← variantes de la escalera bancos → sección → terna (+ regulador)
      mejor ← búsqueda de la combinación más barata que cumple
                                                            src/convertersmartgrid/adaptadores/optimizacion_oraculo.py::buscar_combinacion
      frente ← costo frente a pérdidas y margen             src/convertersmartgrid/adaptadores/optimizacion_oraculo.py::frente_pareto
  mientras tanto, DIgSILENT confirma cada alimentador en cuanto el oráculo lo elige:
      para cada escalón de la escalera, de menor a mayor costo:
          si su obra más barata cuesta más que la ya confirmada entonces saltarlo
          medir en DIgSILENT; si cumple entonces parar en él
                                                            src/convertersmartgrid/presentacion/web/services.py::escalera_por_alimentador
                                                            tools/obras_pf.py::main
  guardar las alternativas que cumplen, con la elegida marcada, para el informe
```

## motores — Motores abiertos de flujo

```text
flujo abierto de una red de distribución (oráculo, calibración, gemelo):
  sistema ← red factorizada una sola vez                    src/convertersmartgrid/adaptadores/digital_twin/flujo.py::SistemaMallado
  motor ← pedido, o CSG_MOTOR_FLUJO, o «auto»
  si auto entonces Z-bus y, si no converge, Newton
  si el motor no está instalado entonces cede al siguiente; nada se bloquea por un motor
                                                            src/convertersmartgrid/adaptadores/digital_twin/motores_flujo.py::resolver_con
     Z-bus: punto fijo        Anderson: punto fijo acelerado
                                                            src/convertersmartgrid/adaptadores/digital_twin/motores_flujo.py::anderson
     Newton-Raphson con KLU                                 src/convertersmartgrid/adaptadores/digital_twin/motores_flujo.py::newton
     power-grid-model                                       src/convertersmartgrid/adaptadores/digital_twin/motores_flujo.py::pgm
     OpenDSS                                                src/convertersmartgrid/adaptadores/digital_twin/motores_flujo.py::dss
  devuelve la solución y qué motor la calculó

pandapower (preflight y VAD sobre el FeederModel; PIT sobre la red del área):
  red ← FeederModel en pandapower, por fases si las trae   src/convertersmartgrid/adaptadores/oraculo.py::red_pandapower
  red del área de transmisión, con tomas, SVC y compensación
                                                            src/convertersmartgrid/adaptadores/pit/red_pandapower.py::calcular
  qué motor calcula cada estudio y con qué alcance          src/convertersmartgrid/dominio/matriz_estudios.py::matriz
  en el plano: DIgSILENT si hay licencia y el proyecto está vinculado; si no, el abierto
                                                            src/convertersmartgrid/adaptadores/resultados_plano.py::elegir_motor
```

## pit — Plan de inversiones en transmisión

```text
web: PIT del área de demanda                                src/convertersmartgrid/presentacion/web/rutas_pit.py::crear_router
  red ← red del área desde su ámbito y su fuente            src/convertersmartgrid/aplicacion/pit/red_area.py::desde_ambito
  motor ← DIgSILENT si hay licencia y se pide; si no, el abierto (pandapower)
                                                            src/convertersmartgrid/adaptadores/pit/motores.py::elegir_motor
  si motor = DIgSILENT entonces encolar(powerfactory, guion del PIT)
                                                            tools/pit_pf.py::main
  si no, encolar(engine, flujo abierto)                     src/convertersmartgrid/adaptadores/pit/motores.py::ejecutar
  para cada año del horizonte:
      diagnóstico con los límites de la norma vigente       src/convertersmartgrid/adaptadores/pit/diagnostico.py::diagnosticar
  alternativas: aplicar cada cambio a la red y comparar     src/convertersmartgrid/adaptadores/pit/alternativas.py::evaluar
  expediente con la forma oficial y su cita normativa       src/convertersmartgrid/adaptadores/pit/expediente.py::emitir
```

## vad — Estudio de costos del VAD

```text
web: estudio VAD de la empresa                              src/convertersmartgrid/presentacion/web/vad_api.py::registrar_rutas_vad
  estudio ← crear con el perfil, el grupo, el periodo y los TdR
                                                            src/convertersmartgrid/aplicacion/vad/estudio.py::crear_estudio
  exigir que cada norma y recurso usado esté vigente        src/convertersmartgrid/aplicacion/vad/estudio.py::exigir_vigente
  encolar(engine, empresa modelo eficiente en cuatro etapas):
                                                            src/convertersmartgrid/aplicacion/vad/trabajo.py::armar_empresa_modelo
      cada sistema eléctrico, paso a paso: caracterización → dimensionamiento → costos → COyM
      dimensionar SED y tramos con el flujo de pandapower sobre la red óptima
                                                            src/convertersmartgrid/adaptadores/vad/dimensionamiento.py::dimensionar
  la red real y la red óptima se calculan por separado
  comprobar el estudio con su registro normativo            src/convertersmartgrid/aplicacion/vad/estudio.py::comprobar_estudio
```

## vnr-guia — VNR de la Guía 232-2017

```text
web: VNR del espacio (no es el adaptador de entrada VNR-GIS)
  encolar(engine, cálculo)                                  src/convertersmartgrid/presentacion/web/vnr_api.py::calcular
  modelo ← el modelo común del espacio, de la fuente que se cargó
  zonas ← mapa de densidad de carga (art. 22)              src/convertersmartgrid/aplicacion/vad/vnr_guia.py::zonificar
  cambio de tecnología de cada tramo (Anexo 6)              src/convertersmartgrid/aplicacion/vad/vnr_guia.py::equivalencia
  adaptar la red MT del sector (art. 28)                    src/convertersmartgrid/aplicacion/vad/vnr_guia.py::adaptar_red_mt
  VNR adaptado del modelo, con los costos del SICODI        src/convertersmartgrid/adaptadores/vad/vnr_estudio.py::estudio_vnr
  formatos del VNR para el VAD
```

## carriles — Colas de trabajo por carril

```text
web: cada petición larga es un trabajo; nunca se calcula dentro de la petición
  encolar(carril, trabajo)                                  src/convertersmartgrid/presentacion/web/jobs.py::JobManager.submit
  un hilo por carril, en serie dentro del carril            src/convertersmartgrid/presentacion/web/jobs.py::JobManager._worker
     engine        conversión, flujo abierto, PIT y VAD sin DIgSILENT, VNR de la Guía, plano
     powerfactory  guiones *_pf.py, uno a la vez en la máquina
     asistente     solo espera: sus pasos encolan en engine o powerfactory
     control       solo cancela, para parar lo que corre con el asistente ocupado
     correo        envío de informes; espera a la red, no al motor ni a DIgSILENT
     red           búsqueda de la publicación oficial del VNR-GIS; espera a la red
  correr, informar avance por WebSocket y dejar el diario
                                                            src/convertersmartgrid/presentacion/web/jobs.py::JobManager._run
  cancelar: pide parar; si aún espera, queda cancelado ya   src/convertersmartgrid/presentacion/web/jobs.py::JobManager.cancel
```

## asistente — Asistente de órdenes

```text
operador escribe una orden en la web                        src/convertersmartgrid/presentacion/web/services.py::asistente_orden
  interpretación ← tarea y datos (codificador, Transformer, LLM local; «ninguna» si es charla)
                                                            src/convertersmartgrid/aplicacion/asistente/interprete.py::interpretar
  plan ← pasos de la tarea con los datos resueltos del espacio
                                                            src/convertersmartgrid/aplicacion/asistente/plan.py::resolver
                                                            src/convertersmartgrid/aplicacion/asistente/ejecutor.py::pasos
  mostrar el plan; nada se ejecuta sin la confirmación del operador
  si confirma entonces encolar(asistente, ejecutar), que llama a la API existente paso a paso
                                                            src/convertersmartgrid/presentacion/web/services.py::asistente_ejecutar
  si un paso falla entonces revisar el error y proponer la corrección
                                                            src/convertersmartgrid/aplicacion/asistente/ejecutor.py::revisar_tras_error
```
