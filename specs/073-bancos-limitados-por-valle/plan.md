# Plan — Spec 073

Lee: `docs/constitution.md`, 025 (RF-44, RF-50, RF-52b), 035, 052 y 063 (RF-21, RF-22, RF-31, RF-33).

| Parte | Cubre | Encaje |
| --- | --- | --- |
| `valle.py`, nuevo y puro: limpieza, suma, ventana, puntos, plan, frase | RF-1 a RF-11, RF-16, RF-22, RF-23, RF-31, RF-33, RF-34 | Capa aplicación; solo lee con `demanda_medida.maximas` |
| `escalera_optima`: `Parametros.modulos_max`, `variantes(modulos_valle=)`, `elegir` | RF-17 a RF-20, RF-24 | El mismo `cumple` juzga el valle |
| `optimizacion_oraculo`: `medir(factor_q, factor_nuevas)`, `evaluar(valle=)`, `modulos_en_valle` | RF-19, RF-21, RF-22 | No toca `_con_pinn` |
| `tools/casos_pf.caso_valle` | RF-13 a RF-15 | Contrato; solo con el doble en esta fase |
| `tools/obras_pf.evaluar` | RF-25, RF-26 | Con el `_Sorteo` de siempre: escenario temporal |
| `pide.plan_por_etapas(vetadas=)`, `pide_economia.propuesta_pide(valle=)` | RF-28, RF-29 | Punto de extensión; `pide_ejecutar` es de la 072 y no se toca |
| `web/services`: `_valle_del_proyecto`, `obras_escalera`, `_optimizar_con_oraculo`, `informe_estudio` | RF-12, RF-30, RF-32 | Lo calcula una vez y lo guarda en el `memo` |
| `informes.Etapa.valle`, `informe_docx._alternativas` | RF-32 | Campo opcional; sin él, «no comprobado» |

## Decisiones

- **El mismo `cumple` en valle**, no un criterio aparte. Descartado: uno nuevo solo con el límite superior; `cumple` ya deja
  pasar una barra que estaba fuera sin obra si no la empeora, y dos criterios acabarían diciendo cosas distintas.
- **Dos puntos, no una media.** Se mide el instante mínimo y el mínimo de la ventana, ambos registros medidos. Descartado:
  calibrar a la media de la ventana, que no es ningún instante y no tiene fijas medidas a esa hora.
- **`modulos_en_valle` sube de uno en uno** y para al pasarse, al no converger o si la tensión no sube (barra fuera del grafo).
  Es monótono en una red radial; no hace falta tope en el código. Con `escalera.modulos_max` del perfil, ese es el techo.
- **N es el tope, no la obra.** Se prueban de 1 a N y la escalera se queda la más barata que cumple (063:RF-22): la
  pregunta del usuario era cuántos se prueban. N + 1 se mide solo, sin combinar, para que RF-20 tenga evidencia.
- **Sin valle: la regla anterior.** `MODULOS_SIN_VALLE` (2) es la única cifra y solo vale marcada como no comprobada, por
  compatibilidad (memoria `reconstruir-no-bloquear`). Descartado: fallar, o derivar un tope de la Q de la máxima sin que nadie
  lo haya pedido.
- **Umbrales de RF-6 con valor por defecto y en el perfil.** No son convención de una empresa, pero se pueden ajustar; el
  número de días, en cambio, no tiene valor por defecto.
- **El caso de valle no se ejecuta aún.** `ajuste_cabecera_pf` lee `caso_del_sistema(app, 'sin', anio)` y `ws.calibraciones`;
  calibrar a valle por ahí machacaría `ultima_calibracion` de la máxima, de la que vive la escalera. Hay que separarlo y
  probarlo en DIgSILENT (T8), no a ciegas.

## Pruebas

`tests/test_valle.py`, con curvas sintéticas sorteadas (`random.Random(semilla)`), medidores y días variables, dos perfiles
distintos. Doble `tests/fake_pf.py` para el caso y el guion. La red del oráculo, la de `test_optimizacion_oraculo.py`.
Con `CSG_DEMANDA_DIR`, una lectura real por `demanda_medida`, en memoria, sin sacar datos del repositorio.
