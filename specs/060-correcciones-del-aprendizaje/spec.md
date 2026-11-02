# Spec 060 — Correcciones verificables del aprendizaje

Estado: cumplida · Fecha: 2026-11-01

## Contexto y autorización

El usuario pide aplicar la auditoría de alumnos, cumpliendo las specs y la arquitectura moderna. Esta ampliación consume 027, 043, 046, 047 y 050; conserva lectores, coordinador, registro y almacenamiento existentes. No declara cumplidas esas specs por corregir estos defectos.

## Requisitos

- RF-1: SI falta entrenamiento, selección, calibración o prueba independiente del PINN, ENTONCES EL SISTEMA impedirá iniciar el ajuste y conservará el modelo activo.
- RF-2: CUANDO ajuste el PINN, EL SISTEMA separará la calibración de la validación usada para parada temprana, conservará los IDs por partición y no reutilizará otra partición como respaldo.
- RF-3: SI la genealogía no demuestra que los datos de calibración y prueba quedaron fuera del ajuste y selección del antecesor, ENTONCES EL SISTEMA entrenará desde cero en vez de heredar esos pesos.
- RF-4: CUANDO prepare un corpus generativo, EL SISTEMA custodiará una copia verificada de la política usada para redactarlo, conservará su origen y rechazará cualquier cambio de esa copia.
- RF-5: CUANDO lea cabeceras temporales, EL SISTEMA reconocerá las fechas de texto soportadas por el lector compartido y rechazará con hoja y fila las fechas inválidas, duplicados, potencias ausentes y huecos sin inventar objetivos.
- RF-6: CUANDO persista un candidato GRU, EL SISTEMA conservará configuración completa, historial de ajuste, pasos y procedencia suficientes para reabrirlo con los mismos ajustes.
- RF-7: CUANDO muestre modelos, EL SISTEMA distinguirá los punteros heredados del registro común y señalará discrepancias sin convertir un modelo heredado en aceptado automáticamente.
- RF-8: CUANDO el operador o una campaña declare hojas y un intervalo temporal antes del ajuste, EL SISTEMA limitará la preparación a ese alcance explícito, conservará el libro original, sus hashes y los recuentos de exclusión por fecha, y rechazará cualquier defecto dentro del intervalo sin imputarlo.
- Aclaración de RF-2: la búsqueda de hiperparámetros usa la misma selección separada; no consume calibración ni prueba.

## Alcance y límites

Correcciones de contratos y ejecución con fuentes locales. Las nuevas campañas conservan destinos distintos de las anteriores. No se cambian hiperparámetros por intuición, no se mezclan proyectos ni se usa prueba para elegir configuración. El entrenamiento y la aceptación nativa requieren evidencia propia; quedan fuera de cualquier afirmación basada solo en pruebas de contrato.

## Fundamento consultado

La [maestría de Witossek, DLR/Leipzig, 2025](https://elib.dlr.de/220552/) justifica comparar maestro, base y alumno con datos de dominio. El [doctorado de Stiasny, DTU, 2023](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) fundamenta contrastar el sustituto físico con el simulador. [Karniadakis et al., Nature Reviews Physics, 2021](https://doi.org/10.1038/s42254-021-00314-5) sustenta evaluar precisión y dominio del modelo físico. [Split Conformal Prediction and Non-Exchangeable Data, JMLR, 2024](https://jmlr.org/papers/v25/23-1553.html) fundamenta explicitar las condiciones de calibración; la separación no demuestra por sí sola intercambiabilidad ni cobertura en otra red.
