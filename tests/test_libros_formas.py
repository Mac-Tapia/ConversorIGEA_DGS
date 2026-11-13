"""Specs 089 y 104: el lector de clientes se adapta a formas de libro que no conocía.

El 2026-11-12 dos libros reales de 2025 quedaron fuera del dataset del pronóstico: al guardarse perdieron todo su texto
(las cabeceras «día, hora», «EA, ERI, Pot» y la hora de cada registro), y el lector solo los reconocía por esos nombres.
Aquí se reproducen esas formas y otras con libros sintéticos pequeños; ningún dato real.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip('python_calamine')
from openpyxl import Workbook  # noqa: E402

from convertersmartgrid import demanda_medida as dm  # noqa: E402
from convertersmartgrid.demanda_medida import catalogar_libros_clientes, curvas_de_clientes  # noqa: E402
from convertersmartgrid.pronostico_demanda import curvas_por_cliente, libros_con_mes  # noqa: E402


def _hoja_sin_textos(wb, nombre: str, codigo: int, dias_con_datos: int, *, dias_plantilla: int = 31,
                     base: float = 10.0, por_dia: int = 96) -> None:
    """Como «0225 Pulso e»: sin ninguna cabecera de texto, la hora en cero, el código en F1 y la plantilla de 31 días
    con ceros tras el último día del mes. F, G, H: EA, ERI, ERC de lectura; J, K, L: por el factor; M: Pot = 4 × J."""
    h = wb.create_sheet(nombre)
    h.append([None, 400.0, None, None, None, codigo])
    h.append([])
    h.append([None, None, None, None, None, None, None, 1])
    h.append([])
    h.append([None, None, None, None, None, 1.0, 1.0, 0, None, 1.0, 1.0, 0, 4.0])
    contador = 6
    for d in range(1, dias_plantilla + 1):
        for k in range(por_dia):
            ea = (base + d + (k % 7) / 10) if d <= dias_con_datos else 0.0
            eri = ea / 3
            h.append([d, 0, 1, 1, f'{d}-', ea, eri, 0, contador, ea, eri, 0, ea * 4])
            contador += 1


def _libro_sin_textos(ruta: Path, clientes: dict[int, int], **kw) -> Path:
    wb = Workbook()
    r = wb.active
    r.title = 'resumen'
    r.append([])
    r.append([None, None, None, None, 'Nis', 'EA', 'ERI', 'ERC', 'Pot'])
    for codigo, dias in clientes.items():
        r.append([None, 1, None, None, codigo, 1.0, 1.0, 0, 40.0])
        _hoja_sin_textos(wb, f'c_{codigo}', codigo, dias, **kw)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _libro_fecha(ruta: Path, codigo: str, inicio: datetime, n: int, cabecera=('SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI',
                                                                               'POT'), resumen: str = 'resumen') -> Path:
    from datetime import timedelta

    wb = Workbook()
    r = wb.active
    r.title = resumen
    r.append(['Nis', 'EA', 'ERI', 'POT'])
    r.append([codigo, 1.0, 1.0, 40.0])
    h = wb.create_sheet(f'h{codigo}')
    h.append(list(cabecera))
    for i in range(n):
        t = inicio + timedelta(minutes=15 * (i + 1))
        h.append([codigo, t.strftime('%d/%m/%Y'), t.strftime('%H:%M'), 5.0 + i % 3, 1.0, 20.0])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _libro_desconocido(ruta: Path) -> Path:
    """Números sin cabecera, sin días ni relación entre columnas: un formato que nadie le enseñó al lector."""
    wb = Workbook()
    r = wb.active
    r.title = 'resumen'
    r.append(['Nis', 'EA'])
    r.append([777, 1.0])
    h = wb.create_sheet('c_777')
    h.append([None, None, 777])
    for i in range(300):
        h.append([(i * 37) % 11 + 0.5, (i * 13) % 7 + 0.25, (i * 5) % 3 + 0.1])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


# ----------------------------------------------------------------------------------------------- columnas
def test_hoja_sin_cabecera_ni_hora_se_lee_por_su_contenido(tmp_path):
    """089:RF-107, 089:RF-109 — «0225 Pulso e» y «0625 Pulso» perdieron sus textos al guardarse y se apartaban «sin
    maestro_lib ni hojas con SUMINISTRO, FECHA, HORA y EA». Ahora el día sale de la columna de enteros en tramos de 96,
    EA y Pot de la relación Pot = 4 × EA, y la hora de la posición en el día; el aviso dice lo reconocido y lo que
    falta."""
    ruta = _libro_sin_textos(tmp_path / '2025/0225 Pulso e.xlsx', {181000485: 28})
    curvas, avisos = curvas_de_clientes(ruta, mes='2025-02')
    curva = curvas['181000485']
    assert len(curva) == 28 * 96
    assert curva[0][0] == datetime(2025, 2, 1, 0, 15) and curva[-1][0] == datetime(2025, 3, 1, 0, 0)
    assert curva[0][1] == pytest.approx((10.0 + 1) * 4) and curva[0][2] is None
    texto = ' '.join(avisos)
    assert 'por su contenido' in texto and 'hora por su posición en el día' in texto
    assert 'falta' in texto and 'ERI' in texto and 'huella' in texto
    assert 'sin «maestro_lib» ni hojas' not in texto


def test_la_regla_confirmada_completa_las_columnas_de_los_libros_iguales(tmp_path):
    """089:RF-110 — confirmada una vez la columna que el contenido no decide (ERI), la regla se aplica a los libros con
    la misma huella sin volver a preguntar."""
    ruta = _libro_sin_textos(tmp_path / '2025/0625 Pulso.xlsx', {181000485: 30})
    _curvas, avisos = curvas_de_clientes(ruta, mes='2025-06')
    huella = dm.huella_de_aviso(' '.join(avisos))
    assert huella
    curvas, avisos = curvas_de_clientes(ruta, mes='2025-06', formatos={huella: {'eri': 10}})
    curva = curvas['181000485']
    assert curva[0][2] == pytest.approx((10.0 + 1) / 3 * 4)
    assert not any('falta' in a for a in avisos)
    assert any('regla confirmada' in a for a in avisos)


def test_columnas_con_otros_nombres_por_los_sinonimos_de_la_empresa(tmp_path):
    """089:RF-108 — una hoja con «Fecha lectura, Hora, kWh, kVArh» no se leía; con esos sinónimos en el fichero de
    alias de la empresa, sí. Sin ellos el libro no se calla: queda en un aviso."""
    ruta = _libro_fecha(tmp_path / '2026/datos.xlsx', '555', datetime(2026, 3, 1), 96,
                        cabecera=('Cliente', 'Fecha lectura', 'Hora', 'kWh', 'kVArh', 'Demanda'))
    curvas, avisos = curvas_de_clientes(ruta)
    assert curvas == {} and avisos
    alias = {**dm.ALIAS, 'fecha': ('fecha lectura', *dm.ALIAS['fecha']), 'ea': ('kwh', *dm.ALIAS['ea']),
             'eri': ('kvarh', *dm.ALIAS['eri']), 'suministro': ('cliente', *dm.ALIAS['suministro'])}
    curvas, _avisos = curvas_de_clientes(ruta, alias=alias)
    assert len(curvas['555']) == 96 and curvas['555'][0][1] == pytest.approx(5.0 * 4)


def test_formato_desconocido_queda_en_un_aviso_con_lo_que_falta(tmp_path):
    """089:RF-109 — un formato que el lector no sabe leer no se pierde en silencio: el aviso nombra el libro, lo que
    reconoció, lo que le falta y su huella para confirmarlo."""
    ruta = _libro_desconocido(tmp_path / '2026/0326 raro.xlsx')
    curvas, avisos = curvas_de_clientes(ruta, mes='2026-03')
    assert curvas == {}
    texto = ' '.join(avisos)
    assert '0326 raro.xlsx' in texto and 'formato no reconocido' in texto
    assert 'falta' in texto and 'día' in texto and dm.huella_de_aviso(texto)


# ----------------------------------------------------------------------------------------------- mes
def test_mes_del_libro_sin_mes_en_el_nombre_por_sus_fechas(tmp_path):
    """089:RF-111 — un libro con nombre nuevo («datos.xlsx») recibe el mes de sus fechas."""
    _libro_fecha(tmp_path / '2026/datos.xlsx', '555', datetime(2026, 3, 1), 200)
    catalogo = catalogar_libros_clientes(tmp_path, None)
    assert [(x.nombre, x.mes, x.origen_mes) for x in catalogo] == [('2026/datos.xlsx', '2026-03', 'contenido')]


def test_mes_en_el_nombre_de_una_hoja(tmp_path):
    """089:RF-111 — sin mes en el nombre del fichero ni fechas en sus filas («día, hora»), el nombre de una hoja que
    diga el mes lo da."""
    ruta = _libro_sin_textos(tmp_path / '2025/clientes.xlsx', {181000485: 31})
    from openpyxl import load_workbook

    wb = load_workbook(ruta)
    wb['resumen'].title = 'resumen marzo'
    wb.save(ruta)
    catalogo = catalogar_libros_clientes(tmp_path, None)
    assert [(x.mes, x.origen_mes) for x in catalogo] == [('2025-03', 'hojas')]


def test_las_fechas_mandan_sobre_el_nombre_y_se_dice(tmp_path):
    """089:RF-112 — el nombre dice marzo y las fechas abril: manda la fecha, y se dice cuál y por qué."""
    ruta = _libro_fecha(tmp_path / '2026/0326clientes.xlsx', '555', datetime(2026, 4, 1), 300)
    libros, _sin_uso = libros_con_mes(tmp_path, None)
    _por, _de, _contra, avisos, apartados = curvas_por_cliente(libros)
    assert not apartados
    texto = ' '.join(n for notas in avisos.values() for n in notas)
    assert 'el nombre dice marzo 2026' in texto and 'sus fechas son de abril 2026' in texto and 'manda la fecha' in texto


def test_libro_dia_hora_con_mas_dias_que_su_mes_se_aparta_y_se_dice(tmp_path):
    """089:RF-113 — «0426clientesImportantes» traía energía los 31 días y abril tiene 30: un libro «día, hora» con más
    días con energía que el mes de su nombre no se puede fechar; se aparta con su motivo. Los días de la plantilla en
    cero (febrero hasta el 28 en una de 31) no cuentan."""
    _libro_sin_textos(tmp_path / '2025/0225 Pulso e.xlsx', {181000485: 28})
    _libro_sin_textos(tmp_path / '2025/0425 Pulso e.xlsx', {181000485: 31}, base=50.0)
    libros, _sin_uso = libros_con_mes(tmp_path, None)
    por, _de, _contra, _avisos, apartados = curvas_por_cliente(libros)
    assert len(por['181000485'].t) == 28 * 96
    motivo = next(a['motivo'] for a in apartados if a['objetivo'] == 'libro:0425 Pulso e.xlsx')
    assert '31 días con energía' in motivo and 'abril 2025 tiene 30' in motivo


def test_libro_sin_textos_que_repite_el_mes_anterior_se_aparta(tmp_path):
    """104:RF-26 con la forma nueva — marzo leído por su contenido que repite febrero registro a registro se aparta."""
    _libro_sin_textos(tmp_path / '2025/0225 Pulso e.xlsx', {181000485: 28})
    _libro_sin_textos(tmp_path / '2025/0325 Pulso e.xlsx', {181000485: 28})
    libros, _sin_uso = libros_con_mes(tmp_path, None)
    _por, _de, _contra, _avisos, apartados = curvas_por_cliente(libros)
    assert any(a['objetivo'] == 'libro:0325 Pulso e.xlsx' and '104:RF-26' in a['motivo'] for a in apartados)
