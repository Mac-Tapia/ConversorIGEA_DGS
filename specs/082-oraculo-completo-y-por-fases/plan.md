# Plan — Spec 082

## Módulos

- `src/convertersmartgrid/oraculo.py` (RF-1 a RF-11): `red_pandapower(..., por_fases=)` deja de saltarse
  elementos, añade los bancos y prepara las secuencias; `tiene_fases`, `_ejecutar`, `_tensiones`,
  `_p_fuente`, `_carga_lineas` y `_carga_trafos` reúnen la diferencia entre los dos flujos, para que
  `validar`, `validar_unida` y la corrección usen la misma lógica.
- `tests/test_oraculo_por_fases.py` (RF-1 a RF-13).
- `docs/regresiones/` (RF-13): la ficha entra al rebasar sobre `integracion/065`, donde nace esa carpeta (spec 081).

## Decisiones

- **`runpp_3ph` de pandapower**, no un barrido por fases propio: ya es dependencia y, medido en TI01 y
  C+æ02, queda cerca de DIgSILENT. Descartado el propio porque duplicaría un motor y su mantenimiento.
- **Todos los tramos son trifásicos en pandapower**, que no tiene conductores ausentes. Un tramo
  monofásico solo lleva corriente en su fase: la caída sale de la impedancia propia, (Z0 + 2·Z1)/3.
  El contraste de RF-14 lo mide.
- **Una SED de n fases, YNyn de 3/n su potencia**: pandapower solo tiene trafos de tres columnas. Así
  cada fase conserva su potencia y su corriente nominal, y pasa la secuencia cero. Descartado colgar la
  carga en media tensión, porque omitiría el transformador (RF-6).
- **Un tramo imposible, conexión con error**: se calcula el resto y el error impide el OK. Antes, un
  solo tramo así dejaba sin calcular todo el alimentador.
- **`validar(comparar=False)` en la bisección**: el flujo de comparación no decide nada allí (RF-8).
- **El equilibrado sigue siendo el flujo de la red toda trifásica**: da lo mismo y es más rápido.

## Pruebas

- Sintéticas con `ExportSpec` sorteado y las dos disposiciones (`reducido`, `completo`).
- Modelos reales de cada empresa contra el flujo desequilibrado de DIgSILENT (RF-14), por la web y el arnés.
