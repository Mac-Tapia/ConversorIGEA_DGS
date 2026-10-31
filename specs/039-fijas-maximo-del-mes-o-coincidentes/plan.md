# Plan — Spec 039

Estado: aprobado (2026-10-31)

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| El criterio en el plan del ajuste: `criterio_fijas` (`maximo_mes` o `coincidente`), con `instante` solo en el segundo; sin el registro, bloqueo con el periodo que daría la misma fecha | `src/igea_dgs/web/services.py` (`ajuste_plan`, `demanda_clientes`), `src/igea_dgs/demanda_medida.py` (`registros_de_maxima` ya admite `instante`) | RF-1 a RF-4, RF-6 |
| La comparación: cada fija con los dos criterios y la suma por registro, con los mismos lectores (`_abrir`, `_filas`, `maestro_lib`) | `src/igea_dgs/demanda_medida.py` (`comparar_criterios_fijas`) | RF-5 |
| Cabecera en el instante (curva de `maximas`) y Q de la red y de los bancos del último informe de calibración (`ajuste_aplicado_en_disco`) | `src/igea_dgs/web/services.py` (`comparar_criterios_fijas`) | RF-5 |
| Selector del criterio y botón «Comparar los criterios de las fijas» con sus tablas; ruta como trabajo del carril `engine` | `frontend/src/components/DemandaMedida.tsx`, `AjusteCabecera.tsx`, `api.ts`, `types.ts`; `src/igea_dgs/web/app.py` | RF-1, RF-5 |
| `tools/sistema_web.py --criterio-fijas` | `tools/sistema_web.py` | RF-1 |

Decisiones: la Q de la red sale del informe de la calibración (cabecera simulada menos lo que
consumen las cargas, más lo que entregan los bancos), no de una simulación aparte: los informes
salen de lo que guardó la ejecución. Sin el registro coincidente no se cae al «máximo del mes» en
silencio (RF-4): mezclar criterios es lo que escondió el desfase de NA203.

Pruebas: libros sintéticos con `openpyxl` (con y sin el instante) para la lectura y el plan; la
API con un informe de calibración en disco; la web, en el navegador real, y NA203 en DIgSILENT.
