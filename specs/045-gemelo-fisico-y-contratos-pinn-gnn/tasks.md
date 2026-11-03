# Tareas — Spec 045

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Versionar episodios, contexto y grafo. (RF-1, RF-2, RF-3, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_contratos_v2.py tests/test_digital_twin_episode.py tests/test_digital_twin_buffer.py tests/test_digital_twin_snapshot_pf.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Física representada y fronteras comprobables. (RF-4, RF-5, RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pinn_fisica_y_fronteras.py tests/test_digital_twin_flujo.py tests/test_digital_twin_in111_ta225.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Ablaciones, dominio y candidato opcional PyG. (RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_pinn.py tests/test_digital_twin_oraculo.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Contraste del gemelo con la red nativa. (RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_fisico_nativo.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Rama `feat/045-cierre`, sobre `feat/044-cierre` (`33b134ee`), 2026-11-03. Pruebas por fichero, con
`OPENBLAS_NUM_THREADS=1`, `PYTHONPATH=src` y `CUDA_VISIBLE_DEVICES=-1`. Sin DIgSILENT.

En Windows, `CUDA_VISIBLE_DEVICES=""` no oculta la GPU; `-1` sí. Con el valor vacío, `tests/test_digital_twin_oraculo.py`
se ejecutó en CUDA dos veces sin autorización mientras la GPU estaba reservada: una cortada a los 280 s y otra entera
(24 pasan, 1 falla, 357 s). Ese resultado no cuenta como evidencia de la T3: era anterior a los últimos cambios del
código y no debió ejecutarse.

- **T1, cerrada.** `tests/test_gemelo_contratos_v2.py`, `test_digital_twin_episode.py`, `test_digital_twin_buffer.py`
  y `test_digital_twin_snapshot_pf.py` pasan. La central, el banco y el caso se capturan con el doble `fake_pf`: es
  el contrato. Que persistan en una red real es el `test_central_y_bancos_persisten` de la T4.
- **T2, cerrada.** `tests/test_pinn_fisica_y_fronteras.py`, `test_digital_twin_flujo.py` y `test_digital_twin_in111_ta225.py`
  pasan; ninguna entrena. El gradiente se contrasta en float64 en CPU, porque es una fórmula y no un modelo. Relación
  fuera de la nominal, toma y banco se contrastan con pandapower (`test_transformador_y_banco_coinciden_con_pandapower`),
  no con DIgSILENT: eso es la T4.
- **T3, abierta.** El código y `tests/test_benchmark_pinn.py` están hechos, con un doble que comprueba el contrato y no
  mide mejora. Falta lo que pide la GPU, sin correr:
  - `pytest tests/test_digital_twin_oraculo.py`, entera, en CUDA;
  - `pytest tests_ml/test_benchmark_pinn_cuda.py`, con el entorno opcional de PyG;
  - la ablación con los episodios reales, `python tools/digital_twin_entrenar.py --ablaciones CONTRATO --output-json INFORME`.
    Necesita antes los episodios con grafo versión 3, que salen de DIgSILENT.
- **T4, abierta.** `[DIgSILENT]`, sin ejecutar. `tests/test_gemelo_fisico_nativo.py` todavía no existe; RF-11 sin prueba.

Limitaciones de lo cerrado:

- `tests/test_pinn_fisica_y_fronteras.py` cayó con un «access violation» de Windows, sin ningún fallo de aserción. Antes
  de importar pandapower antes que PyTorch, la traza lo situaba dentro de esa importación. Después pasó 36 de 37 veces;
  la caída restante no quedó registrada y su causa no está localizada.

- `VERSION_GRAFO` sube a 3 y los episodios capturados hasta hoy no enseñan hasta recapturarlos. Se conservan intactos.
- Un modelo entrenado antes de esta versión queda fuera de dominio y decide la física.
- Con flujo desequilibrado (`iopt_net`, spec 054), el grafo se rechaza para uso predictivo: la física del gemelo es
  equilibrada.
- `ElmVoltreg`, `ElmTr3` y las demás clases de `CLASES_NO_REPRESENTADAS` se declaran y se rechazan; no se modelan.
- Atributos como `dutap`, `nntap0`, `tap_side`, `ngnum` o `bustp` están leídos con el doble y sin confirmar en DIgSILENT.

