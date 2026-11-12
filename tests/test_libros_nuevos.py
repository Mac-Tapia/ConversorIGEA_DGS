"""Spec 104: los libros nuevos de demanda se reconocen, se verifican y se avisan solos; el mes de cada libro."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from convertersmartgrid import demanda_medida as dm
from test_pronostico_demanda import _libro_clientes, _libro_dia_hora, _serie, _suministros

PASO = timedelta(minutes=15)


def _mes_completo(anio: int, mes: int, base: float = 30.0, ruido: int = 0):
    """Del día 1 a las 00:15 hasta el día 1 del mes siguiente a las 00:00, como los libros reales."""
    inicio = datetime(anio, mes, 1, 0, 15)
    fin = datetime(anio + (mes == 12), mes % 12 + 1, 1)
    return _serie(((fin - inicio) / PASO + 1) / 96, base, inicio=inicio, ruido=ruido)


# --------------------------------------------------------------------------- mes de los libros
def test_carpeta_del_anio_elegida_da_el_mes_de_cada_nombre(tmp_path):
    """104:RF-27, 104:RF-28 — «0125 Pulso e», «1025 Pulso» y «0526clientesImportantes» reciben su mes con la
    carpeta de su año elegida directamente; antes quedaban sin mes."""
    anio25 = tmp_path / '2025'
    _libro_dia_hora(anio25 / '0125 Pulso e.xlsx', {'111': 2})
    _libro_dia_hora(anio25 / '1025 Pulso.xlsx', {'111': 2})
    anio26 = tmp_path / '2026'
    _libro_clientes(anio26 / '0526clientesImportantes.xlsx', {'111': _mes_completo(2026, 5)})

    c25 = {x.nombre: (x.mes, x.anio, x.activo) for x in dm.catalogar_libros_clientes(anio25, None)}
    assert c25 == {'0125 Pulso e.xlsx': ('2025-01', 2025, True), '1025 Pulso.xlsx': ('2025-10', 2025, True)}
    (libro,) = dm.catalogar_libros_clientes(anio26, None)
    assert (libro.mes, libro.anio, libro.origen_mes) == ('2026-05', 2026, 'nombre')


def test_sin_carpeta_de_anio_el_mes_del_nombre_con_el_anio_de_sus_fechas(tmp_path):
    """104:RF-28 — sin año de carpeta: el mes del nombre cuyo año dan sus fechas, si ese mes está entre ellas."""
    carpeta = tmp_path / 'clientes'
    _libro_clientes(carpeta / '0526clientesImportantes.xlsx', {'111': _mes_completo(2026, 5)})
    (libro,) = dm.catalogar_libros_clientes(carpeta, None)
    assert (libro.mes, libro.origen_mes, libro.activo) == ('2026-05', 'contenido', True)


def test_libro_sin_mes_deducible_se_dice(tmp_path):
    """104:RF-29 — un libro «día, hora» sin mes en el nombre ni año de carpeta no se calla."""
    carpeta = tmp_path / 'clientes'
    _libro_dia_hora(carpeta / 'Pulso.xlsx', {'111': 1})
    (libro,) = dm.catalogar_libros_clientes(carpeta, None)
    assert libro.mes is None
    assert any('no se reconoce su mes' in a and 'día, hora' in a for a in libro.avisos), libro.avisos


# --------------------------------------------------------------------------- verificación de un libro
def _copia_al_mes(curva, anio: int, mes: int):
    """Los valores de ``curva`` en el mismo día y hora de otro mes: el libro de abril de 2026 que repetía marzo."""
    por_clave = {(t.day, t.hour, t.minute): (p, q) for t, p, q in curva}
    destino = _mes_completo(anio, mes)
    return [(t, *por_clave.get((t.day, t.hour, t.minute), (p, q))) for t, p, q in destino]


def test_mes_repetido_se_detecta_y_uno_distinto_no():
    """104:RF-15 — ≥ 95 % de registros iguales en más de la mitad de las series: repite; otro mes medido, no;
    los clientes en cero no cuentan como iguales."""
    from convertersmartgrid import libros_nuevos as ln

    marzo = {c: _mes_completo(2026, 3, base, ruido=i) for i, (c, base) in enumerate((('1', 30.), ('2', 80.), ('3', 5.)))}
    abril_copia = {c: _copia_al_mes(v, 2026, 4) for c, v in marzo.items()}
    abril_medido = {c: _mes_completo(2026, 4, 30., ruido=10 + i) for i, c in enumerate(marzo)}
    assert ln.repite_otro_mes(abril_copia, marzo)['repite'] is True
    assert ln.repite_otro_mes(abril_medido, marzo)['repite'] is False
    ceros = [(t, 0.0, 0.0) for t, _p, _q in _mes_completo(2026, 3)]
    assert ln.repite_otro_mes({'9': ceros}, {'9': ceros}) == {'series_comparables': 0, 'series_iguales': 0, 'repite': False}


def test_ficha_y_aviso_del_libro_nuevo_como_la_revision_manual(tmp_path):
    """104:RF-7, 104:RF-10, 104:RF-11, 104:RF-12, 104:RF-13, 104:RF-20 — mes y cómo, completo, periodo, nuevos y faltan, sin suministro, en cero y el
    libro de suministros de otro mes, en el texto de la revisión manual."""
    from convertersmartgrid import libros_nuevos as ln

    sep = {c: _mes_completo(2026, 9, 20., ruido=i) for i, c in enumerate(('111', '222', '444'))}
    octubre = {'111': _mes_completo(2026, 10, 20., ruido=7), '222': _mes_completo(2026, 10, 30., ruido=8),
               '333': _mes_completo(2026, 10, 9., ruido=9)}
    libro = _libro_clientes(tmp_path / '2026/1026clientesImportantes.xlsx', octubre)
    sumi = _suministros(tmp_path / '0926 Clientes_spl.xlsx', [('111', '111', 'S1', 'A1'), ('222', '222', 'S1', 'A1'),
                                                             ('444', '444', 'S1', 'A1')])
    ficha = ln.verificar_libro_clientes(libro, '2026-10', origen='nombre', anio=2026, anterior=sep, mes_previo='2026-09',
                                        suministros=ln.suministros_del_libro(sumi), nombre_suministros=sumi.name)
    assert ficha['como'] == 'por su nombre, con el año 2026 de su carpeta'
    assert (ficha['clientes'], ficha['dias'], ficha['esperados'], ficha['completo']) == (3, 31, 31 * 96, True)
    assert ficha['periodo'] == ['2026-10-01T00:15:00', '2026-11-01T00:00:00']
    assert (ficha['nuevos'], ficha['faltan'], ficha['sin_suministro']) == (['333'], ['444'], ['333'])
    assert ficha['falta_suministros_del_mes'] is True and ficha['copia_de'] is None
    assert ln.mensaje_de_clientes(ficha) == (
        'Llegó octubre 2026 de clientes importantes: 3 clientes, completo (31 días), 1 nuevos sin suministro: 333; '
        '1 del mes anterior que no vienen: 444; falta el libro de suministros de octubre')


def test_mes_incompleto_en_cero_y_solape_se_dicen(tmp_path):
    """104:RF-8, 104:RF-9, 104:RF-13, 104:RF-14 — un mes con días de menos, un cliente apagado y registros de un mes
    que ya da otro libro."""
    from convertersmartgrid import libros_nuevos as ln

    corto = _mes_completo(2026, 10)[:10 * 96]
    apagado = [(t, 0.0, 0.0) for t, _p, _q in _mes_completo(2026, 10)]
    con_septiembre = _serie(1, 10., inicio=datetime(2026, 9, 30, 0, 15)) + _mes_completo(2026, 10)
    libro = _libro_clientes(tmp_path / 'oct.xlsx', {'1': corto, '2': apagado, '3': con_septiembre})
    ficha = ln.verificar_libro_clientes(libro, '2026-10', meses_de_otros={'2026-09': '0926.xlsx'})
    assert (ficha['completo'], ficha['incompletos'], ficha['en_cero']) == (False, 1, ['2'])
    assert ficha['solape'] == [{'mes': '2026-09', 'registros': 96, 'libro': '0926.xlsx'}]
    assert ficha['periodo'][0] == '2026-09-30T00:15:00'
    texto = ln.mensaje_de_clientes(ficha)
    assert 'incompleto: 1 de 3' in texto and '1 con todo en cero: 2' in texto and 'que ya da 0926.xlsx' in texto


def test_libro_que_no_se_lee_se_dice(tmp_path):
    """104:RF-18 — un libro roto da su motivo; no lanza."""
    from convertersmartgrid import libros_nuevos as ln

    roto = tmp_path / 'roto.xlsx'
    roto.write_bytes(b'no es un libro')
    ficha = ln.verificar_libro_clientes(roto, '2026-10')
    assert ficha['error'] and 'no se pudo leer' in ln.mensaje_de_clientes(ficha)
    assert ln.verificar_libro_cabecera(roto)['error']


def test_mes_repetido_en_una_hoja_de_cabecera(tmp_path):
    """104:RF-17 — en el libro de cabecera, la hoja cuyo abril repite marzo se dice con la hoja y los dos meses; un
    medidor congelado no."""
    from convertersmartgrid import libros_nuevos as ln
    from test_pronostico_demanda import _libro_cabecera

    marzo = _mes_completo(2026, 3, 500., ruido=1)
    libro = _libro_cabecera(tmp_path / 'cab.xlsx', {
        'M1': marzo + _copia_al_mes(marzo, 2026, 4)[:-1],
        'M2': _mes_completo(2026, 3, 400., ruido=2) + _mes_completo(2026, 4, 400., ruido=3)[:-1],
        # Un medidor congelado da el mismo valor todos los meses: no es un libro copiado (IN216 de Ica, 2026).
        'M3': [(t, 7.0, 1.0) for t, _p, _q in _mes_completo(2026, 3) + _mes_completo(2026, 4)[:-1]]})
    ficha = ln.verificar_libro_cabecera(libro)
    assert [(r['hoja'], r['mes'], r['igual_a']) for r in ficha['repetidos']] == [('M1', '2026-04', '2026-03')]
    assert 'M1 repite en abril 2026 los valores de marzo 2026' in ln.mensaje_de_cabecera(ficha)


def test_foto_y_cambios_sin_abrir_libros(tmp_path, monkeypatch):
    """104:RF-1, 104:RF-3 — la foto lista libros sin abrirlos; nuevos, cambiados y retirados."""
    from convertersmartgrid import libros_nuevos as ln

    (tmp_path / '2026').mkdir()
    (tmp_path / '2026/a.xlsx').write_bytes(b'1')
    (tmp_path / '2026/b.xlsx').write_bytes(b'22')
    monkeypatch.setattr(dm, 'abrir_libro', lambda _p: pytest.fail('no debía abrir ningún libro'))
    foto = ln.foto_de_fuente(tmp_path)
    conocidos = {'2026/a.xlsx': (1, foto[0][2]), '2026/b.xlsx': (1, 0), '2026/viejo.xlsx': (3, 0)}
    (tmp_path / '2026/c.xlsx').write_bytes(b'333')
    assert ln.cambios(conocidos, ln.foto_de_fuente(tmp_path)) == {
        'nuevos': ['2026/c.xlsx'], 'cambiados': ['2026/b.xlsx'], 'retirados': ['2026/viejo.xlsx']}


# --------------------------------------------------------------------------- pronóstico
def test_el_dataset_aparta_el_libro_que_repite_el_mes_anterior(tmp_path):
    """104:RF-26 — fuera de la web también: el libro copiado no entra y su motivo queda en los apartados."""
    import numpy as np

    from convertersmartgrid import pronostico_demanda as pd_
    from test_pronostico_demanda import _equivalencia, _libro_cabecera

    enero = {'111': _mes_completo(2026, 1, 30., ruido=1), '222': _mes_completo(2026, 1, 50., ruido=2)}
    _libro_clientes(tmp_path / 'cli/2026/0126clientes.xlsx', enero)
    _libro_clientes(tmp_path / 'cli/2026/0226clientes.xlsx', {c: _copia_al_mes(v, 2026, 2) for c, v in enero.items()})
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(60, 200.0)})
    eq = _equivalencia(tmp_path / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1')])
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq, clientes=tmp_path / 'cli'))
    assert any(a['objetivo'] == 'libro:0226clientes.xlsx' and 'repite los valores de enero 2026' in a['motivo']
               for a in d.apartados), d.apartados
    curva = next(o for o in d.objetivos if o.clase == 'cliente' and o.ident == '111' and o.magnitud == 'kW').curva
    assert max(curva.t) <= np.datetime64('2026-02-01T00:00')


def test_la_herramienta_guarda_el_perfil_con_el_dataset(tmp_path):
    """104:RF-24, 104:RF-25 — el perfil por serie y por clase (cobertura, huecos, ceros, picos) junto al dataset."""
    import json

    from apoyo import cargar_herramienta
    from test_pronostico_demanda import _fuentes

    f = _fuentes(tmp_path, dias=10)
    herramienta = cargar_herramienta('pronostico_demanda.py', 'pronostico_demanda_herramienta_104')
    destino = tmp_path / 'dataset'
    herramienta.main(['--cabecera', str(f.cabecera), '--equivalencia', str(f.equivalencia), '--clientes', str(f.clientes),
                      '--suministros', str(f.suministros), '--guardar-dataset', str(destino),
                      '--output-json', str(tmp_path / 'informe.json')])
    perfil = json.loads((destino / 'perfil.json').read_text(encoding='utf-8'))
    meta = json.loads((destino / 'dataset.json').read_text(encoding='utf-8'))
    assert perfil['huella'] == meta['huella'] and perfil['objetivos'] == len(meta['objetivos'])
    clases = {(x['clase'], x['magnitud']) for x in perfil['por_clase']}
    assert {('cabecera', 'kW'), ('cliente', 'kW')} <= clases
    fila = next(x for x in perfil['por_clase'] if x['clase'] == 'cabecera' and x['magnitud'] == 'kW')
    for clave in ('cobertura_mediana_pct', 'huecos_mediana', 'cero_mediana_pct', 'series_pico_mayor_2xp95'):
        assert clave in fila
    serie = perfil['por_serie'][0]
    assert {'cobertura_pct', 'huecos', 'cero_pct', 'negativos_pct', 'max_sobre_p95'} <= set(serie)
