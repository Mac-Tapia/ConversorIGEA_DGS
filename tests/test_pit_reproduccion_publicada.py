"""Spec 107 T15 y T16: reproducir fila por fila un cuadro publicado del PIT y cotejar una muestra con un revisor aparte.

Orden del usuario del 2026-11-19: la aceptación usa los formatos que el regulador publica, no «datos autorizados por la
empresa». Estas pruebas usan libros SINTÉTICOS con la forma oficial (rótulos, fila de años, notas al pie); los nombres
de sistema, SET, barra y usuario son inventados (repositorio público). La corrida con el expediente publicado se hace
fuera de git, con el libro descargado de la página del regulador.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from convertersmartgrid.dominio.pit import PitError
from convertersmartgrid.dominio.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
MODULO = 'convertersmartgrid.adaptadores.pit.reproduccion'
ANIOS = list(range(2030, 2034))


def _rep():
    """La ausencia del módulo es la falla de la aserción (rojo), no un error de importación."""
    assert importlib.util.find_spec(MODULO) is not None, 'falta el módulo de reproducción de cuadros publicados (107 T15)'
    return importlib.import_module(MODULO)


#: (sistema, SET, barra, kV) y la serie de cada formato regulado: energía (MWh) y tres potencias (MW).
REGULADOS = [
    (('Sistema Uno', 'SET Alfa', 'ALFA010', 10.0), [1000.0, 1100.0, 1210.0, 1331.0], [2.0, 2.2, 2.4, 2.6]),
    (('Sistema Uno', 'SET Beta', 'BETA023', 22.9), [500.0, 520.0, 540.0, 560.0], [1.0, 1.1, 1.2, 1.3]),
    (('Sistema Dos', 'SET Gama', 'GAMA060', 60.0), [3000.0, 3000.0, 3100.0, 3200.0], [6.0, 6.1, 6.2, 6.3]),
]
#: Usuarios libres: (sistema, SET, barra, kV, usuario), energía y potencia.
LIBRES = [
    (('Sistema Uno', 'SET Alfa', 'ALFA010', 10.0, 'Usuario P'), [200.0] * 4, [0.5] * 4),
    (('Sistema Dos', 'SET Gama', 'GAMA060', 60.0, 'Usuario Q'), [800.0] * 4, [1.5] * 4),
]


def _cabecera(ws, codigo: str, titulo: str, con_usuario: bool) -> int:
    ws.append(['OSINERGMIN'] + [None] * 6 + [codigo])
    ws.append([titulo])
    ws.append([])
    ws.append(['ÁREA DE DEMANDA:  X'])
    ws.append([])
    rotulos = ['SISTEMA', 'SUBESTACIÓN', 'BARRA', 'TENSIÓN'] + (['NOMBRE'] if con_usuario else []) + ['Valor (1)']
    ws.append(rotulos)
    ws.append([None, None, None, '(kV)'] + (['USUARIO'] if con_usuario else []) + ANIOS)
    return len(rotulos) - 1


def _hoja(wb, codigo, filas, con_usuario=False, nombre=None):
    ws = wb.create_sheet(nombre or codigo)
    _cabecera(ws, codigo, f'FORMATO {codigo}', con_usuario)
    for clave, serie in filas:
        ws.append(list(clave) + list(serie))
    ws.append([])
    ws.append(['(1) Nota de la plantilla oficial.'])


def _sumas(regulados, libres, i_reg, i_lib):
    por_barra: dict[tuple, list[float]] = {}
    for clave, *series in regulados:
        por_barra[clave] = list(series[i_reg])
    for clave, *series in libres:
        k = clave[:4]
        previa = por_barra.get(k, [0.0] * len(ANIOS))
        por_barra[k] = [a + b for a, b in zip(previa, series[i_lib])]
    return por_barra


def _libro(tmp_path: Path, *, regulados=REGULADOS, libres=LIBRES, f119=None, resumen=None, extra=None,
           nombre='expediente.xlsx') -> Path:
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    _hoja(wb, 'F-109', [(c, e) for c, e, _p in regulados])
    for codigo in ('F-110', 'F-111', 'F-112'):
        _hoja(wb, codigo, [(c, p) for c, _e, p in regulados])
    _hoja(wb, 'F-115', [(c, e) for c, e, _p in libres], con_usuario=True)
    for codigo in ('F-116', 'F-117', 'F-118'):
        _hoja(wb, codigo, [(c, p) for c, _e, p in libres], con_usuario=True)
    sumas = resumen or _sumas(regulados, libres, 1, 1)
    for codigo in ('F-120', 'F-121', 'F-122'):
        _hoja(wb, codigo, list(sumas.items()))
    ws = wb.create_sheet('F-119')
    ws.append(['OSINERGMIN', None, None, None, 'F-119'])
    ws.append(['RESUMEN DE LA PROYECCION GLOBAL DE LA DEMANDA (GWh)'])
    ws.append([])
    ws.append(['AÑO', 'MAT (1)', 'AT (1)', 'MT (1)', 'TOTAL'])
    if f119 is None:
        at = [sum(e[i] for c, e, _ in regulados if c[3] == 60.0) + sum(e[i] for c, e, _ in libres if c[3] == 60.0)
              for i in range(len(ANIOS))]
        mt = [sum(e[i] for c, e, _ in regulados if c[3] in (10.0, 22.9)) +
              sum(e[i] for c, e, _ in libres if c[3] in (10.0, 22.9)) for i in range(len(ANIOS))]
        f119 = [[a, 0.0, at[i] / 1000, mt[i] / 1000, (at[i] + mt[i]) / 1000] for i, a in enumerate(ANIOS)]
    for fila in f119:
        ws.append(fila)
    ws.append(['(1) Nota.'])
    if extra:
        extra(wb)
    ruta = tmp_path / nombre
    wb.save(ruta)
    return ruta


@pytest.fixture(scope='module')
def registro():
    return cargar_registro(NORMATIVA)


def test_libro_coherente_se_reproduce_celda_a_celda_con_su_huella(tmp_path, registro):
    """107:RF-9 (T15) — F-119 a F-122 calculados por el conversor desde F-109..F-118 publicados dan las mismas cifras."""
    rep = _rep()
    ruta = _libro(tmp_path)
    r = rep.reproducir_resumenes(registro, ruta)
    assert r['referencia']['sha256'] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert r['anios'] == ANIOS
    for codigo in ('F-119', 'F-120', 'F-121', 'F-122'):
        q = r['cuadros'][codigo]
        assert q['diferencias'] == [], (codigo, q['diferencias'][:2])
        assert q['celdas'] and all(c['igual'] for c in q['celdas'])
    f120 = r['cuadros']['F-120']['celdas']
    assert {c['id'] for c in f120 if c['anio'] == ANIOS[0]} == {'F-120!E8', 'F-120!E9', 'F-120!E10'}
    alfa = next(c for c in f120 if c['id'] == 'F-120!E8')
    assert alfa['conversor'] == pytest.approx(2.0 + 0.5) and alfa['publicado'] == pytest.approx(2.5)
    assert r['resumen']['F-119']['celdas'] == 4 * len(ANIOS)


def test_cada_diferencia_lleva_su_causa_deducida_de_las_entradas(tmp_path, registro):
    """107:RF-9 (T15) — tensión de otra barra sumada por nombre, sistema distinto, fila basura y tensión sin nivel."""
    rep = _rep()
    libres = LIBRES + [
        # Un libre en ALFA010 declarado a 22,9 kV: el publicado lo suma por el nombre de la barra en la fila de 10 kV.
        (('Sistema Uno', 'SET Alfa', 'ALFA010', 22.9, 'Usuario R'), [50.0] * 4, [0.25] * 4),
        # Un libre a 13,8 kV, que la regla de niveles no clasifica: el publicado lo pone en MT.
        (('Sistema Dos', 'SET Gama', 'GAMA013', 13.8, 'Usuario S'), [300.0] * 4, [0.75] * 4),
    ]
    sumas = _sumas(REGULADOS, LIBRES, 1, 1)
    sumas[('Sistema Uno', 'SET Alfa', 'ALFA010', 10.0)] = [v + 0.25 for v in sumas[('Sistema Uno', 'SET Alfa', 'ALFA010', 10.0)]]
    # El publicado pone GAMA060 en otro sistema y trae una fila de resto de fórmula.
    sumas = {(('Sistema Tres',) + k[1:] if k[2] == 'GAMA060' else k): v for k, v in sumas.items()}
    sumas[('Sistema Dos', 'SET Gama', 'GAMA013', 13.8)] = [0.75] * 4
    sumas[(None, None, 0, None)] = [0.0] * 4
    f119 = []
    for i, a in enumerate(ANIOS):
        at = (3000 + [0, 0, 100, 200][i] + 800) / 1000
        mt = (REGULADOS[0][1][i] + REGULADOS[1][1][i] + 200 + 50 + 300) / 1000
        f119.append([a, 0.0, at, mt, at + mt])
    r = rep.reproducir_resumenes(registro, _libro(tmp_path, libres=libres, f119=f119, resumen=sumas))
    causas = {d['causa'] for q in r['cuadros'].values() for d in q['diferencias']}
    assert all(c.strip() for c in causas)
    texto = ' | '.join(sorted(causas))
    assert 'por el nombre de la barra, la entrada de 22.9 kV' in texto
    assert 'la entrada publicada declara 22.9 kV en la barra ALFA010' in texto
    assert 'pone la barra en el sistema «Sistema Tres»' in texto
    assert 'resto de fórmula' in texto
    assert 'suma aquí las barras de 13.8 kV' in texto            # MT y total: el publicado la clasificó en MT
    assert 'sin esas barras da la cifra publicada' in texto        # MAT y AT: no la puso ahí
    assert 'cifra propia del expediente' not in texto              # ninguna diferencia queda sin explicar
    f120 = r['cuadros']['F-120']
    gama = [c for c in f120['celdas'] if c['clave'][2] == 'GAMA060']
    assert gama and all(c['igual'] for c in gama)                   # comparada por SET, barra y tensión


def test_hoja_por_rotulo_y_variantes_de_trabajo_no_se_leen(tmp_path):
    """107:RF-9 (T15) — la hoja se halla por su rótulo; «F-110 (SET)» es una vista de trabajo y no sustituye al F-110."""
    rep = _rep()

    def extra(wb):
        wb['F-111'].title = 'Hoja potencia FS'
        copia = wb.copy_worksheet(wb['F-110'])
        copia.title = 'F-110 (SET)'
        copia.cell(8, 5, 999.0)

    ruta = _libro(tmp_path, extra=extra)
    f111 = rep.leer_formato_publicado(ruta, 'F-111')
    assert f111['hoja'] == 'Hoja potencia FS' and len(f111['filas']) == len(REGULADOS)
    f110 = rep.leer_formato_publicado(ruta, 'F-110')
    assert f110['hoja'] == 'F-110' and f110['filas'][0]['serie'][0] == pytest.approx(2.0)
    assert f110['columnas'][ANIOS[0]] == 'E' and f110['filas'][0]['fila'] == 8
    with pytest.raises(PitError, match='F-999'):
        rep.leer_formato_publicado(ruta, 'F-999')


def test_el_expediente_guarda_la_reproduccion_y_no_emite_diferencias_sin_causa(tmp_path, registro):
    """107:RF-9 (T15) — reproducción, referencia con huella y diferencias con causa en el expediente; mismos bytes."""
    rep = _rep()
    r = rep.reproducir_resumenes(registro, _libro(tmp_path))
    a = rep.escribir_en_expediente(tmp_path / 'exp', r)
    b = rep.escribir_en_expediente(tmp_path / 'exp2', r)
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]
    datos = json.loads(a[0].read_text(encoding='utf-8'))
    assert datos['referencia']['sha256'] == r['referencia']['sha256'] and 'F-119' in datos['cuadros']
    malo = json.loads(json.dumps(r))
    malo['cuadros']['F-120']['diferencias'] = [{'id': 'F-120!E8', 'causa': ''}]
    with pytest.raises(PitError, match='sin causa'):
        rep.escribir_en_expediente(tmp_path / 'exp3', malo)


def _acta(r, revisor='revisor-b', origen=None):
    rep = _rep()
    ids = ['F-119!D5', 'F-120!E8', 'F-121!H10']
    valores = {c['id']: c['publicado'] for q in r['cuadros'].values() for c in q['celdas']}
    return {'revisor': revisor, 'origen': origen or rep.ORIGEN_REVISOR, 'fecha': '2030-01-15',
            'muestra': [{'id': i, 'publicado': valores[i], 'observacion': f'leída en el libro: {i}'} for i in ids]}


def test_cotejo_de_un_revisor_independiente_queda_como_observaciones_de_t11(tmp_path, registro):
    """107:RF-9, RF-10 (T16) — acta con celda, valor publicado, del conversor, diferencia y observación, por la vía de T11."""
    rep = _rep()
    r = rep.reproducir_resumenes(registro, _libro(tmp_path))
    cot = rep.cotejar(r, _acta(r), implementador='implementador-a')
    assert cot['origen'] == 'maestro/revisor independiente' and cot['revisor'] == 'revisor-b'
    assert cot['conformes'] == 3 and len(cot['muestra']) == 3
    fila = cot['muestra'][1]
    assert set(fila) >= {'id', 'publicado_revisor', 'conversor', 'diferencia', 'observacion'}
    assert fila['diferencia'] == pytest.approx(0.0)
    obs = cot['observaciones']
    assert [o.afecta for o in obs] == ['celda'] * 3 and obs[0].enlace['id'] == obs[0].referencia
    assert all(o.respuesta.startswith('conforme') for o in obs)
    escritos = rep.escribir_en_expediente(tmp_path / 'exp', r, cot)
    assert [p.name.split('_')[0] for p in escritos] == ['resumenes', 'cotejo', 'observaciones']


def test_cotejo_con_una_lectura_distinta_responde_con_la_diferencia(tmp_path, registro):
    """107:RF-10 (T16) — si el revisor lee otra cifra, la observación lo dice con la diferencia."""
    rep = _rep()
    r = rep.reproducir_resumenes(registro, _libro(tmp_path))
    acta = _acta(r)
    acta['muestra'][0]['publicado'] += 1.0
    cot = rep.cotejar(r, acta, implementador='implementador-a')
    assert cot['conformes'] == 2 and cot['muestra'][0]['lectura_coincide'] is False
    assert cot['muestra'][0]['diferencia'] == pytest.approx(-1.0)
    assert cot['observaciones'][0].respuesta.startswith('diferencia')


@pytest.mark.parametrize('cambio, error', [
    ({'revisor': 'Implementador-A'}, 'es el implementador'),
    ({'origen': 'implementador'}, 'origen'),
    ({'revisor': ''}, 'no nombra'),
    ({'muestra': [{'id': 'F-120!Z99', 'publicado': 1.0}]}, 'no la tiene'),
])
def test_cotejo_sin_independencia_u_origen_se_rechaza(tmp_path, registro, cambio, error):
    """107:RF-10 (T16) — el implementador no se coteja a sí mismo y el acta declara su origen."""
    rep = _rep()
    r = rep.reproducir_resumenes(registro, _libro(tmp_path))
    with pytest.raises(PitError, match=error):
        rep.cotejar(r, {**_acta(r), **cambio}, implementador='implementador-a')
