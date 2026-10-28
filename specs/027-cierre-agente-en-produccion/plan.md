# Plan — Spec 027: cierre del agente en producción

Estado: borrador del 2026-10-28, pendiente de aprobación junto con la spec.

## Módulos y lo que cubre cada uno

| Parte | Ficheros | RF |
| --- | --- | --- |
| A. Episodios de todos los sistemas | `web/services.py` (tras calibrar, obra o estudio), `digital_twin/capture.py`, `digital_twin/buffer.py` | RF-1 |
| B. Particiones por familia | `digital_twin/evaluacion.py` (`particion` por sistema eléctrico, no por hash de familia), `oraculo.entrenar` | RF-2, RF-3 |
| C. Escenarios en copias | `digital_twin/escenarios.py` (muestreo por hipercubo latino del rango medido de cada cabecera) | RF-4 |
| D. Entrenamiento robusto | `digital_twin/oraculo.py` (`Entrenamiento`: `paciencia`, `lr_min`, `clip`; mejor época por validación), `digital_twin/temporal.py` | RF-5, RF-6, RF-10, RF-11 |
| E. Búsqueda de hiperparámetros | `digital_twin/hiperparametros.py` (nuevo), `tools/digital_twin_entrenar.py --buscar` | RF-7 |
| F. Manifiesto y reproducibilidad | `digital_twin/oraculo.guardar` (manifiesto con commit y huellas), `torch.use_deterministic_algorithms` | RF-8, RF-9 |
| G. Incertidumbre conforme | `digital_twin/oraculo.py` (cuantil conforme normalizado por la dispersión del conjunto) | RF-12, RF-13 |
| H. Optimización verificada | `digital_twin/evolutivo.py` (top-k), guion de DIgSILENT por `pf_arnes` (`tools/digital_twin_snapshot_pf.py`) | RF-14, RF-15, RF-16 |
| I. Asistente con órdenes reales | `asistente/almacen.py`, `asistente/transformer.py` (`Puertas`), `asistente/ejecutor.py` (un reintento con el error) | RF-17 a RF-20 |
| J. Ajuste LoRA/QLoRA (condicional) | `asistente/lora.py` (nuevo), `tools/asistente_lora.py` (nuevo) | RF-21 |
| K. Operación | `digital_twin/oraculo.deriva`, `asistente/vigilancia.py`, ruta de vuelta atrás en `web/app.py` | RF-22 a RF-24 |
| L. Trabajador del motor | `web/jobs.py` (carril `engine` en un proceso aparte), `web/services.py` | RF-25 a RF-27 |
| O. Recompensas, penalizaciones y decisión | `asistente/almacen.py` (señal y pares), `asistente/reflexiones.py` (nuevo), `asistente/interprete.py` (umbrales por tarea, ejemplos parecidos), `asistente/indice.responder` (citas comprobadas) | RF-35 a RF-42 |
| P. Proyecto desde cero y PIDE | `asistente/orquestador.py` (nuevo: etapas, puntos de control y reanudación sobre `asistente/ejecutor.py`), `pide_dataset.py` (corpus de PIDEELOR), `asistente/ejemplos_pide.py` (nuevo), `pide.py`, `pide_economia.py` (sin cambiar la norma) | RF-43 a RF-52 |
| N. Auditoría del dataset | `digital_twin/auditoria.py` (nuevo), `tools/digital_twin_auditar.py` (nuevo), `oraculo.entrenar` y `asistente/transformer.entrenar` la llaman antes | RF-29 a RF-34 |
| M. Aceptación | `tools/sistema_web.py` y el asistente sobre todos los sistemas | RF-28 |

## Decisiones

1. **Evaluación «un sistema fuera» (RF-2)** en lugar de particionar por hash de episodio. Con
   hash, episodios casi iguales de IN111–TA225 caen en entrenamiento y prueba y el error sale
   optimista; Donon (2022) y Lin et al. (2024) miden la generalización a redes no vistas.
2. **Parada temprana, coseno y recorte de gradiente (RF-5, RF-6)** frente a 300 épocas fijas.
   Son las prácticas que Bischl et al. (2023) piden para que el resultado no dependa del
   número de épocas elegido a mano.
3. **Búsqueda con Optuna, TPE y poda por mediana (RF-7)** frente a rejilla. Con 4 a 6
   hiperparámetros (ocultas, pasos, lr, peso físico, paciencia, miembros), la rejilla crece
   exponencialmente. Bischl et al. (2023) recomiendan optimización bayesiana o Hyperband con
   presupuesto. Optuna es la herramienta y la fuente es la revisión. Es una dependencia nueva
   que se instala en `requirements.txt` y se prueba en `test_inventario`.
4. **Predicción conforme dividida y normalizada (RF-12)** frente a usar la dispersión del
   conjunto en bruto. Tres miembros no garantizan cobertura, y la conformidad la garantiza con
   la partición de validación sin reentrenar (Mollaali et al., 2024; Renkema et al., 2024).
5. **El sustituto propone y DIgSILENT confirma (RF-14, RF-15)**, como en los evolutivos con
   sustituto (He et al., 2023). Cada verificación descartada vuelve al búfer como episodio:
   así aprende el gemelo (aprendizaje activo, arXiv 2204.09053).
6. **Asistente: realimentación del error y un solo reintento (RF-20)**, como Jia, Cui y Hug
   (2024-2025) y ReAct (ICLR 2023). Se descartan reintentos ilimitados, que esconden fallos y
   gastan GPU.
7. **LoRA/QLoRA solo si las puertas no se cumplen (RF-21)**, frente a afinar siempre. Con
   pocas órdenes reales, afinar sobreajusta; Majumder et al. (Joule, 2024) señalan que la falta
   de datos del dominio es el límite principal. QLoRA (Dettmers et al., 2023) cabe en la GPU
   local.
8. **Carril `engine` en un proceso trabajador (RF-25)** frente a hilos. El lector de libros
   retiene el GIL y la memoria; el 2026-10-27 dejó la API sin respuesta y sin memoria. Un
   proceso aparte (spawn) aísla la memoria y deja libre el bucle de la API. Es la separación
   de servicio de la arquitectura MLOps de Kreuzberger et al. (2023).
9. **Aprendizaje continuo con repetición del histórico (RF-23)**: ya lo hace la 024 (ajuste
   fino desde los pesos promovidos, repitiendo todo el histórico). Es el método de repetición
   de Wang et al. (TPAMI, 2024) contra el olvido.

10. **El agente orquesta lo que ya existe (RF-43, RF-45)** en lugar de reimplementarlo: cada
   etapa es una ruta de la web ya probada (conversión, `sistema_web`, ajuste, obras, PIDE,
   informes). Es el patrón de Jia, Cui y Hug (2024-2025): el modelo razona y el simulador
   ejecuta y realimenta el error, con la traza auditable de ReAct.
11. **El corpus PIDEELOR como contexto y ejemplos, no como norma (RF-46 a RF-48)**: los PIDE 2021
   y 2026 de Electro Oriente enseñan la forma de los entregables. La norma es el contrato de
   2017. Recuperación con cita (Gao et al., 2023-2024), igual que el índice del proyecto.

## Pruebas

- Sintéticas sorteadas con semilla para todo el entrenamiento: parada temprana, planificador,
  manifiesto, reproducibilidad en GPU (la prueba se omite con un motivo explícito si no hay
  CUDA), cobertura conforme sobre datos generados, top-k verificado con `fake_pf`.
- Trabajador del motor: una prueba de API que lanza un trabajo largo y comprueba que
  `/api/health` responde en menos de 1 s durante el trabajo (RF-26) y que el límite de memoria
  detiene el trabajo sin tumbar la API (RF-27).
- Asistente: conjunto de órdenes reales fijo y versionado. Las puertas se prueban con un
  conjunto pequeño sorteado y la evaluación real queda en el informe de la tarea.
- Aceptación (RF-28): en DIgSILENT, desde la web, sistema por sistema, con
  `tools/sistema_web.py`.

## Riesgos

- Pocos episodios por familia: hasta capturar episodios de cada sistema (T1 y T2), las puertas
  de RF-3 impiden promover. Es lo buscado, pero retrasa el cierre.
- LoRA en Windows: `bitsandbytes` y los pesos del modelo base ocupan GPU y disco; por eso es
  condicional (T11).
