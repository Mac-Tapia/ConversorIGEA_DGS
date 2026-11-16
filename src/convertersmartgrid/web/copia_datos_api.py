"""086:RF-85 y RF-86: la copia de los datos desde la web, como trabajo con progreso y cancelación.

Usuario, 2026-11-12: la web avisaba «Aún no hay ninguna copia de sus datos» y la copia solo se hacía con la orden
del manual. Ahora el aviso lleva «Hacer una copia ahora»: pide la carpeta, la recuerda en el equipo
(``config/copia_datos.json``, como ``config/archivo.json`` de la 105) y encola la misma ``crear_copia`` de la orden.

Prueba con la cuenta local, 2026-11-16: un clic escribía unos 20 GB en Google Drive, sin decir antes lo que ocuparía
ni ofrecer «Cancelar», y el aviso no veía la copia que ya estaba en la carpeta. Ahora la previa (aclaración de RF-82 y
RF-83, RF-108) dice lo que ocupará, lo libre y lo que se copia, con las copias que ya hay, sin escribir nada; y la copia
solo se encola con ``confirmada``, que la web manda al pulsar «Copiar».
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from .api_contract import CopiaDatosCarpetaRespuesta, CopiaDatosPeticion, CopiaDatosPreviaRespuesta, JobRespuesta

KIND = 'copia_datos'


def raices_del_servidor(raiz_datos: Path) -> dict[str, Path]:
    """Las raíces de esta instalación, con los espacios que sirve este servidor (``create_app(raiz)``)."""
    from . import copia_datos as copia

    raices = copia.raices_de_datos()
    datos = Path(raiz_datos)
    if raices['datos'].resolve() != datos.resolve():
        raices['datos'] = datos
        if 'heredada' in raices and raices['heredada'].resolve() == datos.resolve():
            del raices['heredada']
    return raices


def registrar_rutas_copia(app: FastAPI, *, ws_or_404, submit, en_curso: Callable[[], int], raiz_datos: Path,
                          rutas_locales: Callable[[], bool]) -> None:
    """Monta las rutas de la copia con la cola y los espacios del único servidor."""
    from . import copia_datos as copia

    @app.get('/api/copia-datos/carpeta', response_model=CopiaDatosCarpetaRespuesta)
    def copia_carpeta() -> dict:
        """086:RF-85: la carpeta que este equipo usó la última vez para sus copias."""
        carpeta = copia.carpeta_recordada()
        return {'carpeta': carpeta.as_posix() if carpeta else None}

    @app.get('/api/copia-datos/previa', response_model=CopiaDatosPreviaRespuesta)
    def copia_previa(carpeta: str = Query(min_length=1, max_length=1024), sin_modelos: bool = False) -> dict:
        """086:RF-82, RF-83, RF-108: lo que ocupará, lo libre, lo que se copia y las copias que ya hay; no escribe.

        Ni recuerda la carpeta: eso lo hace la copia, cuando el operador pulsa «Copiar».
        """
        if not rutas_locales():
            raise HTTPException(403, 'Este servidor no admite rutas locales.')
        try:
            destino = copia.validar_carpeta(carpeta)
            plan = copia.planificar_copia(destino, raices=raices_del_servidor(raiz_datos), sin_modelos=sin_modelos)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {**plan, 'texto': copia.texto_plan(plan), 'copias': copia.listar_copias(destino)}

    @app.post('/api/workspaces/{wid}/copia-datos', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def copia_lanzar(wid: str, body: CopiaDatosPeticion) -> dict:
        """086:RF-85, RF-86: recuerda la carpeta y encola la copia; con otros trabajos en curso no se empieza."""
        ws = ws_or_404(wid)
        if not rutas_locales():
            raise HTTPException(403, 'Este servidor no admite rutas locales.')
        # Aclaración de RF-82: nada se escribe sin que el operador haya visto lo que ocupará y pulsado «Copiar».
        if not body.confirmada:
            raise HTTPException(422, 'Antes de copiar, vea lo que ocupará la copia y pulse «Copiar».')
        # Copiar en medio de una calibración guardaría una mezcla de antes y de después (086:RF-10).
        ocupados = en_curso()
        if ocupados:
            raise HTTPException(409, f'Hay {ocupados} trabajo(s) en curso: la copia se hace con la web en reposo.')
        try:
            carpeta = copia.recordar_carpeta(body.carpeta)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        raices = raices_del_servidor(raiz_datos)

        def trabajo(ctx) -> dict:
            manifiesto = copia.crear_copia(
                carpeta, raices=raices, sin_modelos=body.sin_modelos,
                avisar=lambda plan: ctx.log(copia.texto_plan(plan)),
                progreso=ctx.progress, comprobar_cancelacion=ctx.check_cancel)
            ctx.log(f"Copia hecha en {manifiesto['ruta']}: {len(manifiesto['ficheros'])} ficheros físicos, "
                    f"{manifiesto['nombres']} nombres.")
            if manifiesto['errores']:
                for error in manifiesto['errores'][:20]:
                    ctx.log(f"No se copió {error['ruta']}: {error['motivo']}")
                # Una copia con errores no calla el aviso: el operador cree tener lo que no tiene.
                raise ValueError(f"La copia de {manifiesto['ruta']} tiene {len(manifiesto['errores'])} errores y no "
                                 'cuenta como buena.')
            return {'ruta': manifiesto['ruta'], 'bytes': manifiesto['bytes_total'],
                    'ficheros': len(manifiesto['ficheros']), 'nombres': manifiesto['nombres']}

        return submit(ws, 'copia_datos', 'Copia de los datos', trabajo, lane='engine')
