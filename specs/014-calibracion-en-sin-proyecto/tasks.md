# Tareas — Spec 014

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Doble de DIgSILENT: `IntSstage.GetContents` lista los objetos que cambió la
      etapa, y hay un ayudante para crear una variación del operador con un `ElmTr2`.
      (Base de las demás)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_casos_pf.py tests/test_ajuste_cabecera_guion.py tests/test_cargas_pf_guion_007.py` sigue en verde.
- [x] T2. `objetos_de_variacion`, `es_del_operador` y el grupo `operador` de
      `clasificar()`. (Definiciones; RF-3, RF-15, RF-20)
      Hecho cuando: `pytest -q tests/test_casos_pf.py -k operador` en verde, y una variación
      `Ajuste_…` con un `ElmTr2` sale del operador.
- [x] T3. `preparar()`: variaciones por caso, sin tocar las del operador; «Con proyecto»
      activa las del operador activas en «Sin proyecto» y lo informa.
      (RF-15, RF-16, RF-18, RF-20, RF-21, RF-22)
      Hecho cuando: `pytest -q tests/test_casos_pf.py` en verde.
- [x] T4. `preparar(sin_base=True)` y el ajuste lo llama si faltan los tres casos. (RF-5)
      Hecho cuando: `pytest -q tests/test_casos_pf.py tests/test_ajuste_cabecera_guion.py -k "sin_base or sin_casos"` en verde.
- [x] T5. Ajuste: desactiva solo los ajustes puros, mide con las del operador activas,
      graba en los escenarios de «Sin» y «Con» y nunca en «Caso base». Deja cada caso con
      su escenario activo, también si falla o se cancela. (RF-1 a RF-4, RF-14)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera.py` en verde.
- [x] T6. Ajuste: cargas nuevas fuera de servicio mientras se mide, restauradas al
      terminar o cancelar, y su demanda sin tocar. (RF-6 a RF-9)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py -k cargas_nuevas` en verde,
      con un caso cancelado.
- [x] T7. Gana lo manual: detectar el cambio manual con la etapa del último ajuste, dejar
      la carga fija y sin escribir, y avisar. (RF-10 a RF-13)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera.py -k manual` en verde.
- [x] T8. Cargas nuevas sin duplicados: índice una vez por trabajo, reutilizar, avisar de
      duplicadas y diferencias, activar las del operador en «Con proyecto» y preparar los
      casos si faltan. (RF-19, RF-21 a RF-28)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_007.py tests/test_cargas_pf_guion.py tests/test_cargas_pf.py` en verde.
- [x] T8b. Aviso sin bloqueo por modificaciones manuales, citado. (RF-17)
      Hecho cuando: una prueba con `014:RF-17` en verde.
- [x] T8c. Notas en las specs 004, 006, 007 y 011 sobre los RF que cambia la 014;
      `CODIGO_FUENTE.md` y `docs/MANUAL_COMANDOS.md` al día. (Trazabilidad)
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde.
- [x] T8c-015. La spec 015 (2026-10-14) cambia RF-5 y RF-10 y el contexto: anotado al
      final de la spec. La prueba de T9 se hace después de verificar el «Caso base» de
      CA101 (015, T12).
- [ ] T9. Prueba en DIgSILENT con CA101, sobre el proyecto existente y sin datos
      inventados:
      - un ajuste en «Sin proyecto» deja `_3` activa en «Sin» y «Con», y la cabecera
        incluye sus cuatro transformadores;
      - «Caso base» no cambia;
      - repetir una inserción de cargas nuevas no crea duplicadas;
      - el tiempo de leer las etapas queda medido. (Criterios de finalización)
      Hecho cuando: informe JSON de cada paso en `output/` y resultados anotados aquí.
- [x] T10. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "014:RF-[0-9]+" tests | sort -u` lista los 28 RF y la suite
      con las variables `IGEA_*` pasa.
      Hecho el 2026-10-14: los 28 RF citados; suite con las cinco variables, 1753 correctas
      (`docs/VERIFICACION_SPECS_2026-10-14.md`).
- [x] T11. La carga de una variación se reconoce también con el sufijo «(n)» que le pone la
      etapa (PN107, 2026-10-16), y por su punto con otro nombre. (RF-29, RF-30)
      Hecho cuando: las pruebas que citan 014:RF-29 y RF-30 pasan y reaplicar las cargas de PN107 en
      DIgSILENT reutiliza la variación de CH_9 en vez de crear otra.
      Hecho el 2026-10-16: borrada la variación duplicada de CH_9 (14:05) y sus símbolos;
      reaplicada la tanda en DIgSILENT, CH_9 se reutiliza (Carga_CH_9_PN107_20261016_100306),
      no se crea ninguna y «Sin proyecto» y «Con proyecto» ejecutan el flujo.
