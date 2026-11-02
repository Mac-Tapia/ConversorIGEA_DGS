# Correcciones de la auditoría de alumnos

Implementación local conforme a [spec060](../specs/060-correcciones-del-aprendizaje/spec.md), sus [tareas](../specs/060-correcciones-del-aprendizaje/tasks.md) y las specs027, 043, 046, 047 y050. No se sustituyen las campañas ni se activan pesos por pasar pruebas de contrato.

## Cambios

| Hallazgo | Corrección | Evidencia |
|---|---|---|
| PINN reutilizaba particiones ausentes | Se bloquea el ajuste sin entrenamiento, selección, calibración y prueba; desaparecen los respaldos en ajuste y reproducción | Pruebas060 y regresión del oráculo |
| Parada temprana y calibración usaban validación | Familias de calibración apartadas antes del ajuste; IDs y familias por partición persistidos | Metadatos comprobados por prueba de entrenamiento CUDA |
| Warm-start sin linaje verificable | Se exige genealogía acumulada de IDs y familias; si falta o contamina las reservas, se ajusta desde cero | Pruebas de intersección y del ajuste posterior |
| Política mutable invalidaba el corpus LLM | Copia de política verificada dentro de la versión; origen conservado; cambios de la copia se rechazan | Corpus v5 real auditado; v4 conservado |
| Medianoches desplazadas cinco horas | Se elige la columna con información horaria; las celdas `date` de esa columna se interpretan como medianoche | Pruebas con `Local Time`/`Timestamp` y regresión sobre libros reales |
| Errores temporales sin localizador | Se conserva fila Excel en el lector compartido; diagnóstico con hoja/fila, validación de fechas y huecos sin imputar | Libro2025: L-TM105, fila4280 con potencia ausente |
| Configuración GRU incompleta al guardar | Parámetros completos, optimizador, pasos, historial y validación junto a pesos y sondas | Ajuste CUDA de contrato y reapertura independiente de la instancia |
| Registro común ocultaba modelos heredados | Consulta de metadatos heredados con versión y advertencia explícita; no los promueve ni carga Torch | Registro vacío/rechazado con heredado presente; archivos sin cambios |

Se reutilizan los lectores, módulos de entrenamiento, coordinador y registro actuales.
La [arquitectura](ARQUITECTURA.md#contratos-de-aprendizaje-corregidos-spec-060-2026-11-01)
documenta sus límites. No se añadió otro servidor ni otro registro de modelos.

## Datos reales y pruebas

El corpus nuevo está en `output/alumno_llm_referencias_20261101/corpus_sellado_v5`:

- Huella `03ac1705e1b8f48b09acfb16541e653683ca0675b4ba8f3b7614c9620383fcbe`.
- 1.734 entrenamiento, 54 selección, 54 calibración y 200 prueba.
- Auditoría satisfactoria de 96 contextos y 11 fuentes; tres órdenes humanas reservadas.
- Cero resultados eléctricos fabricados y cero observaciones humanas atribuidas a las solicitudes redactadas.
- Preflight del trabajador generativo satisfactorio; no equivale a entrenamiento.

Informes reproducibles en [output/correcciones_alumnos_20261101](../output/correcciones_alumnos_20261101):

- `lectura_registro_reales.xml`: **122 aprobadas**, cero omisiones, con los libros reales (`CSG_DEMANDA_DIR=referencia`). Sustituye la primera ejecución sin esa variable, que omitió cuatro pruebas.
- `contratos.xml`: **41 aprobadas**, cero omisiones, trabajadores y nuevos contratos iniciales.
- `asistente_regresion.xml`: **46 aprobadas**, cero omisiones.
- `contratos_finales_v2.xml`: **22 aprobadas**, cero omisiones, incluido corpus real y coexistencia del registro con modelos heredados.
- `gru_persistencia_web.xml`: **7 aprobadas**, cero omisiones, incluida persistencia CUDA real. La serie de esta prueba es sintética y está rotulada como contrato.
- `gru_fuente_corregida.json`: operación real bloqueada por el dato ausente; no se completó entrenamiento con ese libro.
- `entrega_contratos_v2.xml`: **96 aprobadas**, cero omisiones, con los contratos finales, coordinador, corpus real y trazabilidad.
- `pinn_reproduccion_hpo_final.xml`: **2 aprobadas**, reproducción CUDA dentro de1e-5p.u. y Optuna usando selección separada de calibración. El informe `redes_final.xml` conserva30 aprobadas y un fallo en una aserción antigua de48 muestras; ese caso se corrigió a96 y se repitió satisfactoriamente. No fue un fallo de precisión del modelo.
- `indice_y_trazabilidad_final.xml`: **91 aprobadas**, cero omisiones; índice, manual, ayudas y estados de specs verificados.
- `entrega_verificada.json`: **352 pruebas distintas con resultado final aprobado**, tras superponer las repeticiones focalizadas de los mismos casos. No es una ejecución única de toda la suite del repositorio.

Los recuentos de suites se solapan; no se suman como pruebas únicas. La primera
regresión del PINN reveló que la fixture anterior aportaba una sola familia de
validación. Se amplió de 12 a24 escenarios por red para separar selección y calibración,
manteniendo los umbrales de precisión. La configuración de la regresión usa20 épocas,
paciencia8 y evaluación cada2; no modifica los hiperparámetros de modelos operativos.
Una ejecución anterior de presupuesto120 se interrumpió para aplicar ese presupuesto
de regresión; no se presenta como resultado satisfactorio.

`pip check` no encontró dependencias rotas. Esto no acredita una instalación desde cero.

## Candidato GRU ajustado con observaciones reales

La selección explícita quedó fijada antes del ajuste en
`alcance_enero_antes_del_ajuste.json`: hoja L-TM105, desde2025-01-01T00:15 hasta
2025-02-01T00:00 exclusivo, zona America/Lima. Se conservaron2975 observaciones
continuas sin imputación;32065 filas quedaron fuera por fecha, no por calidad o error
del modelo. Esto no convierte en válido el libro anual completo.

El trabajador existente ajustó cinco semillas y selección eligió **23**:

| Dato del candidato | Valor real |
|---|---:|
| Ventana / ocultas | 96 /32 |
| Épocas ejecutadas / mejor época registrada (índice0) | 40 /31 |
| Actualizaciones de optimizador | 280 |
| Optimizador / LR inicial / mínimo | Adam /0,01 /0,0001 |
| Lote / paciencia / recorte | 256 /8 /1 |
| Puntos de prueba reservados | 351 |
| MAE de GRU / estacional en esa prueba | **181,381 /864,168 kW** |
| MAPE de GRU / estacional | **4,623% /19,708%** |
| Error máximo tras reapertura en otro proceso | **0 kW** |

Pesos en `gru_enero/candidato_b9e2ecc293614aa786ca1652dd0b931d/modelo_0000.pt`:
16901bytes,3489 elementos F32, CRC correcto y ningún NaN/Inf. SHA256
`ecd7d2191d9fe41ab73acf3a43e7adcf8ad03ae442e9d8bddcd063f91d9950e1`.
Evidencias: `gru_enero_real.json`, `gru_enero_resumen.json`,
`gru_enero_reapertura.json` y `pesos_gru_verificados.json`.

El resultado es **CANDIDATO, no promovido**. Mejora al estacional en ese periodo;
no demuestra generalización a otra red, otro mes ni todos los horizontes de046.

## Intento de destilación generativa con el corpus reparado

`qlora_v5/training_manifest.json` acredita un intento real del trabajador,
**ERROR_ENTORNO** antes de cargar/ajustar pesos: RAM física1,41GiB y memoria
comprometible7,3358GiB frente al mínimo8GiB. El corpus ya supera la auditoría;
el bloqueo actual es de recursos. No se bajó la puerta ni se detuvieron procesos
del usuario para forzar la ejecución. No hay nuevas épocas ni checkpoints LLM
acreditados por este intento.

## Límites que siguen vigentes

El corpus reparado permite volver a ajustar el alumno generativo; no acredita haber
completado su destilación. Tampoco se presentan como aceptados el GRU de mediciones,
el recuperador ajustado ni los optimizadores eléctricos. Faltan datos/validación
independiente por familia según la [auditoría](AUDITORIA_ALUMNOS_2026-11-01.md).
No se aumentaron épocas ni se cambiaron pesos operativos para simular una mejora.

La comprobación global de trazabilidad detectó un cambio concurrente en spec019:
RF-26 estaba definido sin tarea asociada (`corpus_trazabilidad.xml`:22 aprobadas,
1 fallo). Se reparó la trazabilidad con T11 de código y T12 nativa separadas.
T11 pasó19 pruebas sin omisiones (`arnes_trazabilidad.xml`). T12 sigue abierta y
el estado se corrigió de «cumplida» a «implementada», sin atribuirle la evidencia
nativa histórica de otros requisitos. No se borró el informe fallido anterior.

La consulta web se probó con la aplicación local de pruebas. No se reinició el servidor
que tiene trabajos del usuario en curso; el proceso ya iniciado debe recargar el código
para mostrar la nueva advertencia. No se modificaron ni detuvieron trabajos nativos.

## Justificación científica

La separación de evaluación y comparación maestro/base/alumno sigue la
[maestría de Witossek, DLR/Leipzig,2025](https://elib.dlr.de/220552/).
La verificación de un sustituto físico frente al simulador se apoya en el
[doctorado de Stiasny, DTU,2023](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/)
y en [Karniadakis et al., Nature Reviews Physics,2021](https://doi.org/10.1038/s42254-021-00314-5).
La calibración separada y sus condiciones de validez se sustentan en
[Split Conformal Prediction and Non-Exchangeable Data, JMLR,2024](https://jmlr.org/papers/v25/23-1553.html).
Las fuentes justifican los controles; los resultados del conversor proceden de los
artefactos locales anteriores, no de resultados publicados por esos autores.
