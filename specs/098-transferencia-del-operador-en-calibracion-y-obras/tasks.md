# Tareas 098

- [x] T1. Reconocer las zonas transferidas por el operador y qué abrir y cerrar en cada una, en una pasada por clase.
      (RF-1, RF-2, RF-8, RF-15)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "sentidos or estado or toca or nuevas or abiertos"` en verde.
- [x] T2. Calibrar y recalibrar con la red de la fuente: desactivar, comprobar, restituir antes de guardar y en el
      `finally`, con el registro en disco y el informe. (RF-3, RF-4, RF-5, RF-6, RF-7, RF-8, RF-10)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py tests/test_ajuste_proyecto_guion.py tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T3. El escaneo dice lo que está en un alimentador por una transferencia desde otro. (RF-9)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k escaneo` y `pytest -q tests/test_escaneo.py` en verde.
- [x] T4. La web lleva al plan los tramos y los abiertos del DGS aceptado y la fecha de la importación. (RF-14)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k web` en verde.
- [x] T5. Las transferencias y los traslados de la escalera, solo donde hay maniobra, que la migración abre con su
      apertura anotada. (RF-11, RF-12, RF-13)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "maniobra or seccionador"` y
      `pytest -q tests/test_obras_integrales.py tests/test_obras_aperturas.py` en verde.
- [x] T7. Comparar la red con el DGS aceptado rama por rama: particiones, enlaces nuevos del operador y el registro
      por nombre completo; la fecha de la importación por el sello del proyecto. (RF-14, RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "particiones or acopladores or frente or web"` en
      verde, con la configuración de CA101 y CHN102 que dieron las sondas del 2026-11-07.
- [ ] T6. [DIgSILENT] Recalibrar por la web el proyecto `20261105-124711_CSG_TXT_CA101_CHN102` (mes 2026-07) y correr
      «Con proyecto». (RF-3, RF-5, RF-7, RF-10, RF-11, RF-17, RF-18)
      Primera corrida (2026-11-07, main 0b130251 + 4d9c230f): siguió con -1 271,2 kW; dos zonas sin tocar porque la
      lectura no veía las particiones ni el acoplador nuevo; de ahí la T7.
      Hecho cuando: la recalibración cuadra sin pérdidas negativas, su informe dice que la transferencia de CA101 a
      CHN102 se desactivó (se abre «Breaker/Switch(1)» y se cierra «Breaker/Switch») y se restituyó con la comprobación en verde, la transferencia sigue en «Sin proyecto» y en
      «Con proyecto» como la dejó el operador, y las transferencias que proponga la escalera salen de barras con
      maniobra.
