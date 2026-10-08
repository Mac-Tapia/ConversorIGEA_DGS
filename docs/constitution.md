# Constitución — Conversor IGEA/CYMDIST → DGS

Principios innegociables. Toda spec (`specs/NNN-*/spec.md`), plan y tarea los cumple; si
una spec necesita romper uno, primero se cambia este documento, con su motivo.

No son reglas nuevas: resumen las de `CLAUDE.md` y los skills `igea-dgs-backend` y
`igea-dgs-frontend`, que siguen siendo el detalle vigente. Cada principio dice cómo se
comprueba; uno que no se pueda comprobar no es un principio.

1. **Determinismo.** Misma entrada, perfil y alias dan el mismo DGS byte a byte, con
   `workers=1` y con `workers>1`. *Se comprueba:* `TestParallelWorkers`.
2. **Escala variable.** El número de alimentadores no está fijado (10, 50, 200…): nada
   de recorrer una tabla entera por alimentador, ni números fijos en código o pruebas.
   *Se comprueba:* `TestNoFullTableScanPerFeeder` y las pruebas sorteadas con `ExportSpec(seed=…)`.
3. **Dos disposiciones de export.** Todo cambio en el lector se prueba con la reducida y
   con la completa. *Se comprueba:* `tests/test_export_layouts.py`.
4. **Modo estricto y sin referencia en runtime.** No se inventan tipos `DEFAULT`; los
   alias solo vienen de un JSON del usuario; `NA205.dgs` es solo de desarrollo.
5. **Una sola vía para las reglas.** Toda conversión pasa por `reglas.py`
   (`preparar_dataset`, `aplicar_reglas`, `auditar_completitud`); una vía nueva las
   llama, no las copia. Lo mismo vale para leer la entrada y escribir el DGS: una
   responsabilidad, un sitio.
6. **Publicación atómica e independencia por alimentador.** Nunca queda un `.dgs` a
   medias; un alimentador que falla no invalida a los demás; `batch_manifest.json` se
   escribe siempre, también al cancelar.
7. **Nada largo dentro de una petición HTTP.** Lo que tarda más de un segundo es un
   trabajo en cola, con progreso por WebSocket y cancelable; PowerFactory, en un único
   carril en serie.
8. **Entorno.** Python 3.12 exacto (lo exige `powerfactory.pyd` de PF 2024). Todas las
   dependencias del núcleo en un único `requirements.txt`, salvo los drivers opcionales de
   VNR-GIS, que van en `requirements-drivers.txt`: un driver que no se descargue no
   puede impedir instalar el conversor. Un módulo externo (spec 002) declara las suyas en
   su propio paquete, y ninguna puede ser necesaria para instalar o arrancar el núcleo.
   *Cambio del 2026-10-08:* antes no había módulos externos; se permite para que un
   estudio o un formato nuevo se distribuya sin tocar este repositorio.
9. **Datos de la distribuidora.** Los TXT de `referencia/` y las bases de
   `D:\BaseDatosElectroDunas` nunca se publican, ni se suben, ni se envían a un servicio
   externo, tampoco a un modelo de IA de terceros. Un módulo externo solo se carga si
   figura en la lista de módulos permitidos, porque se ejecuta con acceso a esos datos.
   *Se comprueba:* prueba de que un módulo instalado y no permitido no se carga.
10. **Idioma y estilo.** Código, comentarios, mensajes y commits en español. Los
    comentarios explican el **porqué**, con el caso real que lo motivó.
11. **Las pruebas son la puerta.** Una tarea termina con la suite en verde, y con datos
    reales (las tres variables `IGEA_*`) si toca el lector o el modelo. Sin ellas, la suite
    «pasa» sin haber probado nada real.
12. **La spec manda.** Un comportamiento nuevo entra primero en la spec activa y luego en
    el código; cada requisito `RF-n` tiene al menos una prueba que lo cita.
13. **Universal.** El conversor carga TXT, MDB y paquetes VNR-GIS de cualquier
    distribuidora. Los datos de Electro Dunas son un caso de prueba, no el diseño. Toda
    convención propia de una empresa (CRS de origen, prefijo de las SED de medición, forma
    de los nombres de alimentador, escala del diagrama) va en un perfil de empresa, nunca
    en el código ni como valor por defecto. *Se comprueba:* las pruebas sintéticas
    convierten con al menos dos perfiles distintos, y la comprobación de universalidad
    falla si el núcleo contiene códigos, CRS o prefijos de una empresa concreta.
    *Añadido el 2026-10-08:* el CRS de Ica y la exclusión de SED `M…` estaban fijados
    por defecto, y en otra empresa desplazarían la red o borrarían SED reales sin aviso.
