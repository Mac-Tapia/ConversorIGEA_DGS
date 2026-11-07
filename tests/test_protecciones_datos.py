"""Spec 049, T1: disponibilidad real del estudio de protecciones e inventario de sus entradas.

Ninguna fuente trae protecciones hoy (el TXT solo la fila DEFAULT con poder de corte 0): lo
honesto es bloquear con la lista concreta de lo que falta. Dispositivos, versiones y perfiles
sorteados; ninguna curva ni ajuste de una empresa (constitución P13).
"""

from __future__ import annotations

import random

import pytest
from openpyxl import Workbook

from convertersmartgrid import datos_empresa as de
from convertersmartgrid import estudios_pf as ep
from convertersmartgrid import protecciones as pr

SEMILLAS = [random.randrange(10**6) for _ in range(4)]


def _dispositivo(rng, i, clase=None):
    """Un dispositivo completo según el contrato, con cifras sorteadas."""
    clase = clase or rng.choice(sorted(pr.CLASES))
    d = {'id': f'D{i}_{rng.randrange(999)}', 'cubiculo': f'C{i}', 'clase': clase,
         'fabricante': f'FAB{rng.randrange(99)}', 'modelo': f'M{rng.randrange(99)}',
         'curva': rng.choice(['IEC NI', 'IEEE VI', 'K', 'T']),
         'arranque': round(rng.uniform(5, 400), 2), 'unidad_arranque': 'A',
         'poder_corte_ka': round(rng.uniform(2, 25), 2), 'fuente': f'ficha {rng.randrange(999)}'}
    if clase in pr.CON_DIAL:
        d.update(dial=round(rng.uniform(0.05, 1.0), 3), unidad_dial=rng.choice(sorted(pr.UNIDADES_DIAL)))
    if rng.random() < 0.5 and clase in pr.CON_DIAL:
        d.update(unidad_arranque='A sec', arranque=round(rng.uniform(0.5, 5), 2),
                 ct_primario_a=rng.choice([100, 200, 400, 600]), ct_secundario_a=rng.choice([1, 5]))
    return d


def _capacidades(rng, version='24.0.1', clases=('ElmRelay', 'RelFuse'), nombres=()):
    """Lo que dejaría el modo de capacidades del guion con todo comprobado."""
    comandos = {c: {'existe': True, 'ejecuta': True if c in pr.LICENCIA_PREVIA else None,
                    'metodos': {m: True for m in pr.METODOS_REQUERIDOS.get(c, ())}}
                for c in pr.COMANDOS_REQUERIDOS}
    comandos['ComShc']['atributos'] = {a: True for a in pr.ATRIBUTOS_COMSHC.values()}
    return {'version': version, 'caso': 'Sin proyecto',
            'comandos': comandos,
            'clases': {c: {'cuantos': max(1, len(nombres)), 'nombres': sorted(nombres)} for c in clases}}


def _perfil(rng):
    return {'protecciones': {'cti_s': round(rng.uniform(0.2, 0.4), 2),
                             'factor_sensibilidad': round(rng.uniform(1.5, 2.5), 2),
                             'margen_poder_corte': round(rng.uniform(1.0, 1.3), 2)}}


def _completo(rng):
    disp = [_dispositivo(rng, i) for i in range(rng.randint(2, 6))]
    inventario = {'dispositivos': disp, 'impedancia_real': True}
    return inventario, _capacidades(rng, nombres=[d['id'] for d in disp]), _perfil(rng)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_con_todo_comprobado_el_estudio_esta_disponible(semilla):
    """049:RF-1, 049:RF-2 — dispositivos completos, capacidades comprobadas en la versión
    conectada y criterios del perfil: disponible, sin faltas ni bloqueos, con su alcance."""
    rng = random.Random(semilla)
    inventario, capacidades, perfil = _completo(rng)
    d = pr.disponibilidad_protecciones(inventario, capacidades, perfil)
    assert d['disponible'], d
    assert d['faltan'] == [] and d['bloqueos'] == []
    assert sorted(d['alcance']['dispositivos']) == sorted(x['id'] for x in inventario['dispositivos'])
    assert d['alcance']['version'] == capacidades['version']
    assert d['criterios'] == perfil['protecciones']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_sin_curvas_o_licencia_bloquea(semilla):
    """049:RF-1, 049:RF-2 — la orden presente sin módulo licenciado bloquea, y sin capacidades
    comprobadas tampoco se supone nada; cada ausencia se nombra en concreto."""
    rng = random.Random(semilla)
    inventario, capacidades, perfil = _completo(rng)
    # Sin comprobar nada en DIgSILENT.
    d = pr.disponibilidad_protecciones(inventario, {}, perfil)
    assert not d['disponible'] and any('comprob' in b for b in d['bloqueos'])
    # La orden está, pero DIgSILENT la rechazó por licencia.
    capacidades['comandos']['ComShc']['ejecuta'] = False
    d = pr.disponibilidad_protecciones(inventario, capacidades, perfil)
    assert not d['disponible'] and any('licencia' in b and 'ComShc' in b for b in d['bloqueos'])
    # Sin curva ni ajuste: se dice de qué dispositivo y qué campo.
    capacidades['comandos']['ComShc']['ejecuta'] = True
    victima = rng.choice(inventario['dispositivos'])
    victima.pop('curva')
    victima['arranque'] = None
    d = pr.disponibilidad_protecciones(inventario, capacidades, perfil)
    assert not d['disponible']
    propias = [f for f in d['faltan'] if victima['id'] in f]
    assert any('curva' in f for f in propias) and any('arranque' in f for f in propias)
    assert victima['id'] not in d['alcance']['dispositivos']
    # Sin ningún dispositivo: es lo de hoy con cualquier fuente.
    d = pr.disponibilidad_protecciones({'dispositivos': []}, capacidades, perfil)
    assert any('dispositivo' in f for f in d['faltan'])
    assert any('cortocircuito' in f for f in d['faltan'])        # impedancia por defecto


def test_default_no_es_ficha_real():
    """049:RF-2 — la fila DEFAULT con poder de corte 0 del TXT no habilita el estudio: se dice
    que la fuente solo trae eso, en vez de contarla como ficha."""
    rng = random.Random(3)
    tablas = {t: {'DEFAULT': {'ID': 'DEFAULT', 'InterruptingRating': rng.choice([0, '0', None])}}
              for t in ('FUSE', 'RECLOSER', 'BREAKER', 'RELAY')}
    assert all(pr.es_fila_por_defecto(f) for t in tablas.values() for f in t.values())
    assert not pr.es_fila_por_defecto({'ID': 'F_12K', 'InterruptingRating': 8.0})
    inventario = pr.inventario_protecciones(None, tablas_fuente=tablas)
    assert inventario['dispositivos'] == []
    d = pr.disponibilidad_protecciones(inventario, _capacidades(rng), _perfil(rng))
    assert not d['disponible']
    assert any('DEFAULT' in f and 'poder de corte' in f for f in d['faltan'])
    # Un dispositivo del libro con poder de corte cero tampoco es una ficha real.
    disp = _dispositivo(rng, 1)
    disp['poder_corte_ka'] = 0
    d = pr.disponibilidad_protecciones({'dispositivos': [disp], 'impedancia_real': True},
                                       _capacidades(rng, nombres=[disp['id']]), _perfil(rng))
    assert any(disp['id'] in f and 'poder de corte' in f for f in d['faltan'])


def test_capacidad_por_version():
    """049:RF-1 — una función que se anuncia para PowerFactory 2026 no se supone en 2024 ni en
    2025: solo vale lo que el modo de capacidades comprobó en la versión conectada."""
    rng = random.Random(9)
    inventario, _cap, perfil = _completo(rng)
    inventario['funciones'] = ['ComNueva2026']
    for version in ('24.0.1', '25.0.3'):
        capacidades = _capacidades(rng, version=version, nombres=[d['id'] for d in inventario['dispositivos']])
        capacidades['anunciadas'] = {'ComNueva2026': '2026'}     # lo que dice la web del fabricante
        d = pr.disponibilidad_protecciones(inventario, capacidades, perfil)
        assert not d['disponible']
        assert any('ComNueva2026' in b and version in b for b in d['bloqueos'])
    capacidades['comandos']['ComNueva2026'] = {'existe': True, 'ejecuta': True, 'metodos': {}}
    assert pr.disponibilidad_protecciones(inventario, capacidades, perfil)['disponible']
    # Un método documentado que la versión conectada no tiene también bloquea.
    capacidades['comandos']['ComShctrace']['metodos']['GetDeviceTime'] = False
    d = pr.disponibilidad_protecciones(inventario, capacidades, perfil)
    assert any('GetDeviceTime' in b for b in d['bloqueos'])


def test_dispositivo_sin_modelo_en_el_proyecto_y_criterios_del_perfil():
    """049:RF-1, 049:RF-2 — un dispositivo del libro que no está en el proyecto, una clase sin
    modelar y un criterio que el perfil no da se nombran; sin perfil no se supone ningún CTI."""
    rng = random.Random(21)
    inventario, capacidades, perfil = _completo(rng)
    falta = inventario['dispositivos'][0]['id']
    capacidades['clases'] = {c: {'cuantos': v['cuantos'], 'nombres': [n for n in v['nombres'] if n != falta]}
                             for c, v in capacidades['clases'].items()}
    del perfil['protecciones']['cti_s']
    d = pr.disponibilidad_protecciones(inventario, capacidades, perfil)
    assert any(falta in f and 'proyecto' in f for f in d['faltan'])
    assert any('protecciones.cti_s' in f for f in d['faltan'])
    assert 'cti_s' not in d['criterios']
    d = pr.disponibilidad_protecciones(inventario, {**capacidades, 'clases': {}}, {})
    assert any('ElmRelay' in b or 'RelFuse' in b for b in d['bloqueos'])
    assert d['criterios'] == {}
    with pytest.raises(pr.ProteccionesError, match='cti_s'):
        pr.criterios_de_perfil({'protecciones': {'cti_s': -0.3}})


# --------------------------------------------------------------------------- libro (RF-3)
def _hoja(ruta, filas, *, unidades=None, sin_hojas=()):
    wb = Workbook()
    wb.remove(wb.active)
    for hoja in de.HOJAS:
        if hoja.clave in sin_hojas:
            continue
        ws = wb.create_sheet(hoja.titulo)
        ws.append([c.titulo for c in hoja.columnas])
        ws.append((unidades or {}).get(hoja.clave) or [c.unidad for c in hoja.columnas])
        if hoja.clave == 'tiempos':
            ws.append([de.TIEMPOS['localizacion'], 10])
            ws.append([de.TIEMPOS['manual'], 20])
        if hoja.clave == 'costes':
            ws.append([de.COSTES['descuento'], 10, '%'])
        if hoja.clave == 'protecciones':
            for f in filas:
                ws.append(f)
    wb.save(ruta)
    return ruta


def _fila(d):
    titulos = [c.clave for c in de.POR_CLAVE['protecciones'].columnas]
    valores = {**d, 'clase': pr.CLASES[d['clase']], 'respalda_a': ';'.join(d.get('respalda_a') or ())}
    return [valores.get(k) for k in titulos]


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_ajuste_importado_conserva_modelo_unidades_y_procedencia(tmp_path, semilla):
    """049:RF-3 — cada ajuste del libro conserva fabricante, modelo, unidades y de qué hoja y
    fila sale; vuelve igual del plan guardado con el proyecto."""
    rng = random.Random(semilla)
    disp = [_dispositivo(rng, i) for i in range(rng.randint(1, 5))]
    disp[-1]['respalda_a'] = [disp[0]['id']]
    libro = de.leer_libro(_hoja(tmp_path / 'l.xlsx', [_fila(d) for d in disp]))
    assert len(libro.protecciones) == len(disp)
    for n, (leido, d) in enumerate(zip(libro.protecciones, disp), start=3):
        for k in ('id', 'clase', 'fabricante', 'modelo', 'curva', 'unidad_arranque', 'fuente'):
            assert leido[k] == d[k], k
        assert leido['arranque'] == pytest.approx(d['arranque'])
        assert leido.get('unidad_dial') == d.get('unidad_dial')
        assert leido['origen'] == f'l.xlsx, hoja «Protecciones», fila {n}'
    assert libro.protecciones[-1]['respalda_a'] == [disp[0]['id']]
    assert de.Libro.desde_dict(libro.a_dict()) == libro
    inventario = pr.inventario_protecciones(libro)
    assert [d['id'] for d in inventario['dispositivos']] == [d['id'] for d in disp]


def test_unidad_incompatible_del_libro_se_rechaza_con_hoja_y_fila(tmp_path):
    """049:RF-3 — una unidad que el contrato no admite se rechaza nombrando hoja, fila y
    columna, en vez de guardarse con otra magnitud."""
    rng = random.Random(4)
    d = _dispositivo(rng, 1, clase='rele')
    d['unidad_dial'] = 'ms'
    with pytest.raises(de.DatosEmpresaError) as e:
        de.leer_libro(_hoja(tmp_path / 'l.xlsx', [_fila(d)]))
    assert any('Protecciones' in x and 'fila 3' in x and 'ms' in x for x in e.value.errores)
    # Sin la hoja, el libro se lee y avisa: solo el estudio de protecciones queda sin datos.
    libro = de.leer_libro(_hoja(tmp_path / 'm.xlsx', [], sin_hojas=('protecciones',)))
    assert libro.protecciones == [] and any('Protecciones' in a for a in libro.avisos)


def test_el_catalogo_de_estudios_dice_lo_concreto_que_falta():
    """049:RF-2 — en el catálogo de estudios, protecciones sale no ofrecido con la lista
    concreta (dispositivos, comprobación de DIgSILENT, criterios del perfil), no solo «faltan
    curvas»; los demás estudios no cambian."""
    no = {o['clave']: o for o in ep.estudios_no_ofrecidos()}
    falta = no['protecciones']['falta']
    assert any('dispositivo' in f for f in falta)
    assert any('comprob' in f for f in falta)
    assert any('protecciones.cti_s' in f for f in falta)
    assert no['protecciones']['motivo'].startswith('faltan datos')
    assert 'protecciones' not in {e.clave for e in ep.estudios_ofrecidos()}
    assert no['cortocircuito']['falta']
