# Plan — Spec 039

Estado: aprobado (2026-10-31)

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| El criterio en el plan del ajuste: `criterio_fijas` (`maximo_mes` o `coincidente`), con `instante` solo en el segundo; sin el registro, bloqueo con el periodo que daría la misma fecha | `src/convertersmartgrid/presentacion/web/services.py` (`ajuste_plan`, `demanda_clientes`), `src/convertersmartgrid/aplicacion/demanda_medida.py` (`registros_de_maxima` ya admite `instante`) | RF-1 a RF-4, RF-6 |
| La comparación: cada fija con los dos criterios y la suma por registro, con los mismos lectores (`_abrir`, `_filas`, `maestro_lib`) | `src/convertersmartgrid/aplicacion/demanda_medida.py` (`comparar_criterios_fijas`) | RF-5 |
| Cabecera en el instante (curva de `maximas`) y Q de la red y de los bancos del último informe de calibración (`ajuste_aplicado_en_disco`) | `src/convertersmartgrid/presentacion/web/services.py` (`comparar_criterios_fijas`) | RF-5 |
| Selector del criterio y botón «Comparar los criterios de las fijas» con sus tablas; ruta como trabajo del carril `engine` | `frontend/src/components/DemandaMedida.tsx`, `AjusteCabecera.tsx`, `api.ts`, `types.ts`; `src/convertersmartgrid/presentacion/web/app.py` | RF-1, RF-5 |
| `tools/sistema_web.py --criterio-fijas` | `tools/sistema_web.py` | RF-1 |

| Cliente a su máxima (2026-11-07): en la tabla, los dos valores de cada fija (`valores.coincidente` y `valores.maximo_mes`) y la diferencia; el marcado toma el registro de su POT (`_a_su_maxima`) sin bloquear; la selección en `Workspace.fijas_a_su_maxima`, con `PUT /demanda/clientes/a-su-maxima`; en el plan, `fijas_a_su_maxima` con lo que sale de `fijas_de` | `src/convertersmartgrid/presentacion/web/services.py` (`demanda_clientes`, `_clientes_en_sus_maximas`, `ajuste_plan`, `recalibrar_sistema`), `web/workspace.py`, `web/app.py` | RF-9, RF-10, RF-12, RF-14 a RF-16, RF-19 a RF-22 |
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
silencio (RF-4): mezclar criterios es lo que escondió el desfase de NA293.

Pruebas: libros sintéticos con `openpyxl` (con y sin el instante) para la lectura y el plan; la
API con un informe de calibración en disco; la web, en el navegador real, y NA293 en DIgSILENT.

## MEJ27-FIJAS (orden del usuario del 21-11): RF-24 y RF-25

Caso real (bloque DIgSILENT del 20-11, corrida A): un alimentador de cuatro paraba antes del primer flujo con
`FIJA_A_REVISAR` porque un cliente medía más que su cabecera en 5 registros (hasta 162 kW). La causa era su FM:
545,4545 en el libro de septiembre y 1818,1818 en el de octubre (×3,33), con su energía ×3,82 del 30-09 al 01-10 y la
cabecera sin ese salto. `fm_cambiados` (004:RF-111) no lo veía: el «último día» del libro de septiembre era el 1 de
octubre con el único registro de las 00:00 (48 kWh), y el salto salía ×297. Se corrigió a mano con RF-23.

- `aplicacion/demanda_medida.py`: `_energia_de_un_dia` toma solo días completos (86 de 96 registros) del mes de cada
  libro. Con los libros reales el aviso sale (×3,82 frente a ×3,33, dentro del ± 20 %).
- `dominio/ajuste_cabecera.py`, puro: `registros_atipicos` (Hampel), `cabecera_estable` y `diagnostico_fija_imposible`
  con las cuatro salidas de RF-24; `plausibilidad_fijas` lleva el diagnóstico al motivo y marca `liberar` (RF-25).
- `presentacion/web/services.py`: `_evidencia_fijas` diagnostica cada cliente con las cabeceras del mismo trabajo, y
  según el resultado registra la corrección automática (`registrar_correccion_medidor(..., origen='automatico',
  evidencia=...)`) y corrige la fila (`_escalar_fila`), repara el registro excluido o propone la reasignación. Se
  calcula antes de `fijas_de` para que el plan lleve las fijas ya corregidas.
- `tools/ajuste_cabecera_pf.py`: con `FIJA_A_REVISAR` ya no devuelve rc=2; quita las fijas liberadas de
  `fijas_libro`, las deja en `fijas_liberadas` y sigue.

Fuentes consultadas (21-11-2026):

- Oracle Utilities, *About Measurement Reprocessing*: un multiplicador de consumo mal instalado deja mal el consumo de
  forma retroactiva; al detectar el cambio del multiplicador se reprocesan los intervalos dividiendo por el
  multiplicador combinado de cada registro. Es el mismo arreglo de RF-23 y RF-24 (a), con fecha desde la que vale.
  https://docs.oracle.com/en/industries/utilities/rate-cloud/264/rcs-user-guides/Topics/D1_BG_About_Measurement_Reprocessing.html
- Oracle NMS, *Distribution State Estimation: Bad Data Detection*: prueba chi-cuadrado global y residuo normalizado
  mayor (LNR) para identificar la medida mala, quitarla y estimar de nuevo.
  https://docs.oracle.com/en/industries/energy-water/network-management-system/251200/nms-user-guide/NMS_USER_251200/DistributionStateEstimation.15.5.html
- JuliaGrid, *Bad Data Analysis* (GitHub, mcosovic/JuliaGrid.jl): el mismo bucle chi-cuadrado + LNR con umbral 3 o 4.
  https://mcosovic.github.io/JuliaGrid.jl/dev/manual/badDataAnalysis
- Salehi Dobakhshari, Terzija y Azizi, *Normalized Deleted Residual Test for Identifying Interacting Bad Data in Power
  System State Estimation* (White Rose): el LNR funciona con un dato malo y falla con datos malos que interactúan.
  https://eprints.whiterose.ac.uk/182827/
- Filtro de Hampel (Hampel, 1974): `HampelOutliers.jl` (GitHub, tobydriscoll), `aeon` (HampelFilter) y el paquete
  `hampel` de PyPI; ventana de mediana, escala 1,4826 × MAD y umbral 3. Aquí 3,5 (Iglewicz y Hoaglin) porque se aplica a
  curvas de 15 minutos con escalones de carga reales.
  https://github.com/tobydriscoll/HampelOutliers.jl · https://pypi.org/project/hampel/
- Identificación transformador–medidor con datos AMI (Lee et al., arXiv 2210.00155; CIRED 2025, ORBi): por correlación
  o por suma de potencias; RF-24 (c) usa la suma frente a cada cabecera del mismo trabajo y solo propone.
  https://arxiv.org/abs/2210.00155

Por qué no un estimador de estado completo: la red de un alimentador no trae medidas redundantes (solo la cabecera y los
clientes fijos); el balance cabecera ≥ cliente en cada registro es la única restricción que se puede probar antes del
flujo, y el residuo de cada registro frente a su vecindad hace el papel del LNR.
