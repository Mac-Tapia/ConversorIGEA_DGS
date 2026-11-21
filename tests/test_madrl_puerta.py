"""Spec 074 T8: la puerta del aprendizaje en alimentadores no vistos, sellada antes de aplicar, y su confirmación.

El 2026-11-21 el bloque del entrenamiento informó que nada aplicaba ``puerta_del_aprendizaje`` sobre redes que el modelo
no vio. Las redes de aquí son sintéticas, con nombres inventados, y la política es un doble: la real se prueba en el
fichero hermano, con la marca de los que usan la tarjeta. La corrida del piloto y la de DIgSILENT van aparte.
"""
from __future__ import annotations

import copy
import json

import pytest
from apoyo import cargar_herramienta

from convertersmartgrid.adaptadores.madrl_obras import Accion, ParametrosObras
from convertersmartgrid.adaptadores.madrl_puerta import (
    PREFIJO_PRUEBA,
    SEPARACION,
    PuertaError,
    decidir,
    exigir_proyecto_de_prueba,
    fijar_separacion,
    manifiesto_modelo,
    obra_de,
    orden_confirmacion,
    orden_valida,
    red_declarada,
    sellar_separacion,
    sello_valido,
)
from convertersmartgrid.aplicacion.obras_pf import validar_obra

P = ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0, candidatos=4, max_bancos=3, max_pasos=6)


def _id(red: str, clase: str, nombre: str) -> str:
    return f'{clase}:Network Model.IntPrjfolder\\Network Data.IntPrjfolder\\{red}.ElmNet\\{nombre}.{clase}'


def _sistema(redes: tuple[str, ...], carga: float = 0.4) -> dict:
    """Una SET con un alimentador por red, cada uno con su cabecera: la forma de una captura de DIgSILENT."""
    fuente = _id('SET_X', 'ElmTerm', 'FUENTE')
    nodos = {fuente: {'kv': 10.0, 'fuente': True, 'v_pu': 1.0}}
    ramas = []
    for red in redes:
        previa = _id(red, 'ElmTerm', 'B0')
        nodos[previa] = {'kv': 10.0}
        ramas.append({'id': _id(red, 'ElmCoup', 'CAB'), 'clase': 'ElmCoup', 'desde': fuente, 'hasta': previa,
                      'r_ohm': 0.0, 'x_ohm': 0.0, 'inom_ka': 0.0})
        for i in range(1, 7):
            barra = _id(red, 'ElmTerm', f'B{i}')
            nodos[barra] = {'kv': 10.0, 'p_mw': carga, 'q_mvar': carga * 0.85}
            ramas.append({'id': _id(red, 'ElmLne', f'L{i}'), 'clase': 'ElmLne', 'desde': previa, 'hasta': barra,
                          'r_ohm': 0.6, 'x_ohm': 0.5, 'inom_ka': 1.0, 'km': 1.0})
            previa = barra
    return {'nodos': nodos, 'ramas': ramas}


def _manifiesto(*redes: tuple[str, dict]) -> dict:
    return manifiesto_modelo(politica='gatv2', ocultas=32, cabezas=2, parametros=P,
                             entrenamiento=[red_declarada(n, g) for n, g in redes], huella_pesos='0' * 64)


def _medida(nombre, ref_norma=True, ref_costo=20.0, apr_norma=True, apr_costo=20.0, obras=None):
    return {'nombre': nombre, 'referencia': {'en_norma': ref_norma, 'costo': ref_costo},
            'aprendido': {'en_norma': apr_norma, 'costo': apr_costo}, 'obras_aprendidas': obras or []}


def test_la_separacion_rechaza_lo_que_el_modelo_ya_vio():
    """074:RF-13 — la misma red con otro nombre, o un alimentador repetido, no cuentan como no vistos."""
    vista = _sistema(('ALIM_A', 'ALIM_B'))
    m = _manifiesto(('entreno.json', vista))
    with pytest.raises(PuertaError, match='entrenamiento'):
        sellar_separacion(m, [red_declarada('copia.json', copy.deepcopy(vista))])
    with pytest.raises(PuertaError, match='ya se vieron'):
        sellar_separacion(m, [red_declarada('mezcla.json', _sistema(('ALIM_B', 'ALIM_C')))])
    with pytest.raises(PuertaError, match='otra red no vista'):
        sellar_separacion(m, [red_declarada('c1.json', _sistema(('ALIM_C',))),
                              red_declarada('c2.json', _sistema(('ALIM_C', 'ALIM_D'), carga=0.3))])
    with pytest.raises(PuertaError, match='con qué redes'):
        sellar_separacion({**m, 'entrenamiento': []}, [red_declarada('c.json', _sistema(('ALIM_C',)))])
    sep = sellar_separacion(m, [red_declarada('nueva.json', _sistema(('ALIM_C', 'ALIM_D')))])
    assert sello_valido(sep) and sep['no_vistos'][0]['alimentadores'] == sorted(
        [_id('ALIM_C', 'ElmCoup', 'CAB'), _id('ALIM_D', 'ElmCoup', 'CAB')])
    sep['no_vistos'][0]['nombre'] = 'otra.json'
    assert not sello_valido(sep)


def test_la_separacion_sellada_no_se_cambia_despues(tmp_path):
    """074:RF-13 — en una carpeta queda una sola separación: otra, tras aplicar, no se acepta."""
    m = _manifiesto(('entreno.json', _sistema(('ALIM_A',))))
    sep = sellar_separacion(m, [red_declarada('c.json', _sistema(('ALIM_C',)))])
    assert fijar_separacion(tmp_path, sep)['sello'] == sep['sello']
    assert fijar_separacion(tmp_path, sep)['sello'] == sep['sello']           # repetir la misma vale
    otra = sellar_separacion(m, [red_declarada('d.json', _sistema(('ALIM_D',)))])
    with pytest.raises(PuertaError, match='ya hay otra separación'):
        fijar_separacion(tmp_path, otra)
    guardada = json.loads((tmp_path / SEPARACION).read_text(encoding='utf-8'))
    assert guardada['sello'] == sep['sello']


def test_la_decision_es_pasa_o_archivar_con_su_medida():
    """074:RF-6 / 074:RF-14 — 100 % en norma y no más caro que NSGA-II pasa; si no, se archiva sin integrarlo."""
    m = _manifiesto(('entreno.json', _sistema(('ALIM_A',))))
    sep = sellar_separacion(m, [red_declarada('c.json', _sistema(('ALIM_C',))),
                                red_declarada('d.json', _sistema(('ALIM_D',)))])
    pasa = decidir(sep, [_medida('c.json', apr_costo=10.0), _medida('d.json', ref_norma=False, apr_norma=False)])
    assert pasa['decision'] == 'pasa' and pasa['sello_separacion'] == sep['sello'] and not pasa['integrado_en_flujo']
    assert len(pasa['medidas']) == 2
    caro = decidir(sep, [_medida('c.json', apr_costo=30.0), _medida('d.json')])
    fuera = decidir(sep, [_medida('c.json', apr_norma=False, apr_costo=0.0), _medida('d.json')])
    assert caro['decision'] == fuera['decision'] == 'archivar'
    assert 'cuesta' in caro['puerta']['motivo'] and '50%' in fuera['puerta']['motivo']
    with pytest.raises(PuertaError, match='no son las de la separación'):
        decidir(sep, [_medida('d.json'), _medida('c.json')])
    with pytest.raises(PuertaError, match='sello'):
        decidir({**sep, 'modelo': 'otro'}, [_medida('c.json'), _medida('d.json')])


def test_las_obras_van_como_las_de_la_web():
    """074:RF-10 — el banco y la terna aprendidos son obras de la spec 011, en «Con proyecto»; sin ruta, no se adivinan."""
    banco = obra_de(Accion('banco', _id('ALIM_C', 'ElmTerm', 'B5'), 10.0), P)
    terna = obra_de(Accion('terna', _id('ALIM_C', 'ElmLne', 'L2'), 50.0), P)
    assert banco == {'clase': 'condensador', 'alimentador': 'ALIM_C', 'casos': ['Con proyecto'], 'barra': 'B5',
                     'q_kvar': 300.0, 'escalones': 1}
    assert validar_obra(banco).a_dict() == banco
    assert validar_obra(terna).tramos == ('L2',) and terna['alimentador'] == 'ALIM_C'
    assert obra_de(Accion('banco', 'A3', 10.0), P) is None


def test_la_orden_va_solo_a_un_proyecto_de_prueba(tmp_path):
    """074:RF-10 / 074:RF-14 — solo lo que pasa, solo en un proyecto «PRUEBA…» y con su huella íntegra."""
    m = _manifiesto(('entreno.json', _sistema(('ALIM_A',))))
    sep = sellar_separacion(m, [red_declarada('c.json', _sistema(('ALIM_C',)))])
    obra = obra_de(Accion('banco', _id('ALIM_C', 'ElmTerm', 'B5'), 10.0), P)
    informe = decidir(sep, [_medida('c.json', obras=[{'elemento': 'B5', 'obra': obra}])])
    with pytest.raises(PuertaError, match='proyecto de prueba'):
        orden_confirmacion(informe, espacio='ws1', proyecto='RED_TRABAJADA')
    with pytest.raises(PuertaError, match='proyecto de prueba'):
        exigir_proyecto_de_prueba('ws1', '')
    with pytest.raises(PuertaError, match='archiva'):
        orden_confirmacion({**informe, 'decision': 'archivar'}, espacio='ws1', proyecto=f'{PREFIJO_PRUEBA}074_C')
    sin_sitio = decidir(sep, [_medida('c.json', obras=[{'elemento': 'A3', 'obra': None}])])
    with pytest.raises(PuertaError, match='no se adivinan'):
        orden_confirmacion(sin_sitio, espacio='ws1', proyecto=f'{PREFIJO_PRUEBA}074_C')
    orden = orden_confirmacion(informe, espacio='ws1', proyecto=f'{PREFIJO_PRUEBA}074_C')
    assert orden['feeders'] == ['ALIM_C'] and orden['obras'] == [obra]
    orden_valida(orden, sep)
    with pytest.raises(PuertaError, match='huella'):
        orden_valida({**orden, 'proyecto': 'RED_TRABAJADA'}, sep)
    otra = sellar_separacion(m, [red_declarada('d.json', _sistema(('ALIM_D',)))])
    with pytest.raises(PuertaError, match='separación sellada'):
        orden_valida(orden, otra)


class _WebFalsa:
    def __init__(self, estado='done'):
        self.llamadas, self.estado = [], estado

    def _pedir(self, metodo, ruta, **kw):
        self.llamadas.append((metodo, ruta, kw.get('json')))
        return {'id': f'o{len(self.llamadas)}'}

    def post(self, ruta, **kw):
        self.llamadas.append(('POST', ruta, kw.get('json')))
        return {'id': 'job'}

    def esperar(self, trabajo, limite_s=0):
        return {'status': self.estado, 'result': {'informe': {}}}


def test_confirmar_sigue_la_ruta_de_las_obras_de_la_web(tmp_path):
    """074:RF-10 — guardar, simular y aplicar por la web en el proyecto de prueba; una orden alterada no llega a la web."""
    herramienta = cargar_herramienta('madrl_puerta.py', tools_en_path=True)
    m = _manifiesto(('entreno.json', _sistema(('ALIM_A',))))
    sep = fijar_separacion(tmp_path, sellar_separacion(m, [red_declarada('c.json', _sistema(('ALIM_C',)))]))
    obra = obra_de(Accion('banco', _id('ALIM_C', 'ElmTerm', 'B5'), 10.0), P)
    orden = orden_confirmacion(decidir(sep, [_medida('c.json', obras=[{'elemento': 'B5', 'obra': obra}])]),
                               espacio='ws1', proyecto=f'{PREFIJO_PRUEBA}074_C')
    ruta = tmp_path / 'orden_confirmacion.json'
    ruta.write_text(json.dumps(orden), encoding='utf-8')
    web = _WebFalsa()
    args = herramienta.argparse.Namespace(orden=ruta, url='')
    assert herramienta.confirmar(args, web=web) == 0
    rutas = [r for _m, r, _j in web.llamadas]
    assert rutas == ['/api/workspaces/ws1/obras', '/pf/obras/simular', '/pf/obras/aplicar']
    assert web.llamadas[1][2] == {'project': f'{PREFIJO_PRUEBA}074_C', 'feeders': ['ALIM_C'], 'ids': ['o1']}
    assert json.loads((tmp_path / 'confirmacion.json').read_text(encoding='utf-8'))['confirmada'] is True
    fallida = _WebFalsa('error')
    assert herramienta.confirmar(args, web=fallida) == 2 and len(fallida.llamadas) == 2      # sin aplicar
    ruta.write_text(json.dumps({**orden, 'proyecto': 'RED_TRABAJADA'}), encoding='utf-8')
    intacta = _WebFalsa()
    assert herramienta.confirmar(args, web=intacta) == 2 and intacta.llamadas == []


def _politica_doble(actua: bool):
    """Un doble de la política: deja una obra y la red en norma, o no hace nada; así se decide sin azar."""
    from convertersmartgrid.adaptadores.madrl_obras import resultado

    def evaluar(plano, _politica):
        plano.e.reiniciar()
        if actua:
            plano.e.hechas[min(plano.e.acciones)].add(0)
            return {**resultado(plano.e, 'doble', 1), 'en_norma': True, 'costo': 0.0}
        return {**resultado(plano.e, 'doble', 1), 'en_norma': False}
    return evaluar


def test_aplicar_sella_mide_y_decide(tmp_path, capsys, monkeypatch):
    """074:RF-6 / 074:RF-13 / 074:RF-14 — sella antes de medir; pasa deja la orden y archivar, su medida sin integrarla."""
    import convertersmartgrid.adaptadores.madrl_politica as mp
    from convertersmartgrid.adaptadores.madrl_puerta import huella_fichero

    puerta = cargar_herramienta('madrl_puerta.py', tools_en_path=True)
    entrenar = cargar_herramienta('madrl_entrenar.py', tools_en_path=True)
    vista, nueva = tmp_path / 'entreno.json', tmp_path / 'nueva.json'
    vista.write_text(json.dumps(_sistema(('ALIM_A', 'ALIM_B'))), encoding='utf-8')
    nueva.write_text(json.dumps(_sistema(('ALIM_C',), carga=0.01)), encoding='utf-8')     # la referencia queda en norma
    modelo = tmp_path / 'modelo'
    modelo.mkdir()
    (modelo / 'politica.pt').write_bytes(b'pesos')
    manifiesto = manifiesto_modelo(politica='gatv2', ocultas=8, cabezas=1, parametros=P,
                                   entrenamiento=[red_declarada('entreno.json', _sistema(('ALIM_A', 'ALIM_B')))],
                                   huella_pesos=huella_fichero(modelo / 'politica.pt'))
    (modelo / 'modelo.json').write_text(json.dumps(manifiesto), encoding='utf-8')
    # MaskablePPO no se guarda para redes no vistas: sale antes de entrenar.
    assert entrenar.main(['--grafo', str(vista), '--tension-min', '0.95', '--tension-max', '1.05', '--carga-max', '100',
                          '--banco-mvar', '0.3', '--costo-banco', '10', '--dispositivo', 'cpu',
                          '--modelo-salida', str(tmp_path / 'm2')]) == 2
    base = ['aplicar', '--modelo', str(modelo), '--dispositivo', 'cpu', '--generaciones', '3', '--poblacion', '8']
    # Una política que no es GATv2, o pesos que no son los del manifiesto: con la separación sellada, sin medir nada.
    ajeno = tmp_path / 'ajeno'
    ajeno.mkdir()
    (ajeno / 'politica.pt').write_bytes(b'otros')
    (ajeno / 'modelo.json').write_text(json.dumps(manifiesto), encoding='utf-8')
    assert puerta.main([*base[:1], '--modelo', str(ajeno), *base[3:], '--no-vistos', str(nueva),
                        '--salida', str(tmp_path / 'otros')]) == 2
    assert (tmp_path / 'otros' / SEPARACION).exists() and not (tmp_path / 'otros' / 'informe.json').exists()
    (ajeno / 'modelo.json').write_text(json.dumps({**manifiesto, 'politica': 'maskable_ppo'}), encoding='utf-8')
    assert puerta.main([*base[:1], '--modelo', str(ajeno), *base[3:], '--no-vistos', str(nueva),
                        '--salida', str(tmp_path / 'mppo')]) == 2
    assert 'GATv2' in capsys.readouterr().out
    monkeypatch.setattr(puerta, 'cargar_politica', lambda *_a: object())
    monkeypatch.setattr(mp, 'evaluar_politica', _politica_doble(True))
    trabajado = tmp_path / 'trabajado'
    assert puerta.main([*base, '--no-vistos', str(nueva), '--salida', str(trabajado), '--espacio', 'ws1',
                        '--proyecto', 'RED_TRABAJADA']) == 2
    assert not (trabajado / SEPARACION).exists()                       # se rechaza antes de sellar ni medir
    vistos = tmp_path / 'vistos'
    assert puerta.main([*base, '--no-vistos', str(vista), '--salida', str(vistos)]) == 2
    assert not (vistos / SEPARACION).exists()

    salida = tmp_path / 'pasa'
    assert puerta.main([*base, '--no-vistos', str(nueva), '--salida', str(salida), '--espacio', 'ws1',
                        '--proyecto', f'{PREFIJO_PRUEBA}074_C']) == 0
    informe = json.loads((salida / 'informe.json').read_text(encoding='utf-8'))
    sep = json.loads((salida / SEPARACION).read_text(encoding='utf-8'))
    assert informe['decision'] == 'pasa' and informe['sello_separacion'] == sep['sello']
    assert informe['medidas'][0]['referencia']['control'] == 'nsga2_sistema'
    orden = json.loads((salida / 'orden_confirmacion.json').read_text(encoding='utf-8'))
    assert orden['proyecto'] == f'{PREFIJO_PRUEBA}074_C' and orden['feeders'] == ['ALIM_C']
    assert orden['obras'][0]['clase'] == 'condensador' and orden['obras'][0]['alimentador'] == 'ALIM_C'
    orden_valida(orden, sep)
    assert 'Decisión: pasa' in capsys.readouterr().out

    monkeypatch.setattr(mp, 'evaluar_politica', _politica_doble(False))
    archivo = tmp_path / 'archivar'
    assert puerta.main([*base, '--no-vistos', str(nueva), '--salida', str(archivo), '--espacio', 'ws1',
                        '--proyecto', f'{PREFIJO_PRUEBA}074_C']) == 3
    archivado = json.loads((archivo / 'ARCHIVADO.json').read_text(encoding='utf-8'))
    assert archivado['integrado_en_flujo'] is False and not (archivo / 'orden_confirmacion.json').exists()
    assert json.loads((archivo / 'informe.json').read_text(encoding='utf-8'))['decision'] == 'archivar'
    otra = tmp_path / 'otra.json'
    otra.write_text(json.dumps(_sistema(('ALIM_D',), carga=0.01)), encoding='utf-8')
    assert puerta.main([*base, '--no-vistos', str(otra), '--salida', str(archivo)]) == 2     # la separación no cambia
