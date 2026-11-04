# Tras reiniciar la web, un trabajo a medias desaparece sin rastro

## Síntoma
Con un proceso muerto a media corrida, otro gestor de trabajos veía una lista vacía: ni estado, ni avance, ni registro de lo que dijo el guion.

## Causa
Los trabajos y su registro vivían solo en la memoria del proceso. Los datos del espacio no se perdían, pero nadie sabía que algo quedó a medias.

## Comprobación permanente
`DiarioTrabajos` anota cada trabajo sin terminar y su registro línea a línea en `_trabajos/` junto a los espacios. Al arrancar, lo de un servidor muerto, comparando el pid y su hora de arranque, se ve como `interrumpido`, con el registro en `GET /api/jobs/{id}/registro`; no se relanza solo. Lo terminado se retira.

## Prueba
- `tests/test_trabajos_interrumpidos.py::test_matar_el_proceso_deja_el_trabajo_interrumpido_con_su_registro`
- `tests/test_trabajos_interrumpidos.py::test_la_api_lo_muestra_tras_reiniciar`
- `tests/test_trabajos_interrumpidos.py::test_pid_reutilizado_no_finge_un_trabajo_vivo`
