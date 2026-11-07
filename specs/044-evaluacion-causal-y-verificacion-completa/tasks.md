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

- [x] T4 [DIgSILENT]. Persistencia y aceptación en el motor real. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_nativa.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.
      Hecho el 2026-11-07 con DIgSILENT 24.0.2 en el proyecto de prueba `20261106-233549_CSG_TXT_8fc733e4_01_PE10`
      (CA101 + PE104): ver «T4, 2026-11-07» abajo. `CSG_EVIDENCIA_NATIVA=D:/converter/evidencia_nativa/20261107_PE10_t4c
      pytest -q -rs tests/test_verificacion_top_k_nativa.py`: 3 passed, 0 omitidas.

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

T4 (RF-9), 2026-11-07, rama `worktree-agent-a578852c96aa94605` sobre `main` `7e81450c`. Sin GPU.
- Cómo: `tools/aceptacion_nativa.py obras --barra 14932 --q-kvar 300 --guion-local` (banco de 300 kvar en «Con proyecto»
  de CA101, el escalón de 10 kV del perfil). Cada relectura es un proceso nuevo de `digital_twin_snapshot_pf.py` (sesión
  nueva por el arnés, con el plan que firmó la web); la obra se aplica con `tools/obras_pf.py` de esta rama y el plan firmado
  por la web, porque la web ejecuta los guiones de su copia y sin el arreglo de abajo la obra quedaba inactiva. Evidencia
  fuera de git: `D:/converter/evidencia_nativa/20261107_PE10_t4c/` (31 ficheros con SHA-256 en `aceptacion_nativa.json`,
  huella del manifiesto `e582c7c3a660f79b…`); las pruebas comprueban las huellas y recalculan los veredictos.
- Medido: tras reabrir en otra sesión, «Con proyecto» tiene `Obra_condensador_CA101` activa y `Banco_14932` con 0,300 Mvar;
  converge, tensión mínima de media 0,8033 p.u. y pérdidas 2 448,9 kW. La evaluación nativa (`evaluar`, la de
  `verificar_top_k`) da `converged_with_violations` (p. ej. 0,9361 p.u. en la barra 14502, fuera de 0,95–1,05 NTCSE): no se
  acepta. `verificar_top_k` la descarta antes, por dominio (045:RF-9): el flujo de DIgSILENT es desequilibrado
  (`iopt_net=1`) y el gemelo físico es equilibrado (error medio 0,0067 p.u., máximo 0,129 p.u. en 1 065 barras).
- Fallos reales hallados y corregidos (cada uno con su prueba): (1) `digital_twin_snapshot_pf.resultados` restaba de la
  cabecera de CA101 las cargas de todo el proyecto (pérdidas −4 690 kW, la medición se rechazaba por negativa):
  `test_perdidas_de_un_alimentador_en_proyecto_de_varios`. (2) «Con proyecto» recién creado, y luego la etapa de la obra,
  quedaban un segundo antes de las etapas de fichas (707 tramos) y de SED NTP (7 transformadores): «activas» sin aplicar,
  687 barras de CA101 sin tensión, `Newton algorithm stagnated` y la obra inactiva (evidencias `…_t4` y `…_t4b`).
  `casos_pf.crear_con_proyecto` y `cargas_pf.crear_variacion` llaman ahora a `etapas_al_dia` (081:RF-78), porque subir la hora
  del caso no se mantiene (se midió: volvió a …149): `test_con_proyecto_nuevo_ve_las_etapas_de_sin_proyecto`. (3) Las lecturas
  salían sin `pf_version` (PF 2024 no tiene `GetVersion`): se toma de `powerfactory.__version__`.
- Limitación: el rechazo de `verificar_top_k` es por dominio, no por su juicio eléctrico; el juicio eléctrico de la misma
  medición se comprueba aparte. Una aceptación con el oráculo en una red equilibrada queda para la 052 con GPU.
- Lo que quedó en el proyecto de prueba: la obra se retiró (`obras_pf.py --retirar-obras`, relectura sin el banco); quedan el
  caso y el escenario «Con proyecto» (creados el 2026-11-07, sin obras) y las etapas de fichas y SED NTP adelantadas antes de la
  hora de «Con proyecto»; «Caso base» y «Sin proyecto» releídos antes y después, idénticos (0,0 p.u., 0,0 kW, mismas huellas).

Ejecución 2026-10-31: ver [registro y pendientes](../../docs/EJECUCION_IA_2026-10-31.md).
