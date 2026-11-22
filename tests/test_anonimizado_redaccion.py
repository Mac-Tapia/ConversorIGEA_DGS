"""072:RF-63 a RF-66 — lo que halló la ratificación del 2026-11-22 en el anonimizado del corpus de redacción.

Códigos con guion o subrayado ocultos enteros, nombres con variantes (plural, errata, codificación rota, lugares), el
encabezado de la página fuera del sellado y las salidas con un prefijo de sede o un nombre residual rechazadas. Sin GPU y
con nombres inventados (072:RF-20): ninguno es de una red real.
"""
from __future__ import annotations

import json

import pytest

from convertersmartgrid.aplicacion.asistente import corpus_redaccion as cr

CATALOGO = {'empresa': ['Electro Ficticia'], 'instalacion': ['Villa Quimera', 'Ñandulce']}
ENCABEZADO = 'Primer Informe del PIDE de Electro Ficticia – Diciembre 2025 \n \n \nPágina 14 de 210 \n \n'


def _atributos(*nombres):
    faltan = [n for n in nombres if not hasattr(cr, n)]
    assert not faltan, f'faltan {faltan} en corpus_redaccion'
    return [getattr(cr, n) for n in nombres]


def test_los_codigos_con_guion_o_subrayado_se_ocultan_enteros():
    """072:RF-63 — «TA-201», «CMC_1» y «TD_SM» quedan ‹código› entero; un guion entre palabras o entre cifras, no."""
    texto = cr.sin_cifras('El tramo TA-201, la celda CMC_1 y el proyecto TD_SM; Breusch-Pagan; teórico-práctico; '
                          'periodo 2026-2030.')
    assert texto == ('El tramo ‹código›, la celda ‹código› y el proyecto ‹código›; Breusch-Pagan; teórico-práctico; '
                     'periodo ‹n›-‹n›.')
    assert 'YUS' not in cr.sin_cifras('El alimentador YUS_‹n› y el TA-‹código›.')
    assert cr.sin_cifras('El alimentador YUS_‹n›.') == 'El alimentador ‹código›.'


def test_el_catalogo_cubre_plural_errata_y_codificacion_rota():
    """072:RF-64 — un nombre del catálogo se oculta en plural, con otra letra final, sin tildes y mal codificado."""
    for texto in ('las Villa Quimeras', 'la Villa Quimero', 'la VILLA QUIMERA', 'el ÐANDULCE', 'el Ã‘andulce',
                  'el Nandulce', 'el ñandulce'):
        oculto = cr.sin_nombres(texto, CATALOGO)
        assert '‹instalación›' in oculto and 'uimer' not in oculto and 'andulce' not in oculto, (texto, oculto)
    assert cr.sin_nombres('La villa queda lejos.', CATALOGO) == 'La villa queda lejos.'


def test_rios_provincias_y_localidades_se_ocultan_y_el_corpus_los_recoge():
    """072:RF-64 — lo que sigue a un río, una provincia o una localidad se oculta, y el nombre recogido de un fragmento
    se oculta también donde sale solo; una palabra común no se recoge."""
    assert cr.sin_nombres('El río Aguaclara y la provincia de Monte Bruma.') == \
        'El río ‹nombre› y la provincia de ‹nombre›.'
    frags = [{'empresa': 'Electro Ficticia', 'text': 'La SET Puerto Imaginario atiende el distrito de Monte Bruma.'},
             {'empresa': 'Electro Ficticia', 'text': 'La zonal de Distribución revisa la distribución de la carga.'}]
    catalogo = cr.catalogo_del_corpus(frags)
    assert 'Puerto Imaginario' in catalogo.get('instalacion', []) and 'Monte Bruma' in catalogo.get('nombre', [])
    assert 'Distribución' not in sum(catalogo.values(), [])
    assert cr.sin_nombres('La línea llega a Puerto Imaginario y a Monte Bruma.', catalogo) == \
        'La línea llega a ‹instalación› y a ‹nombre›.'


def test_el_encabezado_de_la_pagina_no_entra_en_el_sellado(tmp_path):
    """072:RF-65 — «Informe … – Mes ‹n›» y «Página ‹n› de ‹n›» se quitan al sellar; un fragmento que solo los trae no
    entra y se cuenta; la validación rechaza un ejemplo que aún los lleve."""
    sin_encabezado, = _atributos('sin_encabezado')
    anonimo = cr.sin_cifras(ENCABEZADO + 'Figura 3: Contraste de la prueba.', CATALOGO)
    assert sin_encabezado(anonimo) == 'Figura ‹n›: Contraste de la prueba.'
    carpeta = tmp_path / 'pide'
    carpeta.mkdir()
    temas = ('la demanda', 'las pérdidas', 'la confiabilidad', 'los costos', 'el crecimiento', 'las obras',
             'la tensión', 'los criterios', 'la calidad', 'el horizonte')
    frags = [{'record_id': f'r{d}', 'empresa': 'Electro Ficticia', 'relative_path': f'PIDE X/{d}.pdf',
              'location': 'page', 'periodo': '2026', 'text': ENCABEZADO + f'En este capítulo se describe {t}.'}
             for d, t in enumerate(temas)]
    frags.append({'record_id': 'solo', 'empresa': 'Electro Ficticia', 'relative_path': 'PIDE X/0.pdf',
                  'location': 'page', 'periodo': '2026', 'text': ENCABEZADO})
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    for f in frags:
        cr.registrar_revision(carpeta / 'revision_redaccion.jsonl', f, revisor='revisor de prueba', origen='maestro',
                              aprobado=True, uso='redaccion', fecha='2026-11-22')
    meta = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'sellado', catalogo=CATALOGO)
    filas = json.loads((tmp_path / 'sellado' / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    assert len(filas) == 10 and not any('Página' in f['respuesta'] or 'Diciembre' in f['respuesta'] for f in filas)
    assert meta.get('solo_encabezado_omitidos') == 1 and meta.get('sin_encabezado') is True
    from convertersmartgrid.aplicacion.evaluacion_modelos import huella
    fila = dict(filas[0], respuesta='Página ‹n› de ‹n›\n' + filas[0]['respuesta'])
    fila['record_id'] = huella({k: v for k, v in fila.items() if k != 'record_id'})
    nuevas = [fila, *filas[1:]]
    with pytest.raises(ValueError, match='encabezado'):
        cr.validar_corpus_redaccion(nuevas, {**meta, 'dataset_hash': huella(nuevas)})


def test_una_salida_con_prefijo_de_sede_o_nombre_residual_se_rechaza():
    """072:RF-66 — «TA-‹n›» deja a la vista la sigla de la sede y «Villa Quimeras», el nombre en plural: no valen."""
    instruccion = 'Redacta un párrafo de un informe PIDE, claro y formal.'
    assert cr.revisar_salida(instruccion, 'El tramo TA-‹n› atiende la demanda.') == ['código']
    assert cr.revisar_salida(instruccion, 'El tramo TA-201 atiende la demanda.') == ['código']
    assert cr.revisar_salida(instruccion, 'Las Villa Quimeras atienden la demanda.', CATALOGO) == ['nombre']
    assert cr.revisar_salida(instruccion, 'El ‹código› atiende la demanda de la ‹instalación›.', CATALOGO) == []


def test_el_sellado_anterior_se_comprueba_por_sus_huellas(tmp_path):
    """072:RF-67 — un sellado anterior que con las reglas de hoy dejaría un prefijo a la vista sirve para sustituirlo;
    uno alterado, no."""
    import inspect
    from convertersmartgrid.aplicacion.evaluacion_modelos import huella
    assert 'anterior' in inspect.signature(cr.sellar_corpus_redaccion).parameters
    carpeta = tmp_path / 'pide'
    carpeta.mkdir()
    temas = ('la demanda', 'las pérdidas', 'la confiabilidad', 'los costos', 'el crecimiento', 'las obras',
             'la tensión', 'los criterios', 'la calidad', 'el horizonte')
    frags = [{'record_id': f'r{d}', 'empresa': 'Electro Ficticia', 'relative_path': f'PIDE X/{d}.docx',
              'location': 'document', 'periodo': '2026', 'text': f'En este capítulo se describe {t}.'}
             for d, t in enumerate(temas)]
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    for f in frags:
        cr.registrar_revision(carpeta / 'revision_redaccion.jsonl', f, revisor='revisor de prueba', origen='maestro',
                              aprobado=True, uso='redaccion', fecha='2026-11-22')
    cr.sellar_corpus_redaccion(carpeta, tmp_path / 'v1', catalogo=CATALOGO)
    # Lo que habría sellado el anonimizado de antes: un prefijo de sede a la vista, con las huellas en regla.
    auditoria = tmp_path / 'v1' / 'corpus_auditoria.json'
    manifiesto = tmp_path / 'v1' / 'dataset_manifest.json'
    filas = json.loads(auditoria.read_text(encoding='utf-8'))
    filas[0] = dict(filas[0], respuesta=filas[0]['respuesta'] + ' Tramo YUS_‹n›.')
    filas[0]['record_id'] = huella({k: v for k, v in filas[0].items() if k != 'record_id'})
    meta = json.loads(manifiesto.read_text(encoding='utf-8'))
    auditoria.write_text(json.dumps(filas, ensure_ascii=False), encoding='utf-8')
    manifiesto.write_text(json.dumps({**meta, 'dataset_hash': huella(filas)}, ensure_ascii=False), encoding='utf-8')
    nuevo = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'v2', catalogo=CATALOGO, anterior=tmp_path / 'v1')
    assert nuevo['sustituye_a']['dataset_hash_anterior'] == huella(filas)
    manifiesto.write_text(json.dumps({**meta, 'dataset_hash': 'otra'}, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError, match='íntegro'):
        cr.sellar_corpus_redaccion(carpeta, tmp_path / 'v3', catalogo=CATALOGO, anterior=tmp_path / 'v1')


_A = ('la demanda', 'la pérdida', 'la tensión', 'el costo', 'la obra', 'el criterio', 'la red', 'el tramo',
      'la carga', 'el plazo')
_B = ('la zona norte', 'la zona sur', 'el área rural', 'el área urbana', 'el sistema aislado', 'la costa',
      'la sierra', 'la selva')


def test_un_documento_muy_grande_se_reparte_por_tramos_seguidos(tmp_path):
    """072:RF-68 — si un documento pasa de la décima parte del total, se parte en tramos seguidos y cada uno va entero
    a una partición: selección y prueba llegan a su décima parte aunque casi todo venga de un solo informe."""
    tramos, = _atributos('tramos_de_documentos')
    carpeta = tmp_path / 'pide'
    carpeta.mkdir()
    frags = [{'record_id': f'g{k:02d}', 'empresa': 'Electro Ficticia', 'relative_path': 'PIDE X/grande.docx',
              'location': f'paragraph:{k}', 'periodo': '2026', 'text': f'Se describe {_A[k % 10]} de {_B[k // 10]} en el informe principal.'}
             for k in range(80)]
    frags += [{'record_id': f'p{d}', 'empresa': 'Electro Ficticia', 'relative_path': f'PIDE X/menor{d}.docx',
               'location': 'paragraph:0', 'periodo': '2026', 'text': f'Nota breve del anexo sobre {_B[d]}.'}
              for d in range(4)]
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    for f in frags:
        cr.registrar_revision(carpeta / 'revision_redaccion.jsonl', f, revisor='revisor de prueba', origen='maestro',
                              aprobado=True, uso='redaccion', fecha='2026-11-22')
    meta = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'sellado', catalogo=CATALOGO)
    total = sum(meta['por_particion'].values())
    assert total == 84
    for parte in ('seleccion', 'prueba'):
        assert meta['por_particion'].get(parte, 0) >= total // 10, meta['por_particion']
    filas = json.loads((tmp_path / 'sellado' / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    orden = {f['record_id']: i for i, f in enumerate(frags)}
    por_grupo: dict = {}
    for f in filas:
        por_grupo.setdefault(f['group_id'], []).append(orden[f['fragmento']])
    for indices in por_grupo.values():       # cada tramo es un trozo seguido del documento
        assert sorted(indices) == list(range(min(indices), max(indices) + 1))
    assert len({f['particion'] for f in filas if f['fragmento'].startswith('g')}) > 1
    assert len(set(tramos(['a', 'b', 'c']))) == 3          # con menos de cuatro documentos no se parte nada
