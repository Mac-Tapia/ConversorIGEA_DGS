# Tareas — Spec 069

- [x] T1 Modelo: codificador, cabezas, contrato, carga y errores. (RF-1 a RF-9, RF-30 a RF-32)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k modelo` en verde.
- [x] T2 Clase `ninguna` en el corpus y en el intérprete. (RF-10 a RF-16)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k ninguna` en verde.
- [x] T3 Puerta de rechazo en la decisión y el informe. (RF-17 a RF-22)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k rechazo` en verde.
- [x] T4 Calibración de temperatura y umbral. (RF-23 a RF-27)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k calibra` en verde.
- [x] T5 Herramientas y frases de operador de las tareas flojas. (RF-28, RF-29)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k integral` en verde.
- [x] T6 Ejecución real única con `tools/asistente_entrenar.py --integral`.
  Hecho cuando: el informe da candidato, estado del registro y puntero antes y después, por familia y con rechazo.
  Hecho el 2026-11-02: candidato `b7d9bd4db807` RECHAZADO, 0,900 en 922 sintéticas, F1 0,993, 3 de 3 humanas; 6 tareas bajo la
  puerta de 0,95. Rechazo en 206 reservados: 0,942 recogido y 0,010 colado, en regla. El modelo en uso sigue `20261024-150042-37ce`.
  Un primer intento se cayó en la reapertura, antes de que el registro decidiera nada (arreglado en `1cb47837`).
- [x] T8 Codificador elegible al entrenar, con su revisión fija y anotado en el modelo. (RF-33)
      Hecho cuando: `tests/test_interprete_codificador.py` (069:RF-33) en verde.
- [x] T9 Cada candidato comprueba al guardarse el codificador que anota. (RF-34)
      Hecho cuando: `tests/test_interprete_codificador.py` (069:RF-34) en verde.
- [x] T10 Puerta selectiva del intérprete y plan que resuelve uniones, rutas y mensaje entero. (RF-35, RF-36)
      Hecho cuando: `tests/test_puerta_selectiva.py` (069:RF-35, RF-36) en verde.
- [x] T11 Umbral de ejecución con el límite inferior de Wilson. (RF-37)
      Hecho cuando: `tests/test_interprete_codificador.py` (069:RF-37) en verde.
- [x] T12 Puerta de no regresión sobre las humanas frente al modelo en uso, con McNemar exacto. (RF-38 a RF-40)
      Hecho cuando: `tests/test_no_regresion_humanas.py` (069:RF-38 a RF-40) en verde, con el caso de reg-75fdd605
      (43 humanas, 41 frente a 32) RECHAZADO y una diferencia de una orden sin bloquear.
      Ampliada el 2026-11-13 (aclaración de RF-38 y RF-39): el modelo en uso se compara fuera de muestra y en el mismo
      conjunto de humanas; `tests/test_no_regresion_humanas.py` (069:RF-39) reproduce el sesgo con las cifras reales de
      prov-8fd8a405 (rojo en 3a02ea17) y pasa; `tests/test_afinado_ordenes.py` (069:RF-39) comprueba `humanas_por_orden`.
- [ ] T7 Que un candidato pase todas las puertas, sin ajustar nada mirando la prueba ya medida.
  Hecho cuando: el registro deja un candidato PROMOVIDO, medido con una prueba que no haya orientado el ajuste.
  Su puerta de no regresión compara con el modelo en uso fuera de muestra (aclaración de RF-38 y RF-39, 2026-11-13):
  hasta entonces comparaba con la medida dentro de muestra de prov-8fd8a405 y ningún candidato honesto podía pasar.
- [ ] T13 Partición de las órdenes humanas por empresa y por fecha, sin paráfrasis de una misma petición en dos
      particiones (Plan Maestro PM-18). (RF-41)
      Hecho cuando: `tests/test_interprete_codificador.py` (069:RF-41) parte un conjunto de humanas con su empresa, su
      fecha y su grupo de paráfrasis y comprueba que ninguna empresa retenida, fecha de prueba ni grupo cae en dos
      particiones.
      Bloqueada por datos (2026-11-20, MEJ13 de d8): las humanas guardadas traen la fecha en que se anotaron, pero no la
      empresa ni el grupo de paráfrasis, que no se pueden deducir del texto sin inventarlos; no se escribe código hasta
      tenerlos. Siguiente acción: el usuario o sus revisores etiquetan las humanas con su empresa y su grupo; después, el código y su
      prueba.
