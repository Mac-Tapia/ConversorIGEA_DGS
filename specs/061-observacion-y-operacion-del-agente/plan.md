# Plan — Spec 061

1. `asistente/observacion.py`: diario SQLite por espacio de estados de trabajos,
   historial acotado por consulta y copias inmutables de evidencia local. Solo metadatos;
   sin Torch, ejecución de informes ni etiquetas físicas generadas. RF-1/2/3/8/9.
2. `web/app.py`: conectar eventos `job` a ese diario y exponer una consulta por espacio.
   `JobManager.submit` revierte el registro en memoria si falla la publicación inicial;
   se conserva la cola y el WebSocket. RF-1/3/4/5/10.
3. `web/services.py`: componer contexto, checkpoint, modelos globales e informes,
   separando estados y bloqueos; fijar identidad del checkpoint y rechazar código1
   del proceso nativo en `agente_proyecto`. RF-6/7/9.
4. `frontend/src/components/MonitorAgente.tsx`: vista de supervisión con estado,
   etapas, operaciones, cancelación mediante API existente e informes verificables.
   Suscribirse a cambios de `jobs` del contexto, con peticiones agrupadas; sin intervalo.
   RF-2/3/4/5/9.
5. `tools/asistente_observar.py`: incorporar explícitamente informes locales para
   observar entrenamientos ya ejecutados. Copias rotuladas globales, sin activar pesos.
   Registrar los informes reales de GRU/LLM de060. RF-8.
6. Pruebas de diario, fallos, API y orquestación; TypeScript/build y prueba HTTP de la
   interfaz compilada. Publicar en el servidor principal solo si está libre; conservar
   el trabajo actual si hay operaciones activas. RF-1 a RF-10.

No se crea un segundo registro de promoción: el diario conserva operaciones e
informes observados; `RegistroModelo` conserva la autoridad sobre modelos aceptados.
