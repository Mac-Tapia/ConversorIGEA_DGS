# Tareas — Spec 013

Escritas el 2026-10-29 en la revisión 033: la spec tenía código y pruebas sin `tasks.md`. Las
tareas hechas recogen lo que ya estaba implementado, con las pruebas que lo citan; las
abiertas, lo que falta. Una tarea cada vez, pruebas primero.

- [x] T1. Carpeta de libros mensuales de clientes: índice, mes por el nombre o por una fecha
      del libro, duplicados y reescaneo. (RF-1 a RF-6)
      Hecho cuando: las pruebas que citan 013:RF-1 a RF-6 pasan (`tests/test_demanda_medida.py`,
      `tests/test_demanda_medida_web.py`).
- [x] T2. Mes de análisis en «2.3»: selector vacío al entrar, elegido y cambiado por el
      operador, máxima y cruce del mes, sin libro del mes reparto por kVA, aviso del mes de la
      máxima de cada alimentador y libro usado en el resultado. (RF-7, RF-8, RF-10 a RF-13,
      RF-15, RF-16)
      Hecho cuando: las pruebas que citan esos RF pasan (`tests/test_cargas_tres_pasos_front.py`,
      `tests/test_central_termica_front.py`, `tests/test_demanda_medida_web.py`,
      `tests/test_client_period_contract.py`).
- [x] T3. Retro (033): «todo el periodo» y las curvas, implementados por la 025 y la 021.
      (RF-17 a RF-21)
      Hecho cuando: las pruebas de 025:RF-10, 021:RF-17 a RF-19 y 006:RF-33 citan también
      estos RF y pasan.
- [x] T4. Retro (033): el ajuste exige que el libro de clientes sea del mes de la máxima y
      guarda su evidencia (commit `d80aab22`). (RF-30 a RF-32)
      Hecho cuando: `pytest -q tests/test_client_period_contract.py tests/test_client_period_autoselect.py`
      en verde.
- [ ] T5. Sin periodo elegido no se busca la máxima ni se habilitan el ajuste y la
      transferencia; junto a la máxima del mes, la del periodo entero y su mes. (RF-9, RF-14)
      Hecho cuando: pruebas de la API y del front que citan 013:RF-9 y RF-14 en verde.
- [ ] T6. Transferencia en el instante común del mes: instantes coincidentes sin interpolar,
      dominancia, carga transferida y SED que cambian de alimentador por sentido y enlace,
      cabeceras antes y después, hoja aparte en el descargable, instante crítico y bloqueo sin
      evidencia completa, sobre `fake_pf`. (RF-22 a RF-29)
      Hecho cuando: pruebas que citan 013:RF-22 a RF-29 en verde, con curvas sorteadas.
- [ ] T7. [DIgSILENT] Transferencia entre CA101 y PE104 en el mismo instante desde la web,
      con el descargable releído. (RF-22 a RF-29)
      Hecho cuando: el usuario confirma la transferencia, las SED transferidas y el instante.
- [ ] T8. Validación: cada RF citado por al menos una prueba y en verde. (RF-1 a RF-32)
      Hecho cuando: `grep -rnoE "013:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-32.
