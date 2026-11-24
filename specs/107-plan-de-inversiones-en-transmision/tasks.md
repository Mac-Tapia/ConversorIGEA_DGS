# Tareas — Spec 107

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Los ficheros nuevos de `src/` y `tools/` entran en `CODIGO_FUENTE.md` y en `docs/architecture/subsistemas.json` en el
mismo cambio (spec 009 y 090). Ninguna tarea toca `src/convertersmartgrid/presentacion/web/services.py`, `pide_economia.py` ni el
adaptador VNR (integrador f9).

- [x] T1. Registro normativo común con la 108 (`registro_normativo.py`, su esquema y `config/normativa/`): contrato de
      una norma con sus reglas, estados `vigente_comprobada`, `modificada`, `prepublicada`, `no_verificada` y
      `derogada`, `regla(clave, fecha)` con su estado y si es obligatoria, e `instantanea()` con la huella. Si la 108 ya
      lo creó, solo se añade lo que le falte al PIT. Dos registros sintéticos. (RF-7, RF-8, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_registro_normativo.py` en verde, con una
      regla `prepublicada` y otra `no_verificada` que salen como no obligatorias.
      Corrección (2026-11-15, f4/RN-VIG): `vigencia_hasta` es el último día de vigencia, INCLUIDO, como lo escriben
      todas las normas del registro; se comparaba como exclusiva y el último día de cada norma quedaba sin regla
      (p. ej., las horas punta del 2025-05-31). De un instante cuenta su fecha. Una norma cuyo fin no dice el texto
      lo marca en `vigencia_hasta_motivo` («fin deducido: …», con su cita): la RM 153-2021 (orden de 28).
      Corrección (2026-11-15, f4/RN-AMB): `regla(clave, fecha)` ya no oculta normas que se suman. Si varias normas
      vigentes a la vez traen la clave y la más reciente no modifica a las demás, directa ni encadenadamente
      (`modifica` / `modificada_por`), lanza `ReglaAmbigua`, que las nombra y remite a `reglas_vigentes(clave, fecha)`
      o a `regla_de_empresa`. El error por empresas de VAD-FE26 es el mismo caso, con su mensaje. `reglas_vigentes`
      da todas las vigentes, ordenadas por vigencia y sin las modificadas. Sin fecha, una norma que sucede a otra sin
      solaparse (las RM de horas punta) no es ambigua. El expediente junta la huella de cada norma de una clave que
      se suma. Pruebas en `tests/test_registro_normativo.py` y `tests/test_pit_registro.py` (107:RF-7, 107:RF-8).
      Avance (2026-11-15, f4/RN-IMP): una norma con recursos de reconsideración los lleva en `impugnada` (por
      recurrente: nombre literal, RUC si se conoce, empresa de la norma o tercero, conceptos con su cita y lo que
      `afecta`, fuente con su sha y estado), en el esquema y en `Norma`; `avisos_de_recurso(empresa, usados, fecha)`
      avisa SOLO de lo impugnado que se usa (una entrada `<clave>.<fila>` avisa en esa fila de la regla o en la regla
      entera, no en otra fila), y de un escrito de alcance no determinado con el aviso genérico. La norma sigue
      obligatoria: regla `lpag.recurso.no_suspende_ejecucion` del DS 006-2026-JUS, art. 216.1, vigente desde el
      2026-05-01 por el art. 109 de la Constitución (el decreto no trae cláusula propia), en
      `config/normativa/ds_006_2026_jus.json`. Pruebas en `tests/test_vad_recursos_185.py` (107:RF-8).
- [x] T2. Leer y transcribir en `config/normativa/` las normas del PIT ya localizadas: RCD 217-2013-OS/CD (articulado,
      COyM, tasa, vida útil y formatos que fije), RCD 112-2024-OS/CD y RCD 149-2024-OS/CD (con los anexos A y B del
      Informe Técnico 565-2024-GRT), cada una con URL, fecha de consulta, huella del PDF, estado jurídico comprobado y
      cita literal con página. Sin reglas supuestas: lo que no se lea queda sin regla. (RF-7, RF-9)
      Hecho cuando: el registro valida contra su esquema en `tests/test_registro_normativo.py`, cada regla tiene página y
      cita literal, y los cuadros oficiales del PIT tienen su definición transcrita o figuran como no transcritos.
      Corrección (2026-11-15, f4/RN-VIG2): vigencias comprobadas en el SPIJ (acceso libre; huella del texto de cada
      ficha). La 018-2018 pasa a `vigente_comprobada` desde el día siguiente a su publicación (Constitución, art. 109)
      y su N-1 de 30 MW ya obliga; la RM 496-2005 queda `modificada` por la RM 102-2010, que no toca la Tabla N° 01, y
      su error admisible por clase obliga con el mismo valor; la 242-2021 trae su fecha y sigue `no_verificada`; la
      177-2021 y la 147-2017 entran sin reglas, con sus transitorias agotadas (`rcd_217_2013_transitorias.json`).
- [x] T3. Leer y transcribir la RCD 199-2026-OS/CD cuando esté accesible (en G0 su enlace daba 404). Hasta entonces figura
      en el registro como `no_verificada` y sin reglas; al leerla se comprueba su existencia, su objeto, el área a la que
      modifica y su fecha de vigencia, y se actualizan `modifica` y `modificada_por` de la 149-2024. (RF-7, RF-8)
      Hecho cuando: la entrada de la 199-2026 tiene URL, huella, estado comprobado y sus reglas con cita literal, y
      `pytest -q tests/test_registro_normativo.py -k modificatoria` en verde con ella.
      Avance (2026-11-14, b3): leída en su edición oficial de El Peruano (14-11-2026, págs. 43-44, 2574534-1; el enlace
      del regulador sigue en 404) y transcrita en `config/normativa/rcd_199_2026.json`: modifica el PIT 2025-2029 en el
      Área de Demanda 9 y no fija vigencia propia. Los elementos modificados están en el IT 655-2026-GRT, sección 6.4,
      que da 404: quedan sin regla hasta leerlo, y la resolución complementaria que los consolide (art. 3) se registra
      al publicarse.
      Avance (2026-11-15, f4/RN-AMB): las RCD 186, 187, 188 y 189-2026-OS/CD (Áreas 1, 3, 12 y 13), leídas en sus
      ediciones del regulador y de El Peruano (19-10-2026), están transcritas en `config/normativa/rcd_186_189_2026.json`
      con sus elementos (sección 6.4 de los IT 599, 601, 597 y 595-2026-GRT). Ninguna tiene cláusula de vigencia:
      rigen desde el 20-10-2026 por el art. 109 de la Constitución, citado en cada nota. La 188-2026 desestima la
      solicitud del Área 12 y no modifica el plan. Las áreas modificadas se piden con `reglas_vigentes`: 1, 3, 9 y
      13. La 112-2024 y la 149-2024 las enlazan en `modificada_por`.
      Corrección (2026-11-15, f4/RN-AMB v2): la 199-2026 tampoco tiene cláusula de vigencia (arts. 1 a 4): rige desde
      el 15-11-2026 por el art. 109 de la Constitución, citado en su nota; ya no se deja sin `vigencia_desde`. Las
      notas que genera `tools/normativa/generar_reconsideraciones.py` citan la RCD 223-2023-OS/CD con su año, y la
      prueba de los actos comprueba que ningún texto del registro cita una RCD sin el año.
      Avance (2026-11-16, f7/PIT-ANON-ELEMENTOS, aprobada por c2): el IT 655-2026-GRT, ya legible (sha256 aec882cf…,
      código de verificación s6CFQ6sbGu), da la regla `pit.modificacion_2025_2029.elementos` del Área 9 (cuadros 6.4 a
      6.7: agregan 2, reprograman 18, eliminan 7, baja 1) y la `correccion_error_material` de su §6.5. Los titulares,
      las instalaciones y los nombres de las descripciones van por su huella en la 199 y en la 186-189; los nombres en
      claro, en la lista local (`CSG_NORMATIVA_ELEMENTOS`, fuera de git). `pit/elementos_modificacion.py` casa por
      huella con la red del usuario; `tests/test_pit_elementos_anonimos.py` es la comprobación permanente.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_pit_elementos_anonimos.py tests/test_registro_normativo.py -k modificatoria.
- [x] T4. Perfil `pit.areas` en el esquema del perfil de empresa (área, titulares, SET, correspondencia SET →
      alimentadores, tensión mínima del ámbito y asignación de los elementos compartidos) y `pit/ambito.py`, que reúne
      los elementos de un área sin mezclarla con otra. Dos perfiles sintéticos A y B en `tests/datos_pit.py`.
      (RF-2, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_ambito.py` en verde con los dos perfiles, incluido el elemento compartido
      sin asignar.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_ambito.py.
- [x] T5. Contrato `RedArea` (`pit/red_area.py`) y su adaptador del libro de la red declarado en el perfil: cada
      elemento con titular, área y fuente, y los elementos sin parámetros en `faltantes` con el dato que les falta.
      El libro se abre con `demanda_medida.abrir_libro` en cualquier formato y se leen todas sus hojas, o las que
      declare `pit.libro_red.hoja`, con la cabecera buscada por contenido. (RF-2, RF-4, RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_red_area.py` en verde, con la línea sin parámetros del perfil B nombrada y
      fuera del diagnóstico completo, el mismo libro leído igual en .xlsx y .xlsm, .xls y .xlsb por el lector común,
      un libro de varias hojas leído entero con la hoja sin contrato en los avisos, la hoja declarada respetada y un
      libro sin ninguna hoja válida detenido con sus hojas y cabeceras.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_red_area.py.
- [x] T6. De `RedArea` a pandapower (`pit/red_pandapower.py`, con transformadores de dos y tres devanados; pandapower
      directo con los parámetros de `oraculo.py`, cuyos auxiliares son privados, y de él solo `oraculo.disponible()`) y la matriz de capacidades estudio × motor (`pit/motores.py`): el motor abierto por defecto,
      DIgSILENT si hay licencia, y cada resultado nombra su motor. (RF-3, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_motores.py` en verde: el flujo de los perfiles A y B converge con
      pandapower, y el cortocircuito y `ComRel3` sin licencia salen como «no disponible con el motor abierto».
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_motores.py.
- [x] T7. Diagnóstico por año (`pit/diagnostico.py`): demanda del área desde `proyeccion_anual` por barra de SET,
      cargabilidad, tensión y N-1 de cada elemento contra los límites del registro o del perfil; el año sin demanda
      queda nombrado, sin extrapolar; trabajo cancelable entre años. (RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_diagnostico.py` en verde, con el N-1 del anillo del perfil B, el año sin
      demanda y una cancelación a mitad del horizonte.
      Avance (2026-11-15, f4/PIT-TEN): los límites de tensión salen por barra desde la norma (aclaración de RF-3 y
      RF-4): NTCSE (`config/normativa/ntcse.json`), NTCSER (`ntcser.json`), el 12.2.1.a y los niveles de la 217-2013
      (`rcd_217_2013_diagnostico.json`), el 12.3.2 vigente de la 018-2018 (`rcd_018_2018_diagnostico.json`) y la
      RM 129-2009 del SPIJ (`rm_129_2009_mem_dm.json`). `limites_de_tension` da el criterio de cada barra, las tomas
      de los AT/MT y los huecos; las referencias van como aviso al diagnóstico, al expediente y a la web. En la v2,
      el N-1 del Área 15 va con el rango normal salvo que `pit.emergencia_rm129` sustente el de emergencia. Pruebas:
      `tests/test_pit_tension_norma.py`.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_diagnostico.py.
- [x] T8. Alternativas mutuamente excluyentes (`pit/alternativas.py`): inversión con `costos_fuentes.valorar_obra`
      (ámbito `transmision`) y los módulos de `set_nueva.leer_modulos_pit`, COyM y pérdidas según el registro, valor
      actual con `pide_economia.frc` y `van`, y confiabilidad según la matriz; misma demanda y mismo motor para todas;
      una alternativa con un costo que falta queda incompleta y fuera de la comparación; una regla no vigente se usa
      como referencia y se dice. (RF-5, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_alternativas.py` en verde, con una alternativa sin costo que no queda
      primera y una tasa `no_verificada` rotulada como referencia.
      Avance (2026-11-15, f4/P-REG): el registro trae `pit.tasa_actualizacion` = 0,12 (art. 79 de la LCE, SPIJ
      consolidado al 22-03-2026, con su verificación estructurada) y `pit.coym_pct` (cuadro de la RCD 163-2021-OS/CD,
      vigente del 01-05-2021 al 30-04-2027); `pit.vida_util_anios` = 30 ya estaba (art. 24.2 de la 217-2013). El COyM
      va por elemento, ubicación, nivel y año, con huecos nombrados y el aviso del transformador elevador
      (aclaraciones de RF-5 y RF-8). Pruebas: `tests/test_pit_coym_registro.py`.
      Hecho en esta entrega (CIERRES-17-11, 4d): tests/test_pit_alternativas.py y tests/test_pit_coym_registro.py, 13 passed; junto con las demás candidatas, 424 passed sin omitidas (D:/csg/INTEGRA_54/cierre_tareas/hechas_r3.log).
- [x] T9. Programa (`pit/programa.py`): cada elemento con su año de puesta en servicio, su titular y su área, con las
      bajas y los reemplazos; un programa por titular cuando el área tiene varios. (RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_programa.py` en verde con el perfil A (un titular) y el B (varios).
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_programa.py.
- [x] T10. Expediente y cuadros (`pit/expediente.py` y `pit/cuadros.py`): carpeta aparte de la del PIDE, instantánea del
       registro al abrirlo, aviso y lista de celdas afectadas si una modificatoria llega después, traza de cada celda
       (fuente con huella, cálculo, motor y regla con su estado), cuadros desde su definición transcrita y escritos en el
       libro modelo con `libro_informe`, determinismo byte a byte, y nunca la frase «aprobado por Osinergmin».
       (RF-1, RF-7, RF-8, RF-9)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_expediente.py` en verde: dos corridas iguales dan el mismo expediente, la
       modificatoria posterior se avisa sin recalcular, y ninguna celda queda sin traza.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_expediente.py.
- [x] T11. Observaciones del regulador (`pit/observaciones.py`): número, fecha, texto, respuesta y el elemento, el caso o
       la celda a los que afecta, enlazados con la traza del expediente. (RF-10)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_observaciones.py` en verde, con una observación sobre una celda y otra
       sobre un elemento del perfil B.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_observaciones.py.
- [x] T12. Guion `tools/pit_pf.py` (con docstring en español y `--help` sin DIgSILENT): `--exportar-red` del proyecto de
       transmisión a `RedArea`, `ComLdf`, `ComSimoutage` y `ComRel3` por año, sin dejar nada cambiado
       (`estudios_red_pf.cambios_de_estado`). (RF-2, RF-3, RF-5)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_pf_guion.py` en verde con el doble `tests/fake_pf.py`.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/fake_pf.py tests/test_pit_pf_guion.py.
- [x] T13. Web: `web/rutas_pit.py` con un `APIRouter` propio (`/api/pit/…`), el diagnóstico y las alternativas como
       trabajos en cola (carril `engine` o `powerfactory`) con progreso por WebSocket, y el panel en
       `frontend/src/features/pit/` con la microcopia mínima. Solo el registro del router en `web/app.py`, pactado antes
       con f9. (RF-1, RF-2, RF-3, RF-5, RF-6, RF-9, RF-10)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_web.py` en verde, el router montado en
       `web/app.py` (lo hace el integrador con `para_f9/107_app.txt`), el panel de `frontend/src/features/pit/` con su
       carga del libro de la red (.xlsx, .xlsm, .xls y .xlsb), y `npm run lint`, `npx tsc --noEmit -p .` y
       `npm run build` sin errores. Pendiente (2026-11-14, S1): el router y su prueba existen; faltan el montaje, el
       panel, la subida del libro con su validación previa (422) y las rutas de alternativas, expediente y cuadros.
       Avance (2026-11-15, f4/P10c): el router está montado en `web/app.py`, y `POST /api/pit/expediente` arma y emite
       el expediente como trabajo del carril engine (`pit/armado.armar_expediente`), con el libro F-000, las
       alternativas del JSON del espacio, los costos de `pit.costos` y la carpeta de fuentes de `CSG_FUENTES_NORMATIVAS`,
       que el doctor comprueba. Falta el panel del PIT (P10d).
       Avance (2026-11-17, f7/P10d): la pestaña «Estudio PIT» (`frontend/src/features/pit/EstudioPit.tsx`, con
       `frontend/src/api/pit.ts`) pide el área, los años, el periodo y el motor, sube el libro de la red (.xlsx, .xlsm,
       .xls y .xlsb), la proyección y las alternativas por `POST /api/pit/entradas`, lanza el diagnóstico y el
       expediente, ofrece sus salidas para guardar (las rutas relativas al espacio que ahora devuelve cada trabajo) y
       registra las observaciones del expediente; sus trabajos avisan en su pestaña. La matriz de cobertura de las rutas
       `/api/pit/*` (llamada, control en pantalla y prueba del servidor) está en `frontend/test/pitPanel.test.mjs`.
      Hecho en esta entrega (LOTE-2): la pestaña «Estudio PIT» (features/pit/EstudioPit.tsx, api/pit.ts) con su
      matriz de cobertura (frontend/test/pitPanel.test.mjs: cada /api/pit/* con su llamada, su control en pantalla y
      su prueba de tests/test_pit_web.py); npm test 268/268, tsc, lint y build (f7).
- [ ] T14. [DIgSILENT] Corrida real sobre una **copia** del proyecto de transmisión del área del primer caso (la
       primera empresa de prueba, con el área y el titular en su perfil): exportar la red, diagnosticar un año con los dos motores y comparar
       con la tolerancia de la 112 (0,005 p.u. en tensión, 1 % en corriente). (RF-2, RF-3, RF-5)
       Hecho cuando: la evidencia de la corrida (informe y registro) queda fuera de git con su huella y las diferencias
       entre motores están dentro de la tolerancia o explicadas elemento por elemento.
       Primera corrida del 2026-11-20 (d8, bloque DIgSILENT): DIgSILENT da ComLdf con código 0 y el motor abierto no
       converge por un defecto del guion (ids por nombre, acoplamientos sin exportar, referencia en una máquina),
       corregido en T44 (RF-25). Falta repetir la corrida con el código de T44.
- [x] T15. Aceptación con datos reales autorizados por la empresa: reproducir, fila por fila, un cuadro de un PIT
       publicado para el área del primer caso, con sus diferencias explicadas. (RF-6, RF-9)
       Hecho cuando: el expediente trae el cuadro reproducido, su cuadro publicado de referencia con su huella, y cada
       diferencia con su causa.
       Nota (orden del usuario del 2026-11-19, aclaración de RF-9 y RF-10): con el expediente publicado ya descargado, no
       con datos autorizados por la empresa. Hecho (2026-11-19, wt_59_osin): `pit/reproduccion.py` lee por contenido los
       formatos publicados y reproduce F-119 a F-122 con `demanda_resumen.resumen_demanda` desde F-109 a F-112 y F-115 a
       F-118 del mismo libro; `escribir_en_expediente` no emite una diferencia sin causa. Pruebas sintéticas en
       `tests/test_pit_reproduccion_publicada.py` (rojo 10 failed por aserción, verde 10 passed). Corrida con el F-100
       publicado de la empresa de prueba (sha256 5b8982b9…40d1): F-120 a F-122, 1 452 de 1 485 celdas iguales cada uno;
       las 33 restantes (una barra de 10 kV que suma por su nombre un libre declarado a 22,9 kV), dos barras con otro
       sistema y una fila de resto de fórmula, con su causa; F-119, 132 celdas sin cifra del conversor porque un libre de
       13,8 kV no está en los niveles del 12.1.1, cada una con la causa deducida (el publicado lo suma en MT). Evidencia
       fuera de git: `D:/csg/INTEGRA_54/cierre_tareas/osinergmin/evidencia_107/`.
- [x] T16. Cotejo de una muestra de celdas por un revisor independiente, con sus observaciones registradas por la vía de
       T11. (RF-9, RF-10)
       Hecho cuando: el expediente guarda el acta del cotejo, la muestra revisada y la respuesta a cada observación.
       Nota (orden del usuario del 2026-11-19): el revisor es otro modelo en otra sesión, con origen «maestro/revisor
       independiente». Hecho (2026-11-19, wt_59_osin): `reproduccion.cotejar` rechaza el acta del propio implementador o
       sin origen, compara cada celda de la muestra con la reproducción y la registra con `observaciones.registrar`
       (afecta «celda», con su traza); pruebas en `tests/test_pit_reproduccion_publicada.py`. Corrida: acta de 37 celdas
       leídas por el revisor sin el código del conversor (`D:/csg/INTEGRA_54/cierre_tareas/osinergmin/evidencia_107/acta_cotejo_revisor.json`); las 37 lecturas
       coinciden con la reproducción, 27 conformes y 10 respondidas con su diferencia y su causa
       (`expediente/reproduccion_publicada/cotejo_*.json` y `observaciones_cotejo_*.json`).
- [x] T17. Universalidad: el paquete `pit/` y `registro_normativo.py` sin números de área, titulares, tensiones, tasas ni
       años de una empresa o un periodo. (RF-11)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_entrega_universal.py tests/test_inventario.py`
       en verde con los ficheros
       nuevos incluidos.
       Hecho (2026-11-15, S-107/108): `tools/comprobar_entrega.py` tiene `valores_fijos` (tensiones, años, tasas y
       números de área escritos en el código, sin comentarios ni docstrings), y
       `test_107_rf11_pit_y_registro_normativo_sin_valores_de_un_area_una_empresa_o_un_periodo` recorre con él cada
       fichero de `pit/` y `registro_normativo.py` y comprueba que entran en la entrega, donde la búsqueda de nombres y
       titulares de 086:RF-29 ya los recorre. Evidencia: `D:/csg/PM_IMPL/S107_108/T17/`.
- [x] T18. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
       Hecho cuando: cada RF definido en `spec.md` (`grep -oE "^- RF-[0-9]+" spec.md`, de RF-1 a RF-18) aparece en
       `grep -rnoE "107:RF-[0-9]+" tests | sort -u`, con sus pruebas en verde, y
       `.venv/Scripts/python.exe -m pytest -rfs tests/test_trazabilidad_specs.py` en verde. Depende de T13 y de T19 a
       T26.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: las del criterio.
- [x] T19. Formatos desde la norma registrada (aclaración de RF-9): transcribir en `config/normativa/` las columnas de
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
       Avance (2026-11-15, f4/delta20): las 966 celdas sombreadas de la 217-2013 («no deben ser llenadas», F-302
       nota (3)) van en cada formato como `no_llenar`, desde `tools/normativa/sombreadas_217.py`, y
       `pit/plantillas.py` las deja vacías sin hueco y da un aviso si la fuente trae un valor para ellas
       (`tests/test_pit_sombreadas.py`).
       Avance (2026-11-15, f4/delta20 v2, órdenes de 28): el generador lee los rellenos de los libros oficiales con
       xlrd (ya en el venv) y los coteja con el mapa derivado de las fuentes (sombreadas/, con su SHA256SUMS): mismas
       966 celdas sombreadas y 176 de color. El F-101 lleva como motivo el literal de su nota (2), A25. Los rellenos
       de color (cabeceras de F-305, F-306, F-401, F-510 y F-522) quedan como observación sin efecto en el llenado.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_formatos.py.
- [x] T20. Documento de absolución (aclaración de RF-10): `observaciones.escribir_absolucion`, con cada observación, su
       objeto, su respuesta y la traza de lo que cambió en el expediente (celdas o elementos, con su huella antes y
       después). (RF-10)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_observaciones.py -k absolucion` en verde:
       cada observación aparece con su objeto y su respuesta, una observación sin cambios lo dice, y una referencia
       desconocida se rechaza.
       Avance (2026-11-15, f4/P14): `observaciones.documento_absolucion` y `escribir_documento_absolucion` dan la forma
       que pide el regulador (IT 438-2024-GRT, pág. 25; plantilla del IT 599-2026-GRT, Anexo A): generales y luego
       específicas con la numeración y la secuencia del oficio, cada respuesta con su lugar corregido (sección, o
       fichero y celda con su huella), la observación sin respuesta como hueco nombrado y la evaluación del regulador
       («Análisis», «Conclusión») vacía con sus conclusiones admitidas; `absolucion` sigue igual. v2 (condiciones de
       28): el oficio intercalado se reagrupa con las generales primero y el documento lo dice («orden del oficio
       reagrupado: generales primero») con la lista de las movidas; la respuesta sin lugar se ve como «lugar
       corregido: no indicado» y sale en los huecos con campos fijos (`CAMPOS_HUECO`) para el expediente.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_observaciones.py -k absolucion.
- [x] T21. Resumen ejecutivo (`pit/informe.py`): la demanda del área por año, la alternativa elegida y el programa de
       inversiones, leídos del expediente emitido. (RF-13)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_informe.py` en verde con los perfiles A y B:
       el resumen trae sus tres apartados con las cifras del expediente, y un expediente sin alternativa elegida da un
       error que lo nombra.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_informe.py.
- [x] T22. Memoria por sección y relación de sustento (`pit/expediente.emitir`): criterios, metodología, entradas y
       resultados de cada sección, y la relación de los documentos de sustento con su descripción, su uso y su huella.
       (RF-14)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_expediente.py -k "memoria or sustento"` en
       verde: cada fichero del expediente figura en la relación con su huella, y cada sección emitida tiene su memoria.
       Avance (2026-11-15, f4/P10): la relación del num. 5.3 de la Norma Tarifas va también por volúmenes
       (`relacion_documentos.json`): n.º, fichero, tipo, descripción, aplicación y volumen con folios consecutivos sin
       reiniciar (num. 5.5), en tabla legible; lo que falta (descripción, aplicación, volumen o folios) es un hueco
       nombrado y el resumen sale «incompleto» con sus pendientes. El «F-000» es el grupo F-001 a F-003 (RCD 217-2013,
       art. 30.1), declarado como alias en `config/pit_mapeo_formatos.json`: cumplido con los tres, o el hueco «F-000
       incompleto: falta F-00x». `relacion_sustento.json` conserva su lista por fichero, con los campos nuevos.
       Avance (2026-11-15, f4/P10b): `expediente.escribir_informacion_general` escribe, antes de emitir, el libro
       `F-000-<área>_<periodo>.xlsx` con F-001 a F-003. Usa el motor de los cuadros (`cuadros.plan_de_formatos` y luego
       `libro_informe.rellenar_con_excel`, que ahora inserta filas) sobre una copia temporal de la plantilla oficial,
       comprobada por su sha256 antes y después. El libro entra en la relación del 5.3. Falta la corrida real con Excel
       o WPS.
       Hecho (2026-11-15, S-107/108): el código ya está en la punta e182c823 (`expediente.emitir` escribe `memoria.json`
       y `relacion_sustento.json`); sus pruebas son `test_memoria_de_cada_seccion`,
       `test_sin_diagnostico_ni_alternativas_la_memoria_no_inventa_secciones` y
       `test_relacion_de_sustento_con_cada_fichero_y_su_huella`. Evidencia: `D:/csg/PM_IMPL/S107_108/MARCAS/`.
- [x] T23. Unifilar en DXF por alternativa y año, con el flujo de cada línea (F-212), y en DWG con el ODA File Converter
       si la configuración o el PATH lo dan, nunca por una ruta fija (`pit/unifilar.py`). (RF-15)
       Avance (2026-11-15, f4): desbloqueada. El auditor 28 instaló `ezdxf` 1.4.5 (MIT) en el entorno, por orden del
       usuario («instala lo que falta, pero avanza»), y queda declarada como dependencia obligatoria con versión fijada
       en `pyproject.toml`, `requirements.txt`, `constraints-python312-win.txt` y `requirements-nucleo.lock`, con la
       huella de su rueda y las de fonttools y pyparsing. Código: `pit/unifilar.py` escribe un espacio papel A3 por
       alternativa y año con el marco, el rótulo del F-212 y los datos que pide el art. 37 de la 217-2013 (pdf pág. 64):
       transformadores con MVA, relación, Vcc, taps y P y Q; líneas con longitud, material, sección y P y Q; barras con
       tensión nominal y calculada; cargas con P y Q, y el año de ingreso de lo nuevo con la convención de colores que la
       norma pide «de preferencia». El flujo de cada elemento lo da el motor abierto (`ResultadoFlujo.flujos`). Lo que
       falta se rotula «sin dato» y se avisa. Devuelve ficheros, avisos y sustento para el manifiesto; la conexión con
       `pit/expediente.py` es de f4. Se marca al correr su verde.
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_unifilar.py` en verde: ezdxf, como lector
       independiente, abre el DXF y encuentra el marco A3, una hoja por alternativa y año y las barras, los
       transformadores y las líneas con su flujo; la ruta del convertidor sale del perfil o del PATH (ninguna fija en el
       código, ningún binario en el repositorio); la conversión a DWG se prueba con un doble del convertidor; con el
       doble ausente y con el doble que falla la entrega queda completa con el DXF, el aviso que dice cómo obtener el
       DWG está en el manifiesto del expediente y no queda ningún DWG vacío.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_unifilar.py.
- [x] T24. Transformadores de reserva (`pit/reserva.py`) con el procedimiento vigente del registro. Bloqueada por datos
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
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_reserva.py.
- [x] T25. Modificación del plan vigente: modo `modificacion` del expediente, que compara el programa vigente con el
       nuevo y lista lo que se elimina, cambia o agrega, con su razón, con la demanda y las alternativas rehechas con los
       mismos criterios. (RF-17)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_programa.py tests/test_pit_expediente.py
       -k modificacion` en verde: dos programas sintéticos (perfiles A y B) dan la lista de diferencias con su razón, un
       cambio sin razón es un error que lo nombra, y el expediente de la modificación no se emite con otros criterios
       que los del vigente ni sobre su misma carpeta.
       Hecho (2026-11-15, S-107/108): el código ya está en la punta e182c823 (`programa.comparar_programas` y el modo
       `modificacion` de `expediente.emitir`); sus pruebas son las dos `test_modificacion_*` de test_pit_programa.py y las
       dos de test_pit_expediente.py. Evidencia: `D:/csg/PM_IMPL/S107_108/MARCAS/`.
- [x] T26. Formato F-208 con la estadística de fallas y los índices de desempeño de las fuentes importadas
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
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_formatos.py -k f208.
- [x] T27. Demanda regulatoria, 3a: las reglas de la cadena (fórmula del art. 8.1, definiciones de FC, FCP y FS) y las
       pérdidas estándar de la fijación del VAD vigente por empresa y periodo en el registro (la 187-2023 modificada
       por la 223-2023 para las 11 empresas de esa fijación), con la comprobación permanente del cargador (FE ≥ 1 y
       FE = 1/(1−p)) y la cruzada contra el informe técnico de la fijación; y el motor de plantillas con series anuales
       cuyo horizonte sale de la norma. (Aclaración de RF-9; RF-7, RF-11)
       Avance (2026-11-15, f4/VAD-FE26): la tabla de FE se elige por empresa entre las fijaciones vigentes
       (`regla_de_empresa`): del 2026-11-01 el grupo 1 toma la RCD 185-2026 y el grupo 2 la 223-2023 hasta el
       2027-10-31; la 187-2023 y la 223-2023 llevan esa vigencia, y el expediente fija la huella de cada fijación.
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
       Hecho (2026-11-15, S-107/108): el código ya está en la punta e182c823 (delta8 y delta13). Los rojos de la tabla
       desplazada, del porcentaje mal leído y del FE < 1 son los casos de
       `test_tabla_de_factores_mal_transcrita_falla_nombrando_la_fila`, y los dos horizontes de norma, los de
       `test_serie_en_columnas_sale_del_horizonte_de_la_norma`. Evidencia: `D:/csg/PM_IMPL/S107_108/MARCAS/`.
- [x] T28. Demanda regulatoria, 3b: F-102 desde la medida del año representativo (días de máxima del sistema, de la
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
       Avance (2026-11-15, f4/RN-VIG2): la RM 496-2005-MEM/DM, comprobada en el SPIJ, queda `modificada` por la RM
       102-2010-MEM-DM, que no toca la Tabla N° 01: el error admisible por clase obliga ya, con el mismo valor.
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_demanda.py -k factores` en verde con curvas
       sintéticas de factores conocidos, y sin medida cada formato queda como plantilla con su causa.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pit_demanda.py -k factores.
- [x] T29. Demanda regulatoria, 3c: F-108 (ventas proyectadas por nivel), F-109 (energía por barra con el factor de
       expansión en cascada y el FPMWHS) y F-110, F-111 y F-112 con la fórmula del art. 8.1; y el aviso que compara F-112
       con la potencia de diagnóstico por SET y año, con la diferencia en %. (Aclaración de RF-9)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_demanda.py -k cadena` en verde con una
       empresa de la fijación y otra sin fijación vigente («no transcrita», sin valores de otra), con un caso en el que
       el FE y 1+p dan resultados distintos, y con la marca «aproximado» cuando la medición centralizada no se separa.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_pit_demanda.py -k cadena.
- [x] T30. Demanda regulatoria, 3d: los resúmenes F-119 a F-122 y F-104 a F-107 desde la proyección con exógenas de
       la spec 031; sin esa fuente, plantilla con su causa. (Aclaración de RF-9)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_demanda.py -k resumen` en verde, y
       `llenado.pendientes_de_mapeo` ya no lista ningún formato de demanda sin causa aceptada.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_pit_demanda.py -k resumen.
- [x] T31. Entradas del PIT desde las fuentes de la empresa: `/api/pit/diagnostico` y `/api/pit/expediente` aceptan
       `fuente_red_area`, `fuente_proyeccion` y `fuente_alternativas` (o la ruta, como antes), y sin ninguna toman la
       vigente de la empresa, salvo las alternativas; la pestaña «Estudio PIT» las elige con `ElegirFuente` y sube por
       `/fuentes`; `/api/pit/areas` dice la empresa del perfil para el aviso de la red del espacio. (RF-19)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_web.py` en verde; `frontend/test/pitPanel.test.mjs`
       y `npm test`, `npm run lint`, `npx tsc --noEmit -p .` y `npm run build` sin errores.
       Hecho en ecad83ea (LOTE-4, PIT-ESPACIO); pruebas: tests/test_pit_web.py frontend/test/pitPanel.test.mjs.
- [x] T32. La norma del PIT desde el registro: `pit/norma.py` lee los años de la programación, el horizonte, el factor
       de potencia de las barras de MT, la demanda mínima del N-1 y las reglas de la comparación; `diagnosticar` y
       `evaluar` las aplican con `registro` y el expediente las cita en `reglas_aplicadas.json`. (RF-20)
       Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_pit_norma.py` y los `tests/test_pit_*.py` en
       verde.
       Hecho en ecad83ea (LOTE-4, PIT-NORMA); pruebas: tests/test_pit_norma.py tests/test_pit_*.py.
- [x] T33. Biblioteca normativa general (`biblioteca_normativa.py`): cargar_biblioteca, huella_biblioteca y
      ruta_capa_usuario. (RF-21)
      Hecho cuando: `pytest tests/test_biblioteca_normativa.py` en verde. Hecho en esta entrega (BIBLIOTECA, 4d): 4 passed.
- [x] T34. La biblioteca con los vínculos entre módulos citados de la norma: el DS 028-2021-EM (VAD sobre la empresa
      modelo, arts. 63, 64 y 67 de la LCE; PIDE del DL 1208 con sus criterios detrás de la fijación del VAD) y la
      RCD 242-2021-OS/CD comprobada con su texto de El Peruano (solo las SCT reasignadas por el DS 018-2021-EM). (RF-21)
      Hecho cuando: `pytest tests/test_biblioteca_normativa.py tests/test_pit_registro.py` en verde. Hecho en esta
      entrega (DATASET-NORMATIVO-1, 4d).
- [x] T35. La biblioteca actualizable desde la consola y como dataset: `agregar_norma` (valida y copia a la capa del
      usuario; lo que no valida no se queda), `exportar_dataset` (normas.jsonl y reglas.jsonl, por huella) y
      `tools/normativa/biblioteca.py` (listar, agregar, exportar). (RF-21)
      Hecho cuando: `pytest tests/test_biblioteca_normativa.py` en verde. Hecho en esta entrega (DATASET-NORMATIVO-2, 4d).
- [x] T36. La pestaña «Biblioteca normativa» en la web: GET /api/normativa (lo que obliga en la fecha),
      GET /api/normativa/reglas (las reglas con su cita) y POST /api/normativa (a la capa del usuario; lo que no
      valida no entra). (RF-21)
      Hecho cuando: `pytest tests/test_normativa_web.py` y `node --test frontend/test/normativaPanel.test.mjs` en
      verde. Hecho en esta entrega (DATASET-NORMATIVO-3W, 4d).
- [x] T37. El vínculo VNR → VAD de la LCE en la biblioteca, citado: el art. 70 en la redacción del DL 1221 (TIR de
      25 años con el VNR, residual cero) y los arts. 71 (banda de 4 puntos) y 77 (VNR cada 4 años). (RF-21)
      Hecho cuando: `pytest tests/test_biblioteca_normativa.py` en verde. Hecho en esta entrega (DATASET-NORMATIVO-4, 4d).
- [x] T38. El catálogo técnico nacional e internacional en la biblioteca (CNE Suministro y Utilización, NTP 370.400,
      IEC 60076, 60287 y 60909, IEEE 1366 y 519): solo de referencia y sin verificar, con quién la usa; no obliga ni
      da reglas hasta que se registre su texto leído. (RF-21)
      Hecho cuando: `pytest tests/test_biblioteca_normativa.py` en verde. Hecho en esta entrega (DATASET-NORMATIVO-5, 4d).
- [x] T39. La base normativa del PIDE en la biblioteca, con su texto oficial y su huella: el DL 1208 (distribuidoras de
      FONAFE, estudio antes de cada fijación del VAD, PIDE en sus anualidades) y su reglamento, el DS 023-2016-EM
      (horizonte de 20 años, anualidad con 30 años y la tasa del art. 79 de la LCE, criterios que aprueba el MINEM); el
      DS 027-2018-EM como derogado (DS 028-2018-EM y DS 029-2018-EM) y la RM 428-2017-MEM/DM como prepublicada.
      (RF-21; 109:RF-26)
      Hecho cuando: `pytest tests/test_biblioteca_normativa.py` en verde. Hecho en esta entrega (DSN-6-PIDE, f7).
- [x] T40. Regenerar un registro de la biblioteca desde su fuente oficial descargada: huella comprobada antes, libros en
      copia y sin COM, comparación con el vigente (reglas que entran, salen o cambian) y vigencia del texto de la norma.
      (RF-22)
      Hecho cuando: rojo por aserción (sin regeneración) y verde con `tests/test_asistente_026_normativa.py`
      (`GET /api/normativa/fuentes`, `POST /api/normativa/regenerar` y `/regenerar/{token}/aplicar`: la vista previa
      corre el generador en una carpeta temporal, no toca la biblioteca y dice qué reglas entran, salen o cambian; aplicar
      escribe en la capa del usuario solo si la biblioteca no cambió), `test_biblioteca_normativa` y `test_pit_sombreadas`.
- [x] T41. Perfil sin áreas del PIT (revisión web del 19-11, W2): `GET /api/pit/areas` da 200 con `areas` vacía y
      su motivo. (RF-19)
      Hecho cuando: `tests/test_revision_web_estados.py` (107:RF-19) en verde con rojo previo por aserción. Hecho en esta
      entrega (ce): rojo VALIDO y verde 41 passed en `D:/csg/PM_IMPL/REVISION_WEB/w2/`.
- [x] T42. El PIT con DIgSILENT desde la web: `crear_router` recibe la disponibilidad real (`services.digsilent_disponible`)
      y `services.guion_pf` con `tools/pit_pf.py`; las rutas del diagnóstico y del expediente encolan el guion en el
      carril `powerfactory` en vez del 409; `pit/motores.py` arma el plan (`plan_pf`) y lee el informe
      (`leer_informe_pf`); `EstudioPit.tsx` ofrece DIgSILENT si está disponible. (RF-23)
      Hecho cuando: rojo por aserción y verde con su prueba: `tests/test_motores_web_mej4.py` (107:RF-23) y las vecinas
      `tests/test_pit_web.py`, `tests/test_pit_motores.py`, `tests/test_pit_pf_guion.py` y `frontend/test/pitPanel.test.mjs`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T43. El diagnóstico que no converge o queda incompleto lo dice la cola: `estado_trabajo` «no_converge» o
      «parcial» con su motivo (`motores.estado_de_trabajo`), con los dos motores; la pestaña enseña el resultado y su
      motivo también en esos estados. (RF-24)
      Hecho cuando: rojo por aserción y verde con su prueba: `tests/test_motores_web_mej4.py` (107:RF-24) y
      `tests/test_pit_web.py`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T44. Ids únicos, acoplamientos y máquina de referencia en la red de transmisión (corrida de T14 del 20-11):
      `tools/pit_pf.py` da a cada elemento su ruta desde la red como id (`_id`) y las mismas claves en `_ejecutar` y
      `estado`; exporta los `ElmCoup` como `union` con su estado y la máquina de referencia (`ip_ctrl`) como red externa
      SL; `red_area` acepta la `union`, y `red_pandapower` une sus barras y mete la red externa PQ o PV con su consigna
      (`inyecciones_externas`). (RF-25)
      Hecho cuando: rojo por aserción y verde con sus pruebas: `tests/test_pit_pf_guion.py` (107:RF-25), con dos
      subestaciones sintéticas de barras con el mismo nombre, acoplamientos y la referencia en una máquina, el flujo
      abierto converge y empareja por id con el ComLdf del doble.
      Hecho el 2026-11-20 (d8, fila MEJ22): rojo sobre la base y verde en D:/csg/PM_IMPL/MEJ22_PIT/.
- [x] T45. Ramas serie en la red de transmisión (corrida de T14 del 21-11): `tools/pit_pf.py` exporta los `ElmScap` y
      los `ElmSind` en servicio como `serie` con `r_ohm` y `x_ohm` (la del condensador, negativa); `red_area` acepta la
      `serie` y la deja en faltantes sin su reactancia, y `red_pandapower` la monta como impedancia. (RF-26)
      Hecho cuando: rojo por aserción sobre 7ed2c05d y verde con `tests/test_pit_pf_guion.py` (107:RF-26): una
      subestación que solo llega por un condensador serie tiene tensión, y una reactancia serie sale con su R y su X.
- [x] T46. Unidades, paralelos, cubículos, tomas y compensaciones en la red de transmisión (corrida de T14 del 22-11):
      `tools/pit_pf.py` convierte `cline` por su unidad, lleva `f_hz`, `paralelo`, las tomas y `abierto_en`, omite lo
      fuera de servicio y da a la compensación su `Qact` (inductiva si `shtype` 1); `red_pandapower` usa la frecuencia,
      los paralelos (los trafo3, por su potencia), las tomas y abre los lados de `abierto_en`. (RF-27)
      Hecho cuando: rojo por aserción sobre 7ed2c05d + DIG2-SERIE y verde con `tests/test_pit_pf_guion.py` (107:RF-27).
- [x] T47. SVC y desfases de grupo en la red de transmisión (corrida de T14 del 22-11): `tools/pit_pf.py` exporta los
      `ElmSvs` como `red_externa` PV (`p_mw` 0, `vm_pu` = `usetp`, `q_min_mvar`/`q_max_mvar`) y `shift_degree`,
      `shift_mv_degree` y `shift_lv_degree` (`_desfase`, `_desfases_tr3`); `red_pandapower` los lleva a pandapower y
      calcula con ángulos si hay desfase. (RF-28)
      Hecho cuando: rojo por aserción sobre el acumulado DIG2-SERIE + DIG2-UNIDADES y verde con
      `tests/test_pit_pf_guion.py` (107:RF-28).
- [x] T48. Nominal común por zona galvánica en el motor abierto (corrida de T14 del 22-11): `red_pandapower.nominales_comunes`
      da a cada barra la nominal de su zona (líneas, acoplamientos y ramas serie); `_red` crea las barras con ella, pasa
      las consignas de las redes externas y de los PV y la Q de las compensaciones desde la nominal propia, y `calcular`
      devuelve la tensión en la nominal propia. (RF-29)
      Hecho cuando: rojo por aserción sobre N5 + UNIDADES + SVC y verde con `tests/test_pit_pf_guion.py` (107:RF-29).
- [x] T49. Impedancia dependiente de la toma del trafo de tres devanados (corrida de T14 del 22-11):
      `tools/pit_pf._vk_tr3` exporta las vk y vkr de cada par en la toma del trafo cuando `itapzdep` = 1
      (`uktr3mn_*`/`uktr3mx_*`, `uktrr3mn_*`/`uktrr3mx_*`, interpolación lineal desde el neutro), y la vkr de
      cada par sobre la potencia del par (`_potencia_del_par`). (RF-30)
      Hecho cuando: rojo por aserción sobre N5 + UNIDADES + SVC + VN y verde con `tests/test_pit_pf_guion.py`
      (107:RF-30).
      Hecho en DIG2-T3MT (22-11): rojo por aserción (rojo_130305) y verde (verde_codigo_130310).
- [x] T50. Control de tensión de máquinas y SVC en el motor abierto (corrida de T14 del 22-11): `tools/pit_pf.py`
      exporta las ElmSym/ElmGenstat con `av_mode` «constv» como PV (usetp, pgini por ngnum, c:Qmin/c:Qmax) y los
      SVC con su `barra_control` (p_rem), sus límites resueltos o como PQ (i_ctrl 2); `red_pandapower` aplica
      `enforce_q_lims`, el control remoto (`_control_remoto`) y una consigna por barra (`_una_consigna_por_barra`).
      (RF-31)
      Hecho cuando: rojo por aserción sobre N7 + T3MT y verde con `tests/test_pit_pf_guion.py` y
      `tests/test_interactive_architecture.py` (107:RF-31).
      Hecho en DIG2-SVCCTRL (22-11): rojo por aserción (rojo_133510 y rojo_b_133818) y verde (verde_codigo_134230).
- [x] T51. Controladores de estación en el motor abierto (corrida de T14 del 22-11): `tools/pit_pf._estacion`
      da a la máquina PV el nudo y la consigna de su ElmStactrl (c_pstac, i_ctrl 0, rembar, usetp);
      `red_pandapower` fija la consigna si el nudo es la barra de la máquina y reparte el ajuste del control
      remoto entre las máquinas del mismo nudo. (RF-32)
      Hecho cuando: rojo por aserción sobre N7 + T3MT + SVCCTRL y verde con `tests/test_pit_pf_guion.py` y
      `tests/test_interactive_architecture.py` (107:RF-32).
      Hecho en DIG2-STACTRL (22-11): rojo por aserción (rojo_135028) y verde (verde_codigo_135556).
- [x] T52. La solución de tensión alta en el motor abierto (corrida de T14 del 22-11): `red_pandapower._solucion_alta`
      repite el flujo por continuación de la carga (0,5; 0,75; 1) si quedan barras por debajo de 0,8 p.u. y se
      queda con la de mayor tensión mínima, con aviso. (RF-33)
      Hecho cuando: rojo por aserción sobre N7 + T3MT + SVCCTRL + STACTRL y verde con `tests/test_pit_pf_guion.py`
      y `tests/test_interactive_architecture.py` (107:RF-33).
      Hecho en DIG2-INICIO (22-11): rojo por aserción (rojo_141141) y verde (verde_codigo_142148).
- [x] T53. Estatismo de los SVC por el punto de operación resuelto (corrida de T14 del 22-11): `tools/pit_pf.py`
      exporta como consigna del SVC con estatismo la tensión resuelta de su nudo (m:u) con `estatismo_aproximado`,
      y `red_pandapower` lo avisa. (RF-34)
      Hecho cuando: rojo por aserción sobre N7 + T3MT + SVCCTRL + STACTRL + INICIO y verde con
      `tests/test_pit_pf_guion.py` y `tests/test_interactive_architecture.py` (107:RF-34).
      Hecho en DIG2-DROOP (22-11): rojo por aserción (rojo_143133) y verde (verde_codigo_143340).
- [x] T54. Conductancia de las líneas (corrida de T14 del 22-11): `tools/pit_pf._conductancia_us_km` exporta el
      gline del tipo como `g_us_per_km` y `red_pandapower` lo pasa a la línea de pandapower. (RF-35)
      Hecho cuando: rojo por aserción sobre N7 + T3MT + SVCCTRL + STACTRL + INICIO + DROOP y verde con
      `tests/test_pit_pf_guion.py` y `tests/test_interactive_architecture.py` (107:RF-35).
      Hecho en DIG2-GLINE (22-11): rojo por aserción (rojo_150015) y verde (verde_codigo_150222).
- [x] T55. Corriente nominal de la línea con su fline (corrida de T14 del 22-11): `tools/pit_pf._corriente_nominal_ka`
      exporta sline · fline como `max_i_ka`. (RF-36)
      Hecho cuando: rojo por aserción sobre la base de GLINE y verde con `tests/test_pit_pf_guion.py` y
      `tests/test_interactive_architecture.py` (107:RF-36).
      Hecho en DIG2-FLINE (22-11): rojo por aserción (rojo_152556) y verde (verde_codigo_152724).
- [x] T56. Potencia de referencia de la cargabilidad del trafo3 (corrida de T14 del 22-11):
      `tools/pit_pf._potencia_de_carga_tr3` exporta `sn_carga_*_mva` y `red_pandapower._cargabilidad_tr3` carga
      sobre ella. (RF-37)
      Hecho cuando: rojo por aserción sobre la base de FLINE y verde con `tests/test_pit_pf_guion.py` y
      `tests/test_interactive_architecture.py` (107:RF-37).
      Hecho en DIG2-RATFAC (22-11): rojo por aserción (rojo_154320) y verde (verde_codigo_154909).
- [x] T57. Rama del devanado con toma en ohmios en el trafo3 con la toma en el punto estrella (corrida de T14 del
      22-11): `tools/pit_pf._impedancia_fija_en_ohmios` corrige las vk y vkr que exporta `_vk_tr3` con itapos = 0.
      (RF-38)
      Hecho cuando: rojo por aserción sobre la base de RATFAC y verde con `tests/test_pit_pf_guion.py` y
      `tests/test_interactive_architecture.py` (107:RF-38).
      Hecho en DIG2-TOMAZ (22-11): rojo por aserción (rojo_195414) y verde (verde_195420).
- [x] T58. Q de la compensación en la nominal de su barra (corrida de T14 del 22-11): `tools/pit_pf.exportar_red`
      escala la Qact de cada `ElmShnt` por (kV de la barra / ushnm)² cuando su nominal propia es otra. (RF-39)
      Hecho cuando: rojo por aserción sobre b5e0c45f y verde con `tests/test_pit_pf_guion.py` (107:RF-39); fuera de
      línea, con la última exportación de T14, las barras fuera de 0,005 p.u. bajan de 81 a 20.
      Hecho en DIG2-USHNM (d8, 23-11): rojo por aserción (N10_SINCODEX/USHNM/rojo_071714.log) y verde; fuera de línea
      DIG_BLOQUE2/T14_pit/ushnm/exp_rf39.json (81 → 20 barras, 20 → 17 ramas).
- [x] T59. Estatismo de los controladores de estación (corrida de T14 del 22-11): `tools/pit_pf._estacion` da a las
      máquinas de un controlador con i_droop 1 y ddroop > 0 la tensión resuelta de su nudo (m:u) como consigna, marcada
      `estatismo_aproximado`. (RF-40)
      Hecho cuando: rojo por aserción sobre b5e0c45f + DIG2-USHNM y verde con `tests/test_pit_pf_guion.py`
      (107:RF-40); fuera de línea, las barras fuera de 0,005 p.u. bajan de 20 a 12.
      Hecho en DIG2-STADROOP (d8, 23-11): rojo por aserción (N10_SINCODEX/USHNM/rojo_stadroop_072445.log) y verde;
      fuera de línea DIG_BLOQUE2/T14_pit/ushnm/exp_rf40.json (12 barras y 13 ramas fuera).
- [x] T60. SVC en control de Q por su controlador de estación (corrida de T14 del 22-11): `tools/pit_pf.exportar_red`
      busca el controlador de cada `ElmSvs` (c_pstac o psym de los `ElmStactrl`) y, con i_ctrl 1, lo exporta PQ con
      −m:Q. (RF-41)
      Hecho cuando: rojo por aserción sobre el código de T59 y verde con `tests/test_pit_pf_guion.py` (107:RF-41);
      fuera de línea, las barras fuera de 0,005 p.u. bajan de 12 a 6.
      Hecho en DIG2-SVCQ (d8, 23-11): rojo por aserción (N10_SINCODEX/USHNM/rojo_svcq_073257.log) y verde; fuera de
      línea DIG_BLOQUE2/T14_pit/ushnm/exp_rf41_-1.json (6 barras y 11 ramas fuera; HORNO ACER 33 0,9819 frente a
      0,982).
- [x] T61. La compensación por su admitancia resuelta (corrida de T14 del 22-11): `tools/pit_pf.exportar_red` da a
      cada `ElmShnt` −m:Q/u² cuando el flujo está hecho. (RF-42)
      Hecho cuando: rojo por aserción sobre el código de T60 y verde con `tests/test_pit_pf_guion.py` (107:RF-42);
      fuera de línea, las barras fuera de 0,005 p.u. bajan de 6 a 3.
      Hecho en DIG2-SHNTY (d8, 23-11): rojo por aserción (N10_SINCODEX/USHNM/rojo_shnty_081202.log) y verde; fuera de
      línea DIG_BLOQUE2/T14_pit/ushnm/exp_rf42.json (3 barras y 9 ramas fuera).
