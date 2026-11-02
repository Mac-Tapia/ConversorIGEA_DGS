# Tareas — Spec 060

- [x] T1. Independencia y genealogía PINN. (RF-1, RF-2, RF-3)
      Hecho cuando: pruebas reproducen rechazo previo al ajuste, separación por familia, registro de IDs y rechazo de herencia contaminada; regresiones afectadas pasan.
- [x] T2. Política del corpus con custodia estable. (RF-4)
      Hecho cuando: modificar el original no altera la copia; modificar la copia falla; corpus nuevo auditado contra fuentes reales, sin reemplazar el anterior.
- [x] T3. Lectura temporal y manifiesto reproducible. (RF-5, RF-6)
      Hecho cuando: fechas reales soportadas, errores con localizador y pruebas de configuración/historial pasan; se informa el resultado del libro real sin imputación.
- [x] T4. Estado heredado explícito en consulta web. (RF-7)
      Hecho cuando: pruebas distinguen registro y punteros heredados, incluido candidato rechazado con heredado promovido; lectura no modifica pesos ni promueve.
- [x] T5. Regresión y entrega de evidencias. (RF-1 a RF-8)
      Hecho cuando: pruebas afectadas pasan sin omisiones y el informe enumera cambios, campañas reales y límites pendientes.
- [x] T6. Alcance temporal explícito y ensayo con observaciones. (RF-8)
      Hecho cuando: pruebas verifican límites, selección y procedencia sin omitir defectos interiores; se ejecuta una campaña sobre enero2025 de la hoja L-TM105, conservando configuración y métricas reales, y se informa ajuste/reapertura o el bloqueo efectivo de recursos.

## Evidencia

T2: corpus nuevo `output/alumno_llm_referencias_20261101/corpus_sellado_v5`, huella
`03ac1705e1b8f48b09acfb16541e653683ca0675b4ba8f3b7614c9620383fcbe`,
1.734/54/54/200 registros; auditoría real de 96 contextos y 11 fuentes satisfactoria.
Tres órdenes humanas siguen reservadas. V4 se conserva sin alterar sus hashes.

T3: `lectura_registro_reales.xml`: 122 pruebas aprobadas con `CSG_DEMANDA_DIR=referencia`,
sin omisiones. `gru_persistencia_web.xml`: 7 aprobadas, incluida una prueba CUDA real
de ajuste, persistencia y reapertura con serie sintética de contrato; no es aprendizaje
validado con mediciones. El libro real sigue bloqueado por potencia ausente en
L-TM105, fila 4280 (`gru_fuente_corregida.json`); no se imputó el objetivo.

T4: `contratos_finales_v2.xml`: 22 aprobadas, sin omisiones; distingue puntero heredado
con registro vacío y con candidato rechazado, preservando todos los archivos.
Evidencias bajo `output/correcciones_alumnos_20261101/`.

T1: ajuste y reproducción CUDA con las particiones persistidas y tres miembros;
reproducción dentro de 1e-5 p.u. y búsqueda Optuna exclusivamente sobre selección.
La primera fixture se amplió porque solo tenía una familia de validación; se corrigió
también una aserción antigua que esperaba48 muestras frente a las96 actuales.
`pinn_reproduccion_hpo_final.xml`: dos pruebas focalizadas aprobadas; las otras30
de `redes_final.xml` ya estaban aprobadas. Se conservan los informes fallidos previos.

T5: `entrega_contratos_v2.xml`:96 aprobadas sin omisiones. El resumen
`entrega_verificada.json` verifica352 pruebas distintas con resultado final aprobado,
superponiendo únicamente las repeticiones de los mismos casos; no suma suites solapadas
ni oculta informes anteriores. `pip check` satisfactorio. Trama global de specs reparada:
22 pruebas aprobadas; la prueba nativa T12 de019 sigue abierta con estado implementada.
Índice, ayudas, manual y trazabilidad final:91 aprobadas sin omisiones en
`indice_y_trazabilidad_final.xml`; los cuatro trabajadores quedaron documentados.
[Entrega y límites](../../docs/CORRECCIONES_ALUMNOS_2026-11-01.md).

T6: campaña CUDA real con2975 observaciones de enero2025 de la hoja L-TM105,
cinco semillas, máximo40 épocas; selección eligió23. Candidato con MAE181,381kW
frente al estacional864,168kW sobre los mismos351 puntos reservados; MAPE4,623%.
40 épocas y280 actualizaciones del optimizador en el modelo elegido. Reapertura en
otro proceso con error0kW. Pesos verificados:3489 elementos F32, cero no finitos,
CRC y SHA256 correctos. No promovido; no generaliza esta evidencia a otro periodo/red.
El ajuste generativo con corpusv5 se intentó y quedó ERROR_ENTORNO por7,336GiB
comprometibles frente al mínimo8; no se acreditan pasos del alumno LLM por ese intento.
