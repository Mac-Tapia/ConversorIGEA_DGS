# Plan — Spec 041

- Núcleo puro en `src/igea_dgs/ajuste_cabecera.py` (RF-1 a RF-7): `Probabilistico`,
  `probabilistico_de_fijas` (regresión log-log de la utilización de las fijas frente a su kVA),
  `probabilistico_del_perfil`, `muestra_de_reparto` (multiplicador `(kVA/kVA medio)^pendiente ×
  lognormal`, P base total conservada), `percentil`, `reparto_p50`, `resumen_probabilistico` y
  `montecarlo` (con `random.Random(semilla)`).
- Guion `tools/ajuste_cabecera_pf.py`: tras el cuadre determinista, `preparar_probabilistico`,
  `probabilistico_de_un_alimentador` (un alimentador) y `_probabilistico_del_proyecto` (varios a
  la vez, los demás quietos en `cuadrar_conjunto`); `lectura_probabilistica` lee la carga del
  transformador de cada escalada y las tensiones. Reutiliza `cuadrar`, `flujo` y la validación de
  siempre: el P50 cuadrado queda escrito (RF-5, RF-8). Las SED de 3.1, fijas (RF-9).
- Web `src/igea_dgs/web/services.py`: el libro de 3.1 se guarda por proyecto
  (`_guardar_sed_medidas`, `sed_medidas_de`); el plan lleva `sed_medidas`, `probabilistico`
  (n, semilla `crc32(proyecto|alimentador|fecha)`, perfil) y `banda_tension` del perfil.
- Front `AjusteCabecera.tsx`: `RepartoProbabilistico`, con las bandas por SED (RF-6).
- Pruebas: `tests/test_reparto_probabilistico.py`.
