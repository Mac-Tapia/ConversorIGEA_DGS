# Tareas 097

- [x] T1. Modelo y prefijos de los vectores por ficha, sin mezclar modelos en un índice. (RF-1, RF-2, RF-3)
      Hecho cuando: `pytest -q tests/test_asistente_vectores_097.py tests/test_asistente_indice.py` en verde.
- [x] T2. Elección del modelo con la calibración en `asistente_evaluar_rag.py` (`--modelo-vectores`, `--comparar`). (RF-4)
      Hecho cuando: `pytest -q tests/test_asistente_vectores_097.py` en verde.
- [ ] T3. Medición real en la GPU: calibrar los candidatos en 047 y 077, sellar una vez el elegido. (RF-4, RF-5, RF-6, RF-7)
      Hecho cuando: el informe está en `docs/` con las métricas de cada candidato y la decisión anotada aquí.
