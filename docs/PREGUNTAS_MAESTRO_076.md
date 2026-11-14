# Preguntas del maestro marcadas como correctas (spec 076)

Generado con `tools/preguntas_entregables.py corpus`. No editar a mano.

Decisión del usuario del 2026-11-04. Escritas y marcadas por el maestro contra el código de la revisión `10fd3e1d`: no son órdenes del operador ni cuentan como humanas. Si una contradice al código, manda el código.

## arquitectura-001

Pregunta: ¿En qué dos mitades se divide el sistema?

Respuesta: El motor en Python sin DIgSILENT, y los guiones de PowerFactory; se comunican solo por ficheros.

Fuentes: docs/ARQUITECTURA.md:11, docs/ARQUITECTURA.md:14.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-001-p1

Pregunta: cuales son las partes del conversor

Respuesta: El motor en Python sin DIgSILENT, y los guiones de PowerFactory; se comunican solo por ficheros.

Fuentes: docs/ARQUITECTURA.md:11, docs/ARQUITECTURA.md:14.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-002

Pregunta: la web calcula algo

Respuesta: No: web/services.py llama al motor o lanza un guion.

Fuentes: docs/ARQUITECTURA.md:58.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-003

Pregunta: ¿Cómo se comprueban las capas?

Respuesta: Cada módulo declara su capa en pyproject.toml y una prueba falla ante una violación nueva.

Fuentes: docs/ARQUITECTURA.md:45, pyproject.toml:109.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-005

Pregunta: ¿Cuántos carriles de trabajos tiene la web?

Respuesta: Cuatro en el código: motor, powerfactory, asistente y control.

Fuentes: src/convertersmartgrid/web/jobs.py:40.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-007

Pregunta: ¿Qué es el arnés de DIgSILENT?

Respuesta: pf_arnes.conectar da el turno exclusivo a guiones y sondas.

Fuentes: docs/ARQUITECTURA.md:120.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-008

Pregunta: el front y la api como no se desfasan

Respuesta: Un guion genera el esquema del front y una prueba detecta divergencias.

Fuentes: docs/ARQUITECTURA.md:122.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-009

Pregunta: ¿Dónde van las convenciones de una empresa?

Respuesta: En un perfil de empresa, nunca en el código ni como valor por defecto.

Fuentes: docs/constitution.md:50.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-011

Pregunta: ¿Quién ejecuta las escrituras del asistente?

Respuesta: Solo el rol operador ejecuta, y toda escritura espera confirmación.

Fuentes: docs/ARQUITECTURA.md:161, src/convertersmartgrid/asistente/equipo.py:62.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-012

Pregunta: los roles fuentes fisica coste riesgo son agentes distintos?

Respuesta: No: son el mismo modelo de Ollama con otro prompt de sistema y su revisión es documental.

Fuentes: docs/ARQUITECTURA.md:187.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-019

Pregunta: ¿Ya hay paquetes por capa y módulos enchufables?

Respuesta: Aún no: la spec de capas está aprobada con tareas pendientes.

Fuentes: docs/ARQUITECTURA.md:44.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-020

Pregunta: vnr_etl q es

Respuesta: Un paquete aparte con su propia arquitectura en capas, que exporta al mismo escritor de DGS.

Fuentes: docs/ARQUITECTURA.md:60.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-022

Pregunta: el pronostico multihorizonte tiene codigo?

Respuesta: Sí: está implementado en el gemelo; la arquitectura dice que es solo especificado y está desactualizada.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:28, src/convertersmartgrid/digital_twin/pronostico.py:328.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-024

Pregunta: cual es mejor arquitectura microservicios o esta

Respuesta: No hay una evaluación de arquitecturas alternativas en el proyecto.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## arquitectura-026

Pregunta: cuanta ram necesita el servidor

Respuesta: No consta un requisito de memoria del servidor en las specs.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-001

Pregunta: ¿Qué tipos de análisis ofrece la calibración?

Respuesta: Tres que no se mezclan: alimentadores, SET por la máxima de su barra y sistema eléctrico.

Fuentes: specs/028-escaneo-del-alimentador/spec.md:108.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-001-p1

Pregunta: tipos de analisis en la calibracion?

Respuesta: Tres que no se mezclan: alimentadores, SET por la máxima de su barra y sistema eléctrico.

Fuentes: specs/028-escaneo-del-alimentador/spec.md:108.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-004

Pregunta: por set q maxima usa

Respuesta: La máxima, registro a registro, de la suma de los medidores de la barra de la SET, y su fecha y hora para todos sus alimentadores.

Fuentes: specs/022-red-unida-por-zonal-y-set/spec.md:144, specs/022-red-unida-por-zonal-y-set/spec.md:147.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-007

Pregunta: ¿Calibra uno por uno los alimentadores del proyecto?

Respuesta: No: los calibra todos en una sola ejecución, en los mismos flujos de «Sin proyecto».

Fuentes: specs/021-maniobras-y-sed-en-el-diagrama/spec.md:212.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-010

Pregunta: como pone a los clientes fijos

Respuesta: Con «máximo del mes» o «coincidente con la cabecera», el criterio elegido al cruzar.

Fuentes: specs/039-fijas-maximo-del-mes-o-coincidentes/spec.md:21.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-011

Pregunta: ¿Cómo reparte a las SED escaladas?

Respuesta: Con repartos aleatorios de utilización y deja en DIgSILENT el P50, reproducible con la semilla guardada.

Fuentes: specs/041-reparto-probabilistico-de-las-escaladas/spec.md:23, specs/041-reparto-probabilistico-de-las-escaladas/spec.md:37, specs/041-reparto-probabilistico-de-las-escaladas/spec.md:42.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-012

Pregunta: cuadra la Q tambien?

Respuesta: Solo la P en la primera calibración; P y Q en cada recalibración.

Fuentes: specs/035-fijas-de-la-tabla-q-con-bancos-y-unidades/spec.md:116.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-013

Pregunta: ¿Y si la medida supera lo que da la red?

Respuesta: No calibra ese alimentador, lo dice con las dos cifras y calibra los demás.

Fuentes: specs/022-red-unida-por-zonal-y-set/spec.md:200.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-015

Pregunta: ¿Pone bancos que falten por defecto?

Respuesta: No: la casilla «Poner los bancos que falten» empieza apagada en la web.

Fuentes: frontend/src/components/AjusteCabecera.tsx:43, specs/021-maniobras-y-sed-en-el-diagrama/spec.md:243.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-016

Pregunta: calibro con otro año q pasa

Respuesta: Crea «Sin proyecto <año>» como copia del «Caso base» verificado, con su propio escenario.

Fuentes: specs/025-calibracion-por-anio/spec.md:93, specs/025-calibracion-por-anio/spec.md:96.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-018

Pregunta: alimentador sin medidor en un sistema

Respuesta: Queda con la demanda del archivo en los mismos flujos, y lo dice.

Fuentes: specs/022-red-unida-por-zonal-y-set/spec.md:195.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## calibracion_alcance-019

Pregunta: ¿Cuál fue la máxima de ALIM-A en el mes pasado?

Respuesta: No lo sé: hay que buscarla con la medición de cabecera del espacio.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-001

Pregunta: ¿Para qué sirve el catálogo de parámetros?

Respuesta: Lista los parámetros de cada elemento que usan los alimentadores: lo que dice el modelo, la ficha, cuánto se separan y de dónde sale.

Fuentes: src/convertersmartgrid/catalog.py:10.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-001-p1

Pregunta: pa q es el catalogo de parametros

Respuesta: Lista los parámetros de cada elemento que usan los alimentadores: lo que dice el modelo, la ficha, cuánto se separan y de dónde sale.

Fuentes: src/convertersmartgrid/catalog.py:10.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-006

Pregunta: como deduce un conductor de otra seccion

Respuesta: Toma la sección más cercana de su familia: R y R0 por la relación de secciones; X, X0 y B1 de la referencia.

Fuentes: specs/053-catalogo-de-fichas-que-crece/spec.md:30.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-007

Pregunta: ¿Y si es AAAC?

Respuesta: Toma la R de la ficha universal del AAAC y el resto de su familia.

Fuentes: specs/053-catalogo-de-fichas-que-crece/spec.md:34.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-008

Pregunta: si no se puede deducir

Respuesta: Añade la fila sin valores, pendiente de ficha, y lo dice; nunca un tramo con impedancia cero sin aviso.

Fuentes: specs/053-catalogo-de-fichas-que-crece/spec.md:40.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-011

Pregunta: ¿Un conductor sin R1 ni X1 en la fuente?

Respuesta: Se trata como falta y se completa con el catálogo de fichas en la misma carga.

Fuentes: specs/053-catalogo-de-fichas-que-crece/spec.md:49.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-016

Pregunta: q marca de conductor me conviene comprar

Respuesta: No hay recomendación de compra en el conversor.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## catalogo_parametros-017

Pregunta: ¿La ficha del fabricante X ya está cargada?

Respuesta: No lo sé: el catálogo dice el estado de cada fila, no de un fabricante.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-001

Pregunta: ¿El DGS sale igual con uno o con varios procesos?

Respuesta: Sí sale igual: misma entrada, perfil y alias dan el mismo DGS byte a byte con uno o con varios procesos.

Fuentes: docs/constitution.md:10.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-002

Pregunta: si se cancela queda un dgs a medias?

Respuesta: No: la publicación es atómica y el manifiesto del lote se escribe siempre, también al cancelar.

Fuentes: docs/constitution.md:23, src/convertersmartgrid/batch.py:4.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-003

Pregunta: ¿Cuántos procesos usa a lo sumo en automático?

Respuesta: Cuatro como máximo, y nunca más que alimentadores.

Fuentes: src/convertersmartgrid/batch.py:348.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-004

Pregunta: si un alimentador falla se cae el lote?

Respuesta: No: un alimentador que falla no invalida a los demás.

Fuentes: docs/constitution.md:24.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-005

Pregunta: ¿Qué deja cada alimentador además del .dgs?

Respuesta: Sus metadatos, la validación en JSON y en texto y, con geografía, su geografía.

Fuentes: src/convertersmartgrid/batch.py:263.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-011

Pregunta: ¿La potencia de los transformadores se corrige en el DGS?

Respuesta: No: se escribe tal como la trae la entrada, aunque la carga la supere.

Fuentes: specs/032-caso-base-original-fichas-en-sin-proyecto/spec.md:42.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-013

Pregunta: ¿Lleva el trazado GPS de las líneas?

Respuesta: Sí, con georreferenciación; sin ella las líneas van sin trazado ni tabla de trazados.

Fuentes: specs/010-trazado-gps-de-las-lineas/spec.md:28, specs/010-trazado-gps-de-las-lineas/spec.md:33.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## dgs_manifiesto-018

Pregunta: ¿El DGS lo abre otra versión de PowerFactory sin problema?

Respuesta: No está comprobado: el conversor se prueba con PowerFactory 2024.

Fuentes: docs/constitution.md:29.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-001

Pregunta: ¿En qué orden prueba las obras la escalera?

Respuesta: Bancos de condensadores, cambio de sección, terna y, al final, regulador.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:92, src/convertersmartgrid/escalera_optima.py:29.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-001-p1

Pregunta: orden de la escalera de obras

Respuesta: Bancos de condensadores, cambio de sección, terna y, al final, regulador.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:92, src/convertersmartgrid/escalera_optima.py:29.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-002

Pregunta: cual elige si varias cumplen

Respuesta: La del primer escalón que deja la red en límites y, dentro de él, la de menor costo anual; no sube si el anterior cumple.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:95.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-003

Pregunta: ¿Siempre prueba regulador?

Respuesta: Entra al final por defecto; el perfil puede quitarlo con escalera.con_regulador en falso.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:111.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-005

Pregunta: ¿Qué tramos cambia de sección?

Respuesta: Solo los de corriente nominal menor que la del conductor nuevo; deja los de igual o mayor sección.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:128.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-006

Pregunta: donde prueba seccion y terna

Respuesta: Sobre el camino eléctrico de la cabecera a cada carga nueva, con su banco justo aguas arriba de la carga.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:141.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-009

Pregunta: ¿Y si cumple con la máxima pero no en los sorteos?

Respuesta: La elige por el orden de prioridad, avisa que los sorteos no la confirmaron y no pasa a otras obras ni a la SET nueva.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:146.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-010

Pregunta: pone obras en sin proyecto?

Respuesta: No: en «Sin proyecto» solo se calibra; las obras van solo en «Con proyecto».

Fuentes: specs/025-calibracion-por-anio/spec.md:212.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-011

Pregunta: ¿Deja creadas las variantes que no eligió?

Respuesta: No: aplica solo las obras de la variante elegida, cada una en su variación.

Fuentes: specs/025-calibracion-por-anio/spec.md:246.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## escalera_obras-013

Pregunta: ¿Vuelve a medir una evaluación que ya hizo?

Respuesta: Reutiliza la del mismo plan terminada sin cancelar en las últimas 24 h, y lo dice.

Fuentes: specs/025-calibracion-por-anio/spec.md:292, src/convertersmartgrid/web/services.py:6198.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-001

Pregunta: ¿Qué estudios se ofrecen en la web?

Respuesta: Flujo equilibrado y desequilibrado, N-1, troncal, punto de apertura, perfil de tensión y balance de fases, y los de confiabilidad y capacidad con sus datos.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:172, src/convertersmartgrid/estudios_pf.py:31.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-001-p1

Pregunta: q estudios hay

Respuesta: Flujo equilibrado y desequilibrado, N-1, troncal, punto de apertura, perfil de tensión y balance de fases, y los de confiabilidad y capacidad con sus datos.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:172, src/convertersmartgrid/estudios_pf.py:31.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-002

Pregunta: con q modulo corre el flujo

Respuesta: Con ComLdf, el flujo de carga nativo de DIgSILENT.

Fuentes: src/convertersmartgrid/studies.py:218.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-003

Pregunta: ¿Qué necesita el flujo desequilibrado?

Respuesta: El reparto real de las cargas por fase, que el conversor escribe.

Fuentes: src/convertersmartgrid/studies.py:204.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-005

Pregunta: ¿Con qué módulo va el N-1?

Respuesta: ComSimoutage, marcado como pesado.

Fuentes: src/convertersmartgrid/studies.py:233.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-007

Pregunta: ¿Y la confiabilidad?

Respuesta: ComRel3, con tasas de falla, clientes por SED y tiempos de maniobra.

Fuentes: src/convertersmartgrid/studies.py:240.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-008

Pregunta: confiabilidad sin tasas de falla q da

Respuesta: ComRel3 correría igual y daría índices en cero: por eso sin el libro de la empresa no se ofrece.

Fuentes: src/convertersmartgrid/studies.py:122.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-009

Pregunta: ¿Qué módulo ubica reconectadores?

Respuesta: ComOpri, para ver dónde un reconectador baja más la ENS.

Fuentes: src/convertersmartgrid/studies.py:247.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-010

Pregunta: capacidad de alojamiento con q

Respuesta: ComHostcap, generación y carga nueva que admite cada nodo.

Fuentes: src/convertersmartgrid/studies.py:254.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-011

Pregunta: ¿Qué usa la ubicación de condensadores?

Respuesta: ComCapo, que necesita precios y el costo de la energía.

Fuentes: src/convertersmartgrid/studies.py:287.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-012

Pregunta: troncal con q modulo

Respuesta: ComBbone, el cálculo de troncal.

Fuentes: src/convertersmartgrid/studies.py:275.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-013

Pregunta: ¿Y el punto de apertura óptimo?

Respuesta: ComTieopt, para ver dónde conviene abrir para reducir pérdidas.

Fuentes: src/convertersmartgrid/studies.py:280.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-014

Pregunta: balance de fases y perfil de tension

Respuesta: ComBalance y ComVoltplan.

Fuentes: src/convertersmartgrid/studies.py:294, src/convertersmartgrid/studies.py:301.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-015

Pregunta: ¿Por qué no se ofrece la cuasi-dinámica?

Respuesta: Faltan los perfiles de carga horarios: no tiene nada que barrer.

Fuentes: src/convertersmartgrid/studies.py:155.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-016

Pregunta: flujo optimo esta?

Respuesta: No se ofrece: está fuera de esta iteración.

Fuentes: src/convertersmartgrid/studies.py:308, src/convertersmartgrid/estudios_pf.py:81.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-018

Pregunta: armonicos se puede

Respuesta: No: faltan los espectros armónicos de las cargas.

Fuentes: src/convertersmartgrid/studies.py:334, src/convertersmartgrid/studies.py:200.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-021

Pregunta: ¿Con qué límites se juzgan los resultados?

Respuesta: Con los del perfil y, sin perfil, ±5 % y 100 %; el informe dice de dónde salen.

Fuentes: src/convertersmartgrid/estudios_pf.py:154.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-022

Pregunta: evaluacion tecnico economica

Respuesta: ComTececo, el VAN de la estrategia de expansión; necesita precios, costo de energía, etapas y proyección.

Fuentes: src/convertersmartgrid/studies.py:315.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-024

Pregunta: ¿Cuánto tarda el N-1 en mi sistema?

Respuesta: No lo sé: depende del tamaño de la red; solo se sabe que es un estudio pesado.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-025

Pregunta: conviene hacer estudios de estabilidad

Respuesta: No hay estudios de estabilidad dinámica en el catálogo del conversor.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios-027

Pregunta: resultado del flujo de ALIM-C

Respuesta: No lo sé: hay que correr el estudio en su proyecto.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-002

Pregunta: en q casos corre los estudios

Respuesta: Primero en «Sin proyecto», después en «Cargas nuevas» si hay cargas y al final en «Con proyecto» si hay cargas u obras.

Fuentes: specs/037-cargas-nuevas-en-estudios-web/spec.md:17.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-004

Pregunta: como se ve una violacion q sale solo con proyecto

Respuesta: Se marca como nueva: aparece en «Con proyecto» y no en «Sin proyecto».

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:203, src/convertersmartgrid/estudios_pf.py:50.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-006

Pregunta: cuanto tiempo puede tardar un estudio

Respuesta: Tiene un límite por estudio, 1800 s por defecto, que el operador puede cambiar; si lo supera se informa no terminado y sigue.

Fuentes: src/convertersmartgrid/web/services.py:4524, specs/011-estudios-sobre-la-red-calibrada/spec.md:221, specs/011-estudios-sobre-la-red-calibrada/spec.md:223.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-008

Pregunta: confiabilidad sin libro de empresa

Respuesta: No se puede: sin libro cargado lista la confiabilidad con el dato que le falta, sin ejecutarla.

Fuentes: specs/012-confiabilidad-y-capacidad-de-la-red/spec.md:128.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-011

Pregunta: ¿Y si la licencia no tiene el módulo?

Respuesta: Lo lista como no disponible con el nombre del módulo y no deja ejecutarlo.

Fuentes: specs/012-confiabilidad-y-capacidad-de-la-red/spec.md:78, src/convertersmartgrid/estudios_pf.py:74.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-012

Pregunta: curvas pv para q son

Respuesta: Para el margen de cada alimentador hasta el colapso de tensión.

Fuentes: src/convertersmartgrid/studies.py:262.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-013

Pregunta: ¿Estudia un alimentador cuyo ajuste no cuadró?

Respuesta: Sí: lo estudia y lo avisa con su error en la cabecera.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:149.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-014

Pregunta: los limites se pueden cambiar

Respuesta: Sí: salen del perfil y el operador puede cambiarlos antes de ejecutar.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:205.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-017

Pregunta: el n-1 vale para la red de transmision?

Respuesta: No consta: el N-1 de la web es de la troncal de media tensión de los alimentadores marcados.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## estudios_resultados-018

Pregunta: ¿Qué valor de SAIFI exige el regulador este año?

Respuesta: No lo sé: la meta regulatoria no está en el código.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-001

Pregunta: ¿Qué hace el botón del informe de la carga nueva?

Respuesta: Prepara los casos, ejecuta los flujos y escribe la evaluación de conexión en un solo trabajo, sin exigir antes el paso de estudios.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:29, src/convertersmartgrid/web/services.py:7743.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-001-p1

Pregunta: el de factibilidad hace todo de una?

Respuesta: Prepara los casos, ejecuta los flujos y escribe la evaluación de conexión en un solo trabajo, sin exigir antes el paso de estudios.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:29, src/convertersmartgrid/web/services.py:7743.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-003

Pregunta: ¿Qué flujos corre y en qué casos?

Respuesta: El equilibrado y el desequilibrado en «Sin proyecto», «Cargas nuevas» y «Con proyecto».

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:47, src/convertersmartgrid/web/services.py:7733.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-004

Pregunta: cuando dice que es factible sin obras

Respuesta: Cuando «Sin proyecto» y «Cargas nuevas» cumplen los límites de tensión y cargabilidad; entonces no propone ninguna obra.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:51, src/convertersmartgrid/informes.py:588.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-009

Pregunta: el punto de diseño cual es?

Respuesta: El nodo de media tensión donde se conecta la carga, con su tensión en el flujo de «Con proyecto».

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:227, src/convertersmartgrid/web/services.py:7615.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-010

Pregunta: ¿Cómo calcula el factor de pérdidas?

Respuesta: Como 0,3·FC + 0,7·FC², con el factor de carga.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:231.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-010-p1

Pregunta: formula del factor de perdidas porfa

Respuesta: Como 0,3·FC + 0,7·FC², con el factor de carga.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:231.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-011

Pregunta: de donde sale el factor de carga

Respuesta: De la medición de cabecera del mes de análisis; si no la hay, se pide en el formulario.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:239, specs/017-informes-de-estudio-y-factibilidad/spec.md:241.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-013

Pregunta: el trafo de la set es obligatorio en la factibilidad?

Respuesta: No: si no se calculó queda fuera del informe, sin contarlo como hueco ni impedir la conclusión.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:182, src/convertersmartgrid/web/services.py:7683.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-014

Pregunta: q pasa si el pdf del solicitante es de otro alimentador

Respuesta: Lo avisa antes de generar.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:85.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-015

Pregunta: ¿Cómo trata a las otras cargas que esperan conexión?

Respuesta: Dice cuántas son, cuántos kW suman por alimentador y qué da el flujo con todas sin obras; solo afirma lo que midió.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:205.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-016

Pregunta: cambie de carga y se quedaron los datos de la otra

Respuesta: Al cambiar la carga elegida, la web vacía la solicitud, el punto de diseño y lo leído de los PDF de la anterior.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:186.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-017

Pregunta: ¿Ya está aprobada la factibilidad de CLIENTE-X?

Respuesta: No lo sé: el conversor no registra aprobaciones de la distribuidora.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## factibilidad_conexion-018

Pregunta: cuantos dias tiene la empresa pa responder la factibilidad

Respuesta: Ese plazo no está en el código ni en las specs: es de la norma de la distribuidora.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-001

Pregunta: ¿Cuáles son los pasos de la fuente al DGS?

Respuesta: Lectura, selección, reconstrucción opcional, reglas, modelo estricto, oráculo, escritura, validación y publicación atómica.

Fuentes: docs/ARQUITECTURA.md:67, docs/ARQUITECTURA.md:85.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-001-p1

Pregunta: de la fuente al dgs q pasos hay

Respuesta: Lectura, selección, reconstrucción opcional, reglas, modelo estricto, oráculo, escritura, validación y publicación atómica.

Fuentes: docs/ARQUITECTURA.md:67, docs/ARQUITECTURA.md:85.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-002

Pregunta: puedo subir un mdb en la casilla de los txt?

Respuesta: No: cada fichero va en la entrada de su fuente; uno de otra fuente no se asigna.

Fuentes: specs/059-fuente-por-lo-que-se-carga/spec.md:29.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-003

Pregunta: ¿Cómo reconoce qué TXT es RED o CARGA?

Respuesta: Por su contenido y no por su nombre; si no encaja, dice qué es y qué se esperaba.

Fuentes: specs/034-motor-base-y-contrato-de-fuentes/spec.md:37.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-004

Pregunta: el txt viene en dos formas

Respuesta: Lee la disposición reducida y la completa, cada tabla una sola vez.

Fuentes: specs/034-motor-base-y-contrato-de-fuentes/spec.md:35.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-005

Pregunta: ¿Qué lee de la vía Access?

Respuesta: La base Access de CYMDIST y, como filtro opcional, su estudio.

Fuentes: specs/034-motor-base-y-contrato-de-fuentes/spec.md:39.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-006

Pregunta: vnr con coordenadas en grados

Respuesta: Se rechaza con el nombre del CRS: VNR-GIS se lee con un CRS proyectado en metros.

Fuentes: specs/034-motor-base-y-contrato-de-fuentes/spec.md:41.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-008

Pregunta: q hace la reconstruccion

Respuesta: Trabaja sobre una copia: valor original, catálogo exacto, de fabricante y global, y anota cada supuesto; nada bloquea salvo una red vacía.

Fuentes: docs/ARQUITECTURA.md:76.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-010

Pregunta: al importar q caso se verifica

Respuesta: El «Caso base», con todas sus comprobaciones, al aceptar el proyecto.

Fuentes: specs/015-caso-base-verificado/spec.md:58.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-011

Pregunta: ¿Cómo nace «Sin proyecto»?

Respuesta: Como copia del «Caso base», solo después de que esté verificado.

Fuentes: specs/015-caso-base-verificado/spec.md:95.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-014

Pregunta: el caso cargas nuevas q es

Respuesta: Una copia de «Sin proyecto» con las cargas nuevas activadas una a una, dejando solo las que convergen y sin obras.

Fuentes: specs/025-calibracion-por-anio/spec.md:324, specs/025-calibracion-por-anio/spec.md:331, specs/025-calibracion-por-anio/spec.md:333.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-015

Pregunta: ¿Se calibra en «Caso base» o en «Con proyecto»?

Respuesta: En ninguno de los dos: el ajuste a la máxima es de «Sin proyecto».

Fuentes: specs/014-calibracion-en-sin-proyecto/spec.md:65.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-016

Pregunta: cada carga nueva va en su variacion?

Respuesta: Sí: una variación nueva por cada carga nueva.

Fuentes: specs/007-cargas-nuevas-sobre-el-ajuste/spec.md:74.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-020

Pregunta: recalibrar reconvierte?

Respuesta: No: recalibra «Sin proyecto» sobre el proyecto ya importado, sin reconvertir ni volver a importar.

Fuentes: specs/028-escaneo-del-alimentador/spec.md:79.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-021

Pregunta: ¿Cada carga de una fuente se custodia?

Respuesta: Sí: cada carga es una ejecución inmutable y no se mezclan fuentes.

Fuentes: docs/ARQUITECTURA.md:70.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-022

Pregunta: el dgs de otra fuente puede ir a powerfactory

Respuesta: No: PowerFactory solo consume el DGS de la ejecución fuente activa.

Fuentes: specs/034-motor-base-y-contrato-de-fuentes/spec.md:88.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-023

Pregunta: ¿Qué fuente es mejor, la TXT o la base Access?

Respuesta: No se comparan: cada fuente se carga, se convierte y se prueba por su cuenta.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-024

Pregunta: cual es la fecha de la ultima entrega de mi empresa

Respuesta: No lo sé: las entregas de cada empresa no están en el repositorio.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## flujo_conversor-027

Pregunta: ¿Quién convierte mejor, el CLI o la web?

Respuesta: No hay diferencia que medir: los dos usan la misma vía de conversión.

Fuentes: specs/001-reorganizacion/spec.md:36.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-001

Pregunta: ¿Cómo salen los formatos del PIDE?

Respuesta: En un libro Excel, una hoja por formato del 01 al 15, más una hoja que reúne los huecos.

Fuentes: src/convertersmartgrid/pide.py:311, src/convertersmartgrid/web/services.py:4700.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-001-p1

Pregunta: los formatos f01 a f15 en q archivo

Respuesta: En un libro Excel, una hoja por formato del 01 al 15, más una hoja que reúne los huecos.

Fuentes: src/convertersmartgrid/pide.py:311, src/convertersmartgrid/web/services.py:4700.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-002

Pregunta: un formato sin datos sale en blanco?

Respuesta: No: queda con su encabezado y el motivo de lo que falta, para que se vea el hueco.

Fuentes: src/convertersmartgrid/pide.py:314, specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:67.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-005

Pregunta: ¿Y el F02 de metrados?

Respuesta: De la red cargada en el espacio; sin red, queda como hueco.

Fuentes: src/convertersmartgrid/formatos_pide.py:20.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-006

Pregunta: el F04 mide la baja hasta el ultimo cliente?

Respuesta: No: mide la barra de baja de cada SED; la caída en la red de baja no está modelada y lo dice.

Fuentes: src/convertersmartgrid/formatos_pide.py:75.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-008

Pregunta: el F06 trae N y D de la NTCSE?

Respuesta: No: el estudio de confiabilidad da SAIFI y SAIDI, no el número y la duración de la NTCSE.

Fuentes: src/convertersmartgrid/formatos_pide.py:54.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-009

Pregunta: ¿Cuándo quedan vacíos F07 a F09?

Respuesta: Cuando el diagnóstico no encontró problemas que pidan obras.

Fuentes: src/convertersmartgrid/formatos_pide.py:25.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-010

Pregunta: y F10 a F15

Respuesta: Quedan vacíos cuando ninguna obra quedó en la cartera.

Fuentes: src/convertersmartgrid/formatos_pide.py:28.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-011

Pregunta: ¿Por qué no sale el desglose LP, RP, SED en el F13?

Respuesta: Porque el costo de la obra viene en un solo total: falta su desglose por componentes.

Fuentes: src/convertersmartgrid/formatos_pide.py:66.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-016

Pregunta: el regulador acepta los formatos en este excel tal cual?

Respuesta: No consta: el conversor no comprueba la aceptación del regulador.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## formatos_pide-017

Pregunta: ¿Hay que llenar el F05 a mano si la empresa no tiene medición?

Respuesta: No hay una regla para llenarlo a mano: el conversor deja el hueco con su motivo y no indica cómo completarlo.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-001

Pregunta: ¿De dónde saca el informe de estudio el estado actual y el proyectado?

Respuesta: El estado actual es el último flujo de «Sin proyecto» y el proyectado el de «Con proyecto» con sus obras activas.

Fuentes: src/convertersmartgrid/web/services.py:6911, specs/017-informes-de-estudio-y-factibilidad/spec.md:137, specs/017-informes-de-estudio-y-factibilidad/spec.md:139.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-001-p1

Pregunta: oe el informe de estudio q casos usa pe

Respuesta: El estado actual es el último flujo de «Sin proyecto» y el proyectado el de «Con proyecto» con sus obras activas.

Fuentes: src/convertersmartgrid/web/services.py:6911, specs/017-informes-de-estudio-y-factibilidad/spec.md:137, specs/017-informes-de-estudio-y-factibilidad/spec.md:139.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-002

Pregunta: el informe de estudio corre digsilent?

Respuesta: No: se arma con lo que guardaron los estudios al ejecutar los casos desde la web, sin otra ejecución de DIgSILENT.

Fuentes: src/convertersmartgrid/web/services.py:6858.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-003

Pregunta: q necesito antes de sacar el informe de estudio

Respuesta: Un flujo de «Sin proyecto» del alimentador hecho en el paso de estudios; sin él la web pide ejecutarlo antes.

Fuentes: src/convertersmartgrid/web/services.py:6942.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-004

Pregunta: ¿Puedo pedir un informe de estudio con varios alimentadores juntos?

Respuesta: No: hoy cada informe de estudio es de un alimentador, aunque la spec diga uno o varios; manda el código.

Fuentes: src/convertersmartgrid/web/services.py:6926, specs/017-informes-de-estudio-y-factibilidad/spec.md:137.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-006

Pregunta: ¿En qué orden evalúa las etapas de obras el informe de estudio?

Respuesta: Bancos existentes, bancos propuestos, reguladores, cambio de conductor, refuerzo de la red y migración, cada una sumada a las anteriores.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:143, specs/017-informes-de-estudio-y-factibilidad/spec.md:409.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-006-p1

Pregunta: orden de las etapas del estudio electrico?

Respuesta: Bancos existentes, bancos propuestos, reguladores, cambio de conductor, refuerzo de la red y migración, cada una sumada a las anteriores.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:143, specs/017-informes-de-estudio-y-factibilidad/spec.md:409.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-007

Pregunta: ¿Cuál alternativa recomienda el informe de estudio?

Respuesta: La primera alternativa que cumple la banda y el umbral, con una tabla que compara el estado actual con cada alternativa.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:439.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-008

Pregunta: como presenta las obras cuando hay de varias etapas

Respuesta: Como alternativas numeradas, una por etapa con obras, cada una sumada a las anteriores.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:421.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-011

Pregunta: si no converge sin proyecto sale igual el informe?

Respuesta: Sí: lo dice en la sección de ese caso, sin valores, y genera el resto.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:125, specs/017-informes-de-estudio-y-factibilidad/spec.md:371.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-012

Pregunta: ¿De dónde salen los clientes fijos que aparecen en el estado actual?

Respuesta: De la última calibración del alimentador, cada fijo con su factor de potencia real y el corregido con que se escribió.

Fuentes: specs/015-caso-base-verificado/spec.md:245, src/convertersmartgrid/web/services.py:6895.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-015

Pregunta: el word del estudio dice sin proyecto y con proyecto?

Respuesta: No: el texto no nombra los casos de DIgSILENT ni el orden en que se evaluaron las obras.

Fuentes: src/convertersmartgrid/informes.py:604.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-016

Pregunta: sin modelo de informe en el perfil q pasa

Respuesta: No genera ese tipo de informe y dice qué clave del perfil falta.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:83, src/convertersmartgrid/informes.py:156.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## informe_estudio-018

Pregunta: q decia el informe de estudio de PROYECTO-X del año pasado

Respuesta: No lo sé: los informes generados quedan en la salida de cada espacio, no en el conjunto de preguntas.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-001

Pregunta: ¿Siempre sale el libro Excel con el informe?

Respuesta: No: solo si el perfil de la empresa declara el libro del informe; si no, no hay libro ni se cuenta como hueco.

Fuentes: specs/066-libro-de-cada-informe/spec.md:14, specs/066-libro-de-cada-informe/spec.md:16, src/convertersmartgrid/libro_informe.py:50.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-001-p1

Pregunta: el excel del informe sale siempre?

Respuesta: No: solo si el perfil de la empresa declara el libro del informe; si no, no hay libro ni se cuenta como hueco.

Fuentes: specs/066-libro-de-cada-informe/spec.md:14, specs/066-libro-de-cada-informe/spec.md:16, src/convertersmartgrid/libro_informe.py:50.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-002

Pregunta: como llena el excel

Respuesta: Excel aplica un plan de celdas por COM, porque openpyxl pierde las imágenes, el gráfico y los vínculos al guardar.

Fuentes: src/convertersmartgrid/libro_informe.py:3.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-004

Pregunta: y las formulas del modelo?

Respuesta: Conserva las fórmulas del modelo que el perfil no declara.

Fuentes: specs/066-libro-de-cada-informe/spec.md:20.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-006

Pregunta: si queda un texto del caso modelo o un #REF

Respuesta: Lo avisa nombrando la hoja y la celda.

Fuentes: specs/066-libro-de-cada-informe/spec.md:23, src/convertersmartgrid/libro_informe.py:24.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-007

Pregunta: ¿Qué hace con un dato del informe que falta?

Respuesta: Deja vacía su celda y la nombra entre los huecos del libro.

Fuentes: specs/066-libro-de-cada-informe/spec.md:25.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-008

Pregunta: y si excel no abre

Respuesta: Dice el motivo y conserva el Word.

Fuentes: specs/066-libro-de-cada-informe/spec.md:27, src/convertersmartgrid/libro_informe.py:246.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-009

Pregunta: ¿Cuándo avisa por diferencia de importes?

Respuesta: Si el importe de pérdidas no reconocidas del libro se separa más de 1 S/. del informe.

Fuentes: specs/066-libro-de-cada-informe/spec.md:28, src/convertersmartgrid/libro_informe.py:23.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-011

Pregunta: ¿El informe de estudio también lleva su libro?

Respuesta: Sí, donde el perfil declara el libro del informe.

Fuentes: specs/066-libro-de-cada-informe/spec.md:31, src/convertersmartgrid/web/services.py:7046.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-012

Pregunta: donde descargo el excel

Respuesta: La web lo ofrece junto al Word.

Fuentes: specs/066-libro-de-cada-informe/spec.md:30.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## libro_excel_informe-018

Pregunta: ¿Quién revisa el libro antes de enviarlo a la empresa?

Respuesta: No consta un paso de revisión humana del libro en el código ni en las specs.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-001

Pregunta: ¿Qué archivos acepta cada casilla de entrada?

Respuesta: .txt en RED, CARGA y EQUIPOS; .mdb o .accdb en las bases Access; .zxst o .xst en el estudio; .json en los alias; los de VNR-GIS los fija el servidor.

Fuentes: frontend/src/components/InputsPanel.tsx:138, src/convertersmartgrid/web/app.py:999, frontend/src/components/InputsPanel.tsx:11, src/convertersmartgrid/web/app.py:969.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-004

Pregunta: suelto todos los txt juntos, como sabe cual es cual

Respuesta: Asigna cada TXT a su casilla por las tablas que trae dentro, no por el nombre.

Fuentes: frontend/src/components/InputsPanel.tsx:215, src/convertersmartgrid/web/app.py:1082, src/convertersmartgrid/web/app.py:1089.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-004-p1

Pregunta: ¿Cómo asigna la web los TXT soltados juntos?

Respuesta: Asigna cada TXT a su casilla por las tablas que trae dentro, no por el nombre.

Fuentes: frontend/src/components/InputsPanel.tsx:215, src/convertersmartgrid/web/app.py:1082, src/convertersmartgrid/web/app.py:1089.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-005

Pregunta: y si suelto dos RED

Respuesta: Una base Access o un paquete VNR-GIS soltados aquí no se asignan; si dos ficheros son del mismo tipo, el segundo queda sin asignar.

Fuentes: frontend/src/components/InputsPanel.tsx:215, src/convertersmartgrid/web/app.py:1082, src/convertersmartgrid/web/app.py:1089.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-006

Pregunta: no me sale bien la base access en la web

Respuesta: Sin pyodbc o sin el driver de Access de 64 bits en el servidor, la web lo avisa.

Fuentes: frontend/src/components/InputsPanel.tsx:207, frontend/src/components/InputsPanel.tsx:223.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-007

Pregunta: no se activa cargar alimentadores

Respuesta: Que el motor esté libre y no falte ninguna entrada obligatoria.

Fuentes: frontend/src/components/FeedersPanel.tsx:235, src/convertersmartgrid/web/app.py:1122.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-008

Pregunta: ¿Cuándo se pulsa «Cargar / listar alimentadores»?

Respuesta: Después de asignar las entradas y antes de convertir.

Fuentes: frontend/src/components/FeedersPanel.tsx:235, src/convertersmartgrid/web/app.py:1122.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-009

Pregunta: convertir que me da

Respuesta: Un .dgs por alimentador y el manifiesto del lote.

Fuentes: frontend/src/components/FeedersPanel.tsx:365, src/convertersmartgrid/web/app.py:1188.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-013

Pregunta: no me deja mandar a digsilent

Respuesta: Que DIgSILENT esté libre y cada seleccionado tenga su conversión correcta.

Fuentes: frontend/src/components/FeedersPanel.tsx:422, src/convertersmartgrid/web/app.py:1319.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-016

Pregunta: aplicar integracion me pide algo de convergencia

Respuesta: Sin flujo previo pide verificar la convergencia o ajustar a la máxima; si no converge, pide corregirlo.

Fuentes: frontend/src/components/CargasTab.tsx:680, src/convertersmartgrid/web/app.py:1493.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-017

Pregunta: ¿Qué tengo que llenar para «Conectar al NMT más cercano»?

Respuesta: Nombre, alimentador, potencia en kW y coordenadas UTM X e Y de la carga.

Fuentes: frontend/src/components/CargasTab.tsx:568, src/convertersmartgrid/web/app.py:1446.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-019

Pregunta: q excel acepta la cabecera

Respuesta: .xls, .xlsx, .xlsb o .xlsm; varios en cabecera, suministros y clientes.

Fuentes: frontend/src/components/DemandaMedida.tsx:65, src/convertersmartgrid/web/app.py:2218, frontend/src/components/DemandaMedida.tsx:16.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-022

Pregunta: ¿Cómo paro un ajuste que lancé mal?

Respuesta: Con «Cancelar» en la barra de trabajos; un guion de DIgSILENT termina lo que tiene en curso y no empieza lo siguiente.

Fuentes: frontend/src/components/AjusteCabecera.tsx:190, src/convertersmartgrid/web/app.py:1631.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-023

Pregunta: preparar estudios sin calibrar

Respuesta: Sin ajuste aplicado, el servidor dice que primero hay que calibrar.

Fuentes: frontend/src/components/EstudiosPF.tsx:120, src/convertersmartgrid/web/app.py:2048.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-026

Pregunta: ¿Qué entrega «Generar informe de factibilidad»?

Respuesta: Word, PDF, JSON y, si el perfil lo declara, el libro Excel.

Fuentes: frontend/src/components/InformesPF.tsx:784, src/convertersmartgrid/web/app.py:2159.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-027

Pregunta: generar informe de estudio abre digsilent?

Respuesta: No: no corre DIgSILENT.

Fuentes: frontend/src/components/InformesPF.tsx:411, src/convertersmartgrid/web/app.py:2078.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-029

Pregunta: libro de perdidas en q formato

Respuesta: .xlsx o .xlsm

Fuentes: frontend/src/components/InformesPF.tsx:734, src/convertersmartgrid/web/app.py:2097.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-030

Pregunta: subi un libro de empresa con errores

Respuesta: Un libro con errores no reemplaza al anterior.

Fuentes: frontend/src/components/DatosEmpresaPF.tsx:33, src/convertersmartgrid/web/app.py:2024, src/convertersmartgrid/web/services.py:6347.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-032

Pregunta: ¿La transferencia deja algo cambiado?

Respuesta: No deja cambios en el proyecto.

Fuentes: frontend/src/components/TransferenciaPF.tsx:62, src/convertersmartgrid/web/app.py:2179.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-033

Pregunta: para que es cancelar en la barra

Respuesta: Pide cancelar ese trabajo.

Fuentes: frontend/src/components/JobBar.tsx:34, src/convertersmartgrid/web/app.py:1216.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-034

Pregunta: ¿«Planificar» del PIDE escribe en DIgSILENT?

Respuesta: Sí: crea los casos por año y puede aplicar bancos y ternas.

Fuentes: frontend/src/components/GemeloPIDE.tsx:61, src/convertersmartgrid/web/app.py:1678.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-036

Pregunta: diagnosticar del sistema completo toca digsilent

Respuesta: No: no toca DIgSILENT.

Fuentes: frontend/src/components/Modules.tsx:220, src/convertersmartgrid/web/app.py:2268.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-037

Pregunta: ¿Por qué un botón se ve gris en mi pantalla ahora mismo?

Respuesta: No lo sé sin ver su pantalla: la condición de cada botón está en el código, pero su estado en pantalla no se comprueba aquí.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-038

Pregunta: donde esta el boton de exportar a pdf el informe de estudio

Respuesta: No hay un botón así: el informe de estudio sale en Word.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:78.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## operacion_web-041

Pregunta: ¿Dónde está el botón para deshacer las cargas nuevas?

Respuesta: No hay botón en la web: deshacer cargas solo está en la línea de órdenes.

Fuentes: specs/007-cargas-nuevas-sobre-el-ajuste/spec.md:174.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-001

Pregunta: ¿Qué año pide el estudio de planeamiento?

Respuesta: El año de presentación; de él calcula el año 00 como el anterior, sin ningún año fijo en el código.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:29, src/convertersmartgrid/estudio_planeamiento.py:5.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-001-p1

Pregunta: q año le pongo al pide

Respuesta: El año de presentación; de él calcula el año 00 como el anterior, sin ningún año fijo en el código.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:29, src/convertersmartgrid/estudio_planeamiento.py:5.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-004

Pregunta: ¿Y si calibré con mediciones de otro año?

Respuesta: Lo dice y sigue.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:33, src/convertersmartgrid/estudio_planeamiento.py:63.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-005

Pregunta: ¿Qué documentos deja el estudio?

Respuesta: Uno por módulo: diagnóstico y alternativas del plan; formulación, evaluación técnica, económica, priorización y propuesta del PIDE.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:62, src/convertersmartgrid/informes_planeamiento.py:251.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-005-p1

Pregunta: los informes del pide son un word grande?

Respuesta: Uno por módulo: diagnóstico y alternativas del plan; formulación, evaluación técnica, económica, priorización y propuesta del PIDE.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:62, src/convertersmartgrid/informes_planeamiento.py:251.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-006

Pregunta: el pide recalcula lo del largo plazo?

Respuesta: No: el PIDE consume el largo plazo y no lo vuelve a calcular.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:34, src/convertersmartgrid/informes_planeamiento.py:8.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-010

Pregunta: las obras de un año pasan al siguiente?

Respuesta: Sí: cada año se mide con sus obras y las de los años anteriores.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:54, src/convertersmartgrid/web/services.py:4685.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-014

Pregunta: la evaluacion con y sin proyecto mide la ens?

Respuesta: No: solo mide el ahorro de pérdidas; la energía no servida y la calidad no entran en el flujo.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/tasks.md:31.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-016

Pregunta: la norma del pide ya esta vigente?

Respuesta: Se trata como prepublicación: su vigencia se confirma antes de citarla como obligatoria.

Fuentes: config/pide_universal_2017.json:9.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-017

Pregunta: si falta el modelo de word del plan se pierde todo?

Respuesta: No: un modelo que falte no pierde el cálculo; el fallo se avisa.

Fuentes: src/convertersmartgrid/web/services.py:4730.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-019

Pregunta: cual es el VNR aprobado de mi empresa

Respuesta: No lo sé: el VNR aprobado está en la resolución de cada empresa, fuera del repositorio.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planeamiento_pide-020

Pregunta: ¿Conviene presentar el PIDE antes de plazo?

Respuesta: No hay criterio sobre eso en el código ni en las specs.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-001

Pregunta: ¿Cómo se dibujan los planos del informe?

Respuesta: Los dibuja la web con la posición GPS de cada barra, el trazado GPS de cada tramo y la tensión y cargabilidad del flujo del caso.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:95, src/convertersmartgrid/mapa_informe.py:6.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-001-p1

Pregunta: los planos los saca digsilent?

Respuesta: Los dibuja la web con la posición GPS de cada barra, el trazado GPS de cada tramo y la tensión y cargabilidad del flujo del caso.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:95, src/convertersmartgrid/mapa_informe.py:6.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-002

Pregunta: xq no exporta la imagen de digsilent

Respuesta: Porque con DIgSILENT sin ventana la exportación deja un fichero de 1 KB sin dibujo.

Fuentes: src/convertersmartgrid/mapa_informe.py:5.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-005

Pregunta: ¿La leyenda va antes o después de la imagen?

Respuesta: Antes de cada imagen coloreada, con sus bandas, colores y anchuras.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:316, specs/017-informes-de-estudio-y-factibilidad/spec.md:318.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-006

Pregunta: como marca la carga nueva en el plano

Respuesta: Con un rótulo con su nombre, sus kW y el código del punto de diseño, y una flecha a su punto de conexión.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:325.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-007

Pregunta: ¿Cómo se ven las obras en el plano de una alternativa?

Respuesta: Los tramos con conductor nuevo en trazo grueso con inicio y fin rotulados, y los bancos nuevos en su barra.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:436.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-009

Pregunta: ¿Qué marca la imagen de ubicación del cliente?

Respuesta: Su punto de conexión, marcado y rotulado, y los alimentadores cercanos, cada uno en su color y con su nombre.

Fuentes: src/convertersmartgrid/mapa_informe.py:469, specs/017-informes-de-estudio-y-factibilidad/spec.md:307.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-010

Pregunta: la vista previa de ubicacion ocupa digsilent?

Respuesta: No: se dibuja con la geografía guardada del último flujo de «Con proyecto» y no ocupa su carril.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:404, src/convertersmartgrid/web/services.py:7491.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-014

Pregunta: ¿En qué coordenadas UTM está la SED de ALIM-A?

Respuesta: No lo sé: las coordenadas son de la red de cada empresa y no están en el repositorio.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## planos_informe-015

Pregunta: puedo sacar el plano en autocad?

Respuesta: No consta una salida a CAD: los planos son imágenes del informe.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-001

Pregunta: ¿El pronóstico corre solo en cada calibración?

Respuesta: No: solo por una petición expresa desde la web o el asistente.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:38.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-001-p1

Pregunta: el pronostico se lanza solo?

Respuesta: No: solo por una petición expresa desde la web o el asistente.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:38.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-004

Pregunta: sin gpu se entrena en cpu?

Respuesta: No: da un error que lo dice para cada modelo neuronal.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:30.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-006

Pregunta: el pronostico escribe en digsilent?

Respuesta: No.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:36.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-008

Pregunta: el pide usa el pronostico como tasa?

Respuesta: No: el PIDE sigue con la tasa de crecimiento, sin leer ningún pronóstico.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:37.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-009

Pregunta: ¿Cómo se elige el ganador?

Respuesta: Uno por objetivo, por separado cabecera y cliente; si ningún neuronal pasa las puertas, gana su referencia.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:31, specs/046-pronostico-causal-multihorizonte/spec.md:32.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-010

Pregunta: q miden las puertas

Respuesta: Incluyen el error en la máxima y en el instante de la máxima frente a la referencia.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:33.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-011

Pregunta: ¿El gemelo temporal pronostica?

Respuesta: No: reproduce el mes a un paso y lo dice; no es un pronóstico.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:40.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-012

Pregunta: puede ver datos del futuro al entrenar

Respuesta: No: solo usa observaciones anteriores al corte de entrenamiento.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:16.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-013

Pregunta: ¿Qué salió en la medición real?

Respuesta: Ningún modelo neuronal superó las puertas: ganó la referencia en todos los objetivos medidos.

Fuentes: specs/046-pronostico-causal-multihorizonte/tasks.md:63.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-014

Pregunta: se puede cancelar el pronostico

Respuesta: Sí: corre como trabajo cancelable en otro proceso.

Fuentes: specs/046-pronostico-causal-multihorizonte/spec.md:39.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-015

Pregunta: ¿Tiene panel propio en la web?

Respuesta: No: el resultado se ve en el trabajo y el asistente lo pide con su formulario.

Fuentes: specs/046-pronostico-causal-multihorizonte/tasks.md:50.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-016

Pregunta: ¿Cuánto será la demanda de ALIM-A el próximo enero?

Respuesta: No lo sé: haría falta correr el pronóstico con su medición.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## pronostico-017

Pregunta: pronostico con variables del clima tb?

Respuesta: Aún no: las variables exógenas son de la proyección econométrica, que está reservada.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:51.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-001

Pregunta: ¿Qué baja «Descargar máxima y clientes en Excel»?

Respuesta: Lo que hay en pantalla: la máxima de cabecera y los clientes cruzados y no cruzados.

Fuentes: frontend/src/components/DemandaMedida.tsx:743.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-001-p1

Pregunta: el excel de maxima y clientes q trae

Respuesta: Lo que hay en pantalla: la máxima de cabecera y los clientes cruzados y no cruzados.

Fuentes: frontend/src/components/DemandaMedida.tsx:743.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-003

Pregunta: ¿Hay plantilla para el libro de cargas?

Respuesta: Sí, vacía, en Excel o en CSV.

Fuentes: frontend/src/components/CargasTab.tsx:360.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-006

Pregunta: como lee los pdf del solicitante

Respuesta: Lee su texto en un trabajo con progreso, con OCR si hace falta, y propone los datos.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:497.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-007

Pregunta: ¿Qué extrae de los PDF?

Respuesta: Cuando están: fecha y lugar, asunto, cliente, potencia, ubicación y otros datos de la solicitud.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:501.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-009

Pregunta: ¿Guardo el registro de la web?

Respuesta: Sí: «Guardar» del registro lo baja como texto en el navegador.

Fuentes: frontend/src/components/LogPanel.tsx:33.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-013

Pregunta: ¿Cómo repito los informes con flujos ya guardados?

Respuesta: Con tools/informe_casos_guardados.py, que no abre ni modifica DIgSILENT.

Fuentes: tools/informe_casos_guardados.py:3.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-014

Pregunta: ¿Dónde está el ZIP que bajé ayer de PROYECTO-Y?

Respuesta: No lo sé: las descargas quedan en el navegador de quien las bajó.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## salidas_auxiliares-016

Pregunta: ¿Cuánto pesa el ZIP de todo el sistema?

Respuesta: No lo sé: depende de las salidas del espacio.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-001

Pregunta: ¿Cuándo va directo a una SET nueva sin escalera?

Respuesta: Cuando las cargas nuevas evaluadas suman más que el umbral del perfil, o el operador lo pide.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:151, src/convertersmartgrid/web/services.py:6174.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-001-p1

Pregunta: cuando se va directo a set nueva

Respuesta: Cuando las cargas nuevas evaluadas suman más que el umbral del perfil, o el operador lo pide.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:151, src/convertersmartgrid/web/services.py:6174.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-004

Pregunta: falta el factor de seguridad en el perfil

Respuesta: Dice cuál falta y no supone un valor.

Fuentes: specs/042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md:80.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-005

Pregunta: ¿Dónde ubica la SET nueva?

Respuesta: En el punto que minimiza el valor esperado de la suma de potencia por distancia, con sorteos de crecimiento por zonas.

Fuentes: specs/042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md:83.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-006

Pregunta: y si con ese punto la tension no cumple

Respuesta: Acerca la SET a las barras que caen y vuelve a comprobar; si ningún punto cumple, lo dice.

Fuentes: specs/042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md:88.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-008

Pregunta: si ningun modulo alcanza la potencia

Respuesta: Si el perfil admite transformadores en paralelo, elige el de menor costo con unidades iguales.

Fuentes: specs/042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md:104.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-011

Pregunta: ¿Si todas las cargas caben en la red?

Respuesta: No hace falta SET nueva y lo dice.

Fuentes: src/convertersmartgrid/web/services.py:5989.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-012

Pregunta: para una set q ya existe la vuelve a crear?

Respuesta: No: diagnostica, evalúa o aplica refuerzos sin crearla ni desplazarla.

Fuentes: src/convertersmartgrid/web/services.py:6523, specs/063-informe-de-factibilidad-en-un-paso/spec.md:160.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-013

Pregunta: ¿Qué informa de la SET nueva?

Respuesta: El destino de cada carga, las obras con su costo, el punto, la potencia de diseño y los alimentadores nuevos con sus tramos.

Fuentes: specs/042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md:97.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-014

Pregunta: cuantos alimentadores nuevos puede tener

Respuesta: En la web, entre uno y veinte.

Fuentes: frontend/src/components/CargasTab.tsx:907.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-015

Pregunta: ¿Qué terreno se compra para SET-A?

Respuesta: No lo sé: la compra de terreno no está en el conversor.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## set_nueva-016

Pregunta: la set nueva necesita estudio de impacto ambiental?

Respuesta: No consta en el código ni en las specs.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-001-p1

Pregunta: diferencia entre informe de estudio y factibilidad

Respuesta: El de factibilidad, para la conexión de un cliente nuevo; el de estudio eléctrico, para la red existente y sus obras sin cliente nuevo.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:73, specs/017-informes-de-estudio-y-factibilidad/spec.md:75.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-002

Pregunta: cual de los dos corre digsilent

Respuesta: El de la carga nueva prepara casos y corre flujos; el de estudio lee los flujos guardados.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:29, src/convertersmartgrid/web/services.py:6858.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-004

Pregunta: en q formato salen

Respuesta: Ambos en Word editable con su JSON; el de la carga nueva además en PDF.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:78, specs/063-informe-de-factibilidad-en-un-paso/spec.md:174.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-005

Pregunta: ¿Y el libro Excel?

Respuesta: Junto a cada informe, si el perfil de la empresa lo declara.

Fuentes: specs/066-libro-de-cada-informe/spec.md:14, specs/066-libro-de-cada-informe/spec.md:31.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-006

Pregunta: hay boton aparte para el paso unico

Respuesta: No: el botón del informe de la carga nueva hace el paso entero; no hay botón nuevo.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:32.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-008

Pregunta: los informes del pide como son

Respuesta: Un documento ligero por módulo del plan y del PIDE, con sus tablas y formatos.

Fuentes: specs/072-pide-y-planeamiento-de-largo-plazo/spec.md:62.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-010

Pregunta: cargabilidad del trafo de la set como se saca

Respuesta: Del proyecto de transmisión del perfil, con la subida de la cabecera de «Sin proyecto» a «Con proyecto».

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:250.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-011

Pregunta: ¿Guarda algo en el proyecto de transmisión?

Respuesta: No: no guarda ningún cambio en él.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:278.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-012

Pregunta: el modelo de informe de donde sale

Respuesta: Del fichero que indica el perfil de empresa, nunca de una ruta fija.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:81.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-016

Pregunta: si cancelo el informe queda medio word

Respuesta: No: no deja un Word a medias.

Fuentes: specs/017-informes-de-estudio-y-factibilidad/spec.md:131.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-018

Pregunta: la factibilidad con varios casos concluye por cada uno?

Respuesta: Sí: concluye por separado sobre cada caso con sus resultados medidos.

Fuentes: specs/063-informe-de-factibilidad-en-un-paso/spec.md:197.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-021

Pregunta: ¿Hay informe de protecciones?

Respuesta: Aún no: la coordinación de protecciones está solo especificada.

Fuentes: specs/049-protecciones-nativas-y-coordinacion/spec.md:16.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-025

Pregunta: ¿El informe sirve como documento legal?

Respuesta: No consta en el código ni en las specs.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## tipos_de_informe-026

Pregunta: puedo sacar el informe en ingles

Respuesta: No hay informes en inglés: el proyecto escribe en español.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-001

Pregunta: ¿Entre cuántos alimentadores se calcula una transferencia?

Respuesta: Entre exactamente dos alimentadores distintos.

Fuentes: src/convertersmartgrid/web/services.py:6755.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-001-p1

Pregunta: transferencia con tres alimentadores se puede?

Respuesta: Entre exactamente dos alimentadores distintos.

Fuentes: src/convertersmartgrid/web/services.py:6755.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-004

Pregunta: por q camino transfiere

Respuesta: Por la troncal que calcula DIgSILENT, del punto de enlace a la cabecera del que cede.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:399.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-005

Pregunta: ¿Qué puntos de maniobra cuenta?

Respuesta: Solo los seccionadores de la troncal del que cede, no fusibles, interruptores ni reconectadores.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:424.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-006

Pregunta: la maxima transferible cual es

Respuesta: La del seccionador viable más lejano del enlace, por sentido y por enlace.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:410.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-007

Pregunta: ¿Suma las máximas de los dos alimentadores?

Respuesta: No: parte de un instante común del mes elegido.

Fuentes: specs/013-mes-de-analisis-y-transferencia/spec.md:117.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-008

Pregunta: sin periodo elegido

Respuesta: No calcula la transferencia: pide elegir el mes o todo el año y volver a buscar la máxima.

Fuentes: src/convertersmartgrid/web/services.py:6723.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-009

Pregunta: ¿Sin instantes comunes?

Respuesta: Bloquea la aceptación y explica qué evidencia falta.

Fuentes: specs/013-mes-de-analisis-y-transferencia/spec.md:135.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-010

Pregunta: q archivo deja

Respuesta: Un libro de transferencias con una fila por caso, sentido, enlace y paso, y las SED transferidas en hoja aparte.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:437, specs/013-mes-de-analisis-y-transferencia/spec.md:127.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-011

Pregunta: ¿La transferencia deja cambios en el proyecto?

Respuesta: No: no cambia el proyecto.

Fuentes: src/convertersmartgrid/web/services.py:6773.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-014

Pregunta: proyecto antiguo sin seccionadores reconocidos

Respuesta: Da solo el resultado por nodos y pide reconvertir o cargar la entrada.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:429.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-015

Pregunta: ¿En qué caso se calcula?

Respuesta: En «Sin proyecto», en «Con proyecto» o en los dos, según elija el operador.

Fuentes: specs/011-estudios-sobre-la-red-calibrada/spec.md:390.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-016

Pregunta: ¿Cuánta carga pasa de ALIM-A a ALIM-B hoy?

Respuesta: No lo sé: hay que calcularla en el proyecto con su máxima.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.

## transferencias-018

Pregunta: ¿Cuánto tiempo aguanta el enlace en emergencia?

Respuesta: No lo sé: los tiempos de emergencia no están en el código.

Fuentes: ninguna: lo preguntado no está en el repositorio.
Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.
