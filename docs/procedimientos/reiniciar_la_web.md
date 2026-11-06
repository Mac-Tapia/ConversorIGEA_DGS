# Reiniciar la web con su acceso directo

Cuándo: después de cambiar el código de la web o el del conversor que la web usa (`CLAUDE.md:178`
(«reiniciarla: parar»)). Los guiones de `tools/` no hacen falta: el servidor de DIgSILENT los vuelve a cargar en cada orden.

1. Comprobar que no hay trabajos en curso en ningún espacio. Si hay uno que deba pararse, se cancela por la web con
   `POST /api/jobs/<id>/cancel` (`src/convertersmartgrid/web/app.py:1347` («/api/jobs/{job_id}/cancel»)); parar un cliente no
   para el trabajo (`CLAUDE.md:181` («POST /api/jobs/<id>/cancel»)).
2. **Lo hace el operador:** parar el proceso que escucha en el puerto 8765 y abrir el acceso directo «ConverterSmartGrid» del
   escritorio (`CLAUDE.md:179` («abrir el acceso directo»)). El asistente no cierra procesos ni abre accesos directos: se lo pide
   al operador y espera.
3. El acceso directo ejecuta `run_gui.bat`, que arranca `convertersmartgrid.web.runtime` (`run_gui.bat:17`
   («-m convertersmartgrid.web.runtime»)) y sirve la web en `http://127.0.0.1:8765/` (`run_gui.bat:5`
   («http://127.0.0.1:8765/»)).
4. Si ya hay un servidor en el puerto, el lanzador compara la huella del código del disco con la que publica el servidor y
   decide si reutilizarlo o reemplazarlo (`src/convertersmartgrid/web/runtime.py:236` («el acceso directo no sabía si»)).
5. Comprobar que responde: `GET /api/health`. Hasta entonces el asistente no lanza ninguna orden.

Si una herramienta conecta con DIgSILENT mientras la web está ociosa, le pide que se cierre (019:RF-14).
