# Plan — Spec 067

## Módulos

| Parte | Ficheros | RF |
| --- | --- | --- |
| Evidencia de la web | `asistente/evidencias_web.py` (nuevo), `asistente/observacion.py`, `emit` de `web/app.py`, `asistente_revisar_plan` | 1 a 7 |
| Aviso del modelo | `asistente/transformer.py` (`motivo_no_disponible`), `asistente/plan.py` (`avisos`), `asistente_orden`, `Asistente.tsx` | 8 a 11 |
| Planes guardados | `asistente/planes_guardados.py` (nuevo), `GobiernoEquipo.sello/restaurar`, ruta `GET asistente/planes` | 12 a 19 |
| Modelos en uso | `asistente/modelos_en_uso.py` (nuevo), `model_registry.retirar_activo`, `destilacion_integral._referencia_activa`, `clasificador.entrenar_gobernado`, `tools/asistente_entrenar.py`, `tools/asistente_destilar.py` | 20 a 29 |
| Tareas | `asistente/tareas.py`, `ejecutor.py`, `interprete.py`, `equipo.py`, y los cuatro conjuntos de intenciones | 30 a 36 |
| Proyecto entero | `orquestador.vista_previa`, ruta `POST agente/proyecto/lista`, `ProyectoDesdeCero` | 37 a 40 |

## Decisiones

- **Evidencia en `emit`, no en cada servicio.** Todo trabajo pasa por ahí, también los que encola el asistente
  por HTTP. Alternativa descartada: una llamada en cada función de servicio, que se olvidaría en la siguiente.
- **Huella de fuente del vínculo primero.** Tras reiniciar la web la fuente no está en memoria, pero el proyecto
  ya importado sigue vinculado a la suya (spec 018). Usar solo la cargada dejaría sin evidencia el caso normal, y
  no inventa nada: es la huella con la que se aceptó el proyecto.
- **Puntero único.** `transformer.cargar` sigue leyendo `promovido.json`, que es la operación atómica; el registro
  decide quién puede escribirlo. Alternativa descartada: que `cargar` leyera del registro, porque los modelos
  heredados en uso no están en él y dejarían de cargar.
- **Comparación medida.** `entrenar_destilacion` pasaba `referencia=None`, así que la puerta «falta comparación»
  fallaba siempre. Medir el modelo en uso sobre la misma prueba no relaja nada: es lo que la puerta pedía.
- **Frase literal para tareas nuevas.** El Transformer en uso no conoce las tareas añadidas y no se pueden tocar sus
  pesos. Sin la regla, «haz la escalera de …» se entendería como `obras`. La regla solo actúa con tareas que el modelo
  no conoce, y siempre lleva a un plan con confirmación.
- **Token de lista.** Huella de espacio, fuente, solicitud y etapas: no autoriza nada que el operador no haya visto.

## Pruebas

Sin GPU, sin DIgSILENT y sin cargar modelos: dobles declarados de los motores, cola y rutas reales con `TestClient`.
Fichero `tests/test_asistente_operativo.py`.
