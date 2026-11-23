# Tareas — Spec 045

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Versionar episodios, contexto y grafo. (RF-1, RF-2, RF-3, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_contratos_v2.py tests/test_digital_twin_episode.py tests/test_digital_twin_buffer.py tests/test_digital_twin_snapshot_pf.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Física representada y fronteras comprobables. (RF-4, RF-5, RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pinn_fisica_y_fronteras.py tests/test_digital_twin_flujo.py tests/test_digital_twin_in191_ta295.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [x] T3. Ablaciones, dominio y candidato opcional PyG. (RF-8, RF-9, RF-12, RF-13)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_pinn.py tests/test_digital_twin_oraculo.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.
      Hecho el 2026-11-21 (d8, bloque GPU): `pytest -q tests/test_benchmark_pinn.py
      tests/test_digital_twin_oraculo.py` 40 passed con la GPU; ablación real en CUDA sobre una copia del búfer con
      identidad 043 (física pura, red sin física e híbrido vigente evaluados y reabiertos, cada uno con su veredicto
      044:RF-5 en `brazos.<variante>.veredicto`; aprueba la física pura y no las dos redes; PowerFlowNet no
      disponible, opcional, RF-13) en D:/csg/PM_IMPL/GPU_BLOQUE/045_T3/ablaciones.json (completo, experimento
      572c6df1…); tests_ml/test_benchmark_pinn_cuda.py 1 passed. El híbrido peor que la física se trata en la T6.

- [x] T4 [DIgSILENT]. Contraste del gemelo con la red nativa. (RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_fisico_nativo.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).

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
- **T2, cerrada.** `tests/test_pinn_fisica_y_fronteras.py`, `test_digital_twin_flujo.py` y `test_digital_twin_in191_ta295.py`
  pasan; ninguna entrena. El gradiente se contrasta en float64 en CPU, porque es una fórmula y no un modelo. Relación
  fuera de la nominal, toma y banco se contrastan con pandapower (`test_transformador_y_banco_coinciden_con_pandapower`),
  no con DIgSILENT: eso es la T4.
- **T3, abierta.** El código y `tests/test_benchmark_pinn.py` están hechos, con un doble que comprueba el contrato y no
  mide mejora. Falta lo que pide la GPU, sin correr:
  - `pytest tests/test_digital_twin_oraculo.py`, entera, en CUDA;
  - `pytest tests_ml/test_benchmark_pinn_cuda.py`, con el entorno opcional de PyG;
  - la ablación con los episodios reales, `python tools/digital_twin_entrenar.py --ablaciones CONTRATO --output-json INFORME`.
    Necesita antes los episodios con grafo versión 3, que salen de DIgSILENT.
- **T4, abierta, medida el 2026-11-07** (rama `worktree-agent-a578852c96aa94605` sobre `7e81450c`, DIgSILENT 24.0.2, sin GPU).
  `tests/test_gemelo_fisico_nativo.py` (045:RF-11) con `CSG_EVIDENCIA_NATIVA=D:/converter/evidencia_nativa/20261107_PE10_t4c`:
  3 passed, 0 omitidas. Proyecto de prueba `20261106-233549_CSG_TXT_8fc733e4_01_PE10` (CA191 + PE194); cada caso releído en un
  proceso nuevo de `digital_twin_snapshot_pf.py` tras reabrir, y contrastado con el flujo mallado del gemelo (CPU) en 1 065 barras:
  «Caso base» error medio 0,0048 p.u. y máximo 0,125; «Sin proyecto» 0,0066 y 0,129; «Con proyecto» con el banco de la obra
  0,0067 y 0,129. Los tres, fuera de dominio para uso predictivo: DIgSILENT calcula desequilibrado (`iopt_net=1`) y la física es
  equilibrada; el máximo supera la tolerancia de 0,01 p.u. Inventario: 12 bancos y 0 centrales en «Caso base» y «Sin proyecto»
  antes y después; «Con proyecto» con 13, el nuevo es solo el declarado. Sigue abierta porque se piden los cuatro papeles y el
  proyecto no tiene «Cargas nuevas» (DIgSILENT: «el proyecto no tiene el caso Cargas nuevas»): hace falta un proyecto de prueba
  con el libro de cargas nuevas (spec 037). NA293–NA295 no se tocaron.

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

- [x] T5. La física base de la PINN nunca da 0 p.u.: Newton-Raphson y, si no, barrido radial. (RF-14)
      Hecho cuando: `tests/test_digital_twin_flujo.py` (045:RF-14) en verde y la red 9f53b98… del búfer a 0,005 p.u. de DIgSILENT.

- [x] T6 [GPU]. El híbrido no empeora a la física: corrección nula al empezar, época elegida con el tope de residuo,
      corrección acotada al predecir, retirada del modelo en uso peor que la física y redes de prueba declaradas en el
      contrato de la ablación. (RF-15, RF-16, RF-17, RF-18)
      Hecho cuando: el código y `tests/test_gemelo_hibrido_acotado.py` (sin GPU) en verde, `tests/test_digital_twin_oraculo.py`
      y `tests_ml/test_benchmark_pinn_cuda.py` en CUDA en verde, y la ablación repetida en la GPU con el mismo contrato
      (`D:/csg/PM_IMPL/GPU_BLOQUE/045_T3/contrato_ablacion.json`) da el híbrido con `veredicto.approved` en global y en las
      5 familias, o `eleccion.brazo` = `fisica_pura` con el híbrido sin empeorarla (mae_v ≤ 2,07·10⁻⁴ p.u., residuo ≤ 0,05
      por familia). Orden: `PYTHONPATH=src .venv/Scripts/python.exe tools/digital_twin_entrenar.py --ablaciones CONTRATO --raiz COPIA_DEL_BUFER
      --output-json INFORME`, sobre una copia nueva de `045_T3/twin_copia`, con el turno de GPU de la cola de d8 (HANDOFF de MEJ30). Abierta: el código y las pruebas sin GPU están hechos; falta la
      medida en GPU.
      Primera medida, 2026-11-21 (`D:/csg/PM_IMPL/GPU_BLOQUE/045_T6_MEJ30/`): no pasa. El híbrido da 5,07·10⁻⁴ p.u. frente a
      2,07·10⁻⁴ (1 de 5 familias) porque la prueba, una red de 30 nodos, estaba fuera del dominio de todos los candidatos
      (169–5 147 nodos) y se medía la predicción cruda; la física en validación (3,04·10⁻³ p.u.) es peor que en esa prueba
      (≤ 2,8·10⁻⁴), así que mejorar la validación no dice nada de ella. Además, `test_incertidumbre_para_el_aprendizaje_activo`
      falló en CUDA (f(30) = 1,0 < f(1)). Corregido en la segunda vuelta de MEJ30 (RF-16); se repite la medida.
      Segunda medida (T6b): contrato `D:/csg/PM_IMPL/GPU_BLOQUE/045_T6b_MEJ30/contrato_ablacion.json` (huella del
      experimento `b9792fa9…`), con `politica.redes_de_prueba` = la red `9f53b983…` (829 nodos, 14 ejemplos, 6 familias),
      dentro del dominio (30–5 147 nodos) y con la física a 4,0·10⁻³ p.u. Acepta si el híbrido pasa las puertas de 044 en
      global y en las 6 familias con `ejemplos_fuera_de_dominio` = 0; si no, queda la física (`eleccion.brazo`) con el motivo
      medido.

      Hecho el 2026-11-22 en la GPU (cola de la noche de d8, D:/csg/PM_IMPL/GPU_BLOQUE/045_T6b_noche/): la ablación
      repetida con el contrato de la T3 sobre una copia nueva del búfer (2260 s) da los cuatro brazos evaluados con
      `veredicto.approved` en global y en las 6 familias, el híbrido incluido (`ablaciones.json`, experimento b9792fa957f3;
      `eleccion.brazo` = powerflownet, el de menor error de tensión entre los que pasan las puertas de 044), y las pruebas
      en CUDA dan 60 passed (`pytest_gpu.log`); espejo en Drive verificado por sha256 (596 iguales).