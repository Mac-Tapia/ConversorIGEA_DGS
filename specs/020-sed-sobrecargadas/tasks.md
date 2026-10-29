# Tareas 020 — SED fijas sobrecargadas

Plan: `specs/020-sed-sobrecargadas/plan.md`. Una tarea cada vez, pruebas primero.

- [x] T1. Tablas de fichas en el perfil de Electro Dunas y su lectura validada.
      (RF-29, RF-30, RF-31)
      Hecho cuando: `pytest -q tests/test_perfil_empresa.py` en verde.
      Resultado del 2026-10-16: `perfil_empresa.transformadores_sed`; Tablas 6 (13 filas) y
      7 (12 filas) en `config/perfiles/electro_dunas.json`, heredadas por el perfil local;
      44 pruebas en verde.
- [x] T2. Regla de dimensionado pura en `trafos_sed.py`. (RF-6, RF-7, RF-8, RF-11)
      Hecho cuando: `pytest -q tests/test_trafos_sed.py` en verde, con los casos de PA217 y
      los sorteados.
      Resultado del 2026-10-16: `tabla_para` y `proponer`; las cuatro SED de PA217 salen
      como en la T26 de la 015 (8, 3 y 2 × 630 kVA y 1 × 500 kVA, Tabla 7) y 500 demandas
      sorteadas cumplen que es la mínima; 7 pruebas en verde. En `CODIGO_FUENTE.md`.
- [x] T3. Detección con los transformadores de cada SED y la propuesta en el informe del
      ajuste; el aviso nombra la sobrecarga como causa probable. (RF-1, RF-2, RF-4, RF-5,
      RF-9, RF-10, RF-12)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
      Resultado del 2026-10-16: `transformadores_de`, `proponer_transformadores` y
      `aviso_sobrecarga` en el guion; el plan trae `transformadores_sed` (la sección del
      perfil) y el informe `fichas_transformador_sed`, cada SED con sus transformadores y
      su `propuesta` (con `tipo_nuevo`, de `trafos_sed.nombre_tipo`) y
      `sobrecarga_causa_probable` si la calibración no sale. 68 pruebas del guion y de la
      regla y las 39 del inventario en verde.
- [x] T4. Cambio de transformadores en «Sin proyecto» antes de calibrar, con sus
      comprobaciones y su informe. (RF-16 a RF-24, RF-27)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
      Resultado del 2026-10-16: `implementar_transformadores` en el guion, con «Sin
      proyecto» activo y antes de leer los kVA; plan con `transformadores` (SED,
      transformador y propuesta); informe `transformadores_implementados` (`cambios` con
      antes y después, `omitidas` con el motivo). 76 pruebas del guion y de la regla en verde.
- [x] T5. Comprobación después de recalibrar y fallo con su diagnóstico. (RF-26, RF-32)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
      Resultado del 2026-10-16: `resultado_transformadores` en el guion; el informe trae
      `resultado_transformadores` (VALIDO o FALLO, con lo que sigue fallando) y un aviso
      TRANSFORMADORES si falla. 79 pruebas del guion y de la regla en verde.
- [x] T6. Servicio y API del botón, en el carril de DIgSILENT, con el registro de la
      calibración. (RF-15, RF-25, RF-28)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_web.py` en verde.
      Resultado del 2026-10-16: `POST …/demanda/ajuste/{token}/transformadores` con
      `{feeder, sed}`, validado antes de encolar (`ajuste_transformadores_pedido`, que toma
      la propuesta del último informe del ajuste en disco); trabajo `ajuste_transformadores`
      en el carril `powerfactory` con una copia del plan y el informe como el de un ajuste
      aplicado; `_correr_guion_ajuste` común con `ajuste_ejecutar`; el plan lleva
      `transformadores_sed` del perfil; ese trabajo vale como base (`_ajuste_aplicado`).
      34 pruebas de la web en verde.
- [x] T7. Front: aviso al principio, propuesta con casillas y botón, resultado.
      (RF-3, RF-4, RF-9, RF-13, RF-14)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_web.py` en verde y
      `npm run build` sin errores.
      Resultado del 2026-10-16: `SedSobrecargadas` (al principio del resultado, causa
      probable, tabla con la propuesta y su ficha, casillas marcadas, botón «Implementar
      transformadores») y `TransformadoresImplementados` en `AjusteCabecera.tsx`; el
      desplegable de la 015:RF-59 sale; `api.ajusteTransformadores`; el resultado trae
      `token`; `CargasTab` toma el trabajo `ajuste_transformadores` como base. `tsc` y
      `npm run build` sin errores; 36 pruebas de la web y 94 del front en verde.
- [x] T8. Índice, `CLAUDE.md` y nota en la 015.
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde.
      Resultado del 2026-10-16: `CODIGO_FUENTE.md` (guion, servicios, componente y
      `trafos_sed.py`), fila de la 020 en `CLAUDE.md` y nota en «Fuera de alcance» de la
      015. 39 pruebas del inventario en verde.
- [x] T9. Validación: cada RF citado por al menos una prueba y la suite en verde.
      Hecho cuando: `grep -rnoE "020:RF-[0-9]+" tests | sort -u` lista los 32 RF.
      Resultado del 2026-10-16: los 32 RF citados; suite sintética 2220 pruebas en verde
      (43 omitidas, las de datos reales: no se toca el lector ni el modelo).
- [x] T10. Prueba en DIgSILENT desde la web con PA217 importado de nuevo: aviso, propuesta,
      implementación y recalibración válida sin adaptar el modelo.
      Hecho cuando: el informe del trabajo dice APLICADO_Y_VALIDADO y está en
      `output/spec020/`.
      Cerrada el 2026-10-29 con SM218 y CA101 de la entrega 231026 (032 T9), no con PA217, que el usuario
      ya trabajó («PA217 no deberías hacer nada»): aviso, propuesta e «Implementar transformadores»
      desde la web, 5 SED cada uno en «SED_NTP_», recalibrados VÁLIDOS (−0,29 % y −0,01 %).
