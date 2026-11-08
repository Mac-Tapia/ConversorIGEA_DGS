# Bitácora MCP perdida por codificación de stderr en Windows

## Síntoma

`test_servidor_real_por_stdio` terminaba aprobado con el servidor en código 0,
pero pytest advertía una excepción de su hilo lector: `UnicodeDecodeError` al
decodificar stderr como UTF-8. Se perdía parte del diagnóstico de las lecturas
rechazadas; con la advertencia tratada como error, la prueba fallaba.

## Causa

El cliente MCP filtra las variables heredadas al lanzar el servidor. Configurar
`PYTHONIOENCODING=utf-8` solo en el cliente no configura el hijo. El guion fijaba
UTF-8 para stdout, mientras la bitácora JSON con acentos salía por stderr en
CP1252. «catálogo» produjo el byte inválido `e1` en la posición 2561 del ensayo.

## Comprobación permanente

`tools/mcp_conversor.py::main` configura ambos canales como UTF-8 antes de
analizar argumentos o arrancar el servidor. Stdout conserva el protocolo y
stderr conserva la bitácora; no se mezclan. Las pruebas de stdio capturan bytes
y decodifican ambos canales estrictamente, conservando el código de salida y
las comprobaciones de herramientas, permisos y datos locales. El rechazo de
una herramienta inexistente debe dejar su diagnóstico completo con acentos.

## Prueba

- `tests/test_mcp_conversor.py::test_servidor_real_por_stdio`
- `tests/test_mcp_conversor.py::test_servidor_real_y_sus_datos_locales`
- `tests/test_mcp_conversor.py::test_error_cli_con_entorno_cp1252_conserva_utf8`

Ejecutar el módulo con
`-W error::pytest.PytestUnhandledThreadExceptionWarning`. La prueba de CLI fuerza
CP1252 y exige código 2 y el argumento con acento intacto. El ensayo real stdio
requiere el paquete opcional MCP; una omisión no acredita esta regresión.
