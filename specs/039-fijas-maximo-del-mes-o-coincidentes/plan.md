# Plan — Spec 039

Estado: aprobado (2026-10-31)

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| El criterio en el plan del ajuste: `criterio_fijas` (`maximo_mes` o `coincidente`), con `instante` solo en el segundo; sin el registro, bloqueo con el periodo que daría la misma fecha | `src/convertersmartgrid/web/services.py` (`ajuste_plan`, `demanda_clientes`), `src/convertersmartgrid/demanda_medida.py` (`registros_de_maxima` ya admite `instante`) | RF-1 a RF-4, RF-6 |
| La comparación: cada fija con los dos criterios y la suma por registro, con los mismos lectores (`_abrir`, `_filas`, `maestro_lib`) | `src/convertersmartgrid/demanda_medida.py` (`comparar_criterios_fijas`) | RF-5 |
| Cabecera en el instante (curva de `maximas`) y Q de la red y de los bancos del último informe de calibración (`ajuste_aplicado_en_disco`) | `src/convertersmartgrid/web/services.py` (`comparar_criterios_fijas`) | RF-5 |
| Selector del criterio y botón «Comparar los criterios de las fijas» con sus tablas; ruta como trabajo del carril `engine` | `frontend/src/components/DemandaMedida.tsx`, `AjusteCabecera.tsx`, `api.ts`, `types.ts`; `src/convertersmartgrid/web/app.py` | RF-1, RF-5 |
| `tools/sistema_web.py --criterio-fijas` | `tools/sistema_web.py` | RF-1 |

| Cliente a su máxima (2026-11-07): en la tabla, los dos valores de cada fija (`valores.coincidente` y `valores.maximo_mes`) y la diferencia; el marcado toma el registro de su POT (`_a_su_maxima`) sin bloquear; la selección en `Workspace.fijas_a_su_maxima`, con `PUT /demanda/clientes/a-su-maxima`; en el plan, `fijas_a_su_maxima` con lo que sale de `fijas_de` | `src/convertersmartgrid/web/services.py` (`demanda_clientes`, `_clientes_en_sus_maximas`, `ajuste_plan`, `recalibrar_sistema`), `web/workspace.py`, `web/app.py` | RF-9, RF-10, RF-12, RF-14 a RF-16, RF-19 a RF-22 |
| El informe lista `fijas_a_su_maxima` junto al criterio | `tools/ajuste_cabecera_pf.py` (las dos líneas del 039:RF-6) | RF-18 |
| `--a-su-maxima COD…` en el cruce y el plan | `tools/sistema_web.py` | RF-16, RF-17 |
| Columnas, orden y filtro por la diferencia, casilla «a su máxima», «Desmarcar todos», botón «Recalibrar con estos criterios» | `frontend/src/components/DemandaMedida.tsx`, `AjusteCabecera.tsx`, `api.ts`, `types.ts` | RF-9 a RF-14, RF-17, RF-18 |

Nota (2026-11-07): el cliente a su máxima no necesita cambio en el reparto del guion: va en `clientes` del plan con
el registro de su POT, y `fijas_de` lo suma a su SED como cualquier fija; las escaladas llenan lo que falta hasta la
cabecera (RF-19). Sin selección en la petición vale la guardada en el espacio, para que `sistema_web.py` y la
recalibración la usen sin repetirla. Descartado: un tercer criterio general; la decisión es cliente a cliente.

Decisiones: la Q de la red sale del informe de la calibración (cabecera simulada menos lo que
consumen las cargas, más lo que entregan los bancos), no de una simulación aparte: los informes
salen de lo que guardó la ejecución. Sin el registro coincidente no se cae al «máximo del mes» en
silencio (RF-4): mezclar criterios es lo que escondió el desfase de NA203.

Pruebas: libros sintéticos con `openpyxl` (con y sin el instante) para la lectura y el plan; la
API con un informe de calibración en disco; la web, en el navegador real, y NA203 en DIgSILENT.
