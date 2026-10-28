# Arquitectura C4 interactiva - diseno

## Intencion

Presentar la arquitectura real de ConversorIGEA_DGS de forma didactica, navegable y
auditable. La persona usuaria debe poder ver el recorrido desde las fuentes de datos
hasta los entregables, reproducir el flujo paso a paso y abrir o copiar el punto de
acceso asociado a cada caja.

## Objetivos

- Mantener un modelo C4 textual, versionable y compatible con Structurizr DSL.
- Mostrar contexto, contenedores y tres flujos dinamicos: conversion, aceptacion
  PowerFactory y aprendizaje/decision.
- Animar cada relacion de forma finita al reproducir el flujo; respetar
  `prefers-reduced-motion`.
- Permitir seleccionar cajas y flechas con raton o teclado.
- Exponer rutas del repositorio, endpoints locales y entregables sin inventar
  integraciones externas.
- Funcionar sin red y sin dependencias JavaScript externas.

## No objetivos

- No ejecutar conversiones ni PowerFactory desde el diagrama.
- No presentar un DGS valido como aceptacion electrica o productiva.
- No publicar el servidor local en Internet ni eludir sus controles.
- No sustituir la documentacion, pruebas o evidencia nativa.

## Enfoques considerados

1. **Structurizr local puro.** Excelente fuente de verdad C4, pero su visor no ofrece
   el flujo animado finito solicitado con el nivel de control requerido.
2. **HTML manual sin modelo.** Permite animacion, pero duplica la arquitectura y deriva
   rapidamente respecto del codigo.
3. **Seleccionado: Structurizr DSL + visualizador HTML complementario.** El DSL conserva
   la semantica y las vistas C4; el HTML ofrece reproduccion, seleccion y acceso directo.

## Diseno de la interaccion

- Barra superior: vista C4 o flujo dinamico, Reproducir/Pausar, Paso siguiente,
  Reiniciar y velocidad.
- Lienzo SVG: cajas accesibles y flechas seleccionables. Solo la transicion activa
  muestra desplazamiento y una particula; la animacion termina al completar el flujo.
- Panel de detalle: responsabilidad, tecnologia, ruta/URL y salida de la caja o flecha.
- Vista estrecha: lista secuencial equivalente para conservar legibilidad.
- Enlaces `http://127.0.0.1:8765` se pueden abrir; las rutas locales se copian para
  abrirlas en el editor o explorador.

## Vistas

- `SystemContext`: operador, fuentes, ConversorIGEA_DGS y PowerFactory.
- `Containers`: React, FastAPI, motor, ejecutor nativo, gemelo, asistente y almacenes.
- `Conversion`: fuente -> API -> custodia -> modelo -> DGS -> validacion/publicacion.
- `PowerFactory`: solicitud -> cola -> preflight consultivo no bloqueante -> importacion nativa -> Caso base/flujo -> guardado y reread.
- `Inteligencia`: episodio -> buffer -> modelos -> optimizacion -> confirmacion -> informe.
- `Deployment`: navegador, Python 3.12, archivos/SQLite, Ollama/GPU y PowerFactory 2024.

## Criterios de aceptacion

- El DSL contiene las seis vistas y enlaces a archivos o endpoints reales.
- El HTML funciona sin errores JavaScript y pesa menos de 1 MB.
- Reproducir recorre todas las flechas y se detiene al final.
- Pausar, avanzar, reiniciar, cambiar vista y seleccionar una caja funcionan.
- El modo de movimiento reducido elimina la animacion continua.
- La vista no corta etiquetas a 1024 px y ofrece alternativa legible a 320 px.
