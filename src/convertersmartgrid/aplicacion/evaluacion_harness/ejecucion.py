"""Ejecución pareada; las dependencias de dominio se inyectan desde la aplicación."""
from __future__ import annotations

import math
import os
import threading
import time
import uuid
from collections import defaultdict
from copy import deepcopy

from ...dominio.evaluacion_harness.contratos import canonico, huella, validar
from ...dominio.evaluacion_harness.metricas import (
    clasificacion,
    comparar_pareado,
    entidades,
    recuperacion,
)

_RUNTIME_VIVOS: dict[str, str] = {}
#: 043:RF-16: cada cuánto se mira la cancelación mientras el proveedor calcula.
_VIGILANCIA_S = 0.05


def segundos_de_entorno(nombre: str, defecto: float) -> float:
    """043:RF-16: los segundos de la variable si son un número positivo y finito; si no, el de por defecto."""
    try:
        valor = float(os.environ.get(nombre, '').strip())
    except ValueError:
        return defecto
    return valor if math.isfinite(valor) and valor > 0 else defecto


class _SinRespuesta(Exception):
    """El proveedor sigue calculando: pasó su plazo o se canceló a mitad (043:RF-16)."""

    def __init__(self, motivo: str, *, cancelado: bool) -> None:
        super().__init__(motivo)
        self.cancelado = cancelado


def _llamar(proveedor, args, *, plazo_s, cancelar, por_presupuesto=False):
    """Llama al proveedor en un hilo y espera como mucho ``plazo_s``, mirando la cancelación.

    Un hilo no se puede matar: si no vuelve, su cálculo puede seguir y su resultado se descarta. Por eso quien llama no
    le pide más casos y el informe lo dice, en vez de dar por detenido lo que sigue en marcha.
    """
    hecho, caja = threading.Event(), {}

    def correr():
        try:
            caja['salida'] = proveedor(*args)
        except BaseException as exc:  # noqa: BLE001 - se relanza en el hilo del harness
            caja['error'] = exc
        finally:
            hecho.set()

    threading.Thread(target=correr, name='harness-proveedor', daemon=True).start()
    limite = None if plazo_s is None else time.monotonic() + plazo_s
    while not hecho.wait(_VIGILANCIA_S if limite is None else max(0.0, min(_VIGILANCIA_S, limite - time.monotonic()))):
        if cancelar is not None and cancelar():
            raise _SinRespuesta('cancelación solicitada durante la llamada; el cálculo del proveedor puede seguir y '
                                'su resultado no se usa', cancelado=True)
        if limite is not None and time.monotonic() >= limite and por_presupuesto:
            raise _SinRespuesta('presupuesto de la campaña agotado durante la llamada; el cálculo del proveedor puede '
                                'seguir y su resultado no se usa', cancelado=True)
        if limite is not None and time.monotonic() >= limite:
            raise _SinRespuesta(f'PlazoAgotado: el proveedor no respondió en el plazo de {plazo_s:g} s; su cálculo '
                                'puede seguir y su resultado no se usa', cancelado=False)
    if 'error' in caja:
        raise caja['error']
    return caja['salida']


def _metrica(medidas, ruta):
    valor = medidas
    for parte in ruta.split('.'):
        if not isinstance(valor, dict) or parte not in valor:
            return None
        valor = valor[parte]
    return valor


def _medir(suite, casos, evaluadores):
    tipo, params = suite['tipo'], suite.get('parametros', {})
    gold = [c['esperado'] for c in casos]
    pred = [c['salida']['prediccion'] for c in casos]
    if tipo in ('clasificacion', 'violaciones'):
        m = clasificacion([{'esperado': g['tarea'], 'obtenido': p.get('tarea')}
                           for g, p in zip(gold, pred, strict=True)], params['clases'])
        return {'metricas': {**m['micro'], **m, 'acierto': m['acierto']}, 'aprobado': True}
    if tipo == 'entidades':
        m = entidades([{'esperados': g['entidades'], 'vistos': p['entidades']}
                       for g, p in zip(gold, pred, strict=True)])
        return {'metricas': m, 'aprobado': True}
    if tipo == 'recuperacion':
        m = recuperacion([{'relevantes': g['documentos'], 'gold_completo': g['completo'],
                           'recuperados': p['documentos']} for g, p in zip(gold, pred, strict=True)],
                          k=params['k'])
        return {'metricas': m, 'aprobado': m['gold_completo']}
    if tipo not in evaluadores:
        raise ValueError('evaluador independiente ausente para '+tipo)
    # El proveedor del candidato no recibe la referencia; solo este evaluador la ve.
    parametros = deepcopy(params)
    parametros['_harness'] = {'grupos': [c['group_id'] for c in casos],
                              'rol': casos[0]['rol'],
                              'modelo_digest': casos[0]['salida']['modelo_digest']}
    resultado = evaluadores[tipo](deepcopy(gold), deepcopy(pred), parametros)
    canonico(resultado)
    if (not isinstance(resultado, dict) or not isinstance(resultado.get('metricas'), dict)
            or type(resultado.get('aprobado')) is not bool):
        raise ValueError('salida de evaluador independiente inválida')
    return resultado


def _puertas(suite, medida, anterior):
    fallos = []
    if not suite.get('puertas'):
        fallos.append('sin puertas predeclaradas: solo diagnóstico')
    for nombre, puerta in suite.get('puertas', {}).items():
        valor, previo = _metrica(medida, nombre), _metrica(anterior, nombre)
        if type(valor) not in (int, float) or not math.isfinite(valor):
            fallos.append(nombre+': ausente/no finito/sin denominador')
            continue
        if ('minimo' in puerta and valor < puerta['minimo']) or (
                'maximo' in puerta and valor > puerta['maximo']):
            fallos.append(nombre+': fuera de puerta')
        if type(previo) not in (int, float) or not math.isfinite(previo):
            fallos.append(nombre+': referencia ausente/no finita')
        elif (('minimo' in puerta and valor < previo) or
              ('maximo' in puerta and valor > previo)):
            fallos.append(nombre+': regresión frente a referencia')
    return fallos


def _comparaciones(cfg, filas, evaluadores, resultados=None):
    salida = []
    comps = cfg['politica']['comparaciones']
    suites = {s['id']: s for s in cfg['suites']}
    for comp in comps:
        por_grupo = defaultdict(lambda: {'referencia': [], 'candidato': []})
        fallidos = set()
        for f in filas:
            if f['suite_id'] != comp['suite_id']:
                continue
            if f['estado'] == 'ok':
                por_grupo[f['group_id']][f['rol']].append(f)
            else:
                fallidos.add(f['group_id'])
        pares = []
        bloqueos = ['grupo con casos fallidos/cancelados '+g for g in sorted(fallidos)]
        for grupo, roles in por_grupo.items():
            if not roles['referencia'] or not roles['candidato']:
                bloqueos.append('grupo incompleto '+grupo)
                continue
            try:
                suite = suites[comp['suite_id']]
                if suite['tipo'] in {'clasificacion', 'entidades', 'violaciones', 'recuperacion'}:
                    valores = {rol: _metrica(_medir(suite, casos, evaluadores)['metricas'], comp['metrica'])
                               for rol, casos in roles.items()}
                else:
                    medidas = resultados[comp['suite_id']]['medidas']
                    if any(not isinstance(medidas[rol]['por_grupo'][grupo], dict) for rol in roles):
                        raise ValueError('por_grupo exige mapa con nombre de métrica, no escalares ambiguos')
                    valores = {rol: medidas[rol]['por_grupo'][grupo][comp['metrica']] for rol in roles}
                pares.append({'group_id': grupo, **valores})
            except (KeyError, TypeError, ValueError) as exc:
                bloqueos.append(str(exc))
        try:
            # Bonferroni predecible: controla toda la familia declarada de contrastes.
            confianza = 1-(1-comp['confianza'])/max(1, len(comps))
            resultado = comparar_pareado(pares, metrica=comp['metrica'], margen=comp['margen'],
                semilla=comp['semilla'], remuestras=comp['remuestras'], confianza=confianza,
                min_grupos=comp['min_grupos'], direccion=comp.get('direccion', 'mayor_mejor'))
        except ValueError as exc:
            resultado = {'mejora_demostrada': False, 'motivo': str(exc)}
        if bloqueos:
            resultado['mejora_demostrada'] = False
        salida.append({**resultado, 'suite_id': comp['suite_id'], 'bloqueos': bloqueos,
                       'correccion': 'Bonferroni', 'confianza_familiar': comp['confianza']})
    return salida


def ejecutar(config: dict, proveedor, *, modo: str, cancelar=None, evaluadores=None,
             plazo_caso_s: float | None = None, presupuesto_s: float | None = None) -> dict:
    """Campaña pareada; con ``plazo_caso_s`` o ``presupuesto_s`` cada llamada queda acotada (043:RF-16)."""
    validar(config)
    if modo not in {'contract', 'replay', 'runtime'} or not callable(proveedor):
        raise ValueError('modo/proveedor inválido')
    for tope in (plazo_caso_s, presupuesto_s):
        if tope is not None and not (type(tope) in (int, float) and math.isfinite(tope) and tope > 0):
            raise ValueError('plazo/presupuesto del harness inválido')
    cfg, evaluadores = deepcopy(config), evaluadores or {}
    inicio = time.monotonic()
    filas, cancelado = [], False
    acotado = plazo_caso_s is not None or presupuesto_s is not None
    sin_respuesta: list[dict] = []
    motivo_corte = 'cancelación solicitada'
    for suite in cfg['suites']:
        descriptor = {k: deepcopy(suite[k]) for k in ('id', 'tipo', 'parametros') if k in suite}
        for caso in suite['casos']:
            if caso['particion'] != 'prueba':
                continue
            for rol, modelo in cfg['modelos'].items():
                fila = {'suite_id': suite['id'], 'record_id': caso['record_id'],
                        'group_id': caso['group_id'], 'rol': rol, 'origen': caso['origen'],
                        'esperado': deepcopy(caso['esperado']), 'entrada_hash': huella(caso['entrada'])}
                restante = None if presupuesto_s is None else presupuesto_s - (time.monotonic() - inicio)
                if not cancelado and restante is not None and restante <= 0:
                    cancelado, motivo_corte = True, 'presupuesto de la campaña agotado'
                if cancelado or (cancelar is not None and cancelar()):
                    cancelado = True
                    filas.append({**fila, 'estado': 'cancelado', 'error': motivo_corte})
                    continue
                t = time.monotonic()
                args = (deepcopy(modelo), deepcopy(descriptor), deepcopy(caso['entrada']))
                try:
                    if acotado:
                        plazo = min(p for p in (plazo_caso_s, restante) if p is not None)
                        salida = _llamar(proveedor, args, plazo_s=plazo, cancelar=cancelar,
                                         por_presupuesto=plazo_caso_s is None or plazo < plazo_caso_s)
                    else:
                        salida = proveedor(*args)
                    canonico(salida)
                    if (not isinstance(salida, dict) or not isinstance(salida.get('prediccion'), dict)
                            or salida.get('modelo_digest') != modelo['digest']
                            or salida.get('config_hash') != modelo['config_hash']
                            or (modelo.get('artifacts') is not None
                                and salida.get('artifacts_hash') != huella(modelo['artifacts']))
                            or any(not isinstance(salida.get(k), str) or not salida[k]
                                   for k in ('backend', 'dispositivo', 'clase_evidencia'))):
                        raise ValueError('salida sin predicción, digest, backend o dispositivo verificable')
                    filas.append({**fila, 'estado': 'ok', 'salida': deepcopy(salida),
                                  'duracion_s': time.monotonic()-t})
                except _SinRespuesta as exc:
                    # 043:RF-16: el atascado no recibe más casos; los que faltan siguen en el denominador.
                    sin_respuesta.append({'suite_id': suite['id'], 'record_id': caso['record_id'], 'rol': rol})
                    cancelado = True
                    motivo_corte = (('presupuesto de la campaña agotado' if str(exc).startswith('presupuesto') else
                                     'cancelación solicitada') if exc.cancelado else
                                    'proveedor sin respuesta: no se le piden más casos')
                    filas.append({**fila, 'estado': 'cancelado' if exc.cancelado else 'error', 'error': str(exc),
                                  'duracion_s': time.monotonic()-t})
                except Exception as exc:  # noqa: BLE001 - frontera del proveedor; conserva el caso fallido.
                    filas.append({**fila, 'estado': 'error', 'error': type(exc).__name__+': '+str(exc),
                                  'duracion_s': time.monotonic()-t})
    # 043:RF-16: el estado sale de las filas, igual que en validar_integridad (un atascado último no cancela nada).
    cancelado = any(f['estado'] == 'cancelado' for f in filas)
    resultados, bloqueos, evidencia_real = {}, [], True
    for suite in cfg['suites']:
        propios = [f for f in filas if f['suite_id'] == suite['id']]
        completa = all(f['estado'] == 'ok' for f in propios)
        fallos, medidas = [], {}
        if not completa:
            fallos.append('casos incompletos')
        else:
            for rol in cfg['modelos']:
                casos = [f for f in propios if f['rol'] == rol]
                try:
                    medidas[rol] = _medir(suite, casos, evaluadores)
                except Exception as exc:  # noqa: BLE001 - frontera del evaluador externo; no pierde cobertura.
                    completa = False
                    fallos.append('evaluador '+rol+': '+type(exc).__name__+': '+str(exc))
            if completa:
                if medidas['candidato']['aprobado'] is not True:
                    fallos.append('evaluación independiente rechazada')
                fallos.extend(_puertas(suite, medidas['candidato']['metricas'],
                                      medidas['referencia']['metricas']))
        real = (completa and all(f['salida']['clase_evidencia'] == 'real' for f in propios)
                and all(m.get('clase_evidencia') == 'real' for m in medidas.values())
                if suite['tipo'] not in {'clasificacion', 'entidades', 'violaciones', 'recuperacion'}
                else completa and all(f['salida']['clase_evidencia'] == 'real' for f in propios))
        if suite['obligatoria']:
            bloqueos.extend(suite['id']+': '+f for f in fallos)
            evidencia_real = evidencia_real and real
        resultados[suite['id']] = {'tipo': suite['tipo'], 'obligatoria': suite['obligatoria'],
            'completa': completa, 'programados': len(propios), 'medidas': medidas,
            'aprobada': completa and not fallos, 'evidencia_real': real, 'bloqueos': fallos}
    completa = all(s['completa'] for s in resultados.values() if s['obligatoria'])
    comps = _comparaciones(cfg, filas, evaluadores, resultados)
    mejora = completa and not cancelado and bool(comps) and all(c['mejora_demostrada'] for c in comps)
    if not mejora:
        bloqueos.append('sin mejora estadística demostrada con el protocolo predeclarado')
    if not evidencia_real:
        bloqueos.append('evidencia de contrato/replay/ausente: no acredita ejecución real')
    if modo != 'runtime':
        bloqueos.append('solo runtime actual puede solicitar promoción')
    resultado = {'schema_version': 1, 'modo': modo, 'configuracion': cfg,
        'config_hash': cfg['sello'], 'estado': 'CANCELADA' if cancelado else 'COMPLETA' if completa else 'INCOMPLETA',
        'programados': len(filas), 'completados': sum(f['estado'] == 'ok' for f in filas),
        'fallidos': sum(f['estado'] != 'ok' for f in filas), 'casos': filas,
        'suites': resultados, 'comparaciones': comps, 'mejora_demostrada': mejora,
        'promocion_permitida': completa and not cancelado and not bloqueos,
        'bloqueos': bloqueos, 'duracion_s': time.monotonic()-inicio,
        'proveedor_sin_respuesta': sin_respuesta,
        'runtime_nonce': uuid.uuid4().hex if modo == 'runtime' else None,
        'aceptacion_electrica': False, 'modelo_promovido': False}
    resultado['sello_informe'] = huella(resultado)
    if modo == 'runtime':
        # No acepta un informe histórico como ejecución actual, ni siquiera resellado.
        if len(_RUNTIME_VIVOS) >= 32:
            _RUNTIME_VIVOS.pop(next(iter(_RUNTIME_VIVOS)))
        _RUNTIME_VIVOS[resultado['runtime_nonce']] = resultado['sello_informe']
    return resultado


def validar_integridad(informe: dict) -> None:
    """Comprueba el contenido y sus invariantes; una huella no autentica la verdad física."""
    contenido = {k: v for k, v in informe.items() if k != 'sello_informe'}
    if informe.get('sello_informe') != huella(contenido):
        raise ValueError('sello del informe inválido')
    cfg = informe['configuracion']
    validar(cfg)
    if informe.get('config_hash') != cfg['sello']:
        raise ValueError('configuración distinta del informe')
    esperados = {(s['id'], c['record_id'], rol): c for s in cfg['suites']
                 for c in s['casos'] if c['particion'] == 'prueba' for rol in cfg['modelos']}
    filas, vistos = informe['casos'], set()
    for f in filas:
        clave = (f['suite_id'], f['record_id'], f['rol'])
        if clave in vistos or clave not in esperados:
            raise ValueError('caso duplicado o ajeno al conjunto')
        vistos.add(clave)
        gold = esperados[clave]
        if (f['esperado'] != gold['esperado'] or f['group_id'] != gold['group_id']
                or f['origen'] != gold['origen'] or f['entrada_hash'] != huella(gold['entrada'])
                or f['estado'] not in ('ok', 'error', 'cancelado')):
            raise ValueError('identidad, gold o estado de caso contradictorio')
        if f['estado'] == 'ok' and (f['salida']['modelo_digest'] != cfg['modelos'][f['rol']]['digest']
                or f['salida']['config_hash'] != cfg['modelos'][f['rol']]['config_hash']
                or (cfg['modelos'][f['rol']].get('artifacts') is not None and
                    f['salida'].get('artifacts_hash') != huella(cfg['modelos'][f['rol']]['artifacts']))):
            raise ValueError('digest de modelo contradictorio')
    if vistos != set(esperados) or informe['programados'] != len(esperados):
        raise ValueError('denominador programado contradictorio')
    if (informe['completados'] != sum(f['estado'] == 'ok' for f in filas)
            or informe['fallidos'] != sum(f['estado'] != 'ok' for f in filas)):
        raise ValueError('denominadores completados/fallidos contradictorios')
    if set(informe['suites']) != {s['id'] for s in cfg['suites']}:
        raise ValueError('cobertura de suites contradictoria')
    for s in cfg['suites']:
        r = informe['suites'][s['id']]
        propios = [f for f in filas if f['suite_id'] == s['id']]
        if (r['tipo'] != s['tipo'] or r['obligatoria'] != s['obligatoria']
                or r['programados'] != len(propios)):
            raise ValueError('identidad/soporte de suite contradictorio')
        if s['tipo'] in {'clasificacion', 'entidades', 'violaciones', 'recuperacion'} and r['completa']:
            for rol in cfg['modelos']:
                recalculado = _medir(s, [f for f in propios if f['rol'] == rol], {})
                if r['medidas'][rol] != recalculado:
                    raise ValueError('resumen contradictorio con los casos')
        if (r['aprobada'] and (not r['completa'] or any(f['estado'] != 'ok' for f in propios)
                    or r['medidas']['candidato']['aprobado'] is not True
                    or _puertas(s, r['medidas']['candidato']['metricas'],
                                r['medidas']['referencia']['metricas']))):
            raise ValueError('aprobación de suite contradictoria')
    comps = _comparaciones(cfg, filas, {}, informe['suites'])
    if informe['comparaciones'] != comps:
        raise ValueError('comparaciones contradictorias')
    completa = all(r['completa'] for r in informe['suites'].values() if r['obligatoria'])
    cancelada = any(f['estado'] == 'cancelado' for f in filas)
    estado = 'CANCELADA' if cancelada else 'COMPLETA' if completa else 'INCOMPLETA'
    mejora = completa and not cancelada and bool(comps) and all(c['mejora_demostrada'] for c in comps)
    if informe['estado'] != estado or informe['mejora_demostrada'] != mejora:
        raise ValueError('estado/mejora contradictorio con la cobertura')


def validar_promocion(informe: dict, config: dict) -> None:
    """Guarda adicional; no escribe el registro ni sustituye sus puertas/recarga."""
    validar(config)
    validar_integridad(informe)
    if informe.get('modo') != 'runtime':
        raise ValueError('promoción exige runtime actual')
    if _RUNTIME_VIVOS.get(informe.get('runtime_nonce')) != informe['sello_informe']:
        raise ValueError('promoción exige runtime vivo del mismo proceso, no evidencia histórica')
    if informe.get('config_hash') != config['sello'] or informe.get('configuracion') != config:
        raise ValueError('modelo/datos/configuración/política distintos')
    if (informe.get('estado') != 'COMPLETA' or informe.get('promocion_permitida') is not True
            or informe.get('bloqueos') or informe.get('mejora_demostrada') is not True):
        raise ValueError('campaña incompleta, rechazada o sin mejora demostrada')
    esperados = {(s['id'], c['record_id'], rol)
                 for s in config['suites'] if s['obligatoria']
                 for c in s['casos'] if c['particion'] == 'prueba' for rol in config['modelos']}
    vistos = []
    for fila in informe['casos']:
        clave = (fila['suite_id'], fila['record_id'], fila['rol'])
        if clave in esperados:
            if (fila['estado'] != 'ok' or fila['salida']['clase_evidencia'] != 'real'
                    or fila['salida']['modelo_digest'] != config['modelos'][fila['rol']]['digest']):
                raise ValueError('caso obligatorio sin evidencia runtime actual')
            vistos.append(clave)
    if len(vistos) != len(esperados) or set(vistos) != esperados:
        raise ValueError('cobertura obligatoria incoherente')
    for suite in config['suites']:
        if suite['obligatoria']:
            r = informe['suites'].get(suite['id'], {})
            if not all(r.get(k) is True for k in ('completa', 'aprobada', 'evidencia_real')):
                raise ValueError('suite obligatoria sin aprobación independiente real')
