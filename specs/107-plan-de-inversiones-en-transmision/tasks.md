# Tareas — Spec 107

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Los ficheros nuevos de `src/` y `tools/` entran en `CODIGO_FUENTE.md` y en `docs/architecture/subsistemas.json` en el
mismo cambio (spec 009 y 090). Ninguna tarea toca `src/convertersmartgrid/web/services.py`, `pide_economia.py` ni el
adaptador VNR (integrador f9).

- [x] T1. Registro normativo común con la 108 (`registro_normativo.py`, su esquema y `config/normativa/`): contrato de
      una norma con sus reglas, estados `vigente_comprobada`, `modificada`, `prepublicada`, `no_verificada` y
      `derogada`, `regla(clave, fecha)` con su estado y si es obligatoria, e `instantanea()` con la huella. Si la 108 ya
      lo creó, solo se añade lo que le falte al PIT. Dos registros sintéticos. (RF-7, RF-8, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_registro_normativo.py` en verde, con una
      regla `prepublicada` y otra `no_verificada` que salen como no obligatorias.
- [x] T2. Leer y transcribir en `config/normativa/` las normas del PIT ya localizadas: RCD 217-2013-OS/CD (articulado,
      COyM, tasa, vida útil y formatos que fije), RCD 112-2024-OS/CD y RCD 149-2024-OS/CD (con los anexos A y B del
      Informe Técnico 565-2024-GRT), cada una con URL, fecha de consulta, huella del PDF, estado jurídico comprobado y
      cita literal con página. Sin reglas supuestas: lo que no se lea queda sin regla. (RF-7, RF-9)
      Hecho cuando: el registro valida contra su esquema en `tests/test_registro_normativo.py`, cada regla tiene página y
      cita literal, y los cuadros oficiales del PIT tienen su definición transcrita o figuran como no transcritos.
- [ ] T3. Leer y transcribir la RCD 199-2026-OS/CD cuando esté accesible (en G0 su enlace daba 404). Hasta entonces figura
      en el registro como `no_verificada` y sin reglas; al leerla se comprueba su existencia, su objeto, el área a la que
      modifica y su fecha de vigencia, y se actualizan `modifica` y `modificada_por` de la 149-2024. (RF-7, RF-8)
      Hecho cuando: la entrada de la 199-2026 tiene URL, huella, estado comprobado y sus reglas con cita literal, y
      `pytest -q tests/test_registro_normativo.py -k modificatoria` en verde con ella.
      Avance (2026-11-14, b3): leída en su edición oficial de El Peruano (14-11-2026, págs. 43-44, 2574534-1; el enlace
      del regulador sigue en 404) y transcrita en `config/normativa/rcd_199_2026.json`: modifica el PIT 2025-2029 en el
      Área de Demanda 9 y no fija vigencia propia. Los elementos modificados están en el IT 655-2026-GRT, sección 6.4,
      que da 404: quedan sin regla hasta leerlo, y la resolución complementaria que los consolide (art. 3) se registra
      al publicarse.
- [ ] T4. Perfil `pit.areas` en el esquema del perfil de empresa (área, titulares, SET, correspondencia SET →
      alimentadores, tensión mínima del ámbito y asignación de los elementos compartidos) y `pit/ambito.py`, que reúne
      los elementos de un área sin mezclarla con otra. Dos perfiles sintéticos A y B en `tests/datos_pit.py`.
      (RF-2, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_ambito.py` en verde con los dos perfiles, incluido el elemento compartido
      sin asignar.
- [ ] T5. Contrato `RedArea` (`pit/red_area.py`) y su adaptador del libro de la red declarado en el perfil: cada
      elemento con titular, área y fuente, y los elementos sin parámetros en `faltantes` con el dato que les falta.
      El libro se abre con `demanda_medida.abrir_libro` en cualquier formato y se leen todas sus hojas, o las que
      declare `pit.libro_red.hoja`, con la cabecera buscada por contenido. (RF-2, RF-4, RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_red_area.py` en verde, con la línea sin parámetros del perfil B nombrada y
      fuera del diagnóstico completo, el mismo libro leído igual en .xlsx y .xlsm, .xls y .xlsb por el lector común,
      un libro de varias hojas leído entero con la hoja sin contrato en los avisos, la hoja declarada respetada y un
      libro sin ninguna hoja válida detenido con sus hojas y cabeceras.
- [ ] T6. De `RedArea` a pandapower (`pit/red_pandapower.py`, con transformadores de dos y tres devanados; pandapower
      directo con los parámetros de `oraculo.py`, cuyos auxiliares son privados, y de él solo `oraculo.disponible()`) y la matriz de capacidades estudio × motor (`pit/motores.py`): el motor abierto por defecto,
      DIgSILENT si hay licencia, y cada resultado nombra su motor. (RF-3, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_motores.py` en verde: el flujo de los perfiles A y B converge con
      pandapower, y el cortocircuito y `ComRel3` sin licencia salen como «no disponible con el motor abierto».
- [ ] T7. Diagnóstico por año (`pit/diagnostico.py`): demanda del área desde `proyeccion_anual` por barra de SET,
      cargabilidad, tensión y N-1 de cada elemento contra los límites del registro o del perfil; el año sin demanda
      queda nombrado, sin extrapolar; trabajo cancelable entre años. (RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_diagnostico.py` en verde, con el N-1 del anillo del perfil B, el año sin
      demanda y una cancelación a mitad del horizonte.
- [ ] T8. Alternativas mutuamente excluyentes (`pit/alternativas.py`): inversión con `costos_fuentes.valorar_obra`
      (ámbito `transmision`) y los módulos de `set_nueva.leer_modulos_pit`, COyM y pérdidas según el registro, valor
      actual con `pide_economia.frc` y `van`, y confiabilidad según la matriz; misma demanda y mismo motor para todas;
      una alternativa con un costo que falta queda incompleta y fuera de la comparación; una regla no vigente se usa
      como referencia y se dice. (RF-5, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_alternativas.py` en verde, con una alternativa sin costo que no queda
      primera y una tasa `no_verificada` rotulada como referencia.
- [ ] T9. Programa (`pit/programa.py`): cada elemento con su año de puesta en servicio, su titular y su área, con las
      bajas y los reemplazos; un programa por titular cuando el área tiene varios. (RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_programa.py` en verde con el perfil A (un titular) y el B (varios).
- [ ] T10. Expediente y cuadros (`pit/expediente.py` y `pit/cuadros.py`): carpeta aparte de la del PIDE, instantánea del
       registro al abrirlo, aviso y lista de celdas afectadas si una modificatoria llega después, traza de cada celda
       (fuente con huella, cálculo, motor y regla con su estado), cuadros desde su definición transcrita y escritos en el
       libro modelo con `libro_informe`, determinismo byte a byte, y nunca la frase «aprobado por Osinergmin».
       (RF-1, RF-7, RF-8, RF-9)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_expediente.py` en verde: dos corridas iguales dan el mismo expediente, la
       modificatoria posterior se avisa sin recalcular, y ninguna celda queda sin traza.
- [ ] T11. Observaciones del regulador (`pit/observaciones.py`): número, fecha, texto, respuesta y el elemento, el caso o
       la celda a los que afecta, enlazados con la traza del expediente. (RF-10)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_observaciones.py` en verde, con una observación sobre una celda y otra
       sobre un elemento del perfil B.
- [ ] T12. Guion `tools/pit_pf.py` (con docstring en español y `--help` sin DIgSILENT): `--exportar-red` del proyecto de
       transmisión a `RedArea`, `ComLdf`, `ComSimoutage` y `ComRel3` por año, sin dejar nada cambiado
       (`estudios_red_pf.cambios_de_estado`). (RF-2, RF-3, RF-5)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_pf_guion.py` en verde con el doble `tests/fake_pf.py`.
- [ ] T13. Web: `web/rutas_pit.py` con un `APIRouter` propio (`/api/pit/…`), el diagnóstico y las alternativas como
       trabajos en cola (carril `engine` o `powerfactory`) con progreso por WebSocket, y el panel en
       `frontend/src/features/pit/` con la microcopia mínima. Solo el registro del router en `web/app.py`, pactado antes
       con f9. (RF-1, RF-2, RF-3, RF-5, RF-6, RF-9, RF-10)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_web.py` en verde, el router montado en
       `web/app.py` (lo hace el integrador con `para_f9/107_app.txt`), el panel de `frontend/src/features/pit/` con su
       carga del libro de la red (.xlsx, .xlsm, .xls y .xlsb), y `npm run lint`, `npx tsc --noEmit -p .` y
       `npm run build` sin errores. Pendiente (2026-11-14, S1): el router y su prueba existen; faltan el montaje, el
       panel, la subida del libro con su validación previa (422) y las rutas de alternativas, expediente y cuadros.
- [ ] T14. [DIgSILENT] Corrida real sobre una **copia** del proyecto de transmisión del área del primer caso (la
       primera empresa de prueba, con el área y el titular en su perfil): exportar la red, diagnosticar un año con los dos motores y comparar
       con la tolerancia de la 112 (0,005 p.u. en tensión, 1 % en corriente). (RF-2, RF-3, RF-5)
       Hecho cuando: la evidencia de la corrida (informe y registro) queda fuera de git con su huella y las diferencias
       entre motores están dentro de la tolerancia o explicadas elemento por elemento.
- [ ] T15. Aceptación con datos reales autorizados por la empresa: reproducir, fila por fila, un cuadro de un PIT
       publicado para el área del primer caso, con sus diferencias explicadas. (RF-6, RF-9)
       Hecho cuando: el expediente trae el cuadro reproducido, su cuadro publicado de referencia con su huella, y cada
       diferencia con su causa.
- [ ] T16. Cotejo de una muestra de celdas por un revisor independiente, con sus observaciones registradas por la vía de
       T11. (RF-9, RF-10)
       Hecho cuando: el expediente guarda el acta del cotejo, la muestra revisada y la respuesta a cada observación.
- [ ] T17. Universalidad: el paquete `pit/` y `registro_normativo.py` sin números de área, titulares, tensiones, tasas ni
       años de una empresa o un periodo. (RF-11)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_entrega_universal.py tests/test_inventario.py`
       en verde con los ficheros
       nuevos incluidos.
- [ ] T18. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
       Hecho cuando: cada RF definido en `spec.md` (`grep -oE "^- RF-[0-9]+" spec.md`, de RF-1 a RF-18) aparece en
       `grep -rnoE "107:RF-[0-9]+" tests | sort -u`, con sus pruebas en verde, y
       `.venv/Scripts/python.exe -m pytest -rfs tests/test_trazabilidad_specs.py` en verde. Depende de T13 y de T19 a
       T26.
- [ ] T19. Formatos desde la norma registrada (aclaración de RF-9): transcribir en `config/normativa/` las columnas de
       cada formato que lista la regla de formatos de la norma vigente (`pit.formatos_217`, hoy `transcrito: false`:
       sus columnas están en los libros Excel de la norma, que no se han descargado) y ampliar `pit/cuadros.py` para que
       emita los formatos que liste el registro, con las celdas derivadas vinculadas por fórmula. Bloqueada por datos
       (2026-11-14, S1): `config/normativa/rcd_217_2013.json`, regla `pit.formatos_217`, «solo los grupos: las columnas
       de cada formato están en los libros Excel de la norma, no leídos». Siguiente acción: descargar los libros de
       formatos de la 217-2013 y del IT vigente y transcribirlos con cita y página. (RF-9, RF-11)
       Avance (2026-11-14, b3): datos desbloqueados. Los libros oficiales («NormaTarifas2013.rar», enlazado por el
       regulador en «Formularios de norma Tarifas y Compensaciones de SST y SCT») traen los 69 formatos de la tabla 1,
       una hoja por formato, transcritos literal en `config/normativa/rcd_217_2013_formatos.json` (reglas
       `pit.formato.F-xxx`) y validados en `tests/test_registro_normativo.py`. Código (b3, delta2):
       `cuadros.formatos_aplicables` (la lista sale de la norma vigente; cada formato, transcrito o nombrado), el
       expediente guarda `formatos.json` y nombra los no transcritos en el resumen, y `plan_de_cuadros(vinculos=…)`
       escribe la celda derivada como fórmula hacia su origen. Se marca al correr su verde.
       107-T19b (b3, delta6; condición de ca): los formatos que exige el estudio salen de la regla
       `pit.plan.formatos_exigidos` (num. 5.7 de la 217-2013: F-001 a F-401, sin los de tarifas), y `pit/llenado.py` da
       cada uno llenado o como plantilla nombrada con su causa, nunca vacío en silencio. Hoy: 46 exigidos, el F-208 con
       mapeo y 45 pendientes de mapeo. T19 no se marca mientras quede uno exigido sin mapeo y sin causa aceptada; el
       mapeo crece formato a formato, cada uno con su prueba de celda y la cita de su hoja y su fila.
       Paso 2 (b3, delta7): motor `pit/plantillas.py` con el mapeo declarado en `config/pit_mapeo_formatos.json`
       (rótulos y marcas comprobados contra la plantilla, columnas sin campo nombradas, totales y filas a insertar);
       F-001, F-002 y F-003 desde la red del área (`pit/formatos_red.py`, niveles de la regla 12.1.1 registrada como
       `pit.niveles_tension_kv`). Quedan 42 pendientes; el siguiente, F-101 a F-124 (orden de ca).
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_formatos.py` en verde con dos registros
       sintéticos de listas y columnas distintas (el número de formatos sale del registro), un formato listado y no
       transcrito nombrado en el resumen y una celda derivada escrita como fórmula; y la 217-2013 transcrita con cita y
       página, validada en `tests/test_registro_normativo.py`.
- [ ] T20. Documento de absolución (aclaración de RF-10): `observaciones.escribir_absolucion`, con cada observación, su
       objeto, su respuesta y la traza de lo que cambió en el expediente (celdas o elementos, con su huella antes y
       después). (RF-10)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_observaciones.py -k absolucion` en verde:
       cada observación aparece con su objeto y su respuesta, una observación sin cambios lo dice, y una referencia
       desconocida se rechaza.
- [ ] T21. Resumen ejecutivo (`pit/informe.py`): la demanda del área por año, la alternativa elegida y el programa de
       inversiones, leídos del expediente emitido. (RF-13)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_informe.py` en verde con los perfiles A y B:
       el resumen trae sus tres apartados con las cifras del expediente, y un expediente sin alternativa elegida da un
       error que lo nombra.
- [ ] T22. Memoria por sección y relación de sustento (`pit/expediente.emitir`): criterios, metodología, entradas y
       resultados de cada sección, y la relación de los documentos de sustento con su descripción, su uso y su huella.
       (RF-14)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_expediente.py -k "memoria or sustento"` en
       verde: cada fichero del expediente figura en la relación con su huella, y cada sección emitida tiene su memoria.
- [ ] T23. Unifilar en DXF por alternativa y año, con el flujo de cada línea (F-212), y en DWG con el ODA File Converter
       si la configuración o el PATH lo dan, nunca por una ruta fija (`pit/unifilar.py`). Bloqueada por dependencia (2026-11-14, S1):
       `ezdxf` no está en `.venv/Lib/site-packages` (comprobado leyendo el entorno, sin instalar nada) y el conversor no
       tiene escritor de DXF propio. Siguiente acción: el integrador añade `ezdxf` como dependencia OBLIGATORIA, con versión
       fijada y su licencia (veredicto del auditor ca, 2026-11-14 20:55: el DXF es la entrega garantizada; solo el DWG es
       opcional). (RF-15)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_unifilar.py` en verde: ezdxf, como lector
       independiente, abre el DXF y encuentra el marco A3, una hoja por alternativa y año y las barras, los
       transformadores y las líneas con su flujo; la ruta del convertidor sale del perfil o del PATH (ninguna fija en el
       código, ningún binario en el repositorio); la conversión a DWG se prueba con un doble del convertidor; con el
       doble ausente y con el doble que falla la entrega queda completa con el DXF, el aviso que dice cómo obtener el
       DWG está en el manifiesto del expediente y no queda ningún DWG vacío.
- [ ] T24. Transformadores de reserva (`pit/reserva.py`) con el procedimiento vigente del registro. Bloqueada por datos
       (2026-11-14, S1): la RCD 094-2022 no está descargada ni transcrita (inventario de entregables de Osinergmin,
       P13: «hay que leer la RCD 094-2022»). Siguiente acción: descargarla del portal del regulador y transcribirla en
       `config/normativa/` con cita y página. (RF-16)
       Avance (2026-11-14, b3): datos desbloqueados. La 094-2022 está descargada del portal del regulador y transcrita
       en `config/normativa/rcd_094_2022.json` (20 reglas con cita y página, y las tablas 1 a 3 de su anexo), validada en
       `tests/test_registro_normativo.py`. Código (b3, delta4): `pit/reserva.py` aplica el horizonte, el costo de la
       ENS, el umbral B/C (que se tiene que superar) y la exclusión por tensión del registro, y elige la viable de mayor
       beneficio neto; sin regla, avisa nombrándola. La ENS evitada por año entra como resultado del modelo de
       confiabilidad, con su huella. Bloqueo citado: el modelo oficial (anexo del IT 305-2022-GRT, num. 5.7) no está en
       Resoluciones-GRT-2022.aspx ni en el portal (2026-11-14); hasta tenerlo, cada resultado lo avisa. Se marca al
       correr su verde.
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_reserva.py` en verde: con un área sintética
       la reserva se elige con la regla del registro y sin regla sale el aviso que la nombra; y la 094-2022 transcrita
       en `config/normativa/`.
- [ ] T25. Modificación del plan vigente: modo `modificacion` del expediente, que compara el programa vigente con el
       nuevo y lista lo que se elimina, cambia o agrega, con su razón, con la demanda y las alternativas rehechas con los
       mismos criterios. (RF-17)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_programa.py tests/test_pit_expediente.py
       -k modificacion` en verde: dos programas sintéticos (perfiles A y B) dan la lista de diferencias con su razón, un
       cambio sin razón es un error que lo nombra, y el expediente de la modificación no se emite con otros criterios
       que los del vigente ni sobre su misma carpeta.
- [ ] T26. Formato F-208 con la estadística de fallas y los índices de desempeño de las fuentes importadas
       (confiabilidad, spec 012), con el hueco nombrado cuando falten. Bloqueada por datos (2026-11-14, S1): depende de T19,
       porque las columnas del F-208 están en los mismos libros de formatos sin transcribir. Siguiente acción: la de T19.
       (RF-18)
       Avance (2026-11-14, b3): datos desbloqueados. El F-208 está transcrito (regla `pit.formato.F-208`: interrupciones
       con ENS y tipo, SAIFI y SAIDI calculados frente a tolerancias, y barras con tensión fuera de tolerancia). Código
       (b3, delta3): `pit/f208.py` lee los bloques y las columnas de la plantilla transcrita y llena las celdas desde
       las fuentes importadas con su huella; «Cumple» sale del cálculo frente a la tolerancia, y un bloque sin datos
       deja su fila vacía con el hueco nombrado. El adaptador desde `historico_interrupciones` (spec 012, tarjeta
       CONFIAB2) se cablea cuando esa tarjeta esté integrada. Se marca al correr su verde.
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_formatos.py -k f208` en verde: con fallas
       sintéticas se llenan los índices, y sin ellas cada celda queda vacía con su hueco nombrado.
- [ ] T27. Demanda regulatoria, 3a: las reglas de la cadena (fórmula del art. 8.1, definiciones de FC, FCP y FS) y las
       pérdidas estándar de la fijación del VAD vigente por empresa y periodo en el registro (la 187-2023 modificada
       por la 223-2023 para las 11 empresas de esa fijación), con la comprobación permanente del cargador (FE ≥ 1 y
       FE = 1/(1−p)) y la cruzada contra el informe técnico de la fijación; y el motor de plantillas con series anuales
       cuyo horizonte sale de la norma. (Aclaración de RF-9; RF-7, RF-11)
       Avance (2026-11-15, f4): la causa del cambio de los FE entre el IT 716 y la 223-2023, por empresa
       (`config/normativa/vad_2023_2027_reconsideraciones.json`): citada en los IT 815, 816 y 817 para 3 empresas, y
       «sin causa localizada» citado para 6 cuyos informes no aceptan nada de pérdidas técnicas (delta13).
       Avance (2026-11-14, b3): pérdidas y comprobaciones escritas (delta8); reglas de la cadena registradas
       (`pit.demanda.potencia_desde_energia`, art. 8.1; `pit.demanda.definiciones_factores`, 3.10-3.12;
       `pit.demanda.definiciones_participacion`, F-103) y motor de series (`serie_columnas` y `serie_filas`, horizonte de
       `pit.horizonte_demanda_anios`, cada año comprobado en la plantilla). Se marca al correr su verde.
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_registro_normativo_factores.py tests/test_pit_registro.py
       tests/test_pit_formatos.py` en verde, con los rojos
       de la tabla desplazada, del porcentaje mal leído y del FE < 1; y la prueba de las series del motor con dos
       horizontes de norma distintos.
- [ ] T28. Demanda regulatoria, 3b: F-102 desde la medida del año representativo (días de máxima del sistema, de la
       SET y del SEIN, y máxima no coincidente) y, de él, F-101 (FC, FCP y FS) y F-103 (FPHMS y FPMWHS). (Aclaración de RF-9)
       Avance (2026-11-15, f4): registro del COES en `config/normativa/coes_maxima_demanda_sein.json` (máxima anual del
       SEIN 2024 y 2025 de la Estadística Anual, contraste mensual, intervalo del glosario y horas punta de las RM
       153-2021-MINEM/DM, hasta el 2025-05-31, y 189-2025-MINEM/DM, del 2025-06-01 al 2029-05-31) y
       `pit/demanda_regulatoria.py` (F-102, F-101 y F-103 con traza, instantes
       incompletos excluidos y contados, dos alineaciones del instante del SEIN con su tolerancia por procedencia: la
       resolución del perfil, la clase del perfil o la clase por defecto, con el error admisible de la RM 496-2005-MEM/DM
       en `config/normativa/medida_clase_precision.json`); y `topologia_desde` (perfil `pit.areas[].sistemas_electricos`
       y `barra_de_alimentador` con la red del área: devanado de cada alimentador, sin suponer barras ni repartos en
       paralelo); y el contraste con el reporte mensual de máxima demanda del COES 2024-2025 (confirma la fecha de 2024 y
       nombra que su mayor mes no es el de la Estadística Anual); y `curvas_de_la_medida` y `demanda_regulatoria`
       (libros de cabecera del perfil → curvas por alimentador con su fuente, y de punta a punta hasta F-101 a F-103,
       cada hueco con su causa); los mapeos de F-102 y F-103 en `config/pit_mapeo_formatos.json` (rótulos leídos de la
       plantilla oficial) con `celdas_f102_f103`; la alineación por defecto del instante del SEIN (fin de intervalo,
       práctica observada del COES) y el PR-30 por vigencia (RCD 173-2026); el COES 2022 (año representativo de la
       empresa de prueba) y las citas con la fila real de Excel; las llamadas a nota en superíndice separadas del rótulo
       en la transcripción de los 69 formatos (desde los originales del rar, con la comprobación de su sha); F-101 por sistema eléctrico (grupos repetidos en
       el motor de plantillas, total con solo el FC). Falta correrlo
       con la medida real del año representativo
       a la topología y a las curvas, y los mapeos de F-101 a F-103 cotejados con la página renderizada.
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_demanda.py -k factores` en verde con curvas
       sintéticas de factores conocidos, y sin medida cada formato queda como plantilla con su causa.
- [ ] T29. Demanda regulatoria, 3c: F-108 (ventas proyectadas por nivel), F-109 (energía por barra con el factor de
       expansión en cascada y el FPMWHS) y F-110, F-111 y F-112 con la fórmula del art. 8.1; y el aviso que compara F-112
       con la potencia de diagnóstico por SET y año, con la diferencia en %. (Aclaración de RF-9)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_demanda.py -k cadena` en verde con una
       empresa de la fijación y otra sin fijación vigente («no transcrita», sin valores de otra), con un caso en el que
       el FE y 1+p dan resultados distintos, y con la marca «aproximado» cuando la medición centralizada no se separa.
- [ ] T30. Demanda regulatoria, 3d: los resúmenes F-119 a F-122 y F-104 a F-107 desde la proyección con exógenas de
       la spec 031; sin esa fuente, plantilla con su causa. (Aclaración de RF-9)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_demanda.py -k resumen` en verde, y
       `llenado.pendientes_de_mapeo` ya no lista ningún formato de demanda sin causa aceptada.
