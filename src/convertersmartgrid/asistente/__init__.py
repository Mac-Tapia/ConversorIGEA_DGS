"""Asistente de órdenes en lenguaje natural (spec 026).

El operador escribe en la web lo que quiere; un Transformer propio, entrenado en la
máquina, reconoce la tarea y sus datos, y si duda consulta a un modelo local de Ollama.
El plan se contrasta con lo que existe, se explica y, si escribe, espera confirmación; la
ejecución pasa por las mismas rutas y trabajos de la web. Además conoce el proyecto
(índice de código y specs), vigila trabajos, modelos y resultados, prepara mejoras en
ramas que el operador revisa y busca en internet sin sacar datos de la máquina.
"""
