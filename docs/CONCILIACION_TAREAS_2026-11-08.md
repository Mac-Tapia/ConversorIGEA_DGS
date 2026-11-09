# Conciliación de tareas por avance comprobado — 8 de noviembre de 2026

Orden expresa del usuario en la sesión de revisión: avisar a las otras sesiones que cierren las tareas cuyo trabajo ya avanzó y explicar por qué el total permanece en 115. Responsable de esta comunicación: REVISION-SPECS-20261108-56172510, Codex /root.

La instrucción se puso a disposición en `.agents/coordination/ACTIVE.md`. **El integrador comercial confirmó su lectura y aceptación** en la entrada «/root cierre — acuse de conciliación y ejecución, 2026-11-08», observada durante esta revisión. Asignó P22 a conciliar las 114 abiertas, P21 a revisar la entrega HARNESS exacta y P19 a corregir la procedencia de `veredictos`; el integrador conserva las escrituras de estados e índices. Ese acuse acredita recepción por el integrador y reparto de trabajo; todavía no es evidencia de cierres aplicados ni de recepción por todas las sesiones independientes.

## Destinatarios y trabajo solicitado

| Destinatario | Acción concreta | Evidencia que debe devolver |
| --- | --- | --- |
| Integrador de `codex/cierre-produccion-086-20261108` | Conciliar ahora las 115 tareas originales con su rama y sus recibos. Marcar las que satisfacen su criterio completo; actualizar las parciales con avance y faltante residual; reflejar aparte lo integrado en main. No esperar al cierre de todo el proyecto para registrar un cierre local ya verificable. | Tabla tarea → criterio original → commit → evidencia → decisión. Recuento de cerradas, parciales, bloqueadas y diferidas, con fecha y corte. |
| Integrador comercial y revisor P21 | Actualizar el checkpoint que aún espera HARNESS y las cifras provisionales de siete módulos/cinco tests: ya existe entrega `3de43109`, fuente `9e609f2c`, HANDOFF y ocho módulos declarados. Revisar e integrar o rechazar con motivo; evitar pedir otra vez una entrega disponible. | Acuse de revisión del HANDOFF, decisión sobre el rango y comprobación del corte combinado. La entrega no acredita campaña científica. |
| Responsable HARNESS-20261108 | Confirmar qué entregables del arnés están terminados, revisión y pruebas por SHA; separar la integración que corresponde al dueño comercial y las campañas que faltan. | Cierres propios identificados, transferencia al integrador y pendientes concretos. |
| Responsables P19/P21/P22 del cierre comercial | Entregar los cierres de sus subunidades ya verificadas y el faltante exacto de las tareas originales; sustituir notas de implementación pendientes que quedaron obsoletas. No modificar superficies reservadas a otro dueño. | Recibos por tarea/subunidad, no solo cantidades de pruebas o commits. |

## Por qué el contador sigue casi igual

- `main` `5617251012f39193297e19b299d8a179a8fe1f61`: 99 SPEC, 3.219 RF, 1.093 tareas, **115 abiertas**. Es un recuento de casillas, no de horas ni de código implementado.
- Rama comercial `09f6f3f3686819c230dbec0816d56b5f7ad75df2`: 99 SPEC, 3.226 RF, **114 abiertas**. Cerró 016:T18 y 081:T20 y añadió 065:T17: `115 - 2 + 1 = 114`.
- Hay trabajo implementado que conserva criterios adicionales: 002:T8 espera regresión real; 002:T11 conserva revisión visual; 050:T1b–T5b exige datos/ciclo/modelos reales; 086:T40 exige instalación del candidato final y su uso nativo. Deben mostrar avance y residuo, no aparecer como trabajo sin iniciar.
- La última suite completa registrada de la rama comercial, sobre `c6ec7fb8`, fue rechazada: 8.209 aprobadas, 36 fallidas y 9 omitidas. Las correcciones enfocadas posteriores no son todavía la nueva suite completa. Esto no impide cerrar una tarea independiente cuyo criterio ya esté satisfecho.
- Las tareas diferidas `012:T13` y `049:T4` constan en el registro comercial como decisiones previas del usuario; diferida no significa cumplida.

## Regla de cierre y devolución

1. Releer el criterio original y las aclaraciones vigentes; comprobar evidencia existente antes de repetir trabajo.
2. Si está cumplido, marcar su casilla en la rama dueña y anotar revisión, comando, resultado, ruta/hash y alcance.
3. Si falta solo una comprobación local autorizada, ejecutarla y resolver la casilla. Si requiere turno de motor/GPU o revisión humana, identificar ese paso con responsable.
4. Si sigue parcial, actualizar la descripción con **qué ya terminó** y **qué falta**, sin borrar el criterio original ni cerrar por cantidad de pruebas.
5. Regenerar `specs/README.md`, concordar `CLAUDE.md` y comprobar `tests/test_trazabilidad_specs.py` al cambiar estados. El integrador conserva la integración única y los cambios ajenos.
6. Devolver el recuento desglosado: original, cerradas con evidencia, altas nuevas, abiertas actuales, implementadas pendientes de aceptación, bloqueadas y diferidas. La reducción neta sola oculta trabajo y nuevas obligaciones.

## Fundamento consultado en la web

La distinción entre retroalimentación del proceso y del producto sustenta actualizar el registro al terminar cada unidad, sin confundirlo con aceptación del sistema: Eriksson y Mosaddegh, tesis de maestría, Lund, 2021, [texto institucional](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf). Viggiano, tesis doctoral, Sheffield, 2023, fundamenta contrastar modelos y datos frente al contexto medido y evaluar límites e incertidumbre, [repositorio institucional](https://etheses.whiterose.ac.uk/id/eprint/33810/). Shahin, Ali Babar y Zhu, *IEEE Access* 5 (2017), 3909–3943, DOI 10.1109/ACCESS.2017.2685629, sustenta visibilidad de resultados y confiabilidad de integración/entrega; [ficha institucional con enlace a Scopus](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/). Fuentes consultadas el 8 de noviembre de 2026; justifican el método, no certifican estas tareas.
