"""Spec 107 T11 — observaciones del regulador enlazadas con la traza del expediente (107:RF-10)."""
from __future__ import annotations

import pytest

from datos_pit import perfil_b

from convertersmartgrid.dominio.pit.ambito import PitError
from convertersmartgrid.dominio.pit.observaciones import escribir_observaciones, leer_observaciones, registrar


def _referencias(caso):
    """Lo que un expediente expone para enlazar: elementos, casos y celdas con su traza."""
    elementos = {e['id']: {'tipo': e['tipo'], 'titular': e['titular']} for e in caso['elementos']}
    celda = 'cuadro.nuevas!F3'
    traza = {'fuente': {'sha256': 'c' * 64}, 'calculo': 'valorar_obra', 'motor': 'abierto',
             'regla': {'clave': 'pit.cuadro.nuevas', 'estado': 'modificada'}}
    return {'elemento': elementos, 'caso': {f'{caso["anios"][0]}:base': {}}, 'celda': {celda: traza}}, celda


def test_observacion_sobre_una_celda_y_otra_sobre_un_elemento(tmp_path):
    """107:RF-10 — cada observación con número, fecha, texto, respuesta y su objeto, enlazada con la traza."""
    caso = perfil_b(12)
    refs, celda = _referencias(caso)
    elemento = caso['pistas']['compartida']
    obs = registrar([
        {'numero': '2', 'fecha': '2031-02-01', 'texto': 'Sustente la inversión.', 'afecta': 'celda',
         'referencia': celda, 'respuesta': 'Sale del módulo estándar citado.'},
        {'numero': '1', 'fecha': '2031-01-15', 'texto': 'Asigne el elemento compartido.', 'afecta': 'elemento',
         'referencia': elemento, 'respuesta': 'Asignado en el perfil.'},
    ], refs)
    assert [o.numero for o in obs] == ['1', '2']
    assert obs[1].enlace['regla']['clave'] == 'pit.cuadro.nuevas' and obs[1].enlace['motor'] == 'abierto'
    assert obs[0].enlace['titular'] and obs[0].respuesta
    ruta = escribir_observaciones(tmp_path / 'obs.json', obs)
    assert leer_observaciones(ruta, refs) == obs
    assert escribir_observaciones(tmp_path / 'otra.json', obs).read_bytes() == ruta.read_bytes()


@pytest.mark.parametrize('cambio,error', [
    ({'referencia': 'cuadro.inexistente!A1'}, 'no tiene celda'),
    ({'afecta': 'tarifa'}, 'afecta'),
    ({'fecha': '15/01/2031'}, 'AAAA-MM-DD'),
])
def test_observacion_sin_objeto_conocido_es_un_error(cambio, error):
    """107:RF-10 — una observación que no se puede enlazar con el expediente no se registra."""
    caso = perfil_b(12)
    refs, celda = _referencias(caso)
    base = {'numero': '1', 'fecha': '2031-01-15', 'texto': 'x', 'afecta': 'celda', 'referencia': celda}
    with pytest.raises(PitError, match=error):
        registrar([{**base, **cambio}], refs)


# --- Documento de absolución (aclaración de 107:RF-10, T20) ---------------------------------------------------------

def _observaciones(caso, celda):
    elemento = caso['pistas']['compartida']
    return [
        {'numero': '1', 'fecha': '2031-01-15', 'texto': 'Asigne el elemento compartido.', 'afecta': 'elemento',
         'referencia': elemento, 'respuesta': 'Asignado en el perfil.'},
        {'numero': '2', 'fecha': '2031-02-01', 'texto': 'Sustente la inversión.', 'afecta': 'celda',
         'referencia': celda, 'respuesta': 'Sale del módulo estándar citado.'},
    ]


def test_absolucion_con_objeto_respuesta_y_traza_de_lo_que_cambio(tmp_path):
    """107:RF-10 — la absolución cita cada observación con su objeto y su respuesta, y la traza de lo que cambió:
    la celda observada cambió (huella antes y después) y el elemento no, y se dice."""
    import json

    from convertersmartgrid.dominio.pit.observaciones import absolucion, escribir_absolucion

    caso = perfil_b(12)
    antes, celda = _referencias(caso)
    despues = {k: dict(v) for k, v in antes.items()}
    despues['celda'][celda] = {**antes['celda'][celda], 'calculo': 'set_nueva.leer_modulos_pit'}
    doc = absolucion(_observaciones(caso, celda), antes, despues)
    por = {d['numero']: d for d in doc}
    assert [d['numero'] for d in doc] == ['1', '2']
    assert por['2']['cambio']['estado'] == 'cambiado'
    assert por['2']['cambio']['huella_antes'] != por['2']['cambio']['huella_despues']
    assert por['2']['cambio']['despues']['calculo'] == 'set_nueva.leer_modulos_pit'
    assert por['1']['cambio']['estado'] == 'sin_cambios' and 'sin cambios' in por['1']['cambio']['texto']
    assert all(d['respuesta'] and d['afecta'] and d['referencia'] for d in doc)
    ruta = escribir_absolucion(tmp_path / 'absolucion.json', _observaciones(caso, celda), antes, despues)
    assert json.loads(ruta.read_text(encoding='utf-8')) == doc
    otra = escribir_absolucion(tmp_path / 'otra.json', list(reversed(_observaciones(caso, celda))), antes, despues)
    assert otra.read_bytes() == ruta.read_bytes()


def test_absolucion_de_un_objeto_retirado_del_expediente(tmp_path):
    """107:RF-10 — si lo observado ya no está en el expediente, la absolución lo dice: no se calla ni se inventa."""
    from convertersmartgrid.dominio.pit.observaciones import absolucion

    caso = perfil_b(12)
    antes, celda = _referencias(caso)
    despues = {**antes, 'celda': {}}
    doc = {d['numero']: d for d in absolucion(_observaciones(caso, celda), antes, despues)}
    assert doc['2']['cambio']['estado'] == 'retirado' and doc['2']['cambio']['despues'] is None


@pytest.mark.parametrize('cambio,error', [
    ({'referencia': 'cuadro.inexistente!A1'}, 'no tiene celda'),
    ({'respuesta': '  '}, 'sin respuesta'),
])
def test_absolucion_sin_objeto_conocido_o_sin_respuesta_es_un_error(cambio, error):
    """107:RF-10 — una absolución con una referencia desconocida, o sin respuesta, no se emite."""
    from convertersmartgrid.dominio.pit.observaciones import absolucion

    caso = perfil_b(12)
    antes, celda = _referencias(caso)
    obs = _observaciones(caso, celda)
    obs[1] = {**obs[1], **cambio}
    with pytest.raises(PitError, match=error):
        absolucion(obs, antes, antes)


# --- Forma oficial del documento de respuestas (107:RF-10, P14) ------------------------------------------------------
# Datos sintéticos: un oficio inventado, sin empresa ni área reales.

def _oficio():
    """Un oficio con las generales y las específicas mezcladas y una numeración que no se ordena como texto."""
    return {'referencia': 'Oficio sintético 0001', 'observaciones': [
        {'numero': '2.1', 'tipo': 'especifica', 'texto': 'Complete el formato de demanda.'},
        {'numero': '1.2', 'tipo': 'general', 'texto': 'Cubra todo el horizonte.'},
        {'numero': '1.10', 'tipo': 'general', 'texto': 'Relacione los documentos de sustento.'},
        {'numero': '2.2', 'tipo': 'especifica', 'texto': 'Georreferencie la SET nueva.'},
    ]}


def _respuestas():
    return [
        {'numero': '2.2', 'respuesta': 'Georreferenciada en el plano.',
         'correcciones': [{'seccion': 'Volumen III, folio 040'}]},
        {'numero': '1.10', 'respuesta': 'Relación añadida.',
         'correcciones': [{'fichero': 'sustento.xlsx', 'celda': 'Relacion!B4'}]},
        {'numero': '1.2', 'respuesta': 'Horizonte completo.',
         'correcciones': [{'fichero': 'demanda.xlsx', 'celda': 'F-100!C7', 'huella': 'a' * 64}]},
        {'numero': '2.1', 'respuesta': 'Formato completado.', 'correcciones': [{'seccion': 'Sección 5.7'}]},
    ]


def _planas(doc):
    return [o for s in doc['secciones'] for o in s['observaciones']]


def test_documento_absolucion_conserva_numeracion_y_orden_generales_primero(tmp_path):
    """107:RF-10 — las respuestas siguen la organización y la secuencia del oficio: las generales primero y, dentro de
    cada clase, el orden del oficio con su número literal (1.2 antes que 1.10); el orden en que llegan las respuestas
    no cambia el documento."""
    from convertersmartgrid.dominio.pit.observaciones import documento_absolucion, escribir_documento_absolucion

    doc = documento_absolucion(_oficio(), _respuestas())
    assert [s['tipo'] for s in doc['secciones']] == ['general', 'especifica']
    assert [o['numero'] for o in _planas(doc)] == ['1.2', '1.10', '2.1', '2.2']
    assert doc['secciones'][0]['titulo'] == 'Observaciones generales'
    assert [o['texto'] for o in _planas(doc)][0] == 'Cubra todo el horizonte.'
    assert doc['oficio'] == 'Oficio sintético 0001' and doc['huecos'] == []
    ruta = escribir_documento_absolucion(tmp_path / 'a.json', _oficio(), _respuestas())
    otra = escribir_documento_absolucion(tmp_path / 'b.json', _oficio(), list(reversed(_respuestas())))
    assert ruta.read_bytes() == otra.read_bytes()


def test_documento_absolucion_enlaza_cada_respuesta_con_el_lugar_corregido():
    """107:RF-10 — cada respuesta lleva el lugar corregido del Estudio: la sección, o el fichero y la celda con la
    huella del Estudio corregido; una huella que no es la del fichero se rechaza."""
    from convertersmartgrid.dominio.pit.observaciones import documento_absolucion

    huellas = {'sustento.xlsx': 'b' * 64}
    por = {o['numero']: o for o in _planas(documento_absolucion(_oficio(), _respuestas(), huellas))}
    assert sorted(por) == ['1.10', '1.2', '2.1', '2.2']
    assert por['1.10']['respuesta'] == 'Relación añadida.'
    assert por['1.10']['correcciones'] == [{'seccion': None, 'fichero': 'sustento.xlsx', 'celda': 'Relacion!B4',
                                            'huella': 'b' * 64}]
    assert por['1.2']['correcciones'][0]['huella'] == 'a' * 64
    assert por['2.2']['correcciones'] == [{'seccion': 'Volumen III, folio 040', 'fichero': None, 'celda': None,
                                           'huella': None}]
    malas = _respuestas()
    malas[1] = {**malas[1], 'correcciones': [{'fichero': 'sustento.xlsx', 'celda': 'B4', 'huella': 'c' * 64}]}
    with pytest.raises(PitError, match='no es la del fichero'):
        documento_absolucion(_oficio(), malas, huellas)


def test_documento_absolucion_observacion_sin_respuesta_es_un_hueco_nombrado():
    """107:RF-10 — una observación sin respuesta queda en el documento sin texto inventado y se nombra como hueco, y
    una respuesta a una observación que el oficio no tiene es un error."""
    from convertersmartgrid.dominio.pit.observaciones import documento_absolucion

    respuestas = [r for r in _respuestas() if r['numero'] != '2.1']
    doc = documento_absolucion(_oficio(), respuestas)
    assert [(h['numero'], h['falta']) for h in doc['huecos']] == [('2.1', 'respuesta'), ('2.1', 'lugar corregido')]
    assert 'sin respuesta' in doc['huecos'][0]['texto']
    sola = next(o for o in _planas(doc) if o['numero'] == '2.1')
    assert sola['respuesta'] is None and sola['correcciones'] == []
    with pytest.raises(PitError, match='el oficio no la tiene'):
        documento_absolucion(_oficio(), [*_respuestas(), {'numero': '9.9', 'respuesta': 'x'}])


def test_documento_absolucion_deja_la_evaluacion_del_regulador_vacia_con_su_estructura():
    """107:RF-10 — cada observación trae el sitio de la evaluación del regulador, «Análisis» y «Conclusión», vacío, y
    el documento nombra las conclusiones admitidas (subsanada, parcialmente subsanada, no subsanada)."""
    from convertersmartgrid.dominio.pit.observaciones import documento_absolucion

    doc = documento_absolucion(_oficio(), _respuestas())
    assert doc['conclusiones_admitidas'] == ['subsanada', 'parcialmente subsanada', 'no subsanada']
    assert [o['evaluacion'] for o in _planas(doc)] == [{'analisis': '', 'conclusion': ''}] * 4


def test_documento_absolucion_dice_que_reagrupa_y_nombra_las_observaciones_movidas():
    """107:RF-10 — si el oficio intercala generales y específicas, el documento las reagrupa con las generales primero
    y lo dice literalmente, con la lista de las que se movieron; cada una conserva su número, la referencia del oficio y
    su posición en él. Si el oficio ya venía con las generales primero, la lista va vacía."""
    from convertersmartgrid.dominio.pit.observaciones import documento_absolucion

    doc = documento_absolucion(_oficio(), _respuestas())
    orden = doc.get('orden') or {}
    assert orden.get('criterio') == 'orden del oficio reagrupado: generales primero'
    assert orden.get('movidas') == [
        {'numero': '1.2', 'posicion_oficio': 2, 'posicion_documento': 1},
        {'numero': '1.10', 'posicion_oficio': 3, 'posicion_documento': 2},
        {'numero': '2.1', 'posicion_oficio': 1, 'posicion_documento': 3},
    ]
    assert [(o['numero'], o.get('oficio'), o.get('posicion_oficio')) for o in _planas(doc)] == [
        ('1.2', 'Oficio sintético 0001', 2), ('1.10', 'Oficio sintético 0001', 3),
        ('2.1', 'Oficio sintético 0001', 1), ('2.2', 'Oficio sintético 0001', 4)]
    en_orden = {**_oficio(), 'observaciones': sorted(_oficio()['observaciones'], key=lambda o: o['tipo'] != 'general')}
    sin_mover = documento_absolucion(en_orden, _respuestas()).get('orden') or {}
    assert sin_mover.get('criterio') == 'orden del oficio reagrupado: generales primero'
    assert sin_mover.get('movidas') == []


def test_documento_absolucion_respuesta_sin_lugar_corregido_es_un_hueco_legible():
    """107:RF-10 — una respuesta que no cita el lugar corregido del Estudio se ve como «lugar corregido: no indicado»,
    sin inventar el lugar, y sale en la lista de huecos con campos fijos que el expediente puede leer después."""
    from convertersmartgrid.dominio.pit.observaciones import documento_absolucion

    respuestas = [{**r, 'correcciones': []} if r['numero'] == '1.10' else r for r in _respuestas()]
    doc = documento_absolucion(_oficio(), respuestas)
    assert doc['huecos'] == [{'documento': 'absolucion', 'oficio': 'Oficio sintético 0001', 'numero': '1.10',
                              'tipo': 'general', 'falta': 'lugar corregido',
                              'texto': 'observación 1.10: lugar corregido: no indicado'}]
    sin_lugar = [o for o in _planas(doc) if o['numero'] == '1.10']
    assert [(o['respuesta'], o['correcciones'], o.get('lugar_corregido')) for o in sin_lugar] == [
        ('Relación añadida.', [], 'no indicado')]
    con_lugar = {o['numero']: o.get('lugar_corregido') for o in _planas(doc) if o['numero'] != '1.10'}
    assert con_lugar == {'1.2': 'demanda.xlsx F-100!C7', '2.1': 'Sección 5.7', '2.2': 'Volumen III, folio 040'}
