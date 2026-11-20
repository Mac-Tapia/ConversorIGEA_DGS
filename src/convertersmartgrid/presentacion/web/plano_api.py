"""111: la API del plano de la red. Toda regla eléctrica vive aquí, en el servidor; el navegador solo la pide (RF-15).

- ``GET …/plano``: la vista de los alimentadores pedidos, con todos los vértices de su fuente, su revisión de la red, el
  motor con que se estudiaría ahora y si hay mapa base (RF-1 a RF-3, RF-11, RF-17).
- ``POST …/plano/variaciones``: abre una variación sobre una revisión de la red; si la red ya cambió, ``409``.
- ``GET …/plano/variaciones``: las variaciones guardadas en el servidor y las que tienen estudio (RF-4, RF-12).
- ``GET/PATCH …/plano/variaciones/{vid}``: lee o edita la variación con su versión; una edición que no vale es ``422``
  con el motivo y una versión vieja o una red cambiada, ``409`` (RF-4 a RF-8).
- ``POST …/plano/variaciones/{vid}/deshacer|rehacer|confirmar`` (RF-9) y ``…/ajuste`` (propuesta, RF-7).
- ``POST …/plano/variaciones/{vid}/estudiar``: un trabajo en su carril, ``powerfactory`` con DIgSILENT disponible y el
  proyecto vinculado a la red cargada, ``engine`` con el motor abierto si no (RF-17, RF-18); el operador puede pedir
  uno u otro (RF-29), y un flujo que no converge termina «no converge» con su motivo (RF-28).
- ``GET …/plano/pagina``: la página del plano (``pagina_plano.py``), aislada como toda página generada (RF-14).
- ``GET …/plano/resultados`` y ``…/plano/comparar``: las capas y la comparación de dos casos (RF-10 a RF-13, RF-19).

La fuente de los datos (modelo con las reglas del proyecto, geografía de la conversión, licencia, vínculo y guion de
DIgSILENT) entra como un objeto (:class:`FuenteWeb` en la web), para que las rutas no dependan de un espacio real.
Las variaciones y sus resultados se guardan en ``<espacio>/variaciones_plano/`` con la escritura atómica única.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from ...adaptadores import plano_red, resultados_plano
from ...aplicacion import variacion_plano
from ...dominio.util import write_json_atomic
from .api_contract import (
    AbrirVariacionPeticion, AjustePlanoPeticion, CapasPlanoRespuesta, ComparacionPlanoRespuesta,
    EditarVariacionPeticion, EstudiarPlanoPeticion, JobRespuesta, PlanoRespuesta, PropuestaAjusteRespuesta,
    TurnoVariacionPeticion, VariacionesPlanoRespuesta, VariacionPlanoRespuesta,
)

#: El guion de DIgSILENT que estudia una variación del plano (T12).
GUION = 'variacion_plano_pf.py'
#: La acción del contexto firmado que el guion exige.
ACCION = 'plano'
CARPETA_RESULTADOS = 'resultados'


class FuenteWeb:
    """La fuente de la web: el espacio de trabajo, el perfil y DIgSILENT, solo por funciones públicas."""

    def alimentadores(self, ws) -> list[str]:
        """Los alimentadores con geografía de la conversión en la salida del espacio."""
        return sorted(p.name[:-len('_geography.json')] for p in Path(ws.out_dir).glob('*_geography.json'))

    def modelo(self, ws, alimentador: str):
        """El modelo con las reglas del proyecto, igual que en el DGS (P5)."""
        from . import services

        return services.build_model(ws, alimentador, geography=True)

    def ruta_geografia(self, ws, alimentador: str) -> Path | None:
        ruta = Path(ws.out_dir) / f'{alimentador}_geography.json'
        return ruta if ruta.is_file() else None

    def disponible(self) -> bool:
        """111:RF-29: DIgSILENT se puede usar en este equipo: una instalación con su API y el Python que pide.

        Se llamaba «licencia» y miraba solo si había intérprete: sin PowerFactory instalada daba el de la web y el
        estudio iba a DIgSILENT para fallar. La licencia solo se sabe al conectar, y su error lo dice el trabajo.
        """
        from . import services

        return services.digsilent_disponible()

    def vinculo(self, ws, project: str, alimentadores: list[str]) -> tuple[Any, bool]:
        """El vínculo del proyecto y si es el de la ejecución de la fuente que se ve en el plano."""
        from . import services

        binding = services.vinculo_del_proyecto(ws, project, alimentadores)
        run = str(getattr(binding, 'source_run_id', '') or '')
        return binding, bool(run) and run == str(getattr(ws, 'active_run_id', '') or '')

    def limites(self):
        from ...aplicacion.estudios_pf import limites_de_perfil

        return limites_de_perfil()

    def perfil(self) -> dict:
        from ...dominio.perfil_empresa import datos_perfil

        return datos_perfil()

    def guion(self, ws, ctx, plan: dict) -> dict:
        """Escribe el plan, ejecuta el guion con el intérprete de DIgSILENT y lee su informe."""
        import uuid

        from ...adaptadores.powerfactory_env import pf_subprocess_env, project_root, tools_dir
        from . import services
        from .requisitos import UserError

        estado = services.powerfactory_status()
        if not services.digsilent_disponible():
            raise UserError('DIgSILENT no se puede usar en este equipo: estudie con el motor abierto.')
        pf_dir = Path(estado['api_dir']) if estado.get('api_dir') else None
        token = uuid.uuid4().hex[:12]
        ruta_plan = Path(ws.plans_dir) / f'plano_pf_{token}.json'
        ruta_plan.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(ruta_plan, plan)
        informe = Path(ws.out_dir) / f'plano_pf_{token}.json'
        rc = ctx.run_process([estado['interpreter'], str(tools_dir() / GUION), '--plan', str(ruta_plan),
                              '--output-json', str(informe)], env=pf_subprocess_env(pf_dir), cwd=str(project_root()))
        if rc == 3:
            raise services.sin_conexion_digsilent()
        try:
            return json.loads(informe.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise UserError(f'El guion de DIgSILENT terminó con el código {rc} sin dejar su informe.') from exc


def _vista_y_revision(fuente, ws, alimentador: str) -> tuple[Any, dict, str]:
    """El modelo, la vista del plano y la revisión de la red de un alimentador."""
    modelo = fuente.modelo(ws, alimentador)
    ruta = fuente.ruta_geografia(ws, alimentador)
    geo = json.loads(ruta.read_text(encoding='utf-8')) if ruta is not None else None
    vista = plano_red.vista(modelo, geo)
    revision = plano_red.revision_red(str(getattr(ws, 'active_run_id', '') or ''),
                                      {alimentador: ruta} if ruta is not None else {})
    if ruta is None:
        vista['avisos'] = [*vista['avisos'], 'Convierta el alimentador para verlo sobre su trazo.']
    return modelo, {**vista, 'revision': revision}, revision


def _fondo() -> dict:
    from ...dominio.salidas_red import salida_permitida

    if salida_permitida('teselas'):
        return {'encendido': True, 'motivo': 'Mapa base encendido.'}
    return {'encendido': False, 'motivo': 'Sin mapa base: la salida de teselas está apagada.'}


def _ruta_resultado(ws, vid: str) -> Path:
    return variacion_plano.ruta_de(ws.root, vid).parent / CARPETA_RESULTADOS / f'{vid}.json'


def _leer_variacion(ws, vid: str) -> dict:
    try:
        return variacion_plano.leer(ws.root, vid)
    except variacion_plano.VariacionError as exc:
        raise HTTPException(422 if 'no válido' in str(exc) else 404, str(exc)) from exc


def _leer_resultado(ws, vid: str) -> dict:
    _leer_variacion(ws, vid)
    ruta = _ruta_resultado(ws, vid)
    if not ruta.is_file():
        raise HTTPException(404, 'Esta variación aún no tiene resultados: estúdiela primero.')
    return json.loads(ruta.read_text(encoding='utf-8'))


def _ejecutar(funcion, *args, **kwargs) -> dict:
    """Una operación del diario: 409 si la versión o la red cambiaron, 422 con el motivo si no vale."""
    try:
        return funcion(*args, **kwargs)
    except variacion_plano.ConflictoVariacion as exc:
        raise HTTPException(409, str(exc)) from exc
    except variacion_plano.VariacionError as exc:
        raise HTTPException(422, str(exc)) from exc


def estudiar(fuente, ws, ctx, vid: str, project: str | None, pedido: str | None = None) -> dict:
    """El trabajo de estudiar una variación: en DIgSILENT si toca, con el motor abierto si no; guarda el resultado."""
    v = variacion_plano.leer(ws.root, vid)
    modelo, vista, revision = _vista_y_revision(fuente, ws, v['alimentador'])
    if revision != v['revision'] or v.get('revision_cambiada'):
        raise variacion_plano.ConflictoVariacion('La red cambió desde que se abrió la variación: no se estudia.')
    motor, binding = _motor(fuente, ws, project, v['alimentador'], pedido)
    if motor['motor'] == 'DIgSILENT':
        from ...dominio.native_action import build_native_action_context

        plan = {'project': project, 'folder': _campo(binding, 'folder'), 'feeders': [v['alimentador']],
                'caso': v['caso'], 'stamp': time.strftime('%Y%m%d_%H%M%S'),
                'variacion': {'id': v['id'], 'version': v['version'], 'revision': v['revision']},
                'ediciones': resultados_plano.plan_pf(vista, v),
                'native_action_context': build_native_action_context(binding, project, [v['alimentador']], ACCION)}
        informe = fuente.guion(ws, ctx, plan)
        if informe.get('error'):
            from .requisitos import UserError

            raise UserError(f'DIgSILENT no pudo estudiar la variación: {informe["error"]}')
        resultado = resultados_plano.traducir_resultados_pf(
            informe.get('geo') or {}, plano_red.identidad(modelo), caso=v['caso'], revision=v['revision'],
            convergio=bool(informe.get('convergio')), mensajes=list(informe.get('mensajes') or ()))
        resultado.update(variacion=v['id'], version=v['version'])
    else:
        resultado = resultados_plano.estudiar(modelo, vista, v)
    resultado['motivo_motor'] = motor['motivo']
    ruta = _ruta_resultado(ws, vid)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(ruta, resultado)
    out = {'variacion': vid, 'motor': resultado['motor'], 'convergio': bool(resultado.get('convergio')),
           'mensajes': list(resultado.get('mensajes') or ())}
    if not out['convergio']:
        # 111:RF-28 (amplía 081:RF-17): un flujo que no converge terminaba «done» como uno bueno; ahora la cola lo
        # marca «no converge», con el motivo del motor. El resultado se guarda igual: las capas dicen por qué no pintan.
        texto = '; '.join(str(m) for m in out['mensajes'][:3]) or 'el motor no dio el motivo'
        out.update(estado_trabajo='no_converge', motivo=f'El flujo no converge con {resultado["motor"]}: {texto}')
    return out


def _normas(limites=None) -> dict:
    """111:RF-21: la norma de cada capa con hallazgos, de la biblioteca normativa general (107:RF-21) con la capa del
    usuario; una biblioteca que no se puede leer deja cada hallazgo con su motivo, no tumba los resultados."""
    from ...aplicacion.biblioteca_normativa import cargar_biblioteca

    try:
        registro = cargar_biblioteca()
    except Exception as exc:  # noqa: BLE001 - los resultados se enseñan igual, con el motivo de que falte la norma
        motivo = f'La biblioteca normativa no se pudo leer: {exc}'
        return {capa: {'falta': motivo} for capa in resultados_plano.REGLA_DE_LA_CAPA}
    return resultados_plano.normas_de_las_capas(registro, limites=limites)


def _campo(binding: Any, nombre: str) -> Any:
    return binding.get(nombre) if isinstance(binding, dict) else getattr(binding, nombre, None)


def _motor(fuente, ws, project: str | None, alimentador: str, pedido: str | None = None) -> tuple[dict, Any]:
    """111:RF-17, RF-29: el motor de la variación y el vínculo; ``pedido`` es la elección del operador."""
    disponible = bool(fuente.disponible())
    binding, vinculado = (fuente.vinculo(ws, project, [alimentador]) if disponible and project else (None, False))
    return resultados_plano.elegir_motor(licencia=disponible, vinculado=vinculado, pedido=pedido), binding


def registrar_rutas_plano(app: FastAPI, *, ws_or_404, submit, fuente: Any = None) -> None:
    """Monta las rutas del plano con la cola y los espacios del único servidor (cableado en ``web/app.py``)."""
    fuente = fuente or FuenteWeb()
    base = '/api/workspaces/{wid}/plano'

    @app.get(base, response_model=PlanoRespuesta)
    def plano(wid: str, alimentador: list[str] = Query(default=[]), project: str | None = Query(default=None)) -> dict:
        """111:RF-1 a RF-3, RF-11, RF-17: la vista de cada alimentador pedido (o de todos los convertidos)."""
        ws = ws_or_404(wid)
        elegidos = list(dict.fromkeys(alimentador)) or fuente.alimentadores(ws)
        vistas = [_vista_y_revision(fuente, ws, a)[1] for a in elegidos]
        motor, _binding = _motor(fuente, ws, project, elegidos[0] if elegidos else '')
        return {**plano_red.resumen_plano(vistas), 'vistas': vistas, 'motor': motor, 'fondo': _fondo()}

    @app.post(f'{base}/variaciones', response_model=VariacionPlanoRespuesta)
    def abrir(wid: str, body: AbrirVariacionPeticion) -> dict:
        """111:RF-4: abre una variación sobre la revisión de la red que vio el navegador; si cambió, 409."""
        ws = ws_or_404(wid)
        _modelo, _vista, revision = _vista_y_revision(fuente, ws, body.alimentador)
        if body.revision != revision:
            raise HTTPException(409, 'La red cambió desde que abrió el plano: vuelva a cargarlo.')
        return variacion_plano.nueva(ws.root, revision=revision, caso=body.caso, alimentador=body.alimentador)

    @app.get(f'{base}/pagina', response_class=HTMLResponse)
    def pagina(wid: str, alimentador: list[str] = Query(default=[]),
               variacion: str | None = Query(default=None)) -> HTMLResponse:
        """111:RF-1, RF-10, RF-14; 086:RF-21: la página del plano, aislada como toda página generada; con
        ``variacion``, sus capas si se pueden pintar en esta revisión de la red."""
        from ...adaptadores.pagina_plano import pagina as pagina_del_plano
        from ...adaptadores.preview import politica_pagina_generada

        ws = ws_or_404(wid)
        elegidos = list(dict.fromkeys(alimentador)) or fuente.alimentadores(ws)
        vistas = [_vista_y_revision(fuente, ws, a)[1] for a in elegidos]
        capas = None
        if variacion:
            r = _leer_resultado(ws, variacion)
            revision = next((v['revision'] for v in vistas if v['alimentador'] == r['alimentador']), None)
            capas = resultados_plano.capas(r, limites=fuente.limites(), revision=revision or '', caso=r['caso'],
                                           normas=_normas(fuente.limites()))
        return HTMLResponse(pagina_del_plano(vistas, capas=capas),
                            headers={'Content-Security-Policy': politica_pagina_generada()})

    @app.get(f'{base}/variaciones', response_model=VariacionesPlanoRespuesta)
    def listar(wid: str, alimentador: str | None = Query(default=None)) -> dict:
        """111:RF-4, RF-12: lo guardado de verdad, en el servidor: las variaciones del alimentador y cuáles tienen
        estudio."""
        ws = ws_or_404(wid)
        variaciones = variacion_plano.listar(ws.root, alimentador=alimentador)
        return {'variaciones': variaciones,
                'estudiadas': [v['id'] for v in variaciones if _ruta_resultado(ws, v['id']).is_file()]}

    @app.get(f'{base}/variaciones/{{vid}}', response_model=VariacionPlanoRespuesta)
    def leer(wid: str, vid: str) -> dict:
        return _leer_variacion(ws_or_404(wid), vid)

    @app.patch(f'{base}/variaciones/{{vid}}', response_model=VariacionPlanoRespuesta)
    def editar(wid: str, vid: str, body: EditarVariacionPeticion) -> dict:
        """111:RF-4 a RF-8, RF-15: valida y versiona una edición; 422 con el motivo, 409 si cambió la versión o la red."""
        ws = ws_or_404(wid)
        v = _leer_variacion(ws, vid)
        _modelo, vista, revision = _vista_y_revision(fuente, ws, v['alimentador'])
        return _ejecutar(variacion_plano.editar, ws.root, vid, body.edicion, version=body.version,
                         revision=revision, vista=vista, perfil=fuente.perfil())

    def _paso(funcion):
        def ruta(wid: str, vid: str, body: TurnoVariacionPeticion) -> dict:
            ws = ws_or_404(wid)
            v = _leer_variacion(ws, vid)
            _modelo, _vista, revision = _vista_y_revision(fuente, ws, v['alimentador'])
            return _ejecutar(funcion, ws.root, vid, version=body.version, revision=revision)
        return ruta

    for nombre, funcion in (('deshacer', variacion_plano.deshacer), ('rehacer', variacion_plano.rehacer),
                            ('confirmar', variacion_plano.confirmar)):
        app.post(f'{base}/variaciones/{{vid}}/{nombre}', response_model=VariacionPlanoRespuesta,
                 name=f'plano_{nombre}', summary=f'111:RF-9: {nombre}')(_paso(funcion))

    @app.post(f'{base}/variaciones/{{vid}}/ajuste', response_model=PropuestaAjusteRespuesta)
    def ajuste(wid: str, vid: str, body: AjustePlanoPeticion) -> dict:
        """111:RF-7: el nodo más cercano como propuesta, con su distancia; no cambia la variación."""
        ws = ws_or_404(wid)
        v = _leer_variacion(ws, vid)
        _modelo, vista, _revision = _vista_y_revision(fuente, ws, v['alimentador'])
        return _ejecutar(variacion_plano.proponer_ajuste, vista, v, list(body.punto), perfil=fuente.perfil())

    @app.post(f'{base}/variaciones/{{vid}}/estudiar', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def estudiar_ruta(wid: str, vid: str, body: EstudiarPlanoPeticion) -> dict:
        """111:RF-17: estudiar es un trabajo en su carril; la red cambiada o la variación marcada es 409."""
        ws = ws_or_404(wid)
        v = _leer_variacion(ws, vid)
        _modelo, _vista, revision = _vista_y_revision(fuente, ws, v['alimentador'])
        if v.get('revision_cambiada') or v['revision'] != revision:
            raise HTTPException(409, 'La red cambió desde que se abrió la variación: ábrala de nuevo sobre la red actual.')
        try:
            motor, _binding = _motor(fuente, ws, body.project, v['alimentador'], body.motor)
        except ValueError as exc:
            # 111:RF-29: pedir DIgSILENT sin poder usarlo es un error antes de encolar, no un cambio de motor callado.
            raise HTTPException(422, str(exc)) from exc
        carril = 'powerfactory' if motor['motor'] == 'DIgSILENT' else 'engine'
        return submit(ws, 'plano_estudiar', f'Plano · {v["alimentador"]} · {v["caso"]} ({motor["texto"]})',
                      lambda ctx: estudiar(fuente, ws, ctx, vid, body.project, body.motor), lane=carril)

    @app.get(f'{base}/resultados', response_model=CapasPlanoRespuesta)
    def resultados(wid: str, variacion: str = Query(..., min_length=1)) -> dict:
        """111:RF-10, RF-11, RF-13, RF-18: las capas del resultado, solo si es de esta revisión de la red y de su caso."""
        ws = ws_or_404(wid)
        r = _leer_resultado(ws, variacion)
        _modelo, _vista, revision = _vista_y_revision(fuente, ws, r['alimentador'])
        return {**resultados_plano.capas(r, limites=fuente.limites(), revision=revision, caso=r['caso'],
                                         normas=_normas(fuente.limites())),
                'variacion': variacion}

    @app.get(f'{base}/comparar', response_model=ComparacionPlanoRespuesta)
    def comparar(wid: str, a: str = Query(..., min_length=1), b: str = Query(..., min_length=1)) -> dict:
        """111:RF-12, RF-19: dos casos por elemento sobre el mismo plano, con aviso si los motores son distintos."""
        ws = ws_or_404(wid)
        return resultados_plano.comparar(_leer_resultado(ws, a), _leer_resultado(ws, b), limites=fuente.limites())
