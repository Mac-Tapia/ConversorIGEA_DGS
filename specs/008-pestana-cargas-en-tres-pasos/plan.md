# Plan — Spec 008

Lee: `docs/constitution.md`, `specs/004-cargas-en-powerfactory/spec.md`,
`specs/006-ajuste-a-la-maxima-de-cabecera/spec.md` y esta spec.

## Módulos

| Fichero | Cambio | RF |
| --- | --- | --- |
| `tools/ajuste_cabecera_pf.py`, `tools/cargas_pf.py` | `main` envuelve `ejecutar`: una excepción escribe el informe con `error` (tipo y mensaje) y la traza va al Registro; código 1. | RF-17 |
| `tools/verificar_pf.py` (nuevo) | Activa el proyecto, ejecuta `ComLdf` con lo que esté activo y mide la cabecera de cada alimentador pedido con `medir_cabecera`. No crea variación ni escribe. | RF-18, RF-19 |
| `src/igea_dgs/web/services.py` | `ajuste_plan(..., medidores=[...])`: un plan por alimentador (uno por medidor elegido; RF-13 si un alimentador tiene varios sin elegir); `ajuste_ejecutar` los recorre con el mismo fichero de cancelación y devuelve `informes` (uno por alimentador, también los fallidos). `pf_verificar` lanza el guion nuevo. La carga del formulario va delante de las del libro. | RF-10, RF-12 a RF-15, RF-18, RF-19, RF-24 |
| `src/igea_dgs/web/app.py` | `AjusteIn.medidores`; `POST /powerfactory/verificar` en el carril `powerfactory`. | RF-12, RF-18 |
| `frontend/src/App.tsx` | Pestañas con `necesitaEntradas`; sin entradas solo «Cargas en DIgSILENT». | RF-1, RF-2 |
| `frontend/src/components/CargasTab.tsx` | Tres pasos; filtro de proyectos; alimentadores marcados (todos al elegir); paso 3 con la verificación, 3.1, 3.2, 3.3 y «Revisar»; aplicar solo con flujo convergido. | RF-3 a RF-7, RF-20 a RF-23 |
| `frontend/src/components/DemandaMedida.tsx`, `AjusteCabecera.tsx` | Medidores por alimentador marcado, máxima en un trabajo, cruce de los marcados; medidor por alimentador y un informe por alimentador. | RF-8 a RF-16 |

## Decisiones

- **Un trabajo para todos los ajustes.** El carril `powerfactory` admite un trabajo a la
  vez (409 si hay otro): lanzar uno por alimentador desde el front exigiría encadenarlos
  a mano. *Descartado:* una cola en el front, que se pierde al recargar la página.
- **Un plan por alimentador en disco**, el mismo JSON de la spec 006: el guion no cambia
  y sus pruebas siguen valiendo.
- **La verificación es un guion aparte** que importa de los dos existentes; meterla en
  `cargas_pf.py` crearía la importación circular que la spec 007 (T2) quiere deshacer.
- **Convergencia para aplicar:** vale el último entre la verificación y el ajuste
  aplicado del mismo proyecto. Un ajuste converge si cada alimentador ajustado tiene
  `cabecera` (el último flujo convergió) y ningún `error`. *Descartado:* exigir que
  cuadre: un ajuste que no cuadra sigue siendo una red que resuelve (spec 007, RF-34).

## Pruebas

- `tests/test_ajuste_cabecera_guion.py`: excepción en `ejecutar` → informe con `error`.
- `tests/test_cargas_pf_guion.py`: lo mismo para el guion de cargas.
- `tests/test_verificar_pf.py`: converge, no converge y alimentador sin `ElmFeeder`, con
  el doble `fake_pf` y un número de alimentadores sorteado.
- `tests/test_ajuste_cabecera_web.py`: plan con varios medidores; medidor ambiguo; un
  ajuste que falla no para el siguiente; cancelación entre alimentadores.
- `tests/test_cargas_pf_web.py`: verificación como trabajo; formulario delante del libro.
- `tests/test_cargas_tres_pasos_front.py`: contrato de la fuente del front.
