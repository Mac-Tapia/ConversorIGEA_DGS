# Tareas — Spec 064

- [x] T1. Prueba que detecta cualquier conexión fuera del arnés. (RF-2)
      Hecho cuando: `tests/test_pf_arnes_sin_atajos.py` falla sobre los siete guiones de hoy.
- [x] T2. Los siete guiones conectan con `pf_arnes.conectar`. (RF-1)
      Hecho cuando: T1 pasa y `--help` de cada guion responde (`test_inventario`).
- [x] T3. La web lanza la red del sistema y el escenario base con el entorno de DIgSILENT. (RF-3)
      Hecho cuando: una prueba de `system_command`/`run_system` ve `PF_PYTHON` en el entorno.
- [x] T4. `pf_estado`: foto y restitución. (RF-4, RF-5, RF-6)
      Hecho cuando: `tests/test_pf_servidor.py` (doble de la API con caso, hora, escenario y variaciones) pasa.
- [x] T5. El servidor restituye tras una orden fallida y sigue si no puede. (RF-5, RF-6, RF-7)
      Hecho cuando: `tests/test_pf_servidor.py` pasa con órdenes que fallan y que lanzan.
- [x] T6. `set_nueva_operacion_pf.py` en el servidor. (RF-8)
      Hecho cuando: una prueba lo encuentra en `GUIONES_SERVIBLES`.
- [x] T7. [DIgSILENT] Desde la web abierta con el acceso directo: una orden que falla y la siguiente encuentran el caso y la hora de antes. (RF-5, RF-6)
      Hecho cuando: el registro de la orden fallida dice qué se restituyó y una lectura posterior lo confirma.

Evidencia de T7 (2026-11-02): en una copia de `20261101-101524_CSG_0205` (Electro Oriente),
borrada al terminar, la orden que falla a mitad dejó activo «Caso base» y la hora de «Sin
proyecto» 10⁶ s atrás; `pf_estado.restituir` dijo «caso «Sin proyecto» activo de nuevo; hora
de estudio repuesta a 1793546125» y la foto final fue igual a la inicial. Por la web,
abierta con el acceso directo, el servidor atendió una lectura de proyectos (código 0) y una
orden fallida (código 2) con la foto tomada en la API real.
