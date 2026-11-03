"""046:RF-9 a RF-12 — cabecera y clientes fijos desde los lectores de la medición."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook
from pronostico_sintetico import sorteo

from convertersmartgrid.digital_twin import temporal_entrenamiento as te
from convertersmartgrid.digital_twin.pronostico import Objetivo, construir_conjunto

INICIO = datetime(2026, 6, 1, 0, 15)


def _cabecera(ruta: Path, medidores: dict[str, float], puntos: int, *, ceros=()) -> Path:
    libro = Workbook()
    libro.remove(libro.active)
    for medidor, base in medidores.items():
        h = libro.create_sheet(medidor)
        h.append(['Fecha', 'kW', 'kVAR'])
        for i in range(puntos):
            kw = 0.0 if medidor in ceros else base + i % 7
            h.append([INICIO + timedelta(minutes=15 * i), kw, kw * .3])
    libro.save(ruta)
    return ruta


def _clientes(ruta: Path, clientes: dict[str, str], inicio: datetime, puntos: int, *, base=40.0) -> Path:
    libro = Workbook()
    m = libro.active
    m.title = 'maestro_lib'
    m.append(['referencia'])
    m.append(['numero_suministro', 'nombre_hoja_exportacion'])
    for codigo, hoja in clientes.items():
        m.append([codigo, hoja])
        h = libro.create_sheet(hoja)
        h.append(['SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI', 'POT'])
        for i in range(puntos):
            t = inicio + timedelta(minutes=15 * i)
            ea = base / 4 + i % 3
            h.append([codigo, t.strftime('%d/%m/%Y'), t.strftime('%H:%M'), ea, ea * .2, ea * 4])
    libro.save(ruta)
    return ruta


def test_cabecera_da_kw_y_kvar_con_el_lector_existente(tmp_path):
    """046:RF-9 — kW y kVAR por alimentador desde ``maximas``; número de alimentadores sorteado."""
    r = sorteo()
    medidores = {f'M{i}': r.uniform(100, 900) for i in range(r.randint(1, 4))}
    libro = _cabecera(tmp_path / 'cabecera.xlsx', medidores, 40)
    pares = [(f'A{i}', m) for i, m in enumerate(medidores)]
    objetivos, apartados = te.objetivos_de_cabecera([libro], pares)
    assert not apartados
    assert {o.nombre for o in objetivos} == {f'cabecera:{a}:{m}' for a, _ in pares for m in ('kW', 'kVAR')}
    kw = next(o for o in objetivos if o.nombre == 'cabecera:A0:kW')
    kvar = next(o for o in objetivos if o.nombre == 'cabecera:A0:kVAR')
    assert kw.clase == 'cabecera' and kw.unidad == 'kW' and kvar.unidad == 'kVAR'
    assert kw.curva[3][0] == INICIO + timedelta(minutes=45)
    assert kvar.curva[3][1] == pytest.approx(kw.curva[3][1] * .3)
    assert kw.fuente['libros'] == ['cabecera.xlsx']


def test_medidor_inexistente_se_aparta_con_su_motivo(tmp_path):
    """046:RF-12 — lo que no se puede leer se dice; los demás siguen."""
    libro = _cabecera(tmp_path / 'cabecera.xlsx', {'M1': 100.0}, 10)
    objetivos, apartados = te.objetivos_de_cabecera([libro], [('A1', 'M1'), ('A2', 'NOESTA')])
    assert {o.ident for o in objetivos} == {'A1'}
    assert apartados[0]['objetivo'] == 'cabecera:A2' and 'NOESTA' in apartados[0]['motivo']


def test_la_central_se_descuenta_con_curva_de_demanda(tmp_path):
    """046:RF-10 — con los medidores de la central, la demanda es la de ``curva_de_demanda``."""
    from convertersmartgrid.demanda_medida import curva_de_demanda, maximas
    libro = _cabecera(tmp_path / 'cabecera.xlsx', {'CAB': 500.0, 'GEN': 80.0, 'LLE': 300.0, 'SAL': 200.0}, 200)
    central = {'A1': {'generacion': 'GEN', 'llegada': 'LLE', 'salida': 'SAL'}}
    objetivos, _apartados = te.objetivos_de_cabecera([libro], [('A1', 'CAB')], centrales=central)
    kw = next(o for o in objetivos if o.magnitud == 'kW')
    res = {r.medidor: r.curva for r in maximas([libro], [('A1', m) for m in ('CAB', 'GEN', 'LLE', 'SAL')])}
    puntos, informe = curva_de_demanda(res['CAB'], res['GEN'], res['LLE'], res['SAL'])
    assert [v for _t, v in kw.curva] == [p[1] for p in puntos]
    assert kw.fuente['central_descontada'] is True and informe.signo_llegada is not None
    sin = te.objetivos_de_cabecera([libro], [('A1', 'CAB')])[0]
    assert next(o for o in sin if o.magnitud == 'kW').fuente['central_descontada'] is False


def test_curvas_de_clientes_del_libro_de_quince_minutos(tmp_path):
    """046:RF-11 — kW = EA × 4 y kVAR = ERI × 4, como 004:RF-66, por hoja del maestro."""
    from convertersmartgrid.demanda_medida import curvas_de_clientes
    libro = _clientes(tmp_path / '0626.xlsx', {'S1': 'Cliente uno', 'S2': 'Cliente dos'}, INICIO, 20)
    curvas, avisos = curvas_de_clientes(libro)
    assert set(curvas) == {'S1', 'S2'} and not avisos
    t, kw, kvar = curvas['S1'][2]
    assert t == INICIO + timedelta(minutes=30)
    assert kw == pytest.approx((40 / 4 + 2) * 4) and kvar == pytest.approx(kw * .2)
    solo, _ = curvas_de_clientes(libro, ['S2'])
    assert set(solo) == {'S2'}


def test_libro_sin_maestro_usa_el_suministro_de_cada_hoja(tmp_path):
    """046:RF-11 — sin «maestro_lib», el código sale de la columna SUMINISTRO de la hoja."""
    from convertersmartgrid.demanda_medida import curvas_de_clientes
    libro = _clientes(tmp_path / '0526.xlsx', {'S1': 'Uno'}, INICIO, 6)
    from openpyxl import load_workbook
    wb = load_workbook(libro)
    wb.remove(wb['maestro_lib'])
    wb.create_sheet('Resumen').append(['SUMINISTRO', 'EA'])
    wb.save(libro)
    curvas, avisos = curvas_de_clientes(libro)
    assert set(curvas) == {'S1'} and len(curvas['S1']) == 6 and not avisos


def test_libro_ilegible_se_dice(tmp_path):
    """046:RF-12 — un mes sin clientes reconocibles no se calla: se aparta con el nombre del libro."""
    wb = Workbook()
    wb.active.append(['otra', 'cosa'])
    malo = tmp_path / '0126.xlsx'
    wb.save(malo)
    bueno = _clientes(tmp_path / '0626.xlsx', {'S1': 'Uno'}, INICIO, 6)
    objetivos, apartados = te.objetivos_de_clientes([malo, bueno])
    assert {o.ident for o in objetivos} == {'S1'}
    assert apartados[0]['objetivo'] == 'libro:0126.xlsx' and 'maestro_lib' in apartados[0]['motivo']


def test_registro_de_maxima_sigue_igual_tras_compartir_el_maestro(tmp_path):
    """004:RF-66 — ``registros_de_maxima`` lee el mismo maestro: el registro de su POT no cambia."""
    from convertersmartgrid.demanda_medida import registros_de_maxima
    libro = _clientes(tmp_path / '0626.xlsx', {'S1': 'Cliente uno'}, INICIO, 12)
    fila = INICIO + timedelta(minutes=30)
    pot = (40 / 4 + 2) * 4
    out, avisos = registros_de_maxima(libro, {'S1': pot})
    assert not avisos
    assert out['S1'][0] == fila.strftime('%d/%m/%Y %H:%M') and out['S1'][1] == pytest.approx((40 / 4 + 2) * .2 * 4)


def test_clientes_de_varios_meses_se_unen(tmp_path):
    """046:RF-11 — un cliente en libros mensuales es una sola serie, en kW y kVAR."""
    n = 10
    a = _clientes(tmp_path / '0626.xlsx', {'S1': 'Uno'}, INICIO, n)
    b = _clientes(tmp_path / '0726.xlsx', {'S1': 'Uno'}, INICIO + timedelta(minutes=15 * n), n)
    objetivos, apartados = te.objetivos_de_clientes([a, b])
    assert not apartados
    assert {o.nombre for o in objetivos} == {'cliente:S1:kW', 'cliente:S1:kVAR'}
    kw = next(o for o in objetivos if o.magnitud == 'kW')
    assert len(kw.curva) == 2 * n and kw.fuente['libros'] == ['0626.xlsx', '0726.xlsx']


def test_cliente_con_meses_contradictorios_se_aparta(tmp_path):
    """046:RF-12 — dos valores distintos del mismo instante no se eligen: se dice."""
    a = _clientes(tmp_path / '0626.xlsx', {'S1': 'Uno', 'S2': 'Dos'}, INICIO, 10)
    b = _clientes(tmp_path / '0726.xlsx', {'S1': 'Uno'}, INICIO, 10, base=900.0)
    objetivos, apartados = te.objetivos_de_clientes([a, b])
    assert {o.ident for o in objetivos} == {'S2'}
    assert apartados[0]['objetivo'] == 'cliente:S1' and 'mismo instante' in apartados[0]['motivo']


def _objetivo(curva, ident='A', magnitud='kW') -> Objetivo:
    return Objetivo(clase='cabecera', ident=ident, magnitud=magnitud, unidad=magnitud, curva=curva)


def test_cadencia_incumplida_se_aparta_sin_rellenar():
    """046:RF-12 — un libro horario no se presenta como de 15 minutos."""
    t0 = datetime(2026, 6, 1)
    buena = [(t0 + timedelta(minutes=15 * i), 1.0 + i) for i in range(200)]
    horaria = [(t0 + timedelta(hours=i), 1.0 + i) for i in range(50)]
    c = construir_conjunto([_objetivo(buena), _objetivo(horaria, 'B')], cadencia_min=15, zona_horaria='UTC')
    assert c.nombres == ['cabecera:A:kW']
    assert c.apartados[0]['objetivo'] == 'cabecera:B:kW' and 'cadencia' in c.apartados[0]['motivo']


def test_objetivo_sin_senal_se_aparta():
    """046:RF-12 — un medidor en cero siempre no es una demanda que aprender."""
    t0 = datetime(2026, 6, 1)
    buena = [(t0 + timedelta(minutes=15 * i), 1.0 + i % 9) for i in range(300)]
    cero = [(t0 + timedelta(minutes=15 * i), 0.0) for i in range(300)]
    c = construir_conjunto([_objetivo(buena), _objetivo(cero, 'B')], cadencia_min=15, zona_horaria='UTC')
    assert c.nombres == ['cabecera:A:kW'] and 'sin señal' in c.apartados[0]['motivo']


def test_huecos_quedan_como_huecos():
    """046:RF-12 — un hueco sigue siendo NaN en la serie y se cuenta en el inventario."""
    import numpy as np
    t0 = datetime(2026, 6, 1)
    curva = [(t0 + timedelta(minutes=15 * i), 5.0 + i % 4) for i in range(300) if i not in (50, 51, 52)]
    c = construir_conjunto([_objetivo(curva)], cadencia_min=15, zona_horaria='UTC')
    assert np.isnan(c.valores['cabecera:A:kW'][50:53]).all()
    inv = te.inventariar([_objetivo(curva)], cadencia_min=15, zona_horaria='UTC')
    fila = inv['objetivos'][0]
    assert fila['huecos'] == 3 and fila['cadencia_moda_min'] == 15 and fila['tramos'] == 2
    assert fila['puntos'] == 297 and fila['ceros'] == 0 and fila['inicio'] and fila['fin']


@pytest.mark.skipif(not os.environ.get('CSG_DEMANDA_DIR'), reason='CSG_DEMANDA_DIR no definida')
def test_clientes_reales_de_un_mes_son_de_quince_minutos():
    """046:RF-11 — el libro real de un mes da curvas de 15 minutos por cliente."""
    from convertersmartgrid.demanda_medida import curvas_de_clientes, libros_de_cabecera
    raiz = Path(os.environ['CSG_DEMANDA_DIR'])
    libros = sorted((raiz / '4.-clientesimportantes').rglob('*.xlsx'), key=lambda p: p.stat().st_size)
    assert libros and libros_de_cabecera is not None
    curvas, _avisos = curvas_de_clientes(libros[0])
    assert curvas
    pasos = {(b[0] - a[0]).total_seconds() / 60 for c in list(curvas.values())[:5] for a, b in zip(c, c[1:])}
    assert 15 in pasos
