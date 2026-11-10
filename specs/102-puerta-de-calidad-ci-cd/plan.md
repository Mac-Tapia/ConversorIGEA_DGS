# Plan 102

## Módulos

- `tools/puerta_calidad.py` (RF-1 a RF-11):
  - `--commit`: lee los ficheros preparados (`git diff --cached --name-only`). `pruebas_del_commit(ficheros, raiz)`
    devuelve las de gobierno (RF-1), más los ficheros de prueba preparados y las pruebas que nombran el módulo o la
    herramienta (RF-2), o solo las de gobierno si no hay código ni specs (RF-4). Corre pytest y para si algo falla (RF-3).
  - `--push`: `variables_de_la_suite(raiz, entorno)` toma `config/suite_completa.json` (fuera de git) y el entorno, y
    comprueba cada ruta (RF-6, RF-7). Corre la suite completa con `-rs` y `--junitxml`; `veredicto(junit)` lista las
    fallidas y las omitidas con su motivo (RF-8, RF-9). El resultado queda en `.git/puerta_calidad/<revisión>.json`
    (RF-10), y una revisión ya aprobada con el árbol limpio no se repite (RF-11).
  - `--ci`: la suite sintética, que para solo por fallos (RF-12, RF-14).
- `.githooks/pre-commit`: regenera el catálogo (090) y llama a `--commit`. `.githooks/pre-push`: llama a `--push`.
  Los activa `tools/generar_arquitectura.py --instalar-ganchos`, que ya fija `core.hooksPath` (RF-16).
- `.github/workflows/ci.yml` (RF-12 a RF-15): Windows, Python 3.12, `requirements.txt`, `python tools/puerta_calidad.py
  --ci`; Node, `npm ci`, `npm run build` y `npm test` en `frontend/`.
- `config/suite_completa.example.json`: las variables con rutas genéricas; `config/suite_completa.json` va en `.gitignore`.

## Decisiones

- El juicio sale del XML de JUnit, no del texto de pytest: el texto cambia con los complementos y con `-q`. Descartado:
  leer la última línea del registro.
- En GitHub se aceptan las omitidas de datos reales: allí no hay ni puede haber datos de la distribuidora (RF-15). La
  regla de cero omitidas la impone la subida local (RF-9).

## Pruebas

- `tests/test_puerta_calidad.py`: selección de pruebas, variables, veredicto del JUnit y caché por revisión, sintéticas.
  Ganchos y flujo de GitHub, leídos como texto.
