# Tareas — Spec 044

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T0. Rechazo puntual de métricas ausentes/no finitas sin dependencias nuevas. (RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py tests/test_digital_twin_evolutivo.py` pasa con el reproductor y sus parámetros de T0; la integración completa queda en T3.

- [x] T1. Particiones independientes y política previa. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_modelos.py tests/test_digital_twin_particiones.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Calibración y puertas por familia. (RF-4, RF-5, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_calibracion_independiente.py tests/test_digital_twin_oraculo.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [x] T3. Cerrar la verificación parcial de alternativas. (RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py tests/test_digital_twin_evolutivo.py tests/test_digital_twin_evaluacion.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [x] T5. Conectar `verificar_top_k` a la aceptación real de las alternativas de la 052, que hoy va por `obras_pf` sin pasar por RF-6 ni RF-7. (RF-6, RF-7)
      Hecho cuando: la aceptación de una alternativa de la 052 pasa por `verificar_top_k` con contexto y las pruebas del llamador pasan; `test_ningun_llamador_verifica_sin_contexto` lo vigila.

- [ ] T4 [DIgSILENT]. Persistencia y aceptación en el motor real. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_nativa.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Cierre T1 y T3, 2026-11-03, rama `feat/044-cierre` sobre `feat/043-cierre` (`5d23f1b5`). Sin GPU ni DIgSILENT; cifras por fichero en el commit que las cierra.

T1 (RF-1 a RF-3): ya estaban `PoliticaEvaluacion`, `Particiones`, `particionar_registros` y los mínimos 30/10/10, usados por el asistente y las series, y en la PINN la calibración apartada de la 060.
Añadido: las cuatro particiones de la PINN pasan por el particionador común con su familia como grupo (`fallos_de_custodia`, `politica_pinn`) antes de abrir modelos o pedir GPU;
el reparto por sistema, por familia y no por episodio (`docs/regresiones/2026-11-03-hermanos-en-el-reparto-por-sistema.md`); `alcance_de`; `test_modo_por_sistema_no_finge_generalizacion`;
un mínimo no declarado da BLOQUEADO_POR_DATOS. RF-3 se prueba con el ajuste real sustituido por un doble: `test_ajuste_no_usa_la_prueba_sellada` y `test_busqueda_de_hiperparametros_no_ve_la_prueba`.
Límite: el recorrido de `entrenar` con la PINN real es de `tests/test_digital_twin_oraculo.py`, que pide CUDA y queda en T2.

T3 (RF-6, RF-7): `validar_medicion_nativa` (contexto, unidades, flujo completo y coherente con su resumen, reapertura, referencia vinculada) y `verificar_top_k`, que además pide `evaluar` en «accepted»;
las claves públicas se conservan. **`verificar_top_k` no tiene llamador en producción**, ni lo tenía: `optimizar_bancos` propone y la confirmación de la 052 va por `obras_pf`, fuera de estos requisitos.
El contrato queda cerrado y probado sobre datos sintéticos; que los flujos reales lo usen es de T4, porque producir la medición (reapertura incluida) pide DIgSILENT. `test_ningun_llamador_verifica_sin_contexto` vigila a quien lo conecte.

T2 (RF-4, RF-5, RF-8), **abierta**: el código y `tests/test_calibracion_independiente.py` están y pasan, con el ajuste real sustituido por un doble. Falta lo que su «Hecho cuando» exige:
`tests/test_digital_twin_oraculo.py`, que entrena en CUDA. Se tocó su fixture (la comparación por familia va parcheada igual que la global, porque sus etiquetas son la física),
`test_evaluar_si_aprendio` (dos particiones más) y `test_intervalo_por_barra_y_no_confiable` (cobertura condicionada a las familias): esos tres cambios están sin ejecutar.
Sin correr tampoco, con las mismas puertas ya no parcheadas: ningún entrenamiento real ha pasado aún por las puertas por familia.
`test_cuantil_conforme_con_su_cobertura` (sin GPU) fallaba por azar en 32 de 400 semillas, también en la rama base: se amplió su muestra; el margen sigue en 0,02.

T5 (RF-6, RF-7), 2026-11-03, rama `fix/pinn-turno-044t5` sobre `5080456a`, sin GPU ni DIgSILENT. `_optimizar_con_oraculo` (052), después de
aplicar lo que confirmó `obras_pf`, llama a `_aceptar_con_medicion_nativa`: el oráculo predice el estado que queda en «Con proyecto» (las obras
aplicadas con todas las cargas nuevas activas), `digital_twin_snapshot_pf.py` relee tras reabrir «Con proyecto» y «Sin proyecto», y
`integration.medicion_de_lecturas` arma la medición (tensiones de media, como las del oráculo) con su contexto y la referencia. `verificar_top_k` decide con
contexto y límites del perfil. Si no pasa, el Registro dice el motivo, el informe del oráculo lo guarda en `aceptacion_nativa` y la corrida sigue con la SET
nueva. La obra queda en DIgSILENT sin aceptar: no se borra. Sin lectura no se dice «no converge», se dice la lectura.
Pruebas con un DIgSILENT doble: `tests/test_optimizacion_oraculo.py` (19, aceptada y cuatro rechazos), `tests/test_verificacion_top_k_completa.py` (76,
incluida `test_ningun_llamador_verifica_sin_contexto` sobre el llamador nuevo). `test_rol_sin_criterio_no_se_acepta_por_omision` ya fallaba en `5080456a`:
desde la 045 «cargas_nuevas» se juzga contrafactual, y la aserción admite los dos motivos.
Límites: con k < n, «Con proyecto» lleva también las cargas que van a la SET nueva, y su evaluación nativa las juzga. La referencia «Sin proyecto» no
tiene las cargas nuevas, y `evaluar` rechaza más pérdidas que ella. Por las dos cosas, lo real puede salir rechazado aunque la obra baste para sus k cargas.
Medirlo en DIgSILENT es de T4.

Ejecución 2026-10-31: ver [registro y pendientes](../../docs/EJECUCION_IA_2026-10-31.md).
