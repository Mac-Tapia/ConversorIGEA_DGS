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

from ...aplicacion.asistente.plan import ETIQUETA_DEL_DATO
from ...aplicacion.asistente.sinteticos import normalizar
from ...aplicacion.asistente.tareas import sin_citas

_TIPO_CAMBIO = re.compile(r'tipo de cambio\s*(?:de|:|=)?\s*(\d+(?:[.,]\d+)?)')
_DIRECTO = re.compile(r'\bdirect[oa]\b.*\bset nueva\b|\bset nueva\b.*\bdirect[oa]\b|\bsin (?:probar )?escalera\b')


def tipo_de_cambio_de(texto: str) -> float | None:
    """El que escribe el operador (025:RF-67): la forma decimal no la puede dar ``numero_de``."""
    m = _TIPO_CAMBIO.search(normalizar(texto))
    return float(m.group(1).replace(',', '.')) if m else None


def parametros_de_costeo(tipo_cambio: float | None) -> None:
    """Lo mismo que comprueba la escalera antes de tocar DIgSILENT (025:RF-57, RF-67, RF-68)."""
    from ...aplicacion import escalera_optima as eo
    from ...dominio.perfil_empresa import PerfilError, datos_perfil

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
    plan.razonamiento.append(f'libros de demanda: los del espacio, en {carpeta}.')  # 070:RF-6


def _obras(svc, ws, plan, extras: dict) -> None:
    tipo_cambio = tipo_de_cambio_de(plan.texto)
    if tipo_cambio:
        extras['tipo_cambio'] = tipo_cambio
    if plan.tarea == 'optimizar_con_proyecto' and _DIRECTO.search(normalizar(plan.texto)):
        extras['directo_set_nueva'] = True
        if not plan.datos.get('ruta'):
            plan.faltan.append('el libro CAPEX: la SET nueva se elige entre sus módulos.')  # 042:RF-7
    try:
        parametros_de_costeo(tipo_cambio)
    except ValueError as exc:
        plan.faltan.append(f'cómo costear las obras: {_claves_en_palabras(sin_citas(str(exc)))}')


#: 070:RF-51: las secciones del perfil, como las nombra el operador.
_SECCIONES_DEL_PERFIL = {'escalera': 'la escalera de obras', 'planificacion': 'la planificación', 'estudios': 'los estudios'}
_CLAVE_DEL_PERFIL = re.compile(r'(?<![\w/\\])(escalera|planificacion|estudios)\.([a-z_]+)\b')


def _claves_en_palabras(texto: str) -> str:
    """«escalera.tolerancia_pu» → «tolerancia pu de la escalera de obras»: el perfil incompleto se dice sin sus claves."""
    return _CLAVE_DEL_PERFIL.sub(lambda m: f"{m.group(2).replace('_', ' ')} de {_SECCIONES_DEL_PERFIL[m.group(1)]}", texto)


def _factibilidad(plan, extras: dict) -> None:
    formulario = extras.get('formulario') or {}
    if formulario and not formulario.get('solicitud'):
        plan.faltan.append('la solicitud de la carga en el formulario del informe: rellénela en el paso 4.4.')


def _maxima_buscada(plan, extras: dict) -> None:
    if not (extras.get('ultima_maxima') or {}).get('id'):
        plan.faltan.append('la máxima: búsquela antes; las búsquedas viven en memoria y tras un reinicio hay que '
                           'volver a buscarlas.')  # 070:RF-24
    if re.search(r'\bcon bancos\b|\bcompleta\w* (los )?bancos\b', normalizar(plan.texto)):
        extras['completar_bancos'] = True


#: Los libros del estudio que la orden puede nombrar, con el campo de la ruta ``/pide`` que los recibe.
_LIBROS_DEL_PIDE = (('capex', re.compile(r'\bcapex\b', re.I), 'el libro CAPEX'),
                    # Solo «formato 01»: «F1» es también el nombre de un alimentador en la misma orden.
                    ('formato_01', re.compile(r'\bformato\s*(?:n\s*[°º.]?\s*)?0?1\b(?!\d)', re.I),
                     'el Formato 01 del mercado'))


def _libro_tras(texto: str, palabra: re.Pattern) -> str | None:
    """La ruta que sigue a la palabra que nombra el libro: «con el capex D:/x.xlsx»."""
    from ...aplicacion.asistente.interprete import ruta_de

    m = palabra.search(texto)
    return ruta_de(texto[m.end():]) if m else None


#: 072:RF-29: lo que se pregunta cuando la orden no dice cuál de los tres análisis es, o dice más de uno.
PREGUNTA_DEL_TIPO = ('el tipo de análisis: ¿corto plazo (la carga, la escalera de obras, los estudios y el informe), '
                     'PIDE (aplica las obras de su periodo) o planeamiento de largo plazo (las plantea sin aplicarlas)? '
                     'Dígalo en la orden.')  # 072:RF-29


def _tipos_de_analisis(plan) -> list[str]:
    from ...aplicacion.asistente.tareas import tipos_de_analisis_de

    return tipos_de_analisis_de(normalizar(plan.texto))


def _tipo_del_pide(plan, extras: dict) -> None:
    """El PIDE o el largo plazo, por lo que dice la orden; si no lo dice, o dice dos, se pregunta (072:RF-29).

    El largo plazo va por la misma ruta con su ``plazo``: escribe solo sus módulos y no aplica obras (072:RF-34, RF-35).
    El PIDE sigue siendo el de siempre, con los dos entregables.
    """
    tipos = _tipos_de_analisis(plan)
    if tipos == ['largo_plazo']:
        extras['plazo'] = 'largo_plazo'
        plan.razonamiento.append('tipo de análisis: planeamiento de largo plazo; plantea las obras sin aplicarlas en '
                                 '«Con proyecto» y escribe solo sus módulos.')  # 072:RF-34, RF-35
    elif tipos == ['pide']:
        plan.razonamiento.append('tipo de análisis: PIDE, con las obras de su periodo.')  # 072:RF-31
    else:
        plan.faltan.append(PREGUNTA_DEL_TIPO)


def _pide(plan, extras: dict) -> None:
    """El estudio de planeamiento, con lo mismo que pide la web antes de encolar (072:RF-1, RF-18).

    Sin año de presentación, ``pide_ejecutar`` diagnostica pero no genera ningún módulo del plan ni del PIDE:
    el asistente decía «hecho» sin entregables. Se dice antes de confirmar, y los libros que la orden nombra
    van en el cuerpo de la ruta, igual que los manda el formulario de la web.
    """
    from ...dominio.perfil_empresa import datos_perfil

    _tipo_del_pide(plan, extras)
    anio = str(plan.datos.get('periodo') or '')[:4]
    if not anio.isdigit():
        try:
            del_perfil = (datos_perfil().get('planificacion') or {}).get('anio_presentacion')
        except Exception:  # noqa: BLE001 - un perfil ilegible lo dice la ruta; aquí solo falta el año
            del_perfil = None
        if del_perfil is None:
            plan.faltan.append('el año de presentación del estudio: dígalo en la orden («el pide de … para 2027») o '
                               'en la planificación del perfil de empresa; sin él no hay módulos del plan ni del '
                               'PIDE.')  # 072:RF-1
        else:
            plan.razonamiento.append(f'año de presentación: {del_perfil}, el del perfil de empresa.')  # 072:RF-1
    for clave, palabra, nombre in _LIBROS_DEL_PIDE:
        ruta = _libro_tras(plan.texto, palabra)
        if ruta is None:
            continue
        if not Path(ruta).is_file():
            plan.faltan.append(f'{nombre}: {ruta} no existe.')
            continue
        extras[clave] = ruta
        plan.razonamiento.append(f'{nombre}: {ruta}.')  # 072:RF-18


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
        plan.faltan.append(f'la estructura de la empresa: {sin_citas(str(exc))}')
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
    from ...dominio.perfil_empresa import PerfilError, centrales_termicas, datos_perfil

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
        plan.faltan.append(sin_citas(str(exc)))
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
        plan.razonamiento.append('factor de potencia: 0,98, el que propone el formulario 3.2; dígalo si es otro.')  # 008:RF-27
    from ...aplicacion.asistente.interprete import ubicacion_de

    # 070:RF-29: «x … y …», «coordenadas X Y» o «lat … lon …», con la misma lectura que aparta esos números de la SED.
    lugar, barra = ubicacion_de(plan.texto) or {}, _BARRA.search(plan.texto)
    if 'x' in lugar:
        nueva['CoordX'], nueva['CoordY'] = _numero(lugar['x']), _numero(lugar['y'])
    elif 'lat' in lugar:
        nueva['Lat'], nueva['Lon'] = float(lugar['lat'].replace(',', '.')), float(lugar['lon'].replace(',', '.'))
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
    from ...dominio.estructura import clave

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


#: 070:RF-51: los datos que puede faltarle a una etapa, como los llama el operador; «falta ruta_cargas» enseñaba el campo.
_FALTA_DE_LA_ETAPA = {**ETIQUETA_DEL_DATO, 'ruta_cargas': 'el libro de cargas nuevas', 'formulario': 'el formulario del informe',
                      'nueva': 'los datos de la carga', 'ruta': 'los libros de demanda', 'alimentadores': 'los alimentadores'}


def _etapas_en_palabras(lista: dict) -> list[str]:
    def fila(e: dict) -> str:
        falta = ', '.join(_FALTA_DE_LA_ETAPA.get(k, k.replace('_', ' ')) for k in e['falta'])
        por_que = e.get('motivo') or f'falta {falta}'
        sufijo = {'hecha': ' (ya hecha)', 'se_omitira': f' (se omitirá: {por_que})',
                  'falta_dato': f' (falta {falta})'}.get(e['estado'], '')
        if not sufijo and e.get('condicion'):
            sufijo = f" ({e['condicion']})"
        return f"{e['nombre'].replace('_', ' ')}{sufijo}"

    return [fila(e) for e in lista['etapas']]


def _modulos_del_proyecto_entero(ws, plan) -> tuple[dict, dict]:
    """027:RF-72: el PIT, el VAD y el VNR del proyecto entero, con lo que la orden y el espacio dan de cada uno.

    Se leen con lo mismo que sus órdenes sueltas (``_pit``, ``_vad_empresa_modelo``, ``_vnr``) sobre una copia del plan:
    lo que a un módulo le falte no entra en ``plan.faltan`` (no impide el resto), sino en su motivo para saltarlo.
    """
    from dataclasses import replace

    from ...aplicacion.asistente.orquestador import MOTIVO_SIN_DATO

    datos: dict[str, Any] = {}
    omitir: dict[str, str] = {}
    for nombre, tarea, leer in (('pit', 'pit_expediente', lambda p, x: _pit(ws, p, x)),
                                ('vad', 'vad_empresa_modelo', lambda p, x: _vad_empresa_modelo(ws, p, x)),
                                ('vnr', 'vnr_estudio', _vnr)):
        copia = replace(plan, tarea=tarea, datos=dict(plan.datos), faltan=[], razonamiento=[], avisos=[])
        extras: dict[str, Any] = {}
        try:
            leer(copia, extras)
        except Exception as exc:  # noqa: BLE001 - un módulo que no se puede leer se salta con su motivo (027:RF-72)
            copia.faltan.append(str(exc))
        if copia.faltan or not extras.get(nombre):
            omitir[nombre] = f"{MOTIVO_SIN_DATO[nombre]}: {sin_citas('; '.join(copia.faltan))}".rstrip(': ')
        else:
            datos[nombre] = extras[nombre]
    return datos, omitir


def _datos_del_proyecto_entero(plan) -> dict:
    return {k: plan.datos[k] for k in ('sistema', 'periodo', 'ruta') if plan.datos.get(k)}


def camino_del_proyecto(ws, lista: dict, datos: dict) -> dict:
    """026:RF-48: el camino entero con su motivo, con la norma vigente hoy y el perfil de la empresa."""
    from datetime import date

    from ...aplicacion.asistente.orquestador import ETAPAS_PROYECTO_ENTERO, camino_de, norma_de_la_biblioteca
    from ...dominio.perfil_empresa import datos_perfil

    try:
        perfil = datos_perfil()
    except Exception:  # noqa: BLE001 - sin perfil legible, sus parámetros quedan como falta, nunca inventados
        perfil = None
    try:
        norma = norma_de_la_biblioteca(date.today().isoformat())
    except Exception:  # noqa: BLE001 - sin biblioteca legible, ídem
        norma = None
    return camino_de(lista, datos, norma=norma, perfil=perfil, etapas=ETAPAS_PROYECTO_ENTERO)


def _proyecto_entero(svc, ws, plan, extras: dict) -> None:
    _libros_de_la_demanda(svc, ws, plan)
    datos = _datos_del_proyecto_entero(plan)
    modulos, omitir = _modulos_del_proyecto_entero(ws, plan)
    datos.update(modulos)
    lista = svc.agente_proyecto_lista(ws, datos, omitir=omitir)
    if lista['bloqueo']:
        plan.faltan.append(lista['bloqueo'])
    extras['lista_confirmacion'] = lista['confirmacion']
    extras['etapas_en_palabras'] = _etapas_en_palabras(lista)
    extras['camino'] = camino = camino_del_proyecto(ws, lista, datos)                    # 026:RF-48
    plan.razonamiento.append(camino['motivo'])


def _ruta_de_control_de_carga(plan_datos: dict) -> str:
    return f"agente_carga_{re.sub(r'[^0-9A-Za-z]+', '_', str(plan_datos.get('sed') or ''))[:40]}.json"


def _capex_de_la_orden(plan, datos: dict) -> None:
    """El libro CAPEX que nombra la orden, para la etapa de las obras (``orquestador._ruta_de_la_etapa``)."""
    _clave, palabra, nombre = _LIBROS_DEL_PIDE[0]
    ruta = _libro_tras(plan.texto, palabra)
    if ruta is None:
        return
    if not Path(ruta).is_file():
        plan.faltan.append(f'{nombre}: {ruta} no existe.')
        return
    datos['capex'] = ruta
    plan.razonamiento.append(f'{nombre} de las obras: {ruta}.')  # 070:RF-13


def _ruta_de_control_de_corto_plazo(datos: dict) -> str:
    """Otro punto de control que el de la factibilidad de la misma carga: son dos análisis (072:RF-29)."""
    nombre = datos.get('sed') or Path(str(datos.get('ruta_cargas') or '')).stem
    return f"agente_corto_plazo_{re.sub(r'[^0-9A-Za-z]+', '_', str(nombre))[:40]}.json"


def _lista_de_corto_plazo(svc, ws, datos: dict) -> tuple[tuple, dict]:
    from ...aplicacion.asistente.orquestador import ETAPAS_CORTO_PLAZO, ETAPAS_CORTO_PLAZO_LIBRO

    etapas = ETAPAS_CORTO_PLAZO_LIBRO if datos.get('ruta_cargas') else ETAPAS_CORTO_PLAZO
    return etapas, svc.agente_proyecto_lista(ws, datos, etapas=etapas, control=_ruta_de_control_de_corto_plazo(datos))


def _corto_plazo(svc, ws, plan, extras: dict) -> None:
    """El estudio de corto plazo: la carga, la escalera de obras, los estudios y el informe, con un clic (072:RF-31 a
    RF-33). La orden lo pedía y el asistente hacía una sola de las cuatro, la que entendiera el modelo.

    La carga es la sola que describe la orden («… de 800 kW … barra …», como en 3.2) o las de un libro de cargas
    nuevas. Todo parte de la calibración aplicada y el informe, de su formulario de 4.4: lo que falte se dice aquí.
    """
    proyecto = plan.datos.get('proyecto')
    ruta = plan.datos.get('ruta')
    libro = ruta if ruta and Path(str(ruta)).suffix.lower() in ('.xlsx', '.xls') else None
    if libro:
        # Con el libro no hay una SED que nombrar: son las del libro (specs 007 y 014).
        plan.faltan[:] = [f for f in plan.faltan if not f.startswith(ETIQUETA_DEL_DATO['sed'] + ':')]
    else:
        _datos_de_la_carga(plan, extras)
    _exige_calibracion(svc, ws, plan)
    _obras(svc, ws, plan, extras)
    if not proyecto or not plan.datos.get('alimentadores') or not (libro or plan.datos.get('sed')):
        return
    formulario = ((ws.informes.get('formularios') or {}).get(proyecto) or {}).get('estudio')
    if not formulario:
        plan.faltan.append('el formulario del informe de estudio: rellénelo una vez en el paso 4.4.')
    datos: dict[str, Any] = {'proyecto': proyecto, 'alimentadores': list(plan.datos['alimentadores']),
                             'formulario': formulario or {}}
    if libro:
        datos['ruta_cargas'] = libro
    else:
        datos.update(sed=plan.datos['sed'], nueva=extras.get('nueva') or {})
    if extras.get('tipo_cambio'):
        datos['tipo_cambio'] = extras['tipo_cambio']
    _capex_de_la_orden(plan, datos)
    _etapas, lista = _lista_de_corto_plazo(svc, ws, datos)
    if lista['bloqueo']:
        plan.faltan.append(lista['bloqueo'])
    plan.razonamiento.append('tipo de análisis: corto plazo, con las obras de implementación inmediata.')  # 072:RF-31
    extras.update(plazo='corto_plazo', datos_etapas=datos, lista_confirmacion=lista['confirmacion'],
                  etapas_en_palabras=_etapas_en_palabras(lista))


def _lista_de_la_carga(svc, ws, datos: dict) -> dict:
    """Con lo que ya se sabe del proyecto, para que la lista no prometa una calibración que no hará (070:RF-53)."""
    from ...aplicacion.asistente.orquestador import ETAPAS_CARGA

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
    _capex_de_la_orden(plan, datos)
    lista = _lista_de_la_carga(svc, ws, datos)
    if lista['bloqueo']:
        plan.faltan.append(lista['bloqueo'])
    extras['datos_etapas'] = datos
    extras['lista_confirmacion'] = lista['confirmacion']
    extras['etapas_en_palabras'] = _etapas_en_palabras(lista)


def ejecutar_etapas(svc, ws, ctx, plan, extras: dict, base: str, http: Any) -> dict:
    """La lista confirmada; si cambió desde que se mostró, no se ejecuta (067:RF-39, 070:RF-52)."""
    if plan.tarea == 'evaluar_carga_nueva' and extras.get('plazo') == 'corto_plazo':
        from ...aplicacion.asistente.ejecutor import entregables

        datos = extras['datos_etapas']
        etapas, lista = _lista_de_corto_plazo(svc, ws, datos)
        if lista['confirmacion'] != extras.get('lista_confirmacion'):
            raise svc.UserError('La lista de etapas cambió desde que se mostró: escriba la orden de nuevo.')
        svc.agente_proyecto_anotar(ws, datos, lista)
        r = svc.agente_proyecto(ws, ctx, datos, base, http, etapas=etapas, control=_ruta_de_control_de_corto_plazo(datos))
        return {**r, 'entregables': entregables(r.get('etapas')),
                'texto': 'Estudio de corto plazo hecho: la carga, las obras, los estudios y el informe; vea el informe.'}
    if plan.tarea == 'evaluar_carga_nueva':
        from ...aplicacion.asistente.ejecutor import entregables
        from ...aplicacion.asistente.orquestador import ETAPAS_CARGA

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
    modulos, omitir = _modulos_del_proyecto_entero(ws, plan)                 # 027:RF-72: lo mismo que se enseñó
    datos.update(modulos)
    lista = svc.agente_proyecto_lista(ws, datos, omitir=omitir)
    if lista['confirmacion'] != extras.get('lista_confirmacion'):
        raise svc.UserError('La lista de etapas cambió desde que se mostró: escriba la orden de nuevo.')
    svc.agente_proyecto_anotar(ws, datos, lista)
    return svc.agente_proyecto(ws, ctx, datos, base, http)


_CORREO = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])")
_PROVEEDOR = (('google', re.compile(r'\b(google|gmail|drive)\b')), ('microsoft', re.compile(r'\b(microsoft|outlook|onedrive)\b')))


def _proveedor_de(texto: str) -> str | None:
    """El proveedor que nombra la orden, si nombra uno solo; «google drive» y «onedrive» no se confunden."""
    t = normalizar(texto)
    nombrados = {p for p, rx in _PROVEEDOR if rx.search(t)}
    return nombrados.pop() if len(nombrados) == 1 else None


def _informe_cerrado(ws, plan) -> str | None:
    """El Word de la salida que nombra la orden, o el último cerrado (con su resumen .json, 110:RF-12)."""
    salida = Path(ws.out_dir)
    nombrado = plan.datos.get('ruta')
    if nombrado:
        nombre = Path(str(nombrado)).name
        if not nombre.lower().endswith('.docx'):
            nombre += '.docx'
        return nombre if (salida / nombre).is_file() else None
    cerrados = [p for p in salida.glob('*.docx') if p.with_suffix('.json').is_file()] if salida.is_dir() else []
    return max(cerrados, key=lambda p: (p.stat().st_mtime_ns, p.name)).name if cerrados else None


#: 026:RF-45 (T19): el módulo cuyos entregables nombra la orden, por sus palabras (sin las rutas); el orden importa: «el
#: expediente del PIT» no es el PIDE, y «el informe del VNR» es del VNR.
_MODULOS_ENTREGABLES = (('pit', re.compile(r'\bpit\b')), ('vad', re.compile(r'\bvad\b')),
                        ('vnr', re.compile(r'\bvnr\b|\bvalor nuevo de reemplazo\b')), ('pide', re.compile(r'\bpide\b')),
                        ('informes', re.compile(r'\binformes?\b')))
NOMBRE_DEL_MODULO = {'pit': 'el PIT', 'vad': 'el VAD', 'vnr': 'el VNR', 'pide': 'el PIDE', 'informes': 'los informes'}
#: 026:RF-45: el PIT y el VAD dejan sus entregables en su carpeta del espacio, fuera de la salida (``app.get_file``
#: los sirve); la nube y el correo de la web solo publican y adjuntan lo que está en la salida.
_MODULOS_EN_LA_RAIZ = ('pit', 'vad')


def modulo_entregable_de(texto: str) -> str | None:
    """026:RF-45: el módulo que nombra la orden; ninguno si no nombra o si nombra varios (no se elige por el operador)."""
    t = normalizar(_RUTA_EN_ORDEN.sub(' ', texto))
    nombrados = [m for m, rx in _MODULOS_ENTREGABLES if rx.search(t)]
    if len(nombrados) > 1 and nombrados[-1] == 'informes':
        nombrados.pop()                                   # «el informe del VNR» es del VNR
    return nombrados[0] if len(nombrados) == 1 else None


def _informes_cerrados(ws, plan) -> list[str]:
    """Los informes cerrados de la salida (el que nombra la orden, o todos), cada uno con su PDF y su libro si están."""
    salida = Path(ws.out_dir)
    nombrado = _informe_cerrado(ws, plan) if plan.datos.get('ruta') else None
    docx = ([salida / nombrado] if nombrado else
            sorted(p for p in salida.glob('*.docx') if p.with_suffix('.json').is_file()) if salida.is_dir() else [])
    return [p.with_suffix(e).name for p in docx for e in ('.docx', '.pdf', '.xlsx') if p.with_suffix(e).is_file()]


def _seleccion_en_la_salida(ws, plan, modulo: str) -> list[str]:
    """026:RF-45: lo que el ZIP de la salida toma del módulo (``preparar_zip`` elige por nombre o por prefijo)."""
    salida = Path(ws.out_dir)
    if modulo == 'informes':
        return _informes_cerrados(ws, plan)
    if not salida.is_dir():
        return []
    if modulo == 'vnr':
        return ['vnr'] if any(p.is_file() for p in (salida / 'vnr').rglob('*')) else []
    return sorted(p.name for p in salida.iterdir() if p.is_file() and p.name.lower().startswith('pide_'))


def _ultimo_trabajo(extras: dict, *tipos: str) -> dict | None:
    hechos = [j for j in extras.get('_trabajos') or [] if j.get('kind') in tipos and j.get('status') == 'done']
    return max(hechos, key=lambda j: str(j.get('finished_at') or j.get('created_at') or '')) if hechos else None


def _entrega(ws, plan, extras: dict, modulo: str) -> None:
    """026:RF-45: dónde están los entregables del módulo, para bajarlos por la ruta que los sirve en la web."""
    que = NOMBRE_DEL_MODULO[modulo]
    if modulo == 'pit':
        trabajo = _ultimo_trabajo(extras, 'pit_expediente', 'pit_diagnostico')
        if trabajo is None:
            plan.faltan.append(f'los entregables de {que}: aún no hay ningún expediente ni diagnóstico terminado en este '
                               'espacio; ármelo antes, por ejemplo «arma el expediente del PIT con …».')
            return
        extras['entrega'] = {'modulo': modulo, 'trabajo': str(trabajo['id'])}
        return
    if modulo == 'vad':
        estudios = sorted(p.parent.name for p in (Path(ws.root) / 'vad').glob('*/estudio.json'))
        nombrado = [e for e in estudios if e.lower() in plan.texto.lower()]
        if len(nombrado) == 1 or (not nombrado and len(estudios) == 1):
            extras['entrega'] = {'modulo': modulo, 'estudio': (nombrado or estudios)[0]}
        elif estudios:
            plan.faltan.append('el estudio del VAD: diga cuál de ' + ', '.join(estudios) + '.')
        else:
            plan.faltan.append(f'los entregables de {que}: aún no hay ningún estudio del VAD en este espacio.')
        return
    seleccion = _seleccion_en_la_salida(ws, plan, modulo)
    if not seleccion:
        plan.faltan.append(f'los entregables de {que}: aún no hay ninguno en la salida del espacio.')
        return
    extras['entrega'] = {'modulo': modulo, 'seleccion': seleccion}


def _descarga(ws, plan, extras: dict) -> None:
    """026:RF-45: «descarga el PIDE» baja los entregables de ese módulo; sin módulo, el ZIP de siempre."""
    if (modulo := modulo_entregable_de(plan.texto)) is not None:
        _entrega(ws, plan, extras, modulo)


def _publicar_modulo(ws, plan, extras: dict, modulo: str) -> None:
    """026:RF-45: la tarjeta de publicar lleva la selección del módulo en la salida (109:RF-24)."""
    que = NOMBRE_DEL_MODULO[modulo]
    if modulo in _MODULOS_EN_LA_RAIZ:
        plan.faltan.append(f'publicar {que}: sus entregables están en su carpeta del espacio, fuera de la salida, y la web '
                           f'solo publica la salida. Bájelos con «descarga {que}» y súbalos usted.')
        return
    # El PIDE, por el prefijo de sus libros en la salida; el VNR, por su carpeta; un informe, el que nombra la orden o el
    # último cerrado (la tarjeta publica una sola selección).
    salida = (_informe_cerrado(ws, plan) if modulo == 'informes' else
              modulo if _seleccion_en_la_salida(ws, plan, modulo) else None)
    if salida:
        extras['salida'] = salida
    else:
        plan.faltan.append(f'los entregables de {que}: aún no hay ninguno en la salida del espacio.')


def _nube_y_correo(ws, plan, extras: dict) -> None:
    """070:RF-79, RF-80, RF-83: lo que la tarjeta necesita, sacado de la orden escrita por el operador."""
    extras['proveedor'] = _proveedor_de(plan.texto)
    extras['para'] = list(dict.fromkeys(m.lower() for m in _CORREO.findall(plan.texto)))
    modulo = modulo_entregable_de(plan.texto) if plan.tarea in ('enviar_informe', 'publicar_nube') else None
    if plan.tarea == 'publicar_nube' and modulo is not None:
        _publicar_modulo(ws, plan, extras, modulo)                             # 026:RF-45
        return
    if plan.tarea == 'enviar_informe' and modulo not in (None, 'informes'):
        # 026:RF-45, 110:RF-3: el correo de la web lleva un informe cerrado y sus adjuntos; nunca otro libro en su lugar.
        que = NOMBRE_DEL_MODULO[modulo]
        extras['informe'] = None
        plan.faltan.append(f'enviar {que} por correo: el correo de la web solo lleva un informe cerrado con su PDF y su '
                           f'libro. ' + (f'Bájelo con «descarga {que}».' if modulo in _MODULOS_EN_LA_RAIZ else
                                         f'Publíquelo con «publica {que} en drive» y comparta el enlace.'))
        return
    if plan.tarea == 'enviar_informe':
        extras['informe'] = _informe_cerrado(ws, plan)
        if not extras['informe']:
            plan.faltan.append('un informe cerrado en la salida del espacio: ' + (
                f'«{plan.datos["ruta"]}» no está.' if plan.datos.get('ruta') else 'aún no hay ninguno.'))
        if not extras['para']:
            plan.faltan.append('a quién va: escriba en la orden la dirección de correo.')
    elif plan.tarea == 'publicar_nube':
        extras['salida'] = str(plan.datos.get('ruta') or '')


_RUTA_EN_ORDEN = re.compile(r'"([^"]+)"|«([^»]+)»|(?<![\w])([A-Za-z]:[\\/][^\s"«»,;]+)')
_RANGO_ANIOS = re.compile(r'\b(20\d\d)\s*(?:-|–|a|al|hasta)\s*(20\d\d)\b')
_ANIO = re.compile(r'\b(20\d\d)\b')
_ALTERNATIVA = re.compile(r'alternativa\s+(?:elegida\s+)?[«"]([^»"]+)[»"]', re.IGNORECASE)


def _rutas_de_la_orden(plan) -> list[str]:
    rutas = [next(g for g in m.groups() if g) for m in _RUTA_EN_ORDEN.finditer(plan.texto)]
    dato = plan.datos.get('ruta')
    for d in dato if isinstance(dato, list) else [dato] if dato else []:
        if str(d) not in rutas:
            rutas.append(str(d))
    return rutas


def _pit(ws, plan, extras: dict) -> None:
    """070:RF-79: el área, los años, el periodo y los ficheros del PIT, sacados de la orden; lo que falta lo dice el plan."""
    from ...dominio.perfil_empresa import datos_perfil
    from ...dominio.pit import PitError
    from ...dominio.pit.ambito import areas_del_perfil

    rutas = _rutas_de_la_orden(plan)
    libros = [r for r in rutas if Path(r).suffix.lower() in ('.xlsx', '.xlsm', '.xls')]
    jsons = [r for r in rutas if Path(r).suffix.lower() == '.json']
    alternativas = [r for r in jsons if 'alternativ' in Path(r).name.lower()]
    proyecciones = [r for r in jsons if r not in alternativas]
    pit: dict[str, Any] = {'workspace_id': ws.id}
    for clave, lista, que in (('libro_red', libros, 'el libro de la red del área (.xlsx)'),
                              ('proyeccion', proyecciones, 'la proyección de la demanda (.json)')):
        if len(lista) != 1:
            plan.faltan.append(f'{que}: escriba en la orden su ruta entre comillas.' if not lista
                               else f'{que}: la orden nombra varios; deje solo uno.')
        elif not Path(lista[0]).is_file():
            plan.faltan.append(f'{que}: «{lista[0]}» no existe.')
        else:
            pit[clave] = lista[0]
    if alternativas:
        pit['alternativas'] = alternativas[0]
        if (m := _ALTERNATIVA.search(plan.texto)) is not None:
            pit['alternativa_elegida'] = m[1].strip()
        elif plan.tarea == 'pit_expediente':
            plan.faltan.append('la alternativa elegida: escríbala entre comillas, por ejemplo alternativa «A».')
    if (rango := _RANGO_ANIOS.search(plan.texto)) is not None and int(rango[1]) <= int(rango[2]):
        pit['anios'] = list(range(int(rango[1]), int(rango[2]) + 1))
        pit['periodo'] = f'{rango[1]}-{rango[2]}'
    else:
        pit['anios'] = sorted({int(a) for a in _ANIO.findall(plan.texto)})
    if not pit['anios']:
        plan.faltan.append('los años del estudio: por ejemplo, «de 2027 a 2031».')
    if plan.tarea == 'pit_expediente' and 'periodo' not in pit:
        plan.faltan.append('el periodo del expediente: por ejemplo, «de 2027 a 2031».')
    try:
        areas = [a.codigo for a in areas_del_perfil(datos_perfil())]
    except PitError as exc:
        plan.faltan.append(sin_citas(str(exc)))
        areas = []
    texto = plan.texto.lower()
    nombradas = [a for a in areas if re.search(rf'(?<![\w-]){re.escape(a.lower())}(?![\w-])', texto)]
    if len(nombradas) == 1 or (not nombradas and len(areas) == 1):
        pit['area'] = (nombradas or areas)[0]
    elif areas:
        plan.faltan.append('el área de demanda: diga cuál de ' + ', '.join(areas) + '.')
    extras['pit'] = pit


#: 026:RF-44: el sector típico de la Guía 232 por sus palabras; sin ninguna, el de la pestaña (urbano de densidad media-baja).
_SECTOR_GUIA = (('urbano_rural', r'\burbano[\s-]+rural\b'), ('rural_ser', r'\b(rural|ser)\b'),
                ('urbano_alta', r'\b(urbano[\s-]+)?(de\s+)?alta(\s+densidad)?\b'),
                ('urbano_media_baja', r'\b(media|baja)\b'))
_SECTOR_SICODI = re.compile(r'\bsector(?:\s+t[ií]pico)?\s+(?:del\s+)?sicodi\s+([\w-]+)', re.IGNORECASE)
_RESOLUCION = re.compile(r'\bresoluci[oó]n\s+(?:n[º°.o]*\s*)?([\w./-]*\d[\w./-]*)', re.IGNORECASE)
_MES = re.compile(r'\b(\d{4})-(0[1-9]|1[0-2])\b')


def _vnr(plan, extras: dict) -> None:
    """026:RF-44: los datos del Estudio VNR de la orden; la red y el SICODI, los del espacio (como la pestaña)."""
    texto = normalizar(plan.texto)
    sector = next((s for s, patron in _SECTOR_GUIA if re.search(patron, texto)), 'urbano_media_baja')
    vnr: dict[str, Any] = {'sector': sector, 'moneda': 'PEN' if re.search(r'\b(soles|pen)\b', texto) else 'USD'}
    if (m := _SECTOR_SICODI.search(plan.texto)) is not None:
        vnr['sector_sicodi'] = m[1]
    else:
        plan.faltan.append('el sector típico del SICODI: por ejemplo, «sector SICODI 2».')
    if (m := _RESOLUCION.search(plan.texto)) is not None:
        vnr['resolucion'] = m[1]
    else:
        plan.faltan.append('la resolución del SICODI: por ejemplo, «resolución 158-2023-OS/CD».')
    # El año de la valorización, sin contar el que va dentro de la resolución («158-2023-OS/CD»).
    sin_resolucion = _RESOLUCION.sub(' ', plan.texto)
    if (anios := _ANIO.findall(sin_resolucion)):
        vnr['anio'] = int(anios[-1])
    else:
        plan.faltan.append('el año de la valorización: por ejemplo, «2025».')
    extras['vnr'] = vnr


def _clientes_fijos(plan, extras: dict) -> None:
    """026:RF-44: el rango de meses de la orden (AAAA-MM a AAAA-MM, o un año o un rango de años entero)."""
    meses = [f'{a}-{m}' for a, m in _MES.findall(plan.texto)]
    if not meses and (rango := _RANGO_ANIOS.search(plan.texto)) is not None and int(rango[1]) <= int(rango[2]):
        meses = [f'{rango[1]}-01', f'{rango[2]}-12']
    elif not meses and (anios := _ANIO.findall(plan.texto)):
        meses = [f'{anios[0]}-01', f'{anios[0]}-12']
    if not meses:
        plan.faltan.append('el rango de meses: por ejemplo, «de 2025-01 a 2025-12» o «de 2024 a 2025».')
        return
    desde, hasta = min(meses), max(meses)
    extras['clientes_fijos'] = {'desde': desde, 'hasta': hasta,
                                'con_cabecera': not re.search(r'\bsin\s+(la\s+)?cabecera\b', normalizar(plan.texto))}


#: 026:RF-46: el generador de la biblioteca por sus palabras (107:RF-22); el orden importa: «guía VNR» antes que «217».
_GENERADOR_NORMATIVA = (('guia_vnr_232', r'\b(guia\s+(del?\s+)?vnr|vnr|232)\b'),
                        ('formatos_217', r'\b(formatos?|sombread\w*|217|norma tarifas)\b'),
                        ('coes', r'\bcoes\b'), ('reconsideraciones', r'\breconsideraci\w*\b'))


def _normativa(plan, extras: dict) -> None:
    """026:RF-46: agregar pide el .json de la norma; regenerar, cuál de los generadores de la biblioteca."""
    if plan.tarea == 'normativa_agregar':
        ruta = str(plan.datos.get('ruta') or '')
        if not ruta.lower().endswith('.json'):
            plan.faltan.append('el fichero .json de la norma (con el esquema de la biblioteca normativa): por ejemplo, '
                               '«agrega la norma D:/normas/rcd_123_2026.json».')
        elif not Path(ruta).is_file():
            plan.faltan.append(f'el fichero {Path(ruta).name}: no está en esa ruta.')
        return
    texto = normalizar(plan.texto)
    generador = next((g for g, patron in _GENERADOR_NORMATIVA if re.search(patron, texto)), None)
    if generador is None:
        plan.faltan.append('qué registro regenerar: la Guía VNR 232, los formatos 217, el COES o las '
                           'reconsideraciones.')
        return
    extras['normativa'] = {'generador': generador}


def _texto_normativa(plan, resultado: dict) -> None:
    """026:RF-46: lo que entró en la biblioteca, y qué reglas entran, salen o cambian si se regeneró."""
    final = resultado.get('resultado') or {}
    actos = ', '.join(final.get('actos') or []) or 'ninguna'
    if plan.tarea == 'normativa_agregar':
        resultado['texto'] = f'Norma agregada a la capa del usuario: {actos}.'
        return
    if final.get('sin_cambios'):
        resultado['texto'] = 'Regenerado desde su fuente oficial: igual que el vigente, no se escribió nada.'
        return
    partes = []
    for c in final.get('cambios') or []:
        cuenta = (f"{len(c.get('entran') or [])} entran, {len(c.get('salen') or [])} salen, "
                  f"{len(c.get('cambian') or [])} cambian")
        vigencia = '; cambia su vigencia' if c.get('vigencia') else ''
        partes.append(f"{c['acto']}{' (nueva)' if c.get('nueva') else ''}: {cuenta}{vigencia}")
    resultado['texto'] = f"Regenerado y escrito en la capa del usuario ({actos}). " + '. '.join(partes) + '.'
    if final.get('otros'):
        otros = len(final['otros'])                              # 086:RF-110: singular o plural reales
        resultado['texto'] += (f" También rehízo {otros} {'fichero que viaja' if otros == 1 else 'ficheros que viajan'} "
                               'con el programa '
                               '(no se escriben desde aquí).')
    resultado['cambios'] = final.get('cambios') or []


_GRUPO = re.compile(r'\bgrupo\s+(\d)\b', re.IGNORECASE)
_ESTUDIO_VAD = re.compile(r'[\w-]+')


def _registro_vad():
    from ...dominio.registro_normativo import cargar_registro
    from ...adaptadores.powerfactory_env import project_root

    return cargar_registro(project_root() / 'config' / 'vad', project_root() / 'config' / 'normativa')


def _vad_crear(plan, extras: dict) -> None:
    """070:RF-79: el grupo, el periodo y el TdR del estudio, de la orden; el TdR, el que nombre o el único del registro."""
    vad: dict[str, Any] = {}
    if (m := _GRUPO.search(plan.texto)) is not None:
        vad['grupo'] = int(m[1])
    else:
        plan.faltan.append('el grupo del estudio: por ejemplo, «del grupo 1».')
    if (r := _RANGO_ANIOS.search(plan.texto)) is not None and int(r[1]) < int(r[2]):
        vad['periodo'] = f'{r[1]}-{r[2]}'
    else:
        plan.faltan.append('el periodo del estudio: por ejemplo, «para 2027-2031».')
    try:
        normas = _registro_vad().normas
    except (OSError, ValueError) as exc:
        plan.faltan.append(f'el registro normativo del VAD no se pudo leer: {sin_citas(str(exc))}')
        normas = {}
    texto = normalizar(plan.texto)
    nombrados = [a for a in normas if a in texto]
    tdr = [a for a, n in normas.items() if 'términos de referencia' in n.titulo.lower()]
    elegido = nombrados if len(nombrados) == 1 else (tdr if not nombrados and len(tdr) == 1 else [])
    if elegido:
        vad['version_tdr'] = elegido[0]
    elif normas:
        plan.faltan.append('el TdR del estudio: diga cuál de ' + ', '.join(sorted(tdr or normas)) + '.')
    extras['vad'] = vad


def _vad_empresa_modelo(ws, plan, extras: dict) -> None:
    """070:RF-79, RF-86: el caso (sistemas.json y lo que nombra) y el estudio: el nombrado o el único del espacio."""
    import json

    vad: dict[str, Any] = {}
    carpetas = [Path(r) for r in _rutas_de_la_orden(plan)]
    carpetas = [c if c.is_dir() else c.parent for c in carpetas if (c if c.is_dir() else c.parent).joinpath('sistemas.json').is_file()]
    if len(carpetas) != 1:
        plan.faltan.append('la carpeta del caso del VAD, con su sistemas.json: escriba su ruta entre comillas.')
    else:
        try:
            sistemas = json.loads((carpetas[0] / 'sistemas.json').read_text(encoding='utf-8')).get('sistemas') or {}
            nombrados = sorted({str(r) for pasos in sistemas.values() for r in (pasos or {}).values()})
        except (OSError, ValueError, AttributeError) as exc:
            plan.faltan.append(f'un sistemas.json que se pueda leer: {exc}')
            nombrados = []
        vad['ficheros'] = [str(carpetas[0] / 'sistemas.json'), *(str(carpetas[0] / n) for n in nombrados)]
        if (sueltos := [n for n in nombrados if not (carpetas[0] / n).is_file()]):
            plan.faltan.append('los ficheros que nombra sistemas.json: no están ' + ', '.join(sueltos) + '.')
    estudios = sorted(p.parent.name for p in (Path(ws.root) / 'vad').glob('*/estudio.json'))
    texto = plan.texto.lower()
    nombrado = [e for e in estudios if e.lower() in texto]
    if len(nombrado) == 1 or (not nombrado and len(estudios) == 1):
        vad['estudio'] = (nombrado or estudios)[0]
    elif estudios:
        plan.faltan.append('el estudio del VAD: diga cuál de ' + ', '.join(estudios) + '.')
    else:
        plan.faltan.append('un estudio del VAD en este espacio: créelo antes, por ejemplo «crea el estudio del VAD del '
                           'grupo 1 para 2027-2031».')
    extras['vad'] = vad


def _texto_vad(plan, resultado: dict) -> None:
    final = resultado.get('resultado') or {}
    if plan.tarea == 'vad_crear_estudio':
        resultado['texto'] = f"Estudio del VAD {final.get('id') or ''} creado ({final.get('estado') or 'sin estado'})."
    else:
        estados = list((final.get('sistemas') or {}).values())
        resultado['texto'] = (f"Empresa modelo armada: {estados.count('OK')} de {len(estados)} sistema(s) en OK; el "
                              f"estudio está «{final.get('estado_estudio') or 'sin estado'}».")


_MANIOBRA = re.compile(r'\b(?:maniobra|interruptor|seccionador|reconectador|recloser|cuchilla|equipo)\s+'
                       r'(?:n(?:umero|°|º|o\.?)\s*)?([A-Za-z0-9][\w.-]*)', re.IGNORECASE)
_CASO_PLANO = re.compile(r'\bcaso\s+[«"]([^»"]+)[»"]', re.IGNORECASE)


def _plano(plan, extras: dict) -> None:
    """070:RF-79: el alimentador, la maniobra, abrir o cerrar y el caso (el de la orden, o «Caso base» como la web)."""
    texto = normalizar(plan.texto)
    alimentadores = [a for a in plan.datos.get('alimentadores') or [] if a != 'todos']
    plano: dict[str, Any] = {'caso': (m[1].strip() if (m := _CASO_PLANO.search(plan.texto)) else 'Caso base')}
    if len(alimentadores) == 1:
        plano['alimentador'] = alimentadores[0]
    else:
        plan.faltan.append('el alimentador: uno solo, el de la maniobra.')
    if (m := _MANIOBRA.search(plan.texto)) is not None:
        plano['maniobra'] = m[1]
    else:
        plan.faltan.append('la maniobra: su número de equipo, por ejemplo «el seccionador S-104».')
    abre, cierra = (bool(re.search(rf'\b{v}\w*\b', texto)) for v in ('abr', 'cierr'))
    if abre != cierra:
        plano['estado'] = 'abierto' if abre else 'cerrado'
    else:
        plan.faltan.append('si se abre o se cierra la maniobra.')
    extras['plano'] = plano


def _texto_plano(plan, resultado: dict, extras: dict) -> None:
    final = resultado.get('resultado') or {}
    p = extras.get('plano') or {}
    motor = final.get('motor') or 'el motor elegido'
    resultado['texto'] = (f"Variación con la maniobra {p.get('maniobra')} {p.get('estado')} en {p.get('alimentador')} "
                          f"({p.get('caso')}), estudiada con {motor}: véala en el plano; el caso base no cambió.")


#: 026:RF-42 (T16): la casilla por las palabras de la orden (sin sus rutas), en este orden: «la base de equipos» no es la
#: base de la red, y «los equipos complementarios» no son los equipos.
_CASILLA_POR_PALABRAS = (
    ('aliases', r'\balias\w*\b'), ('vnr_package', r'\b(vnr|gis|paquete)\b'), ('study', r'\bestudio\b|\bzxst\b'),
    ('equipment_extra', r'\bequipos?\b.*\bcomplementari\w*\b|\bcomplementari\w*\b.*\bequipos?\b'),
    ('equipment_mdb', r'\bbase de (los )?equipos\b|\bequipos?\b.*\bmdb\b'),
    ('equipment', r'\bequipos?\b|\bcatalogo de conductores\b'), ('loads', r'\bcargas?\b'),
    ('mdb', r'\bbase\b|\bmdb\b|\baccess\b'), ('red', r'\bred\b|\btopologia\b'))
#: Lo que se deduce del fichero cuando la orden no nombra la casilla: su extensión, sin adivinar entre los TXT.
_CASILLA_POR_EXTENSION = {'.mdb': 'mdb', '.accdb': 'mdb', '.zxst': 'study', '.gdb': 'vnr_package', '.gpkg': 'vnr_package'}
_NUBE_EN_ORDEN = re.compile(r'\b(nube|drive|onedrive|google drive)\b')


def _fichero_de_la_orden(plan, que: str) -> Path | None:
    """El único fichero que nombra la orden, si existe en la máquina; si no, lo que falta va al plan. Manda la ruta
    escrita en la orden (entre comillas o con su unidad); la del intérprete, solo si la orden no trae ninguna: una ruta
    con espacios la recortaba y contaba como otra."""
    rutas = list(dict.fromkeys(next(g for g in m.groups() if g) for m in _RUTA_EN_ORDEN.finditer(plan.texto)))
    if not rutas and plan.datos.get('ruta'):
        dato = plan.datos['ruta']
        rutas = [str(d) for d in (dato if isinstance(dato, list) else [dato])]
    if len(rutas) != 1:
        plan.faltan.append(f'{que}: escriba en la orden su ruta entre comillas.' if not rutas
                           else f'{que}: la orden nombra varios; deje solo uno.')
        return None
    ruta = Path(rutas[0])
    if not ruta.is_file():
        plan.faltan.append(f'{que}: «{ruta.name}» no está en esa ruta.')
        return None
    return ruta


def casilla_de(texto: str, ruta: Path | None) -> str | None:
    """026:RF-42: la casilla que nombra la orden; sin palabras, la de la extensión del fichero, si solo cabe en una."""
    t = normalizar(_RUTA_EN_ORDEN.sub(' ', texto))
    por_palabras = next((c for c, patron in _CASILLA_POR_PALABRAS if re.search(patron, t)), None)
    if por_palabras is not None:
        return por_palabras
    return _CASILLA_POR_EXTENSION.get(ruta.suffix.lower()) if ruta is not None else None


def _asignar_entrada(plan, extras: dict) -> None:
    """026:RF-42: el fichero y su casilla; de la nube lo elige el operador en el selector (109:RF-3, 070:RF-81)."""
    from .workspace import SLOTS

    if not _RUTA_EN_ORDEN.search(plan.texto) and _NUBE_EN_ORDEN.search(normalizar(plan.texto)):
        plan.faltan.append('el fichero de la nube: lo elige usted en el selector de su cuenta; pídalo con «importa el '
                           'libro desde google drive» y elija la casilla allí.')
        return
    ruta = _fichero_de_la_orden(plan, 'el fichero que entra en la casilla')
    if ruta is None:
        return
    casilla = casilla_de(plan.texto, ruta)
    if casilla is None:
        plan.faltan.append('la casilla: diga en la orden si es la red, las cargas, los equipos, la base de la red, el '
                           'estudio, el paquete del VNR-GIS o los alias.')
        return
    extras['entrada'] = {'casilla': casilla, 'ruta': str(ruta), 'etiqueta': SLOTS[casilla]['etiqueta']}


#: 026:RF-42: la clase del libro de la empresa por sus palabras (``fuentes_empresa.CLASES``), en este orden: «el caso del
#: VAD» no es el estudio del VAD, ni «las cargas nuevas» la demanda.
_CLASE_POR_PALABRAS = (
    ('sicodi', r'\bsicodi\b'), ('interrupciones', r'\binterrupcion\w*\b'), ('perfil', r'\bperfil\b'),
    ('catalogo', r'\bcatalogo\b'), ('tdr', r'\btdr\b|\bterminos de referencia\b'), ('pfd', r'\bpfd\b'),
    ('vad_caso', r'\bcaso\b.*\bvad\b'), ('vad', r'\bvad\b'), ('red_area', r'\bred del area\b'),
    ('cargas_nuevas', r'\bcargas nuevas\b'), ('proyeccion', r'\bproyeccion\b'), ('alternativas', r'\balternativas\b'),
    ('medicion', r'\bmedicion\w*\b'), ('demanda', r'\bdemanda\b'), ('pit', r'\bpit\b'), ('pide', r'\bpide\b'))
NOMBRE_DE_LA_CLASE = {'sicodi': 'el SICODI', 'interrupciones': 'las interrupciones', 'perfil': 'el perfil de la empresa',
                      'catalogo': 'el catálogo', 'tdr': 'los términos de referencia', 'pfd': 'el proyecto de DIgSILENT',
                      'vad_caso': 'el caso del VAD', 'vad': 'el estudio del VAD', 'red_area': 'la red del área',
                      'cargas_nuevas': 'las cargas nuevas', 'proyeccion': 'la proyección', 'alternativas': 'las alternativas',
                      'medicion': 'la medición', 'demanda': 'la demanda', 'pit': 'el PIT', 'pide': 'el PIDE',
                      'otro': 'otro libro'}
#: Los libros que valen igual para todos los años: el resto entra en su año (RF-42: «a su carpeta y a su año»).
_CLASES_SIN_ANIO = ('perfil', 'catalogo', 'tdr', 'pfd')
_PERIODO_DE_LIBRO = re.compile(r'\b(20\d\d)(?:-(0[1-9]|1[0-2]))?\b')


def _subir_fuente(plan, extras: dict) -> None:
    """026:RF-42: el libro, su clase y su año, sacados de la orden; lo que no dice, lo pregunta el plan."""
    from ...aplicacion import fuentes_empresa as fe

    ruta = _fichero_de_la_orden(plan, 'el libro de la empresa')
    t = normalizar(_RUTA_EN_ORDEN.sub(' ', plan.texto))
    clase = next((c for c, patron in _CLASE_POR_PALABRAS if re.search(patron, t)), None)
    if clase is None or clase not in fe.CLASES:
        plan.faltan.append('qué libro es: el SICODI, la demanda, el perfil de la empresa, las interrupciones, el catálogo '
                           'u otro de la empresa.')
        return
    m = _PERIODO_DE_LIBRO.search(_RUTA_EN_ORDEN.sub(' ', plan.texto))
    periodo = '' if m is None else m.group(1) + (f'-{m.group(2)}' if m.group(2) else '')
    if not periodo and clase not in _CLASES_SIN_ANIO:
        plan.faltan.append(f'el año de {NOMBRE_DE_LA_CLASE[clase]}: escríbalo en la orden, por ejemplo «del 2025».')
        return
    if ruta is not None:
        extras['fuente'] = {'clase': clase, 'periodo': periodo, 'ruta': str(ruta)}


def _texto_entradas(plan, resultado: dict, extras: dict) -> None:
    """026:RF-42: lo que entró y dónde, con el aviso de la casilla si lo dio."""
    final = resultado.get('resultado') or {}
    if plan.tarea == 'asignar_entrada':
        e = extras.get('entrada') or {}
        resultado['texto'] = f"«{Path(e.get('ruta') or '').name}» entró en la casilla «{e.get('etiqueta') or ''}»."
        if final.get('warning'):
            resultado['texto'] += f" Aviso: {final['warning']}"
        return
    f = extras.get('fuente') or {}
    periodo = final.get('periodo') or f.get('periodo')
    resultado['texto'] = (f"«{final.get('nombre') or Path(f.get('ruta') or '').name}» quedó en las fuentes de la empresa "
                          f"como {NOMBRE_DE_LA_CLASE.get(f.get('clase') or '', 'libro')}"
                          f"{f' del {periodo}' if periodo else ''}; lo usan todos los módulos.")


def _texto_descarga(ws, plan, resultado: dict, extras: dict) -> None:
    """La descarga: el ZIP de la salida (de un módulo o de todo) o, del PIT y el VAD, sus ficheros uno por uno."""
    entrega = extras.get('entrega') or {}
    que = NOMBRE_DEL_MODULO.get(entrega.get('modulo') or '', '')
    final = resultado.get('resultado') or {}
    if entrega.get('trabajo') or entrega.get('estudio'):
        if entrega.get('trabajo'):
            r = final.get('result') or {}
            rutas = list((r.get('salidas_relativas') or {}).values()) or [r.get('salida_relativa')]
        else:
            rutas = list(final.get('salidas') or [])
        rutas = [x for x in rutas if isinstance(x, str) and x and '..' not in x]
        resultado['entregables'] = rutas                  # el panel los enlaza con su descarga (``app.get_file``)
        resultado['texto'] = (f"Los entregables de {que}: {len(rutas)} {'fichero' if len(rutas) == 1 else 'ficheros'}, "
                              'cada uno con su enlace.' if rutas else f'{que.capitalize()} no tiene entregables todavía.')
        return
    trabajo = next((p['trabajo'] for p in resultado.get('pasos') or []), None)
    if trabajo:
        resultado['enlace'] = f'/api/workspaces/{ws.id}/outputs.zip?job={trabajo}'
        resultado['texto'] = f'ZIP de {que} preparado: bájelo del enlace.' if que else 'ZIP preparado: bájelo del enlace.'


def _benchmark(ws, plan) -> None:
    """070:RF-79: el benchmark sale de la fuente TXT cargada en el espacio; sin ella, el plan lo dice."""
    faltan = [n for s, n in (('red', 'RED'), ('loads', 'CARGA'), ('equipment', 'EQUIPOS'))
              if not ws.input_path(s) or not Path(ws.input_path(s)).is_file()]
    if faltan:
        plan.faltan.append('la fuente TXT cargada en el espacio: falta ' + ', '.join(faltan) + '.')


def _texto_pit(plan, resultado: dict) -> None:
    """070:RF-79: lo que el operador lee del diagnóstico o del expediente."""
    r = resultado.get('resultado') or {}
    if plan.tarea == 'pit_diagnostico':
        avisos = r.get('avisos') or []
        resultado['texto'] = (f"Diagnóstico del PIT {'completo' if r.get('completo') else 'incompleto'}, con "
                              f"{len(avisos)} aviso(s); queda en {Path(str(r.get('salida') or '')).name or 'el espacio'}.")
    else:
        pendientes = r.get('pendientes') or []
        resultado['texto'] = (f"Expediente del PIT {r.get('tipo') or ''} ({r.get('estado') or 'sin estado'}), con "
                              f"{len(pendientes)} pendiente(s).").replace('  ', ' ')


#: 070:RF-80: lo que dice cada tarjeta antes del clic del operador.
_TEXTO_DE_LA_TARJETA = {
    'enviar_informe': 'Borrador listo. Revíselo y pulse «Confirmar y enviar»: sin ese clic no sale nada.',
    'publicar_nube': 'Elija la carpeta de destino y pulse «Publicar»: sin ese clic no se sube nada.',
    'compartir_nube': 'Elija el expediente y revise el acceso: sin su confirmación no se comparte nada.',
    'importar_nube': 'Elija el fichero en el selector de la nube: entra con lo que usted elija.',
    'conectar_nube': 'Pulse «Conectar» y escriba la contraseña en la página del proveedor.',
}


def _tarjeta(plan, resultado: dict, extras: dict) -> None:
    """070:RF-80, RF-81: la tarjeta del panel; su botón lo pulsa el operador y el navegador lo manda."""
    final = resultado.get('resultado') or {}
    tarjeta: dict[str, Any] = {'tipo': plan.tarea, 'proveedor': extras.get('proveedor'), 'para': extras.get('para') or []}
    if plan.tarea == 'enviar_informe':
        tarjeta['previa'] = final
    elif plan.tarea == 'publicar_nube':
        tarjeta['salida'] = extras.get('salida') or ''
    elif plan.tarea == 'conectar_nube':
        tarjeta['proveedores'] = final.get('proveedores') or []
    resultado['tarjeta'] = tarjeta
    resultado['texto'] = _TEXTO_DE_LA_TARJETA[plan.tarea]


def presentar(ws, plan, resultado: dict, extras: dict | None = None) -> None:
    """Lo que el operador lee del resultado (070:RF-35, RF-37)."""
    if plan.tarea in _TEXTO_DE_LA_TARJETA:
        _tarjeta(plan, resultado, extras or {})
    elif plan.tarea in ('pit_diagnostico', 'pit_expediente'):
        _texto_pit(plan, resultado)
    elif plan.tarea in ('vad_crear_estudio', 'vad_empresa_modelo'):
        _texto_vad(plan, resultado)
    elif plan.tarea == 'plano_maniobra':
        _texto_plano(plan, resultado, extras or {})
    elif plan.tarea in ('normativa_agregar', 'normativa_regenerar'):
        _texto_normativa(plan, resultado)
    elif plan.tarea == 'descargar_resultados':
        _texto_descarga(ws, plan, resultado, extras or {})                     # 026:RF-45
    elif plan.tarea in ('asignar_entrada', 'subir_fuente_empresa'):
        _texto_entradas(plan, resultado, extras or {})                         # 026:RF-42
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
            plan.faltan.append(sin_citas(str(exc)))
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
        # 072:RF-29: «estudio de corto plazo con la carga X» y «evalúa la carga X» son dos análisis distintos.
        (_corto_plazo if _tipos_de_analisis(plan) == ['corto_plazo'] else _evaluar_carga)(svc, ws, plan, extras)
    elif tarea in ('alimentadores_completo', 'set_completo'):
        _libros_de_la_demanda(svc, ws, plan)
        if tarea == 'alimentadores_completo':
            _tope_de_alimentadores(svc, plan, list(plan.datos.get('alimentadores') or []))
    elif tarea == 'recalibrar':
        try:
            svc.recalibrar_datos(ws, plan.datos.get('proyecto') or '')
        except svc.UserError as exc:
            plan.faltan.append(sin_citas(str(exc)))
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
    elif tarea in _TEXTO_DE_LA_TARJETA:
        _nube_y_correo(ws, plan, extras)
    elif tarea in ('pit_diagnostico', 'pit_expediente'):
        _pit(ws, plan, extras)
    elif tarea == 'vad_crear_estudio':
        _vad_crear(plan, extras)
    elif tarea == 'vad_empresa_modelo':
        _vad_empresa_modelo(ws, plan, extras)
    elif tarea == 'vnr_estudio':                                           # 026:RF-44
        _vnr(plan, extras)
    elif tarea == 'clientes_fijos_evolucion':
        _clientes_fijos(plan, extras)
    elif tarea in ('normativa_agregar', 'normativa_regenerar'):             # 026:RF-46
        _normativa(plan, extras)
    elif tarea == 'plano_maniobra':
        _plano(plan, extras)
    elif tarea == 'descargar_resultados':                                  # 026:RF-45
        _descarga(ws, plan, extras)
    elif tarea == 'asignar_entrada':                                       # 026:RF-42
        _asignar_entrada(plan, extras)
    elif tarea == 'subir_fuente_empresa':
        _subir_fuente(plan, extras)
    elif tarea == 'benchmark_anonimo':
        _benchmark(ws, plan)
