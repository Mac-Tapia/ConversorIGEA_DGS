# Tareas — Spec 050

- [ ] T1. Auditar y congelar una instantánea común real. (RF-1, RF-2, RF-8)
      Hecho cuando: pruebas de custodia/contexto pasan y existe manifiesto local con copias verificadas de todos los datos requeridos.
- [ ] T2. Preparar datasets por familia con procedencia y replay sin fuga. (RF-2, RF-3, RF-6, RF-9)
      Hecho cuando: preparación real contrasta fuentes/etiquetas y pruebas rechazan predicciones presentadas como resultados eléctricos.
- [ ] T3. Conectar el ciclo común a coordinador, cola y vigilancia. (RF-4, RF-5, RF-8)
      Hecho cuando: cambio de datos real inicia un ciclo único, cancelable y presupuestado; las etapas consumen la instantánea y no promueven por separado.
- [ ] T4. Evaluar retención y publicar el conjunto compatible. (RF-5, RF-6, RF-7)
      Hecho cuando: modelos reales entrenados/reabiertos superan puertas individuales y conjuntas, y promoción/reversión se verifican por readback.
- [ ] T5. Verificar el ciclo automático completo y sus estados web/CLI. (RF-4, RF-8, RF-9, RF-10)
      Hecho cuando: una segunda captura real demuestra deduplicación y actualización, con evidencia sin skips de funcionamiento y rechazo de regresiones.

## Evidencia y límites actuales

2026-11-01: inspeccionados búfer/captura, oráculo, series, vigilancia, registro y
coordinador. Existen piezas de aprendizaje; no hay evidencia de aceptación de un
ciclo sincronizado integral. En 047 T7 se auditó el corpus real, pero el primer
ajuste generativo falló con error Windows 1455; no se produjeron pesos entrenados.
Estas observaciones justifican mantener todas las tareas abiertas.
