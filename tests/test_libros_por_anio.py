"""Libros de demanda por año (spec 025).

El usuario dejó la medición de cabecera y los clientes importantes en una subcarpeta por año
(``2025``, ``2026``…) y seguirán llegando años, libros y subcarpetas. Los árboles se sortean
(semilla en el mensaje: ``IGEA_SCALE_SEED``) y los nombres no son de ninguna empresa.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from igea_dgs import demanda_medida as dm
from igea_dgs import libros_por_anio as lpa

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _tocar(raiz: Path, relativa: str) -> Path:
    p = raiz / relativa
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'')
    return p


def _arbol_sorteado(rng: random.Random, raiz: Path) -> dict[str, int | None]:
    """Libros en años, en subcarpetas de un año y sueltos; devuelve relativa → año."""
    esperado: dict[str, int | None] = {}
    anios = rng.sample(range(2015, 2035), rng.randint(1, 5))
    for anio in anios:
        for i in range(rng.randint(0, 4)):
            sub = rng.choice(['', 'enviados/', 'zona norte/', 'a/b/c/'])
            ext = rng.choice(['.xlsx', '.xls', '.xlsb', '.XLSX'])
            rel = f'{anio}/{sub}libro {i}{ext}'
            _tocar(raiz, rel)
            esperado[rel] = anio
    for i in range(rng.randint(0, 3)):
        rel = f'suelto {i}.xlsx'
        _tocar(raiz, rel)
        esperado[rel] = None
    # Un año a cualquier altura: la carpeta del año más cercano manda.
    rel = f'historico/{anios[0]}/viejo.xlsx'
    _tocar(raiz, rel)
    esperado[rel] = anios[0]
    # Lo que no es un libro no entra.
    _tocar(raiz, f'{anios[0]}/~$abierto.xlsx')
    _tocar(raiz, f'{anios[0]}/notas.txt')
    return esperado


def test_arbol_por_anio_sorteado(tmp_path):
    """025:RF-1, RF-2, RF-3, RF-26 — cada libro con su año y su ruta relativa."""
    rng = random.Random(SEMILLA)
    esperado = _arbol_sorteado(rng, tmp_path)
    libros = lpa.arbol_de_libros(tmp_path)
    assert {x.relativa: x.anio for x in libros} == esperado, f'semilla {SEMILLA}'
    assert all(x.ruta == tmp_path / x.relativa for x in libros)
    # Determinista: mismo orden en cada llamada, por ruta relativa.
    assert [x.relativa for x in libros] == [x.relativa for x in lpa.arbol_de_libros(tmp_path)]
    assert lpa.anios_de(libros) == sorted({a for a in esperado.values() if a is not None})


def test_el_anio_mas_cercano_manda(tmp_path):
    """025:RF-26 — un libro bajo dos carpetas de año es del más cercano."""
    _tocar(tmp_path, '2026/2025/x.xlsx')
    _tocar(tmp_path, '2026/no-es-anio-20251/y.xlsx')
    libros = {x.relativa: x.anio for x in lpa.arbol_de_libros(tmp_path)}
    assert libros == {'2026/2025/x.xlsx': 2025, '2026/no-es-anio-20251/y.xlsx': 2026}


def test_carpeta_sin_anios_es_como_antes(tmp_path):
    """025:RF-2 — sin subcarpetas de año, los libros sueltos y sin pedir año."""
    _tocar(tmp_path, 'a.xlsx')
    _tocar(tmp_path, 'b.xls')
    libros = lpa.arbol_de_libros(tmp_path)
    assert [x.relativa for x in libros] == ['a.xlsx', 'b.xls']
    assert lpa.anios_de(libros) == []
    assert lpa.libros_del_periodo(libros, None) == libros


def test_un_anio_nuevo_entra_sin_cambiar_nada(tmp_path):
    """025:RF-27 — un año, una subcarpeta o un libro nuevos aparecen en la siguiente lectura."""
    _tocar(tmp_path, '2025/a.xlsx')
    assert lpa.anios_de(lpa.arbol_de_libros(tmp_path)) == [2025]
    _tocar(tmp_path, '2026/b.xlsx')
    _tocar(tmp_path, '2025/nueva/c.xlsx')
    libros = lpa.arbol_de_libros(tmp_path)
    assert lpa.anios_de(libros) == [2025, 2026]
    assert '2025/nueva/c.xlsx' in {x.relativa for x in libros}


def test_libros_del_periodo(tmp_path):
    """025:RF-7 — un año o un mes eligen los libros de su año y los sueltos."""
    for rel in ('2025/a.xlsx', '2026/b.xlsx', 'suelto.xlsx'):
        _tocar(tmp_path, rel)
    libros = lpa.arbol_de_libros(tmp_path)
    for periodo in ('2025', '2025-07'):
        assert [x.relativa for x in lpa.libros_del_periodo(libros, periodo)] == [
            '2025/a.xlsx', 'suelto.xlsx']
    assert [x.relativa for x in lpa.libros_del_periodo(libros, '2024')] == ['suelto.xlsx']
    with pytest.raises(dm.DemandaError, match='año'):
        lpa.libros_del_periodo(libros, None)
    with pytest.raises(dm.DemandaError, match='Periodo no válido'):
        lpa.libros_del_periodo(libros, '2025-13')


def test_carpeta_que_no_existe(tmp_path):
    with pytest.raises(dm.DemandaError, match='No existe'):
        lpa.arbol_de_libros(tmp_path / 'no')


@pytest.mark.parametrize('fecha, periodo, dentro', [
    (datetime(2025, 7, 3, 10), '2025', True),
    (datetime(2025, 7, 3, 10), '2025-07', True),
    (datetime(2025, 7, 3, 10), '2025-08', False),
    (datetime(2026, 1, 1), '2025', False),
    ('03/07/2025 10:00', '2025', True),
    (None, '2025', False),
    (datetime(2025, 7, 3), None, True),
])
def test_en_periodo(fecha, periodo, dentro):
    """025:RF-7 — un registro está en un año o en un mes."""
    assert dm.en_periodo(fecha, periodo) is dentro


def test_maxima_del_anio_entre_varios_anios():
    """025:RF-7 — con periodo AAAA, la máxima del año entero y no la de otro año."""
    rng = random.Random(SEMILLA)
    inicio = datetime(2025, 1, 1)
    registros, mejor = [], None
    for i in range(0, 2 * 365 * 4, rng.randint(3, 9)):          # dos años, cada 6 h aprox.
        t = inicio + timedelta(hours=6 * i)
        kw = rng.uniform(100, 4000)
        if t.year == 2026:
            kw += 5000                                          # el otro año, siempre mayor
        registros.append(dm.Registro(t, {'kw': kw}))
        if t.year == 2025 and (mejor is None or kw > mejor[1]):
            mejor = (t, kw)
    res = dm.maxima_de_registros(registros, dm.MaximaCabecera(medidor='X'), periodo='2025')
    assert res.error is None, f'semilla {SEMILLA}'
    assert res.kw == pytest.approx(mejor[1]) and res.fecha == mejor[0].isoformat(sep=' ')


# =========================================================================== clientes (T2)
openpyxl = pytest.importorskip('openpyxl')


def _libro_clientes(path: Path, fecha: datetime | None = None) -> Path:
    """Un libro de clientes mínimo: hoja «resumen» y, si se da, una fecha dentro."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = 'Resumen'
    hoja.append(['SUMINISTRO', 'EA_TOTAL', 'ERI_TOTAL', 'POT_MAX'] + (['FECHA'] if fecha else []))
    hoja.append(['9011', 1.0, 1.0, 1.0] + ([fecha] if fecha else []))
    wb.save(path)
    return path


MESES_ES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
            'septiembre', 'octubre', 'noviembre', 'diciembre')
MESES_EN = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
            'september', 'october', 'november', 'december')


@pytest.mark.parametrize('forma', ['MMAA', 'AAAAMM', 'AAAA-MM', 'MM-AAAA', 'es', 'en', 'ES3'])
def test_mes_del_nombre_en_cualquier_forma(forma):
    """025:RF-6 — el mes del nombre en las formas habituales, con nombres de cualquier empresa."""
    rng = random.Random(SEMILLA)
    for _ in range(20):
        anio, mes = rng.randint(2015, 2034), rng.randint(1, 12)
        token = {'MMAA': f'{mes:02d}{anio % 100:02d}', 'AAAAMM': f'{anio}{mes:02d}',
                 'AAAA-MM': f'{anio}-{mes:02d}', 'MM-AAAA': f'{mes:02d}_{anio}',
                 'es': MESES_ES[mes - 1].capitalize(), 'en': MESES_EN[mes - 1].upper(),
                 'ES3': MESES_ES[mes - 1][:3]}[forma]
        empresa = rng.choice(['Pulso e', 'clientesImportantes', 'Grandes Usuarios', 'CLI'])
        nombre = rng.choice([f'{token} {empresa}.xlsx', f'{empresa}_{token}.xlsb',
                             f'{empresa} - {token}.xls'])
        assert dm.mes_generico(nombre, anio) == f'{anio}-{mes:02d}', (nombre, SEMILLA)


@pytest.mark.parametrize('nombre', [
    'clientes.xlsx',                 # sin mes
    '0125 y 0225 clientes.xlsx',     # dos meses
    'enero-febrero.xlsx',            # dos meses
    '1325 clientes.xlsx',            # mes 13
    '0124 clientes.xlsx',            # otro año (se pide 2025)
    'version 12345.xlsx',            # cinco cifras: no es un mes
])
def test_mes_del_nombre_dudoso_no_se_supone(nombre):
    """025:RF-6 — sin un único mes del año en el nombre, no se supone ninguno."""
    assert dm.mes_generico(nombre, 2025) is None


def test_catalogo_de_clientes_por_anio(tmp_path):
    """025:RF-3, RF-4, RF-6 — cada libro con su ruta relativa, su año y su mes; sin perfil."""
    for rel in ('2025/0125 Pulso e.xlsx', '2025/1225 Pulso.xlsx',
                '2026/0126clientesImportantes.xlsx', '2026/marzo/Clientes Marzo.xlsx'):
        _libro_clientes(tmp_path / rel)
    catalogo = dm.catalogar_libros_clientes(tmp_path, None)
    assert {(x.nombre, x.anio, x.mes, x.origen_mes, x.activo) for x in catalogo} == {
        ('2025/0125 Pulso e.xlsx', 2025, '2025-01', 'nombre', True),
        ('2025/1225 Pulso.xlsx', 2025, '2025-12', 'nombre', True),
        ('2026/0126clientesImportantes.xlsx', 2026, '2026-01', 'nombre', True),
        ('2026/marzo/Clientes Marzo.xlsx', 2026, '2026-03', 'nombre', True)}
    assert all(Path(x.path) == tmp_path / x.nombre for x in catalogo)


def test_libro_de_otro_anio_que_su_carpeta_no_se_usa(tmp_path):
    """025:RF-5 — el mes del libro es de otro año que su carpeta: no se activa y se dice."""
    patron = r'(?i)^(?P<mes>\d{2})(?P<anio>\d{2})clientes\.xlsx$'
    _libro_clientes(tmp_path / '2025/0126clientes.xlsx')
    _libro_clientes(tmp_path / '2025/sin mes.xlsx', fecha=datetime(2026, 4, 2))
    libros = {x.nombre: x for x in dm.catalogar_libros_clientes(tmp_path, patron)}
    for nombre in ('2025/0126clientes.xlsx', '2025/sin mes.xlsx'):
        libro = libros[nombre]
        assert not libro.activo, nombre
        assert any('2025' in a and '2026' in a for a in libro.avisos), libro.avisos


def test_mes_por_contenido_dentro_de_un_anio(tmp_path):
    """025:RF-6 — sin mes en el nombre, sigue 013:RF-4: la fecha dentro del libro."""
    _libro_clientes(tmp_path / '2025/clientes.xlsx', fecha=datetime(2025, 9, 30))
    (libro,) = dm.catalogar_libros_clientes(tmp_path, None)
    assert (libro.mes, libro.origen_mes, libro.activo) == ('2025-09', 'contenido', True)


def test_varios_patrones_en_el_perfil(tmp_path):
    """025:RF-6b — una lista de patrones: la empresa que cambia el nombre de un año a otro."""
    patrones = [r'(?i)^(?P<mes>\d{2})(?P<anio>\d{2})clientesImportantes\.xlsx$',
                r'(?i)^CLI(?P<anio>\d{4})(?P<mes>\d{2})\.xlsx$']
    assert dm.mes_de_nombre('0126clientesImportantes.xlsx', patrones) == '2026-01'
    assert dm.mes_de_nombre('CLI202507.xlsx', patrones) == '2025-07'
    from igea_dgs.perfil_empresa import PerfilEmpresa, PerfilError
    assert PerfilEmpresa(patron_libro_clientes=patrones).patron_libro_clientes == tuple(patrones)
    with pytest.raises(PerfilError, match='mes'):
        PerfilEmpresa(patron_libro_clientes=[patrones[0], r'(?P<anio>\d{4})'])


# =========================================================================== medidor → hoja (T3)
def _libro_cabecera(path: Path, hojas: dict[str, float]) -> Path:
    """Un libro de cabecera: cada hoja con 4 registros y su kW máximo dado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, pico in hojas.items():
        hoja = wb.create_sheet(nombre)
        hoja.append(['Local Time', 'kW tot', 'kVAR tot'])
        for i, kw in enumerate([pico / 2, pico, pico / 3, pico / 4]):
            hoja.append([datetime(2025, 5, 1) + timedelta(minutes=15 * i), kw, kw / 5])
    wb.save(path)
    return path


@pytest.mark.parametrize('prefijo', ['', 'L-', 'ALIM ', 'Alim_', 'x.'])
def test_hoja_por_codigo_del_alimentador(tmp_path, prefijo):
    """025:RF-12 — el medidor del libro no tiene hoja: se usa la del código del alimentador,
    solo o tras un prefijo separado, y se avisa con el medidor y la hoja."""
    libro = _libro_cabecera(tmp_path / '2025/cabecera.xlsx',
                            {f'{prefijo}QX301': 900.0, 'QX3011': 50.0, 'OTRO': 10.0})
    (res,) = dm.maximas([libro], [('QX301', 'M-QX999')])
    assert res.error is None and res.kw == 900.0
    assert res.hojas == [f'{prefijo}QX301']
    assert any('M-QX999' in a and f'{prefijo}QX301' in a for a in res.avisos), res.avisos


def test_el_medidor_con_hoja_va_antes_que_el_codigo(tmp_path):
    """025:RF-12 — si el medidor tiene hoja, manda la del medidor."""
    libro = _libro_cabecera(tmp_path / 'c.xlsx', {'M-QX999': 700.0, 'L-QX301': 900.0})
    (res,) = dm.maximas([libro], [('QX301', 'M-QX999')])
    assert res.hojas == ['M-QX999'] and res.kw == 700.0


def test_dos_hojas_con_el_codigo_no_se_elige_ninguna(tmp_path):
    """025:RF-12b — dos hojas casan con el código del alimentador: ninguna, y se dicen."""
    libro = _libro_cabecera(tmp_path / 'c.xlsx', {'L-QX301': 900.0, 'ALIM QX301': 800.0})
    (res,) = dm.maximas([libro], [('QX301', 'M-QX999')])
    assert res.kw is None and 'L-QX301' in res.error and 'ALIM QX301' in res.error


def test_sin_hoja_del_medidor_ni_del_codigo(tmp_path):
    """025:RF-13 — ni el medidor ni el código: ese alimentador queda sin medición del año."""
    libro = _libro_cabecera(tmp_path / 'c.xlsx', {'OTRO': 10.0})
    (res,) = dm.maximas([libro], [('QX301', 'M-QX999')])
    assert res.kw is None and 'M-QX999' in res.error and 'QX301' in res.error


def test_dos_canales_sin_hoja_del_mismo_medidor_dan_una_fila(tmp_path):
    """025:RF-12 (004:RF-45) — el libro de un año sin las hojas de los canales: los dos se
    leen como su medidor base y quedan en una sola fila (IN111 en 2025: «IN111_V18 Y
    IN111_V119» y solo la hoja «IN111»; el plan del ajuste se paraba con dos medidores)."""
    libro = _libro_cabecera(tmp_path / '2025/c.xlsx', {'QX7': 640.0})
    res = dm.maximas([libro], [('QX7', 'QX7_V18'), ('QX7', 'QX7_V119')])
    assert len(res) == 1 and res[0].kw == 640.0 and res[0].canal_de == 'QX7'
    assert any('QX7_V119' in a for a in res[0].avisos)


def test_medidor_en_dos_libros_del_anio_usa_el_mas_reciente(tmp_path):
    """025:RF-30 — la misma hoja en dos libros del mismo año: el de modificación más reciente."""
    viejo = _libro_cabecera(tmp_path / '2025/b viejo.xlsx', {'M1': 100.0})
    nuevo = _libro_cabecera(tmp_path / '2025/a nuevo.xlsx', {'M1': 200.0})
    os.utime(viejo, (1_700_000_000, 1_700_000_000))
    os.utime(nuevo, (1_800_000_000, 1_800_000_000))
    (res,) = dm.maximas([tmp_path], [('A1', 'M1')])
    assert res.kw == 200.0 and res.libro == 'a nuevo.xlsx'
    assert any('b viejo.xlsx' in a for a in res.avisos)


# =========================================================================== tipos por contenido (T8)
def _libro_hojas(path: Path, hojas: dict[str, list[list]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        h = wb.create_sheet(nombre)
        for f in filas:
            h.append(f)
    wb.save(path)
    return path


def _carpeta_de_demanda(raiz: Path, rng: random.Random) -> dict[str, str]:
    """Las cuatro clases de libro en carpetas con nombres sorteados, de ninguna empresa."""
    nombres = rng.sample(['a', 'datos 1', 'zz', 'Medidas', 'otro-x', 'q'], 4)
    _libro_hojas(raiz / nombres[0] / 'relacion.xlsx',
                 {'h': [['Codigo Alimentador', 'Medidor'], ['F1', 'M1']]})
    _libro_hojas(raiz / nombres[1] / '2025' / 'medida.xlsx',
                 {'M1': [['Local Time', 'kW tot'], [datetime(2025, 1, 1), 1.0],
                         [datetime(2025, 1, 1, 0, 15), 2.0]]})
    _libro_hojas(raiz / nombres[2] / '2025' / '0125 grandes.xlsx',
                 {'Resumen': [['SUMINISTRO', 'EA_TOTAL', 'ERI_TOTAL', 'POT_MAX'], ['9', 1, 1, 1]]})
    _libro_hojas(raiz / nombres[3] / 'padron.xlsx',
                 {'s': [['Suministro', 'Suministro Act', 'SED', 'RADIAL'], [1, 2, 'E1', 'F1']]})
    return {'medidores': nombres[0], 'cabecera': nombres[1], 'clientes': nombres[2],
            'suministros': nombres[3]}


def test_tipo_de_cada_carpeta_por_su_contenido(tmp_path):
    """025:RF-25b — medidores, cabecera, clientes y suministros por lo que traen sus libros,
    no por el nombre de su carpeta."""
    rng = random.Random(SEMILLA)
    esperado = _carpeta_de_demanda(tmp_path, rng)
    tipos, avisos = dm.clasificar_carpeta_demanda(tmp_path)
    assert {t: p.relative_to(tmp_path).parts[0] for t, p in tipos.items()} == esperado, SEMILLA
    assert tipos['medidores'].is_file() and tipos['cabecera'].is_dir()
    assert not avisos


def test_dos_carpetas_del_mismo_tipo_o_ninguna_se_dicen(tmp_path):
    """025:RF-25c — dos carpetas del mismo tipo, o ninguna: se dice con sus nombres."""
    _carpeta_de_demanda(tmp_path, random.Random(1))
    _libro_hojas(tmp_path / 'copia' / 'otra relacion.xlsx',
                 {'h': [['Codigo Alimentador', 'Medidor'], ['F2', 'M2']]})
    tipos, avisos = dm.clasificar_carpeta_demanda(tmp_path)
    assert 'medidores' not in tipos
    assert any('medidores' in a and 'copia' in a for a in avisos)
    vacia = tmp_path / 'vacia'
    vacia.mkdir()
    _tipos, avisos = dm.clasificar_carpeta_demanda(vacia)
    assert any('medición de cabecera' in a for a in avisos)


REAL = os.environ.get('IGEA_DEMANDA_DIR', '').strip()
real = pytest.mark.skipif(not REAL or not Path(REAL).is_dir(),
                          reason='IGEA_DEMANDA_DIR no apunta a la carpeta de la distribuidora')


def _sub_real(prefijo: str) -> Path:
    return next(p for p in Path(REAL).iterdir() if p.is_dir() and p.name.startswith(prefijo))


@real
def test_real_cada_libro_de_clientes_tiene_su_mes_sin_perfil():
    """025:RF-1, RF-6 — con los libros reales, cada libro de clientes de cada año da su mes
    por la regla general, sin patrón de la empresa, y queda activo (2025: «MMAA Pulso»;
    2026: «MMAAclientesImportantes»)."""
    catalogo = dm.catalogar_libros_clientes(_sub_real('4.'), None)
    assert catalogo and lpa.anios_de(lpa.arbol_de_libros(_sub_real('4.')))
    sin_mes = [x.nombre for x in catalogo if x.anio is not None and not x.activo]
    assert not sin_mes, sin_mes
    assert all(x.mes and x.mes[:4] == f'{x.anio:04d}' for x in catalogo if x.anio)


@real
def test_real_cada_anio_da_la_maxima_de_sus_alimentadores():
    """025:RF-8, RF-12 — en cada año, todo alimentador del libro de medidores cuya hoja está
    en los libros de ese año (por su medidor o por su código) da la máxima de ese año. En
    2025 cuatro hojas llevan el código del alimentador y no el del medidor."""
    meds = dm.leer_medidores(next(_sub_real('1.').iterdir()))
    arbol = lpa.arbol_de_libros(_sub_real('2.'))
    for anio in lpa.anios_de(arbol):
        libros = [x.ruta for x in lpa.libros_del_periodo(arbol, str(anio))]
        hojas = {h for p in libros for h in dm._abrir(p).sheet_names}
        # Las filas «Barra10KV», «Barra60KV»… no son alimentadores: agrupan los medidores de
        # barra de varias SET (CHNB1T1 no existe en 2025) y van por 022:RF-84 (libro del
        # 2026-10-27).
        con_hoja = [a for a in dm.alimentadores_de(meds) if 'barra' not in dm.normalizar(a)
                    and (dm.hojas_del_alimentador(sorted(hojas), a)
                         or any(any(dm.hojas_del_medidor(sorted(hojas), m)) for m in dm.medidores_de(meds, a)))]
        assert con_hoja, anio
        pares = [(a, m) for a in con_hoja for m in dm.medidores_de(meds, a)]
        res = dm.maximas(libros, pares, periodo=str(anio))
        # Una hoja sin kW numérico en el año es un dato de la medición (PI101 en 2026), no
        # que no se encontrara: lo que no puede pasar es «no está en ningún libro».
        perdidos = sorted({r.alimentador for r in res if r.error and 'ningún libro' in r.error})
        assert not perdidos, (anio, perdidos)
        ok = [r for r in res if not r.error]
        assert ok and all(r.fecha and r.fecha[:4] == str(anio) for r in ok), anio


def test_maxima_de_barra_del_anio():
    """025:RF-7 — la máxima de barra también por año."""
    a = [(datetime(2025, 3, 1), 10.0, 1.0), (datetime(2026, 3, 1), 99.0, 1.0)]
    b = [(datetime(2025, 3, 1), 5.0, 1.0), (datetime(2026, 3, 1), 99.0, 1.0)]
    mx = dm.maxima_de_barra([a, b], '2025')
    assert mx['fecha'] == datetime(2025, 3, 1) and mx['kw'] == 15.0
