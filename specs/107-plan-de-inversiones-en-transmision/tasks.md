# Tareas — Spec 107

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Los ficheros nuevos de `src/` y `tools/` entran en `CODIGO_FUENTE.md` y en `docs/architecture/subsistemas.json` en el
mismo cambio (spec 009 y 090). Ninguna tarea toca `src/convertersmartgrid/web/services.py`, `pide_economia.py` ni el
adaptador VNR (integrador f9).

- [ ] T1. Registro normativo común con la 108 (`registro_normativo.py`, su esquema y `config/normativa/`): contrato de
      una norma con sus reglas, estados `vigente_comprobada`, `modificada`, `prepublicada`, `no_verificada` y
      `derogada`, `regla(clave, fecha)` con su estado y si es obligatoria, e `instantanea()` con la huella. Si la 108 ya
      lo creó, solo se añade lo que le falte al PIT. Dos registros sintéticos. (RF-7, RF-8, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_registro_normativo.py` en verde, con una
      regla `prepublicada` y otra `no_verificada` que salen como no obligatorias.
- [ ] T2. Leer y transcribir en `config/normativa/` las normas del PIT ya localizadas: RCD 217-2013-OS/CD (articulado,
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
- [ ] T4. Perfil `pit.areas` en el esquema del perfil de empresa (área, titulares, SET, correspondencia SET →
      alimentadores, tensión mínima del ámbito y asignación de los elementos compartidos) y `pit/ambito.py`, que reúne
      los elementos de un área sin mezclarla con otra. Dos perfiles sintéticos A y B en `tests/datos_pit.py`.
      (RF-2, RF-11)
      Hecho cuando: `pytest -q tests/test_pit_ambito.py` en verde con los dos perfiles, incluido el elemento compartido
      sin asignar.
- [ ] T5. Contrato `RedArea` (`pit/red_area.py`) y su adaptador del libro de la red declarado en el perfil: cada
      elemento con titular, área y fuente, y los elementos sin parámetros en `faltantes` con el dato que les falta.
      (RF-2, RF-4)
      Hecho cuando: `pytest -q tests/test_pit_red_area.py` en verde, con la línea sin parámetros del perfil B nombrada y
      fuera del diagnóstico completo.
- [ ] T6. De `RedArea` a pandapower (`pit/red_pandapower.py`, con transformadores de dos y tres devanados y los auxiliares
      de `oraculo.py`) y la matriz de capacidades estudio × motor (`pit/motores.py`): el motor abierto por defecto,
      DIgSILENT si hay licencia, y cada resultado nombra su motor. (RF-3, RF-5)
      Hecho cuando: `pytest -q tests/test_pit_motores.py` en verde: el flujo de los perfiles A y B converge con
      pandapower, y el cortocircuito y `ComRel3` sin licencia salen como «no disponible con el motor abierto».
- [ ] T7. Diagnóstico por año (`pit/diagnostico.py`): demanda del área desde `proyeccion_anual` por barra de SET,
      cargabilidad, tensión y N-1 de cada elemento contra los límites del registro o del perfil; el año sin demanda
      queda nombrado, sin extrapolar; trabajo cancelable entre años. (RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_pit_diagnostico.py` en verde, con el N-1 del anillo del perfil B, el año sin
      demanda y una cancelación a mitad del horizonte.
- [ ] T8. Alternativas mutuamente excluyentes (`pit/alternativas.py`): inversión con `costos_fuentes.valorar_obra`
      (ámbito `transmision`) y los módulos de `set_nueva.leer_modulos_pit`, COyM y pérdidas según el registro, valor
      actual con `pide_economia.frc` y `van`, y confiabilidad según la matriz; misma demanda y mismo motor para todas;
      una alternativa con un costo que falta queda incompleta y fuera de la comparación; una regla no vigente se usa
      como referencia y se dice. (RF-5, RF-8)
      Hecho cuando: `pytest -q tests/test_pit_alternativas.py` en verde, con una alternativa sin costo que no queda
      primera y una tasa `no_verificada` rotulada como referencia.
- [ ] T9. Programa (`pit/programa.py`): cada elemento con su año de puesta en servicio, su titular y su área, con las
      bajas y los reemplazos; un programa por titular cuando el área tiene varios. (RF-6)
      Hecho cuando: `pytest -q tests/test_pit_programa.py` en verde con el perfil A (un titular) y el B (varios).
- [ ] T10. Expediente y cuadros (`pit/expediente.py` y `pit/cuadros.py`): carpeta aparte de la del PIDE, instantánea del
       registro al abrirlo, aviso y lista de celdas afectadas si una modificatoria llega después, traza de cada celda
       (fuente con huella, cálculo, motor y regla con su estado), cuadros desde su definición transcrita y escritos en el
       libro modelo con `libro_informe`, determinismo byte a byte, y nunca la frase «aprobado por Osinergmin».
       (RF-1, RF-7, RF-8, RF-9)
       Hecho cuando: `pytest -q tests/test_pit_expediente.py` en verde: dos corridas iguales dan el mismo expediente, la
       modificatoria posterior se avisa sin recalcular, y ninguna celda queda sin traza.
- [ ] T11. Observaciones del regulador (`pit/observaciones.py`): número, fecha, texto, respuesta y el elemento, el caso o
       la celda a los que afecta, enlazados con la traza del expediente. (RF-10)
       Hecho cuando: `pytest -q tests/test_pit_observaciones.py` en verde, con una observación sobre una celda y otra
       sobre un elemento del perfil B.
- [ ] T12. Guion `tools/pit_pf.py` (con docstring en español y `--help` sin DIgSILENT): `--exportar-red` del proyecto de
       transmisión a `RedArea`, `ComLdf`, `ComSimoutage` y `ComRel3` por año, sin dejar nada cambiado
       (`estudios_red_pf.cambios_de_estado`). (RF-2, RF-3, RF-5)
       Hecho cuando: `pytest -q tests/test_pit_pf_guion.py` en verde con el doble `tests/fake_pf.py`.
- [ ] T13. Web: `web/rutas_pit.py` con un `APIRouter` propio (`/api/pit/…`), el diagnóstico y las alternativas como
       trabajos en cola (carril `engine` o `powerfactory`) con progreso por WebSocket, y el panel en
       `frontend/src/features/pit/` con la microcopia mínima. Solo el registro del router en `web/app.py`, pactado antes
       con f9. (RF-1, RF-2, RF-3, RF-5, RF-6, RF-9, RF-10)
       Hecho cuando: `pytest -q tests/test_pit_web.py` en verde, y `npm run build` sin errores.
- [ ] T14. [DIgSILENT] Corrida real sobre una **copia** del proyecto de transmisión del área del primer caso (Electro
       Dunas, con el área y el titular en su perfil): exportar la red, diagnosticar un año con los dos motores y comparar
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
       Hecho cuando: `pytest -q tests/test_entrega_universal.py tests/test_inventario.py` en verde con los ficheros
       nuevos incluidos.
- [ ] T18. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
       Hecho cuando: `grep -rnoE "107:RF-[0-9]+" tests | sort -u` lista de RF-1 a RF-11.
