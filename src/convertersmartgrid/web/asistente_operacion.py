"""Lo que cada tarea del asistente necesita del espacio, antes de ofrecer confirmar (spec 070).

Varias tareas fallaban después de que el operador confirmara, o quedaban a medias en silencio: los estudios
sin su base, el sistema sin la carpeta de los libros, la escalera sin cómo costear. Aquí se comprueba con lo que
la web ya sabe, y lo que no está va a ``plan.faltan``: nunca se deduce ni se inventa un valor.

Es un módulo aparte de ``services.py``, que comparten varias sesiones; las rutas y sus validaciones siguen
siendo las de allí (026:RF-10). ``svc`` es ese módulo, recibido como parámetro: ``services`` llama aquí, y importarlo
desde aquí cerraría un ciclo entre los dos.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..asistente.sinteticos import normalizar

_TIPO_CAMBIO = re.compile(r'tipo de cambio\s*(?:de|:|=)?\s*(\d+(?:[.,]\d+)?)')
_DIRECTO = re.compile(r'\bdirect[oa]\b.*\bset nueva\b|\bset nueva\b.*\bdirect[oa]\b|\bsin (?:probar )?escalera\b')


def tipo_de_cambio_de(texto: str) -> float | None:
    """El que escribe el operador (025:RF-67): la forma decimal no la puede dar ``numero_de``."""
    m = _TIPO_CAMBIO.search(normalizar(texto))
    return float(m.group(1).replace(',', '.')) if m else None


def parametros_de_costeo(tipo_cambio: float | None) -> None:
    """Lo mismo que comprueba la escalera antes de tocar DIgSILENT (025:RF-57, RF-67, RF-68)."""
    from .. import escalera_optima as eo
    from ..perfil_empresa import PerfilError, datos_perfil

    try:
        eo.parametros(datos_perfil(), tipo_cambio)
    except (eo.EscaleraError, PerfilError) as exc:
        raise ValueError(str(exc)) from exc


def _exige_calibracion(svc, ws, plan) -> None:
    proyecto = plan.datos.get('proyecto')
    if proyecto and svc.ajuste_aplicado_en_disco(ws, proyecto) is None:
        plan.faltan.append(f'la calibración: {proyecto} no tiene ninguna aplicada en este espacio; calíbrelo antes.')


def _estudio_nombrado(svc, ws, plan) -> None:
    pedido = plan.datos.get('estudio')
    if not pedido:
        return
    catalogo = svc.estudios_catalogo(ws, plan.datos.get('proyecto') or '')
    clave = normalizar(str(pedido)).strip()

    def coincide(fila: dict) -> bool:
        return clave in (normalizar(str(fila.get('clave'))), normalizar(str(fila.get('nombre'))))

    ofrecido = next((e for e in catalogo.get('ofrecidos') or [] if coincide(e)), None)
    if ofrecido is not None:
        plan.datos['estudio'] = ofrecido['clave']
        return
    negado = next((e for e in catalogo.get('no_ofrecidos') or [] if coincide(e)), None)
    plan.faltan.append(f"el estudio {pedido}: {negado['motivo']}" if negado else
                       f'el estudio {pedido}: no está en el catálogo de esta versión.')


def _libros_de_la_demanda(svc, ws, plan) -> None:
    if plan.datos.get('ruta'):
        return
    carpeta = svc.carpeta_de_libros(ws)
    if carpeta is None:
        plan.faltan.append('la carpeta de los libros de demanda: dígala en la orden o asígnelos en «2.1».')
        return
    plan.datos['ruta'] = carpeta
    plan.razonamiento.append(f'libros de demanda: los del espacio, en {carpeta} (070:RF-6).')


def _obras(svc, ws, plan, extras: dict) -> None:
    tipo_cambio = tipo_de_cambio_de(plan.texto)
    if tipo_cambio:
        extras['tipo_cambio'] = tipo_cambio
    if plan.tarea == 'optimizar_con_proyecto' and _DIRECTO.search(normalizar(plan.texto)):
        extras['directo_set_nueva'] = True
        if not plan.datos.get('ruta'):
            plan.faltan.append('el libro CAPEX: la SET nueva se elige entre sus módulos (042:RF-7).')
    try:
        parametros_de_costeo(tipo_cambio)
    except ValueError as exc:
        plan.faltan.append(f'cómo costear las obras: {exc}')


def _factibilidad(plan, extras: dict) -> None:
    formulario = extras.get('formulario') or {}
    if formulario and not formulario.get('solicitud'):
        plan.faltan.append('la solicitud de la carga en el formulario del informe: rellénela en el paso 4.4.')


def _maxima_buscada(plan, extras: dict) -> None:
    if not (extras.get('ultima_maxima') or {}).get('id'):
        plan.faltan.append('la máxima: búsquela antes; las búsquedas viven en memoria y tras un reinicio hay que '
                           'volver a buscarlas (070:RF-24).')
    if re.search(r'\bcon bancos\b|\bcompleta\w* (los )?bancos\b', normalizar(plan.texto)):
        extras['completar_bancos'] = True


#: Los libros del estudio que la orden puede nombrar, con el campo de la ruta ``/pide`` que los recibe.
_LIBROS_DEL_PIDE = (('capex', re.compile(r'\bcapex\b', re.I), 'el libro CAPEX'),
                    # Solo «formato 01»: «F1» es también el nombre de un alimentador en la misma orden.
                    ('formato_01', re.compile(r'\bformato\s*(?:n\s*[°º.]?\s*)?0?1\b(?!\d)', re.I),
                     'el Formato 01 del mercado'))


def _libro_tras(texto: str, palabra: re.Pattern) -> str | None:
    """La ruta que sigue a la palabra que nombra el libro: «con el capex D:/x.xlsx»."""
    from ..asistente.interprete import ruta_de

    m = palabra.search(texto)
    return ruta_de(texto[m.end():]) if m else None


def _pide(plan, extras: dict) -> None:
    """El estudio de planeamiento, con lo mismo que pide la web antes de encolar (072:RF-1, RF-18).

    Sin año de presentación, ``pide_ejecutar`` diagnostica pero no genera ningún módulo del plan ni del PIDE:
    el asistente decía «hecho» sin entregables. Se dice antes de confirmar, y los libros que la orden nombra
    van en el cuerpo de la ruta, igual que los manda el formulario de la web.
    """
    from ..perfil_empresa import datos_perfil

    anio = str(plan.datos.get('periodo') or '')[:4]
    if not anio.isdigit():
        try:
            del_perfil = (datos_perfil().get('planificacion') or {}).get('anio_presentacion')
        except Exception:  # noqa: BLE001 - un perfil ilegible lo dice la ruta; aquí solo falta el año
            del_perfil = None
        if del_perfil is None:
            plan.faltan.append('el año de presentación del estudio: dígalo en la orden («el pide de … para 2027») o '
                               'en «planificacion.anio_presentacion» del perfil; sin él no hay módulos del plan ni del '
                               'PIDE (072:RF-1).')
        else:
            plan.razonamiento.append(f'año de presentación: {del_perfil}, el del perfil de empresa (072:RF-1).')
    for clave, palabra, nombre in _LIBROS_DEL_PIDE:
        ruta = _libro_tras(plan.texto, palabra)
        if ruta is None:
            continue
        if not Path(ruta).is_file():
            plan.faltan.append(f'{nombre}: {ruta} no existe.')
            continue
        extras[clave] = ruta
        plan.razonamiento.append(f'{nombre}: {ruta} (072:RF-18).')


def _alimentadores_del_alcance(svc, ws, plan) -> tuple[str, list[str]]:
    """El alcance de la orden y sus alimentadores, de la estructura; lo que no esté se dice en el plan."""
    datos = plan.datos
    alcance = datos.get('alcance') or ('set' if datos.get('set') else 'sistema' if datos.get('sistema') else 'alimentadores')
    if alcance == 'alimentadores':
        return alcance, list(datos.get('alimentadores') or [])
    pedido = datos.get('set') if alcance == 'set' else datos.get('sistema')
    if not pedido:
        plan.faltan.append(f'{alcance}: dígalo en la orden.')
        return alcance, []
    try:
        zonales = svc.estructura_resumen(ws).get('zonales') or []
    except svc.UserError as exc:
        plan.faltan.append(f'la estructura de la empresa: {exc}')
        return alcance, []
    if alcance == 'sistema':
        fila = next((z for z in zonales if z['nombre'] == pedido), None)
    else:
        fila = next((s for z in zonales for s in z.get('sets_detalle') or [] if s['codigo'] == pedido), None)
    if fila is None or not fila.get('alimentadores'):
        plan.faltan.append(f'{pedido}: no tiene alimentadores en la fuente cargada.')
        return alcance, []
    return alcance, list(fila['alimentadores'])


def _centrales_del_perfil(feeders: list[str]) -> dict[str, dict]:
    from ..perfil_empresa import PerfilError, centrales_termicas, datos_perfil

    try:
        perfil = centrales_termicas(datos_perfil())
    except PerfilError:
        return {}
    pedidos = {f.upper() for f in feeders}
    return {a: c for a, c in perfil.items() if a.upper() in pedidos}


def _tope_de_alimentadores(svc, plan, feeders: list[str]) -> bool:
    """070:RF-58: se dice en el plan, con la alternativa: no se pregunta ni se trocea."""
    try:
        svc.comprobar_analisis_por_alimentadores(feeders)
    except svc.UserError as exc:
        plan.faltan.append(str(exc))
        return False
    return True


def _buscar_maxima(svc, ws, plan, extras: dict) -> None:
    alcance, feeders = _alimentadores_del_alcance(svc, ws, plan)
    if not feeders:
        if alcance == 'alimentadores':
            plan.faltan.append('alimentadores: dígalos, o nombre la SET o el sistema.')
        return
    if alcance == 'alimentadores' and not _tope_de_alimentadores(svc, plan, feeders):
        return
    medidores = svc.medidores_por_alimentador(ws, feeders)
    pares = [{'alimentador': a, 'medidor': m} for a in feeders for m in medidores.get(a) or []]
    if not pares:
        plan.faltan.append('los medidores: ninguno de esos alimentadores tiene medidor en el libro; asígnelo en «2.1».')
        return
    centrales = _centrales_del_perfil(feeders)
    ya = {p['medidor'] for p in pares}
    for a, c in centrales.items():
        for m in (c['generacion'], c['llegada'], c['salida']):
            if m not in ya:
                pares.append({'alimentador': f'Central {a}', 'medidor': m})
    extras['maxima'] = {'medidores': pares, 'periodo': plan.datos.get('periodo'),
                        'por_barra': alcance != 'alimentadores', 'sistema_60kv': alcance == 'sistema',
                        'coincidente': alcance == 'alimentadores' and len(feeders) > 1,
                        'centrales': {a: {k: c[k] for k in ('generacion', 'llegada', 'salida')} for a, c in centrales.items()}}
    plan.razonamiento.append(f'alcance: {alcance}, con {len(feeders)} alimentador(es) y {len(pares)} medidor(es).')


def _cruzar_clientes(plan, extras: dict) -> None:
    periodo = plan.datos.get('periodo')
    if periodo and len(str(periodo)) != 7:
        plan.faltan.append('el mes del cruce (AAAA-MM): los libros de clientes son mensuales.')
    filas = ((extras.get('ultima_maxima') or {}).get('result') or {}).get('resultados') or []
    pedidos = set(plan.datos.get('alimentadores') or [])
    maximas = {f['alimentador']: {k: f.get(k) for k in ('fecha', 'kw', 'kvar', 'fp')} for f in filas
               if f.get('alimentador') and f.get('fecha') and not f.get('error')
               and not str(f['alimentador']).lower().startswith('central ')
               and (not pedidos or f['alimentador'] in pedidos)}
    extras['maximas_clientes'] = maximas
    if not pedidos and maximas:
        plan.datos['alimentadores'] = sorted(maximas)
    elif not pedidos:
        plan.faltan.append('los alimentadores: dígalos o busque antes su máxima.')


_NUMERO = r'(\d+(?:[.,]\d+)?)'
_POTENCIA = re.compile(_NUMERO + r'\s*(kw|mw)\b')
_FP = re.compile(r'\b(?:fp|factor de potencia)\s*(?:de|:|=)?\s*(\d?[.,]\d+)')
_UTM = re.compile(r'\bx\s*[:=]?\s*' + _NUMERO + r'[\s,;]+(?:e\s+)?y\s*[:=]?\s*' + _NUMERO)
_LATLON = re.compile(r'\blat\w*\s*[:=]?\s*(-?\d+[.,]\d+)[\s,;]+lon\w*\s*[:=]?\s*(-?\d+[.,]\d+)')
_BARRA = re.compile(r'\bbarra\s+(\S+)', re.IGNORECASE)
#: El que propone el formulario 3.2 (008:RF-27); el plan lo dice para que el operador lo cambie.
FP_PROPUESTO = .98


def _numero(texto: str) -> float:
    # «1,500» es mil quinientos; «1,5», uno y medio.
    if re.fullmatch(r'\d{1,3}[.,]\d{3}', texto):
        return float(re.sub(r'[.,]', '', texto))
    return float(texto.replace(',', '.'))


def _carga_sola(svc, ws, plan, extras: dict) -> None:
    _exige_calibracion(svc, ws, plan)
    _datos_de_la_carga(plan, extras)


def _datos_de_la_carga(plan, extras: dict) -> None:
    feeders = plan.datos.get('alimentadores') or []
    if len(feeders) > 1:
        plan.faltan.append('un solo alimentador: la carga sola se conecta en uno.')
    t = normalizar(plan.texto)
    nueva: dict[str, Any] = {'nombre': plan.datos.get('sed') or '', 'SED': plan.datos.get('sed') or '',
                             'alimentador': feeders[0] if feeders else ''}
    if (m := _POTENCIA.search(t)) is not None:
        nueva['Kw'] = _numero(m.group(1)) * (1000. if m.group(2) == 'mw' else 1.)
    else:
        plan.faltan.append('la potencia de la carga: dígala en kW o MW.')
    if (m := _FP.search(t)) is not None:
        nueva['FP'] = _numero(m.group(1))
    else:
        nueva['FP'] = FP_PROPUESTO
        plan.razonamiento.append('factor de potencia: 0,98, el que propone el formulario 3.2; dígalo si es otro (008:RF-27).')
    utm, latlon, barra = _UTM.search(t), _LATLON.search(t), _BARRA.search(plan.texto)
    if utm is not None:
        nueva['CoordX'], nueva['CoordY'] = _numero(utm.group(1)), _numero(utm.group(2))
    elif latlon is not None:
        nueva['Lat'], nueva['Lon'] = float(latlon.group(1).replace(',', '.')), float(latlon.group(2).replace(',', '.'))
    elif barra is not None:
        nueva['barra'] = barra.group(1).strip(' ,.;')
    else:
        plan.faltan.append('la ubicación de la carga: «x … y …» en UTM, «lat … lon …» o «barra …».')
    extras['nueva'] = nueva


def _cancelar(plan, extras: dict) -> None:
    fuera = ('asistente_interpretar', 'asistente_control', 'asistente_indice')
    vivos = [{'id': j['id'], 'titulo': j.get('title') or j['id']} for j in extras.get('_trabajos') or []
             if j.get('status') not in ('done', 'parcial', 'no_converge', 'failed', 'cancelled') and j.get('kind') not in fuera]
    if not vivos:
        plan.faltan.append('un trabajo en curso: en este espacio no hay ninguno que cancelar.')
    extras['cancelar'] = vivos


def _documentos(plan, extras: dict) -> None:
    ruta = plan.datos.get('ruta')
    if not ruta:
        return
    from pathlib import Path

    p = Path(ruta)
    rutas = sorted(x for x in p.iterdir() if x.suffix.lower() == '.pdf') if p.is_dir() else ([p] if p.suffix.lower() == '.pdf' else [])
    if not rutas:
        plan.faltan.append(f'los PDF del solicitante: en {ruta} no hay ninguno.')
    extras['documentos'] = [str(x) for x in rutas]
    extras['tipo_documentos'] = 'estudio' if re.search(r'\bestudio\b', normalizar(plan.texto)) else 'factibilidad'


_ZONA = re.compile(r'(?<![\w:/\\.-])(?:zona(?: horaria)?\s+)?(utc|[A-Z][A-Za-z_]+/[A-Z][A-Za-z_]+)(?![\w/\\.-])', re.IGNORECASE)
_CADENCIA = re.compile(r'\b(\d+)\s*min(?:utos?)?\b')
_HORIZONTES = re.compile(r'\bhorizontes?\s*(?:de|:|=)?\s*(\d+(?:\s*,\s*\d+)*)')
_ALGORITMOS = ('ingenuo', 'estacional_semanal', 'gru', 'nhits', 'tft', 'patchtst')


def _pronostico(svc, ws, plan, extras: dict) -> None:
    """La clase, la zona y la cadencia no se suponen (046:RF-23): se leen de la orden o se piden."""
    ruta = plan.datos.get('ruta')
    sin_ruta = plan.texto.replace(str(ruta), ' ') if ruta else plan.texto
    t = normalizar(sin_ruta)
    clase = 'cliente' if re.search(r'\bclientes?\b|\bfijas?\b', t) else 'cabecera' if re.search(r'\bcabecera\b', t) else None
    if clase is None:
        plan.faltan.append('la clase del pronóstico: cabecera o clientes.')
    zona = _ZONA.search(sin_ruta)
    if zona is None:
        plan.faltan.append('la zona horaria de la medición: «zona America/…» o «UTC»; no se supone.')
    cadencia = _CADENCIA.search(t)
    if cadencia is None:
        plan.faltan.append('la cadencia de la medición: «cada 15 min»; no se supone.')
    if clase is None or zona is None or cadencia is None or not ruta:
        return
    pedido: dict[str, Any] = {'clase': clase, 'libros': [str(ruta)], 'zona_horaria': zona.group(1),
                              'cadencia_min': int(cadencia.group(1))}
    feeders = list(plan.datos.get('alimentadores') or [])
    if feeders:
        medidores = svc.medidores_por_alimentador(ws, feeders)
        pedido['pares'] = {a: medidores[a][0] for a in feeders if medidores.get(a)}
        centrales = _centrales_del_perfil(feeders)
        if centrales:
            pedido['centrales'] = {a: {k: c[k] for k in ('generacion', 'llegada', 'salida')} for a, c in centrales.items()}
    if (h := _HORIZONTES.search(t)) is not None:
        pedido['horizontes'] = [int(x) for x in h.group(1).split(',')]
    if (c := re.search(r'\bclientes\s*:\s*([^;]+)', sin_ruta, re.IGNORECASE)) is not None:
        pedido['clientes'] = [x.strip() for x in c.group(1).split(',') if x.strip()]
    algoritmos = [a for a in _ALGORITMOS if re.search(rf'\b{a}\b', t)]
    if algoritmos:
        pedido['algoritmos'] = algoritmos
    extras['pronostico'] = pedido


def alcance_de_sistema_web(svc, ws, plan) -> tuple[list[str], str]:
    """Las opciones de ``tools/sistema_web.py`` para la orden y cómo llamarla en un error (070:RF-20, RF-21)."""
    from ..estructura import clave

    d = plan.datos
    if plan.tarea == 'alimentadores_completo':
        return ['--red', *d['alimentadores']], f"{', '.join(d['alimentadores'])}"
    if plan.tarea == 'set_completo':
        e = svc.estructura_del_espacio(ws)
        fila = e.sets.get(clave(d['set'])) if e is not None else None
        if fila is None:
            raise svc.UserError(f"La SET {d['set']} no está en la estructura de la empresa.")
        return ['--zonal', fila.zonal, '--set', d['set']], f"La SET {d['set']}"
    return ['--zonal', d['sistema']], f"El sistema {d['sistema']}"


def _etapas_en_palabras(lista: dict) -> list[str]:
    def fila(e: dict) -> str:
        por_que = e.get('motivo') or f"falta {', '.join(e['falta'])}"
        sufijo = {'hecha': ' (ya hecha)', 'se_omitira': f' (se omitirá: {por_que})',
                  'falta_dato': f" (falta {', '.join(e['falta'])})"}.get(e['estado'], '')
        if not sufijo and e.get('condicion'):
            sufijo = f" ({e['condicion']})"
        return f"{e['nombre']}{sufijo}"

    return [fila(e) for e in lista['etapas']]


def _datos_del_proyecto_entero(plan) -> dict:
    return {k: plan.datos[k] for k in ('sistema', 'periodo', 'ruta') if plan.datos.get(k)}


def _proyecto_entero(svc, ws, plan, extras: dict) -> None:
    _libros_de_la_demanda(svc, ws, plan)
    lista = svc.agente_proyecto_lista(ws, _datos_del_proyecto_entero(plan))
    if lista['bloqueo']:
        plan.faltan.append(lista['bloqueo'])
    extras['lista_confirmacion'] = lista['confirmacion']
    extras['etapas_en_palabras'] = _etapas_en_palabras(lista)


def _ruta_de_control_de_carga(plan_datos: dict) -> str:
    return f"agente_carga_{re.sub(r'[^0-9A-Za-z]+', '_', str(plan_datos.get('sed') or ''))[:40]}.json"


def _lista_de_la_carga(svc, ws, datos: dict) -> dict:
    """Con lo que ya se sabe del proyecto, para que la lista no prometa una calibración que no hará (070:RF-53)."""
    from ..asistente.orquestador import ETAPAS_CARGA

    omitir = {}
    if svc.ajuste_aplicado_en_disco(ws, datos['proyecto']) is not None:
        omitir['calibracion'] = f"{datos['proyecto']} ya tiene calibración aplicada"
    return svc.agente_proyecto_lista(ws, datos, etapas=ETAPAS_CARGA, control=_ruta_de_control_de_carga(datos), omitir=omitir)


def _evaluar_carga(svc, ws, plan, extras: dict) -> None:
    _datos_de_la_carga(plan, extras)
    proyecto = plan.datos.get('proyecto')
    if not proyecto or not plan.datos.get('sed') or not plan.datos.get('alimentadores'):
        return
    formulario = ((ws.informes.get('formularios') or {}).get(proyecto) or {}).get('factibilidad')
    if not formulario:
        plan.faltan.append('el formulario del informe de factibilidad: rellénelo una vez en el paso 4.4.')
    elif not formulario.get('solicitud'):
        plan.faltan.append('la solicitud de la carga en el formulario del informe: rellénela en el paso 4.4.')
    if svc.ajuste_aplicado_en_disco(ws, proyecto) is None:
        if not plan.datos.get('periodo'):
            plan.faltan.append(f'el periodo con que calibrar: {proyecto} no tiene calibración aplicada.')
        _libros_de_la_demanda(svc, ws, plan)
    datos = {'proyecto': proyecto, 'alimentadores': list(plan.datos['alimentadores']), 'sed': plan.datos['sed'],
             'nueva': extras.get('nueva') or {}, 'formulario': formulario or {},
             **{k: plan.datos[k] for k in ('periodo', 'ruta') if plan.datos.get(k)}}
    tipo_cambio = tipo_de_cambio_de(plan.texto)
    if tipo_cambio:
        datos['tipo_cambio'] = tipo_cambio
    lista = _lista_de_la_carga(svc, ws, datos)
    if lista['bloqueo']:
        plan.faltan.append(lista['bloqueo'])
    extras['datos_etapas'] = datos
    extras['lista_confirmacion'] = lista['confirmacion']
    extras['etapas_en_palabras'] = _etapas_en_palabras(lista)


def ejecutar_etapas(svc, ws, ctx, plan, extras: dict, base: str, http: Any) -> dict:
    """La lista confirmada; si cambió desde que se mostró, no se ejecuta (067:RF-39, 070:RF-52)."""
    if plan.tarea == 'evaluar_carga_nueva':
        from ..asistente.ejecutor import entregables
        from ..asistente.orquestador import ETAPAS_CARGA

        datos = extras['datos_etapas']
        lista = _lista_de_la_carga(svc, ws, datos)
        if lista['confirmacion'] != extras.get('lista_confirmacion'):
            raise svc.UserError('La lista de etapas cambió desde que se mostró: escriba la orden de nuevo.')
        svc.agente_proyecto_anotar(ws, datos, lista)
        r = svc.agente_proyecto(ws, ctx, datos, base, http, etapas=ETAPAS_CARGA, control=_ruta_de_control_de_carga(datos))
        evaluacion = ((r.get('etapas') or {}).get('informe') or {}).get('resultado') or ((r.get('etapas') or {}).get('evaluacion') or {}).get('resultado') or {}
        conclusion = evaluacion.get('factible')
        return {**r, 'entregables': entregables(r.get('etapas')),
                'texto': (f"Carga {datos['sed']}: " + ('factible' if conclusion is True else 'no factible' if conclusion is False else 'sin conclusión')
                          + '; vea el informe.')}
    datos = _datos_del_proyecto_entero(plan)
    lista = svc.agente_proyecto_lista(ws, datos)
    if lista['confirmacion'] != extras.get('lista_confirmacion'):
        raise svc.UserError('La lista de etapas cambió desde que se mostró: escriba la orden de nuevo.')
    svc.agente_proyecto_anotar(ws, datos, lista)
    return svc.agente_proyecto(ws, ctx, datos, base, http)


def presentar(ws, plan, resultado: dict) -> None:
    """Lo que el operador lee del resultado (070:RF-35, RF-37)."""
    if plan.tarea == 'descargar_resultados':
        trabajo = next((p['trabajo'] for p in resultado.get('pasos') or []), None)
        if trabajo:
            resultado['enlace'] = f'/api/workspaces/{ws.id}/outputs.zip?job={trabajo}'
            resultado['texto'] = 'ZIP preparado: bájelo del enlace.'
    elif plan.tarea == 'pronostico':
        r = resultado.get('resultado') or {}
        lineas = []
        for objetivo, g in (r.get('ganadores') or {}).items():
            quien = 'la referencia' if g.get('es_referencia') else 'un modelo neuronal'
            lineas.append(f"{objetivo}: ganó {g.get('ganador')} ({quien}): {g.get('motivo')}.")
        if not lineas:
            lineas.append(f"Sin ganadores: {r.get('reason') or r.get('status') or 'el informe no los trae'}.")
        resultado['texto'] = ' '.join(lineas) + ' Es un pronóstico, nunca una medición: no pasa a la calibración ni a los informes.'


def requisitos(svc, ws, plan, extras: dict) -> None:
    """Completa el plan con lo que el espacio resuelve y dice lo que falta (070:RF-2 a RF-15, RF-22 a RF-37)."""
    tarea: Any = plan.tarea
    if tarea in ('calibrar', 'simular_calibracion'):
        _maxima_buscada(plan, extras)
        try:
            svc.comprobar_que_se_calibra(plan.datos.get('proyecto') or '')     # 070:RF-61
        except svc.UserError as exc:
            plan.faltan.append(str(exc))
    elif tarea == 'buscar_maxima':
        _buscar_maxima(svc, ws, plan, extras)
    elif tarea == 'cruzar_clientes':
        _cruzar_clientes(plan, extras)
    elif tarea == 'carga_nueva_sola':
        _carga_sola(svc, ws, plan, extras)
    elif tarea == 'cancelar_trabajo':
        _cancelar(plan, extras)
    elif tarea == 'leer_solicitud':
        _documentos(plan, extras)
    elif tarea == 'pronostico':
        _pronostico(svc, ws, plan, extras)
    elif tarea == 'proyecto_entero':
        _proyecto_entero(svc, ws, plan, extras)
    elif tarea == 'evaluar_carga_nueva':
        _evaluar_carga(svc, ws, plan, extras)
    elif tarea in ('alimentadores_completo', 'set_completo'):
        _libros_de_la_demanda(svc, ws, plan)
        if tarea == 'alimentadores_completo':
            _tope_de_alimentadores(svc, plan, list(plan.datos.get('alimentadores') or []))
    elif tarea == 'recalibrar':
        try:
            svc.recalibrar_datos(ws, plan.datos.get('proyecto') or '')
        except svc.UserError as exc:
            plan.faltan.append(str(exc))
    elif tarea == 'estudios':
        _exige_calibracion(svc, ws, plan)
        _estudio_nombrado(svc, ws, plan)
    elif tarea == 'cargas_nuevas':
        _exige_calibracion(svc, ws, plan)
    elif tarea == 'sistema_completo':
        _libros_de_la_demanda(svc, ws, plan)
    elif tarea in ('obras_escalera', 'optimizar_con_proyecto'):
        _obras(svc, ws, plan, extras)
    elif tarea == 'informe_factibilidad':
        _factibilidad(plan, extras)
    elif tarea == 'pide':
        _pide(plan, extras)
