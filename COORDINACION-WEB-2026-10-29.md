# Coordinación de la verificación web — 29 de octubre de 2026

Instrucción del usuario: conservar el trabajo de la otra sesión, repartir responsabilidades y concluir lo que quede pendiente sin sobrescribirlo.

## Responsabilidades

| Sesión | Trabajo | Archivos y límites |
| --- | --- | --- |
| Claude `535212a5-d3e8-477a-b0f8-7ed2f94cbb84`, detectada en este proyecto | Implementación de la spec 035 y revisión de «Preparar los estudios»; sus registros también muestran sondas nativas de SM218. | Conserva la propiedad de sus cambios en `src/`, `tools/`, `frontend/src/`, `tests/`, `specs/`, `CLAUDE.md`, `CODIGO_FUENTE.md` y `.claude/settings.json`. |
| Codex, esta sesión | Verificar el lanzador, compilar, reiniciar la web, restaurar la carga de la misma fuente, comprobar API y recursos servidos, ejecutar regresiones y guardar evidencia. | Solo escribe la compilación `frontend/dist`, los artefactos de ejecución/carga, `AUDIT/web_restart_20261029*` y este registro. No modifica el código de la otra sesión. |

Este reparto documenta el alcance de esta sesión. No hay canal de mensajería entre estas dos sesiones externas; no se ha recibido aceptación de Claude y no se ha escrito en su historial ni en sus archivos internos.

## Resultado operativo confirmado

- El acceso directo `Conversor IGEA-DGS.lnk` apunta a `D:\converter\ConversorIGEA_DGS\run_gui.bat` con el directorio de trabajo correcto.
- Se ejecutó ese `run_gui.bat`, después de comprobar cero trabajos activos. El proceso anterior fue reemplazado por el propio lanzador.
- Web: `http://127.0.0.1:8765/`. PID nuevo 45392; huella del servidor y del código: `047092efd9ed8203`.
- `npm --prefix frontend run build`: correcto; JavaScript y CSS descargados por HTTP son idénticos a los archivos compilados del disco, comprobados byte a byte y por SHA-256.
- Se recargó la fuente TXT del espacio `5f11283a33c94ea5`: 101 alimentadores, 97 con topología y 4 solo con cabecera; 38 927 tramos y 7 339 cargas. Los totales y la huella de la fuente coinciden con los anteriores.
- Se conservaron entradas, opciones, calibraciones, proyectos vinculados, libros de demanda, grupos y cantidad de conversiones. No se ejecutó una calibración ni una obra en PowerFactory.
- SM218, máxima de septiembre: 15 clientes y 15 SED con `REGISTRO_DEL_INSTANTE`; la P y Q de la tabla coinciden con las que prepara `fijas_de`.
- SM218, máxima de octubre: 15 clientes; informa la ausencia del libro de octubre y usa explícitamente el de septiembre. Estos valores son del registro de la POT de septiembre, no del instante de octubre.

## Verificación y pendientes

- Pruebas focalizadas: 54 aprobadas, ninguna omitida.
- Regresión ampliada: 385 aprobadas en 279,55 segundos, ninguna omitida. Resultado en `AUDIT/web_restart_20261029_regression.xml`. Total de ambas ejecuciones: 439 aprobadas, 0 fallidas, 0 errores y 0 omitidas. Es la selección de módulos revisados, no la suite completa del repositorio.
- La inspección visual de Chrome se detuvo porque Computer Use no pudo determinar con confianza la URL. La verificación por API y recursos HTTP sí se completó; no equivale a una revisión visual.
- La tarea nativa T6 de la spec 035 sigue abierta en `tasks.md`. Las pruebas automatizadas no la cierran ni demuestran aceptación eléctrica.
- No asumir cambios de código mientras la otra sesión siga trabajando. Si entrega trabajo incompleto, revisar su diferencia y evidencia antes de continuar; actualizar este reparto para evitar dos escritores sobre los mismos archivos.
- La sonda `sonda_trafos_sm218.py` pertenece a Claude y seguía activa al revisar los procesos. No se ha detenido, reiniciado ni modificado.

## Evidencia y repetición

La evidencia local está en `AUDIT/web_restart_20261029/`: salud y espacio de trabajo antes y después, cruces reales de SM218 y `verification.json`. Los XML de pytest están en `AUDIT/`.

Comandos ejecutados desde el directorio del proyecto:

```powershell
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m pytest tests/test_lanzador_web.py tests/test_web_runtime_front.py tests/test_web_runtime_dependencies.py tests/test_q_con_bancos.py tests/test_tabla_en_el_instante.py tests/test_unidades_pf.py tests/test_client_period_contract.py tests/test_libros_por_anio_front.py -q -ra --junitxml=AUDIT/web_restart_20261029_focused.xml
.\.venv\Scripts\python.exe -m pytest tests/test_web_api.py tests/test_ajuste_cabecera.py tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera_web.py tests/test_demanda_medida_web.py tests/test_cargas_pf_web.py tests/test_libros_por_anio_web.py tests/test_sistema_web.py tests/test_caso_base_web.py tests/test_inventario.py -q -ra --junitxml=AUDIT/web_restart_20261029_regression.xml
.\.venv\Scripts\python.exe -m igea_dgs.web.runtime
.\.venv\Scripts\python.exe -m igea_dgs.web.runtime --front
git diff --check
```

## Entrega a Git solicitada por el usuario

El usuario autorizó expresamente hacer los commits, pull y push. Esta autorización permite
versionar el parche existente de la otra sesión sin editar su implementación. Los cambios
de la spec 035 y del índice de demanda se agrupan con sus pruebas y especificaciones;
los permisos de herramientas de Claude y este registro se versionan por separado.

Antes de preparar la entrega se comprobó que los 28 archivos pendientes permanecían
estables, que `HEAD` y `origin/main` coincidían tras `git fetch origin`, y que no había
patrones de claves privadas o tokens en el diff preparado. Se repitieron las 54 pruebas
focalizadas (sin omisiones) y la compilación del front, ambas correctas. Esta entrega no
cambia el estado pendiente de la aceptación nativa T6.

## Sustento metodológico consultado en la web

Se aplicó una combinación de compilación, pruebas de regresión y comprobación del despliegue efectivo. Es una aplicación práctica de las fuentes siguientes; estas referencias no certifican este conversor ni sus resultados eléctricos.

- Vos, A. S. J. (2025). *CIMMI: A Maturity Model for CI/CD Practices*. Tesis de maestría, TU Delft. [Repositorio institucional](https://repository.tudelft.nl/record/uuid:6f228a29-877f-4c0e-b390-a792a7cde7a3).
- Shamshiri, S. (2016). *Automated Unit Testing of Evolving Software*. Tesis doctoral, University of Sheffield. La evaluación de cambios y regresiones sustenta comprobar el comportamiento después de actualizar. [Repositorio institucional](https://etheses.whiterose.ac.uk/id/eprint/17066/).
- Shahin, M., Ali Babar, M., y Zhu, L. (2017). *Continuous Integration, Delivery and Deployment: A Systematic Review on Approaches, Tools, Challenges and Practices*. IEEE Access, 5, 3909–3943. DOI: [10.1109/ACCESS.2017.2685629](https://doi.org/10.1109/ACCESS.2017.2685629). [Registro institucional](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/), [indexación DBLP](https://dblp.org/rec/journals/access/ShahinBZ17).
