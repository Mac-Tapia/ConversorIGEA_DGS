# Plan — spec 037

1. `web/services.py` guarda `anio_casos` desde la base y devuelve los nombres de los
   casos en el plan; pide renovar el diagnóstico al preparar los casos (RF-1, RF-2, RF-4).
2. `tools/casos_pf.py` reutiliza `cargas_nuevas` y los callbacks de diagnóstico de
   `tools/cargas_pf.py`; devuelve su estado y exclusiones (RF-2, RF-5, RF-7). Se prefiere
   renovar desde «Sin proyecto» a reutilizar un diagnóstico que podría estar desactualizado.
3. `tools/estudios_pf.py` resuelve el diagnóstico por nombre y marca del año sin ampliar
   el contrato compartido de `tres_casos` (RF-4, RF-7).
4. `web/services.py` añade el rol `cargas` entre `sin` y `con`; conserva los CSV existentes
   y evita registrar el diagnóstico como estado de otro caso en el gemelo (RF-3, RF-6).
5. `EstudiosPF.tsx` y `types.ts`: explicación visible, confirmación de casos y resultados
   del diagnóstico con cargas activas y rechazadas (RF-1, RF-5).

Pruebas: `test_estudios_pf_web.py`, `test_estudios_pf_guion.py`, `test_casos_pf.py`,
`test_obras_estudios_front.py`, `test_estudios_pf.py`, trazabilidad e inventario;
`npm --prefix frontend run build`. No se cambia el lector ni el modelo de conversión.
