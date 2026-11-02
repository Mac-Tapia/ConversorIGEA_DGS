# Integración del monitor del agente — 2026-11-01

El conversor incorpora el monitor en la pestaña **Asistente**, con operaciones del
espacio, etapas del proyecto, cancelación por la ruta existente y evidencia real
del aprendizaje. Implementación y aceptación de software: spec061, RF-1 a RF-10.

## Acceso verificado

- Servidor principal: <http://127.0.0.1:8765/?espacio=5f11283a33c94ea5&panel=asistente>.
  Consulta de solo lectura: monitor HTTP200, una operación activa, registro íntegro
  y cuatro informes. No se detuvo ni reinició este servidor. La huella de su proceso
  `b2920c5581be30c4` difiere de la del disco `821b2dd90b198f06` en la comprobación;
  no acredita la recarga de todas las últimas correcciones. Debe recargarse cuando
  termine su operación mediante el procedimiento habitual del conversor.
- Vista de verificación del mismo proyecto, con servidor actualizado y espacio
  aislado: <http://127.0.0.1:8766/?espacio=ae9551fd68b84bf1&panel=asistente>.
  Se cargaron los tres TXT reales de referencia; no se ejecutó PowerFactory.

## Funcionamiento y custodia

La cola publica los cambios por el WebSocket existente. El monitor agrupa consultas
al recibir esos cambios; no añade sondeo periódico. El diario SQLite por espacio
guarda los eventos y el contexto de fuente fijado al encolar. El historial sobrevive
al reinicio y distingue trabajos de otra sesión sin reejecutarlos. Fallar al persistir
el encolado rechaza la operación y elimina su reserva en memoria; un fallo posterior
de persistencia se presenta como observación incompleta.

El ejecutor conserva las rutas, los carriles y las confirmaciones existentes. Un
código de proceso distinto de cero impide completar etapas. La reanudación verifica
la identidad de fuente y solicitud; el reinicio explícito archiva el control anterior.
El proceso hijo usa la URL del servidor que solicita la operación.

Los cuatro informes incorporados corresponden al ajuste GRU de enero, su reapertura,
la configuración del candidato y el intento LLM bloqueado por recursos. Cada copia
conserva procedencia y SHA256; se verifica tanto el contenido como su identidad.
Son evidencia global sin asignación implícita a proyectos. Mostrar el informe no
activa pesos, no promueve candidatos y no acredita aceptación eléctrica.

## Verificación efectuada

- `output/integracion_monitor_20261101/entrega.xml`: **176 pruebas aprobadas**, sin
  fallos, errores ni omisiones. Incluye API, cola, orquestador, monitor, vigilancia,
  inventario, trazabilidad y arquitectura interactiva; no es toda la suite del repositorio.
- Tras cerrar061 y regenerar el índice: **92 pruebas aprobadas** de trazabilidad e
  inventario (`cierre_indice.xml`), sin omisiones. Son una repetición de ese subconjunto,
  no 92 casos nuevos que sumar a los176. Revisión de espacios de los archivos afectados
  sin errores mediante `git diff --check`.
- Compilación TypeScript y Vite aprobada. Artefacto servido:
  `frontend/dist/assets/index-BeVpgonx.js`. Vite conserva el aviso de tamaño del bundle.
- HTTP real: carga de TXT, estado final, consulta del monitor y reapertura tras
  reiniciar el servidor de verificación; el trabajo anterior aparece como histórico.
  Evidencias: `http_real.json`, `http_reinicio.json` y `http_principal.json` en esa carpeta.
- WebSocket real: **11 eventos**, estados en cola/ejecutando/terminado y ocho líneas
  de registro. Esta carga no emitió avance numérico; no se inventó porcentaje.
  Evidencia: `websocket_real.json`.
- No se completó una inspección visual automatizada: el host del navegador no estaba
  disponible. Las comprobaciones HTTP y de compilación no sustituyen esa inspección.

## Alcance que sigue abierto

El monitor observa las operaciones de la cola y los informes incorporados; no vigila
cualquier proceso externo arbitrario. La ejecución sigue supervisada. El ciclo
autónomo sincronizado y su aceptación integral siguen abiertos en050. El candidato
GRU no está promovido. El entrenamiento generativo LLM completo sigue bloqueado por
recursos del entorno; el informe lo muestra como tal. Esta entrega no acredita
aceptación conjunta nativa ni modifica planos externos de IGEA.

## Justificación científica

La [tesis de maestría de Witossek, DLR/Leipzig, 2025](https://elib.dlr.de/220552/)
sustenta evaluar al alumno frente al maestro y al modelo base en el dominio. La
[tesis doctoral de Stiasny, DTU, 2023](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/)
sustenta contrastar los modelos informados por física con las referencias del
sistema eléctrico. El artículo de [Kreuzberger, Kühl y Hirschl, IEEE Access, 2023](https://doi.org/10.1109/ACCESS.2023.3262138)
respalda separar orquestación, seguimiento y ciclo de vida de modelos. Estas fuentes
justifican el diseño; los resultados locales proceden exclusivamente de los
artefactos de verificación enumerados arriba.
