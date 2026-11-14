# Spec 108 — Estudio de costos del VAD con la empresa modelo eficiente

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-18, y orden del usuario del 2026-11-14:
«haz nuevos spec». G0: `D:/csg/G0_PLAN_MAESTRO/D/D_FILAS_BP.md` y `MATRIZ_PIDE_NORMA_FORMULA_VARIABLE.md`.

## Contexto y objetivo
Osinergmin fija el VAD por grupos de empresas: grupo 1, 2026–2030; grupo 2, 2027–2031. Los términos de referencia
están en la RCD 174-2025-OS/CD y la 033-2026-OS/CD. El estudio se hace en cuatro etapas: recopilación, empresa modelo
eficiente, cargos adicionales y VAD. Sus anexos piden la caracterización de la carga (anexo 4), el modelo geométrico
urbano (anexo 5) y el modelo georreferenciado rural, que **conserva la traza real de MT/BT** y las SED reales (anexo 6).
G0 encontró que el conversor solo lee el VNR (RCD 184-2026) y cita el TdR en comentarios: no hay ningún flujo VAD. El
conversor ya tiene lo que el anexo 6 necesita (trazas reales, SED y demanda medida), pero **VNR real ≠ red óptima de la
empresa modelo**: esta spec crea ese cálculo separado.

## Usuarios / actores
- Equipo de regulación de la concesionaria que prepara su estudio de costos.
- Revisor que reproduce los libros.

## Historias de usuario
- H1: Como regulación, quiero armar la empresa modelo de un sistema típico desde el inventario VNR y la demanda
  medida, conservando las trazas reales en el modelo rural, para sustentar los costos del estudio.
- H2: Como revisor, quiero cada tabla del estudio con la fuente, la versión del TdR y la fórmula de cada celda.

## Requisitos funcionales (EARS)
- RF-1: EL SISTEMA guardará el estudio VAD aparte del PIDE y del PIT, con su grupo, su periodo y su empresa.
- RF-2: CUANDO el operador cargue el inventario VNR, las tablas técnicas, comerciales y contables y los costos de un
  sistema, EL SISTEMA validará cada tabla contra el formato del anexo 2 vigente, con sus unidades y su periodo.
- RF-3: SI una tabla obligatoria falta o trae unidades distintas de las del anexo, ENTONCES EL SISTEMA lo dirá por
  tabla y campo, sin rellenarla.
- RF-4: EL SISTEMA caracterizará la carga del sistema (factor de carga, simultaneidad y curvas MT/BT) desde la
  medición del conversor, según el anexo 4.
- RF-5: CUANDO se arme el modelo georreferenciado rural, EL SISTEMA usará las trazas MT/BT, las longitudes y las SED
  reales del VNR sin alterar ningún vértice, y distinguirá la troncal de las derivaciones.
- RF-6: CUANDO se arme el modelo geométrico urbano, EL SISTEMA elegirá la red adaptada por densidad de carga según el
  anexo 5.
- RF-7: EL SISTEMA dimensionará la red de la empresa modelo (conductor, transformación y pérdidas) con el motor
  físico, y nunca dará como costo estándar el costo real del VNR sin ese cálculo.
- RF-8: EL SISTEMA calculará el COyM técnico (anexo 7), las pérdidas estándar y el balance de potencia y energía por
  sistema y tensión.
- RF-9: EL SISTEMA guardará con cada fórmula y cada parámetro el anexo, la versión del TdR, su estado jurídico y la
  moneda, con el IGV incluido o excluido según lo exija el anexo.
- RF-10: SI el TdR aplicable al grupo o al periodo no está registrado como vigente, ENTONCES EL SISTEMA no emitirá
  el estudio como conforme.
- RF-11: CUANDO se emitan los entregables, EL SISTEMA generará las tablas A y B en Excel con sus fórmulas, los mapas
  de densidad (anexo 9) y el manifiesto de fuentes con sus huellas.
- RF-12: EL SISTEMA registrará las observaciones del regulador con su respuesta y la tabla o el cálculo al que
  afectan.
- RF-13: EL SISTEMA no tendrá valores de una empresa, de un sistema típico ni de un periodo en el código (P13).

## Requisitos no funcionales
- Fidelidad geométrica: el hash de los vértices de cada tramo del modelo rural coincide con el del VNR.
- El armado de la empresa modelo es un trabajo en cola, cancelable (P7).
- Universal: las pruebas usan al menos dos empresas sintéticas.

## Casos límite
- Un sistema con zonas urbanas y rurales a la vez.
- Un VNR sin la geometría de parte de la BT.
- Un cambio del TdR a mitad del estudio.
- Una SED sin medición.

## Fuera de alcance
- La fijación tarifaria.
- El plan SMI (anexo 8) y los cargos adicionales de innovación, que se tratan en una iteración posterior.
- Copiar resultados de estudios anteriores: solo se aprende su estructura.
- Declarar el estudio «aprobado».

## Criterios de finalización
Cada RF citado por una prueba (`grep "108:RF-"`). El modelo rural conserva el hash de los vértices del VNR. Un libro
de un estudio publicado se reproduce en su estructura con una empresa autorizada, y un revisor coteja una muestra de
celdas.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario («debes hacer lo recomendado, piensa como un humano»), en
`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 3.
- Primer caso: Electro Dunas, del grupo 1 (2026–2030), **solo como caso de prueba**. Su nombre y su sistema típico
  van en el perfil local, nunca en el código ni en las pruebas (P13). Que pertenezca al grupo 1 se dedujo de los
  considerandos de la RCD 174-2025 y se comprobará en su anexo 1.
- Primera iteración: el anexo 6 rural, que reutiliza las trazas reales. El anexo 5 urbano (RF-6) viene después, en
  una tarea propia.
- Costos estándar: los del catálogo SICODI con `valorar_obra`, con la fuente anotada en cada elemento.
