# Tareas — Spec 112

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar. Ninguna toca
`pronostico_demanda.py` (la 089 la corrige f9, H6/H7): solo se lee su salida. Ningún dato de la distribuidora entra en
`tests/`.

- [ ] T1. Patrones de privacidad en `privacidad.py` del núcleo; `web/soporte.py` los importa sin cambiar su
      comportamiento. (RF-2, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_instalacion_programa.py tests/test_benchmarks_seudonimos.py`
      en verde (las pruebas de 086:RF-42 sin tocar).
- [ ] T2. Seudónimos: permutación sorteada por tipo de identificador, coherente entre RED, CARGA y BD_Equipo;
      coordenadas a un origen neutro con giro sorteado; el mapa nunca se escribe; misma semilla, mismos bytes. (RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_seudonimos.py` en verde.
- [ ] T3. Redes: lista cerrada de secciones y columnas, escritura del trío TXT en las dos disposiciones, BD_Equipo con
      los parámetros resueltos, perfil neutro, columnas de texto libre fuera; generación sin red. (RF-1, RF-3, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_redes.py` en verde, con `ExportSpec`
      sorteado, `layout='reducido'` y `'completo'`, dos perfiles y un solo alimentador.
- [ ] T4. Reproducción del estudio con `reglas` y `oraculo.validar`/`validar_unida`: tensiones, cargas, recuento y
      veredicto dentro de la tolerancia declarada (por defecto 0,005 p.u. y 1 %); si no, no se emite y dice qué
      magnitud y qué elemento. (RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_redes.py -k reproduce` en verde en al
      menos dos redes sintéticas distintas, y con las tres variables `CSG_*` en la red real (salida en `tmp_path`).
- [ ] T5. Series del 089: identificador nuevo, escala sorteada, semanas completas desplazadas, exógenas como columnas,
      potencia en bandas, CSV determinista; WAPE y MASE de los métodos de base iguales dentro del 1 %. (RF-3, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_series.py` en verde, con series
      sintéticas y sin GPU.
- [ ] T6. Control de reidentificación y prueba negativa con fugas plantadas: identificador, coordenada, cliente, término
      del perfil, fecha, secuencia de valores, fragmento de informe y fichero de más; cada una rechazada con su clase.
      (RF-4, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_reidentificacion.py` en verde.
- [ ] T7. Manifiesto y emisión atómica: huella del origen, versión, semilla, transformaciones, columnas omitidas,
      tolerancia con su fuente, métricas de referencia y huella de cada fichero; nada a medias si algo falla. (RF-1, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_redes.py tests/test_benchmarks_series.py -k manifiesto`
      en verde, con la generación repetida dos veces y las mismas huellas.
- [ ] T8. Cohortes por empresa (una fuera) y por tiempo con franja de separación, por componente conexo de alimentadores
      y clientes, validadas con `particionar_registros`; con una sola empresa, la frase de que la generalización no está
      demostrada. (RF-6, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_cohortes.py` en verde, con dos empresas
      sintéticas, un cliente transferido y el caso de una sola empresa.
- [ ] T9. Sellado de la prueba antes de elegir modelo (apertura exclusiva, huella en el manifiesto, rechazo si cambia) e
      informe publicado con todos los resultados, también los negativos. (RF-7, RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmarks_evaluacion.py` en verde.
- [ ] T10. Herramienta `tools/benchmark_anonimo.py` con `--help` sin DIgSILENT, alta en `CODIGO_FUENTE.md` con la spec
      112. (RF-1)
      Hecho cuando: `.venv/Scripts/python.exe tools/benchmark_anonimo.py --help` sale con 0 y las pruebas del inventario
      (spec 009) en verde.
- [ ] T11. Validación: cada RF citado por al menos una prueba y en verde. (RF-1 a RF-11)
      Hecho cuando: `grep -rnoE "112:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-11 y la suite completa con las tres
      variables `CSG_*` está en verde.
