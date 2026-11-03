# Una spec citaba como evidencia un informe que nunca se confirmó

## Síntoma
El plan de la auditoría de raíz daba por entregables un informe por carpeta y un manifiesto de limpieza. Al cerrarla, ninguno de los dos estaba en el historial de git ni en disco. Además, el manual, un skill y la constitución seguían mandando a una carpeta de datos que ya había salido del proyecto.

## Causa
El informe se escribió fuera de lo confirmado y el código se integró sin él: ninguna comprobación relacionaba el plan con sus documentos. Si llegó a existir, no se sabe dónde quedó: causa sin confirmar en ese punto; solo una copia del informe la confirmaría. Las rutas viejas siguieron porque el traslado de los datos solo actualizó `CLAUDE.md` y las pruebas.

## Comprobación permanente
Una spec cumplida no puede citar un documento de `docs/` que no exista. Toda carpeta versionada de la raíz tiene que estar en el inventario, los enlaces locales de los documentos vivos tienen que resolverse y ninguno puede mandar a la carpeta de datos retirada.

## Prueba
- `tests/test_auditoria_raiz.py::test_una_spec_cumplida_no_cita_un_documento_que_no_existe`
- `tests/test_auditoria_raiz.py::test_el_informe_cubre_cada_carpeta_versionada`
- `tests/test_auditoria_raiz.py::test_los_enlaces_locales_de_los_documentos_existen`
- `tests/test_auditoria_raiz.py::test_ningun_documento_manda_a_la_carpeta_de_datos_retirada`
