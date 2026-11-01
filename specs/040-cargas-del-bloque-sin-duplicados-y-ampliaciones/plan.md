# Plan — Spec 040

Estado: aprobado (2026-10-31)

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Filas repetidas del libro por alimentador y punto, antes de resolver cada fila | `tools/cargas_pf.py` (`duplicadas_del_libro`, `resolver_nuevas`) | RF-1, RF-2 |
| SED existentes de cada alimentador (cargas de la red que no son de una variación `Carga_…`, con la barra de baja y su GPS), y la ampliación por palabra del nombre o a 30 m | `tools/cargas_pf.py` (`sed_existentes`, `ampliacion_de`, `resolver_nuevas`) | RF-3 |
| La ampliación crea solo la carga en la barra de baja de la SED, en su variación; se mide como las demás | `tools/cargas_pf.py` (`crear_carga`, `_una_carga`) | RF-4 |
| Propuesta de transformador con `potencia_efectiva`, `transformadores_de` y `proponer_transformadores` de la calibración; las fichas en el plan de cargas | `tools/cargas_pf.py`, `tools/ajuste_cabecera_pf.py` (sin cambios), `src/convertersmartgrid/web/services.py` | RF-5 |
| Variaciones `Carga_…` que sobran: desactivadas en cada caso y eliminadas; la primera por nombre se conserva | `tools/cargas_pf.py` (`eliminar_variaciones`, `ya_creada`, `ejecutar`) | RF-6 a RF-8 |
| Avisos y listas del informe (`duplicadas`, `ampliaciones`, `eliminadas`) | `tools/cargas_pf.py` | RF-9 |

Decisiones:

- La ampliación es una carga nueva en la barra de baja de su SED, en su propia variación, y no un
  cambio de la carga existente: la potencia de una carga es dato del escenario, y escribirla en
  «Con proyecto» no se podría activar ni desactivar carga a carga (007:RF-12) ni dejaría intacta
  la calibración. Descartado también crear una SED en el mismo punto: es lo que duplicaba.
- El punto de la SED existente es el GPS de la barra de baja de su carga (los 188 de NA203 +
  NA205 lo tienen); la palabra del nombre se compara con los nombres de la red, sin patrón de
  empresa (P13).
- Dos filas son la misma solo en el mismo alimentador del libro, como pidió el usuario.

Pruebas: el doble `tests/fake_pf.py` con barras de baja (`bt=True`), en
`tests/test_cargas_pf_guion_040.py`; la de 014:RF-26 se cambia a RF-7. NA203 + NA205 en DIgSILENT
desde la web.
