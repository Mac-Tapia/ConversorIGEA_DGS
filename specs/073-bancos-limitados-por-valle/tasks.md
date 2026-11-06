# Tareas — Spec 073

- [x] T1 Ventana de valle desde la medición, por alcance. (RF-1, RF-2, RF-3, RF-4, RF-5, RF-6, RF-7, RF-8, RF-9, RF-10, RF-11, RF-34)
      Hecho cuando: `pytest -q tests/test_valle.py -k ventana` en verde, con curvas sorteadas.
- [x] T2 Contrato de la calibración a valle en su propio caso. (RF-13, RF-14, RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_valle.py -k calibracion` en verde, con el doble de DIgSILENT.
- [x] T3 Escalera y oráculo: valle en la elección y número de módulos. (RF-17, RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-27)
      Hecho cuando: `pytest -q tests/test_valle.py -k escalera` en verde, con el caso «la máxima cumple con bancos y el valle no».
- [x] T4 El guion de la evaluación mide en valle sin dejar nada. (RF-25, RF-26)
      Hecho cuando: `pytest -q tests/test_valle.py -k guion` en verde, con el doble de DIgSILENT.
- [x] T5 PIDE: el banco que el valle no admite no se propone. (RF-28, RF-29)
      Hecho cuando: `pytest -q tests/test_valle.py -k pide` en verde.
- [x] T6 Informe y compatibilidad. (RF-12, RF-30, RF-31, RF-32)
      Hecho cuando: `pytest -q tests/test_valle.py -k informe` en verde.
- [x] T7 Entrada para el pronóstico, sin sustituir a la medición. (RF-33)
      Hecho cuando: `pytest -q tests/test_valle.py -k pronostico` en verde.
- [ ] T8 [DIgSILENT] Calibrar a valle en «Valle <año>» y correr la escalera con esos puntos, sobre un proyecto de prueba de la sesión.
      Hecho cuando: el flujo a valle cuadra con la cabecera medida (`m:Psum`, memoria iopt-lev), la máxima sigue idéntica, y la tensión del oráculo y la de DIgSILENT quedan comparadas con una variante de bancos.
- [x] T9 Alimentador con central: el valle con su curva de demanda, `curva_de_demanda`, en vez de dejarlo sin comprobar. (RF-12)
      Hecho cuando: una prueba con una central da su valle por la demanda, no por la cabecera.
      Hecho el 2026-11-03: `valle.curva_con_central` y `_valle_del_proyecto`, con los medidores de `centrales_termicas` del
      perfil. Sobre curvas sorteadas el valle cae en el de la demanda y la cabecera sola lo daría donde genera la central.
      `pytest -q tests/test_valle.py -k central` en verde (6). Sin DIgSILENT: la tensión en valle de una central real no se
      ha medido, y esa medida deja el generador como en la calibración.
- [x] T11 Corrección del usuario: energía, duración por optimización, cargas nuevas en dos casos y toda obra. (RF-35, RF-36, RF-37, RF-38, RF-39, RF-40, RF-41)
      Hecho cuando: `pytest -q tests/test_valle.py` en verde, y la lectura real de `CSG_DEMANDA_DIR` da inicio, fin y duración por objetivo.
- [x] T10 La web muestra `valle_texto` en la tabla de variantes de `CargasTab.tsx`. (RF-30)
      Hecho cuando: `pytest -q tests/test_valle_front.py` en verde, con `npx tsc --noEmit -p .` y `npm run build` correctos.
      Avance del 2026-11-03: columna «En valle» en `CargasTab.tsx`; `npm run typecheck` y `npm run build` con código 0. Falta verla:
      reiniciar la web y correr la escalera en «Con proyecto» sobre un proyecto de prueba, porque la tabla sale de ese resultado.
      Hecho el 2026-11-06: `tests/test_valle_front.py` (4) comprueba que la fila de la API lleva `valle_texto` de
      `frase_valle`, que la columna «En valle» cuadra con su celda y que el front no rehace la frase ni escribe «cumple en
      valle» (RF-31). La SET nueva, otra alternativa (RF-40), también enseña su `oraculo.valle_texto` en «Con proyecto».
      `npx tsc --noEmit -p .`, `npm run build` y `npm test` (40) con código 0; `frontend` no tiene guion `lint`. La vista
      en el navegador real, que pide correr la escalera en DIgSILENT, pasa a la T12.
- [ ] T12 [DIgSILENT] Ver la columna «En valle» y la frase de la SET nueva en el navegador real. (RF-30)
      Hecho cuando: con la web reiniciada, la escalera de «Con proyecto» sobre un proyecto de prueba de la sesión enseña en
      cada variante la frase del valle, o «no comprobado en valle» si no hay valle medido.
