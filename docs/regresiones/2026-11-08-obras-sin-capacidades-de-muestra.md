# Obras sin capacidades ni tensiones de muestra

## Síntoma

Un usuario sin perfil de bancos recibía propuestas de300kvar a10kV y450kvar a22,9kV. Un perfil de banco inválido también se sustituía silenciosamente por esos valores. Sin par de tensiones elegido se proponía migrar10→22,9kV. Los ejemplos se habían convertido en parámetros físicos para cualquier usuario.

## Causa

042:RF-39 había tratado el módulo de banco como referencia universal; obras_escalera lo completaba incluso al capturar PerfilError. Parametros/parametros suponían10/22,9kV. La memoización podía retener capacidad de una elección anterior al pasar a un perfil vacío.

La aclaración expresa del usuario del2026-11-08 define las empresas/alimentadores y esas capacidades como muestras. Las nuevas capacidades y tensiones deben proceder del perfil o entrada real elegidos; la ausencia no impide calcular otras alternativas respaldadas.

## Comprobación permanente

Sin banco configurado, conservarNone y avisar que se omiten sus alternativas; sin par completo de migración, omitir solo cambio de nivel con motivo. Rechazar valores explícitos inválidos/no finitos antes de leer/operar el proyecto. Incluir módulos y par de tensiones en la identidad de memo. Ninguna muestra activa se copia, modifica o borra. Las fixtures que ensayan10→22,9kV lo declaran explícitamente.

La configuración válida conserva propuestas, parámetros, orden y avisos anteriores. Se comprueba también13,8→24,9kV y20→33kV, sin fijar empresa, geografía ni nombre real de alimentador.

## Prueba

- `tests/test_universalidad_obras.py::test_sin_par_de_tensiones_se_omite_solo_nivel_con_motivo` (042:RF-50).
- `tests/test_universalidad_obras.py::test_par_explicito_conserva_propuesta_sin_geografia_fija` (042:RF-50).
- `tests/test_universalidad_obras.py::test_servicio_sin_bancos_no_activa_modulos_de_muestra` (042:RF-39).
- `tests/test_universalidad_obras.py::test_servicio_rechaza_banco_invalido_antes_de_leer_proyecto` (042:RF-39).
- `tests/test_universalidad_obras.py::test_memo_no_reintroduce_bancos_de_un_perfil_anterior` (042:RF-39).

Evidencia externa: p25_universalidad_auditoria_20261108/correccion. RED: 14 fallos y 4 controles positivos; RED de memo: un fallo; RED de desbordamiento: un fallo. Regresión final: 235 casos sin omitidas. Contraste puro previo/actual: tres pares explícitos con propuestas y avisos idénticos; perfil vacío conserva tres alternativas restantes. Sin PF/GPU/instalación, sin aceptación nativa ni cambio de umbrales/costos/criterios eléctricos.
