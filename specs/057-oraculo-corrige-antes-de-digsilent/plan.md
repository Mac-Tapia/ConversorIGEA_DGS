# Plan — Spec 057

Sin módulos nuevos: una regla más en la vía única de `reglas.py`, con la detección en
`sed_potencia.py` (donde ya está el redimensionado de SED sobrecargadas) y la búsqueda del
factor en `oraculo.py`.

1. `sed_potencia.py` (RF-2, RF-3)
   - `demanda_fuera_de_escala(model)`: las claves de las SED cuya demanda es de relleno (la misma
     P > 0 en todas las cargas de SED del alimentador, con dos o más potencias instaladas
     distintas) o cuya potencia aparente supera la instalada. Una SED en cero no entra
     (nota «caso base con demanda cero»).
   - `corregir_demanda(model, claves, factor)`: P = kVA × factor × 0,98 y Q con el mismo FP,
     en el sitio; devuelve cada cambio con el valor de la fuente, el nuevo y la regla.
2. `oraculo.py` (RF-1, RF-3, RF-6)
   - `corregir_para_converger(model)`: sin SED de RF-2, o si el oráculo ya converge, no toca
     nada. Si no, prueba el factor 0,8 y, si no converge, busca por bisección el mayor que
     converge en (0, 0,8]. Si ninguno converge, deja el modelo como estaba y lo dice.
   - El docstring deja de decir «Qué no hace: corregir»: corrige solo esto, con regla.
   Alternativa descartada: bajar todas las cargas por igual (015:RF-38): no arregla una SED de
   5 kVA con 39 kW sin dejar casi vacías las grandes.
3. `reglas.py` (RF-4)
   - `Reglas.corregir_con_oraculo = True` (apagada en `SIN_REGLAS`); `aplicar_reglas` la llama
     al final y deja `informe['demanda_corregida']` y un aviso en el modelo, como los puentes y
     el trafomix: el manifiesto y la web lo muestran sin código nuevo.
4. `web/services.py` (RF-5, RF-6)
   - `pandapower_preflight` devuelve los alimentadores que aun corregidos no convergen; la
     importación los deja fuera, los nombra y sigue con los demás.

Pruebas: `tests/test_oraculo_corrige.py`, con exports sintéticos sorteados en las dos
disposiciones; la demanda de relleno se fuerza en el modelo. Determinismo: dos corridas dan el
mismo informe y el mismo DGS. Datos reales: NJA202 por la web (T4).
