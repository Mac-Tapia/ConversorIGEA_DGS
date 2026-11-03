# Plan — Spec 076

- `docs/asistente/preguntas_entregables.jsonl`: el conjunto; `reparto` y `grupo_parafrasis` van en cada fila. (RF-1 a RF-3, RF-8, RF-17, RF-18)
- `docs/asistente/hechos_web.jsonl`: un hecho por botón o casilla, con componente, ancla, ruta y función de `api.ts`. (RF-19, RF-25)
- `docs/asistente/reglas_operador_sin_codigo.jsonl`: reglas de las memorias sin confirmar en el código. (RF-14)
- `docs/asistente/preguntas_entregables_huecos.json`: huecos, contradicciones y pendientes. (RF-13, RF-15, RF-26)
- `docs/asistente/preguntas_entregables_informe.md`: se genera con `informe`. (RF-13)
- `tools/preguntas_entregables.py`: `verificar`, `exportar`, `importar`, `informe`, `generar`, `cobertura`. (RF-4, RF-5, RF-8 a RF-13, RF-20 a RF-24)
- `tests/test_preguntas_entregables.py`: huella, fuentes, cifras, nombres, reparto, hoja y generador.

Decisiones:

- La huella es del contenido canónico sin los campos de revisión. Alternativa descartada: la de los bytes del fichero, que cambiaría
  al importar la hoja y al sacar CRLF.
- Reparto por `sha256` de una sal y el grupo, dentro de cada entregable y tipo. Alternativa descartada: `random` con semilla, porque
  añadir una fila cambiaría el orden de todas.
- La línea citada se comprueba con `git show` de la revisión fijada, que no se mueve; en el árbol basta que siga el ancla. Alternativa
  descartada: comprobar la línea en el árbol, que fallaría con cualquier cambio ajeno en `web/services.py`.
- `generar` reutiliza `sinteticos.expandir` para variantes y erratas, sin sus datos `{tipo}`: inventa códigos con forma de alimentador.
  Los marcadores se añaden después, y son de la forma `ALIM-A`, que no puede ser real.
- Un corpus estocástico excluye los hechos que cita una fila sellada; si no, enseñaría lo que se va a medir.

Pruebas: solo con el repositorio; no abren datos de la distribuidora, ni DIgSILENT, ni GPU.
