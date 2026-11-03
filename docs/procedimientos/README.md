# Procedimientos del conversor para el asistente

Lo que el asistente debe saber hacer, paso a paso, con la ruta de la web o la herramienta de cada paso. El usuario, el
2026-11-02: «debes enseñarle desde el reinicio de la web, entrada de su acceso directo, cómo se reconstruye, lo faltante, cómo
se hace converger, cómo se reemplaza con datos de catálogo».

Reglas comunes:

- Cada afirmación lleva su cita, `` `fichero:línea` («texto de esa línea») `` o `NNN:RF-n`. La comprueba
  `tests/test_procedimientos.py`; si una cita no casa, el procedimiento está desfasado y no se usa.
- Lo que solo puede hacer una persona (abrir el acceso directo, mirar DIgSILENT a mano) lo pide el asistente al operador; no lo
  ejecuta.
- Sin datos de ninguna distribuidora: `<espacio>`, `<proyecto>`, `<alimentador>`, `<zonal>`, `<periodo>` y `<ruta>` son marcadores.
- Una fuente por vez: TXT, MDB y VNR-GIS no se mezclan en una conversión, un espacio ni una orden.

| Procedimiento | Fichero |
| --- | --- |
| Reiniciar la web con su acceso directo | `reiniciar_la_web.md` |
| Reconstruir lo que la fuente no trae | `reconstruir.md` |
| Completar lo que falta | `completar_lo_que_falta.md` |
| Hacer converger | `hacer_converger.md` |
| Reemplazar con datos del catálogo | `reemplazar_con_el_catalogo.md` |
