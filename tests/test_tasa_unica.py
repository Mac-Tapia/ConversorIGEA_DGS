"""UNA-TASA (orden de c3, 2026-11-15) — la tasa del art. 79 de la LCE, una sola vez en el registro, y el FRC, una sola
fórmula en el código (107:RF-7, 107:RF-11, 108:RF-9, 108:RF-13, 108:RF-17).

La regla principal es ``pit.tasa_actualizacion`` (DL 25844, la fuente de derecho); ``vad.tasa_actualizacion`` es una
remisión ``{"mismas_que": "pit.tasa_actualizacion"}`` con la cita del TdR. El FRC (factor de recuperación del capital)
sale solo de ``convertersmartgrid.util.frc``: lo comprueba un análisis del árbol sintáctico de todo ``src/``. La
mutación de la tasa se hace en una copia del registro real en ``tmp_path``; la red, la demanda y los costos del PIT son
los sintéticos y sorteados de ``test_pit_coym_registro`` (ninguna cifra de una empresa).
"""
from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

from test_pit_coym_registro import CI, MONEDA, VIGENTES, _alta, _caso, _una

from convertersmartgrid.registro_normativo import RegistroError, cargar_registro
from convertersmartgrid.vad import pide_vad
from convertersmartgrid.vad.pide_vad import CONTRATO, VadNivel, incorporar_pide, pide_desde_dict

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'src'
NORMATIVA = RAIZ / 'config' / 'normativa'
CONFIG_VAD = RAIZ / 'config' / 'vad'
RESULTADOS = CONFIG_VAD / 'tdr_vad_2026_resultados.json'
LCE = 'dl_25844_lce.json'
#: Fechas en que rigen a la vez el TdR del VAD (anexo de la RCD 033-2026, desde el 26-02-2026) y la LCE; None = sin fecha.
FECHAS = [None, '2026-02-26', '2026-11-15', '2027-04-30', '2030-12-31', '2045-06-30']
BASE = {'N1': VadNivel(anualidad=100.0, oym=10.0, demanda=10.0)}
KW = {'ambito_fonafe': True, 'periodo': '2041-2045', 'moneda': 'XUS'}


def _frc_a_mano(i: float, n: int) -> float:
    """Oráculo independiente de la prueba, i·(1+i)^n / ((1+i)^n − 1); el código no lo usa."""
    return i * (1 + i) ** n / ((1 + i) ** n - 1)


def _copia_del_registro(tmp_path: Path, tasa: float | None = None) -> tuple[Path, Path]:
    """Copia ``config/normativa`` y ``config/vad`` en ``tmp_path``; con ``tasa``, la regla de la LCE pasa a valer eso."""
    normativa, vad = tmp_path / 'normativa', tmp_path / 'vad'
    shutil.copytree(NORMATIVA, normativa)
    shutil.copytree(CONFIG_VAD, vad)
    if tasa is not None:
        datos = json.loads((normativa / LCE).read_text(encoding='utf-8'))
        regla = next(r for n in datos['normas'] for r in n['reglas'] if r['clave'] == 'pit.tasa_actualizacion')
        regla['valor'] = tasa
        (normativa / LCE).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding='utf-8')
    return normativa, vad


def _pide(anios: int):
    return pide_desde_dict({
        'contrato': CONTRATO, 'id': 'pide-sintetico-una-tasa', 'estado': 'aprobado', 'acto_aprobacion': 'rcd-sintetica',
        'periodo': '2041-2045', 'moneda': 'XUS', 'huella': 'e' * 64,
        'niveles': {'N1': {'inversion': [100.0] * anios, 'oym': [4.0] * anios, 'demanda': [1.0] * anios}}})


def _vad_a_mano(i: float, frc: float, anios: int) -> float:
    """El VAD ajustado de BASE con el PIDE de ``_pide`` y la fórmula del TdR (numeral 7.5), calculado a mano."""
    descuento = [(1 + i) ** (n - 1) for n in range(1, anios + 1)]
    return (100 + 10 + sum(100 * frc / d + 4 / 4 for d in descuento)) / (10 + sum(1 / d for d in descuento))


# ------------------------------------------------------------------------------------------- (a) una sola tasa
def test_las_dos_claves_dan_el_mismo_valor_en_cualquier_fecha(tmp_path):
    """107:RF-7, 108:RF-9, 108:RF-13 — ``vad.tasa_actualizacion`` no tiene valor propio: remite a la principal
    ``pit.tasa_actualizacion`` (DL 25844, art. 79) y conserva la cita del TdR; en cualquier fecha en que rigen las dos
    dan el mismo valor, de la misma norma, y obligan. Si una modificatoria (sintética) cambiara la tasa de la LCE, la
    remisión daría la nueva desde su vigencia y la anterior antes."""
    datos = json.loads(RESULTADOS.read_text(encoding='utf-8'))
    remision = next(r for r in datos['reglas'] if r['clave'] == 'vad.tasa_actualizacion')
    assert remision['valor'] == {'mismas_que': 'pit.tasa_actualizacion'}, (
        f'vad.tasa_actualizacion tiene valor propio ({remision["valor"]!r}): la tasa del art. 79 está dos veces')
    assert 'artículo 79 de la LCE' in remision['cita_literal'] and remision['lineas']
    registro = cargar_registro(NORMATIVA, CONFIG_VAD)
    for fecha in FECHAS:
        principal = registro.regla('pit.tasa_actualizacion', fecha)
        remitida = pide_vad.regla_remitida(registro, 'vad.tasa_actualizacion', fecha)
        assert remitida.valor == principal.regla.valor, fecha
        assert remitida.principal.norma.acto == 'DL 25844' and remitida.remision.regla.clave == 'vad.tasa_actualizacion'
        assert remitida.obligatoria, fecha
    normativa, vad = _copia_del_registro(tmp_path)
    regla_10 = {'clave': 'pit.tasa_actualizacion', 'valor': 0.10, 'unidad': 'real anual (fracción)',
                'articulo_o_anexo': 'art. 79', 'lineas': '1', 'cita_literal': '«la nueva Tasa de Actualización»'}
    (normativa / 'zz_lce_sintetica.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'DS-SINTETICO-79', 'titulo': 'Modificatoria sintética del art. 79', 'estado_juridico': 'vigente_comprobada',
        'sha256': 'a' * 64, 'vigencia_desde': '2031-01-01', 'modifica': ['DL 25844'], 'reglas': [regla_10]}]}),
        encoding='utf-8')
    modificado = cargar_registro(normativa, vad)
    for fecha, esperado in (('2030-12-31', 0.12), ('2031-01-01', 0.10), ('2045-06-30', 0.10)):
        assert modificado.regla('pit.tasa_actualizacion', fecha).regla.valor == esperado
        assert pide_vad.regla_remitida(modificado, 'vad.tasa_actualizacion', fecha).valor == esperado, fecha


# --------------------------------------------------------------------------------------------- (b) un solo FRC
def _es_uno(n: ast.AST) -> bool:
    return isinstance(n, ast.Constant) and not isinstance(n.value, bool) and n.value == 1


def _potencia_de_uno_mas(n: ast.AST, nombres: set[str]) -> bool:
    """``(1 + x) ** y`` (o ``(x + 1) ** y``), o un nombre al que se le asignó eso en la misma función."""
    if isinstance(n, ast.Name):
        return n.id in nombres
    return (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow) and isinstance(n.left, ast.BinOp)
            and isinstance(n.left.op, ast.Add) and (_es_uno(n.left.left) or _es_uno(n.left.right)))


def _formulas_de_frc(arbol: ast.Module) -> set[tuple[str, int]]:
    """(función, línea) de cada FRC escrito a mano: ``… / ((1+i)^n − 1)``, ``… / (1 − (1+i)^−n)`` o el 0,124144."""
    hallados: set[tuple[str, int]] = set()
    ambitos: list[tuple[str, ast.AST]] = [('<módulo>', arbol)]
    ambitos += [(n.name, n) for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for nombre, ambito in ambitos:
        potencias = {t.id for n in ast.walk(ambito) if isinstance(n, ast.Assign) and _potencia_de_uno_mas(n.value, set())
                     for t in n.targets if isinstance(t, ast.Name)}
        for n in ast.walk(ambito):
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and isinstance(n.right, ast.BinOp) \
                    and isinstance(n.right.op, ast.Sub):
                resta = n.right
                if _es_uno(resta.right) and _potencia_de_uno_mas(resta.left, potencias):
                    hallados.add((nombre, n.lineno))
                if _es_uno(resta.left) and isinstance(resta.right, ast.BinOp) and isinstance(resta.right.op, ast.Pow) \
                        and isinstance(resta.right.right, ast.UnaryOp) and _potencia_de_uno_mas(resta.right, set()):
                    hallados.add((nombre, n.lineno))
            if isinstance(n, ast.Constant) and isinstance(n.value, float) and round(n.value, 6) == 0.124144:
                hallados.add((f'{nombre} (literal 0,124144)', n.lineno))
    return hallados


def _frc_en_src() -> dict[str, set[str]]:
    """Fichero de ``src/`` → las funciones que escriben un FRC; la de un módulo anidado cuenta en su función."""
    salida: dict[str, set[str]] = {}
    for ruta in sorted(SRC.rglob('*.py')):
        hallados = _formulas_de_frc(ast.parse(ruta.read_text(encoding='utf-8'), filename=str(ruta)))
        funciones = {f for f, _ in hallados}
        # Una fórmula dentro de una función aparece también en el ámbito del módulo: cuenta solo en su función.
        if funciones - {'<módulo>'}:
            funciones.discard('<módulo>')
        if funciones:
            salida[ruta.relative_to(SRC).as_posix()] = funciones
    return salida


def test_el_frc_sale_de_una_sola_funcion():
    """107:RF-11, 108:RF-13 — en todo ``src/`` el FRC se escribe una sola vez, en ``util.frc``, y no hay ningún
    0,124144 escrito; ``pide_economia.frc`` es la misma función (el PIT la importa de ahí) y la anualidad del libro de
    la empresa y la del VAD salen de ella. El detector no es vacío: encuentra la de ``util.frc``."""
    hallados = _frc_en_src()
    assert hallados == {'convertersmartgrid/util.py': {'frc'}}, (
        f'FRC escrito fuera de util.frc (o util.frc no lo tiene): {hallados}')
    from convertersmartgrid import datos_empresa, pide_economia, util
    from convertersmartgrid.pit import alternativas
    assert pide_economia.frc is util.frc and alternativas.frc is util.frc and pide_vad.factor_recuperacion is util.frc
    assert util.frc(0.12, 30) == pytest.approx(_frc_a_mano(0.12, 30)) and round(util.frc(0.12, 30), 6) == 0.124144
    assert util.frc(0.0, 30) == pytest.approx(1 / 30)
    assert datos_empresa.anualidad(250.0, 0.07, 12) == pytest.approx(250.0 * _frc_a_mano(0.07, 12))
    with pytest.raises(ValueError, match='vida útil'):
        util.frc(0.12, 0)


# ------------------------------------------------------------------------------ (c) la LCE mueve el VAD y el PIT
def test_una_mutacion_de_la_lce_mueve_el_vad_y_el_pit(tmp_path):
    """107:RF-7, 108:RF-17, 108:RF-13 — con la tasa de la LCE cambiada del 12 % al 10 % en una copia del registro,
    el VAD ajustado con el PIDE y la anualidad y el valor presente del PIT se mueven a la vez, y cada uno coincide con
    el cálculo a mano con el 10 %. El FRC del 10 % ya no es el 0,124144 que publica el TdR: el VAD usa el calculado y
    lo avisa."""
    normativa, vad = _copia_del_registro(tmp_path / 'r12')
    con_12 = cargar_registro(normativa, vad)
    normativa, vad = _copia_del_registro(tmp_path / 'r10', tasa=0.10)
    con_10 = cargar_registro(normativa, vad)
    anios = con_12.regla('vad.pide.anios').regla.valor
    vad_12 = incorporar_pide(con_12, BASE, _pide(anios), **KW)
    vad_10 = incorporar_pide(con_10, BASE, _pide(anios), **KW)
    assert vad_12.incorporado and vad_10.incorporado, (vad_12.avisos, vad_10.avisos)
    assert vad_10.vad_ajustado['N1'] != pytest.approx(vad_12.vad_ajustado['N1']), (
        'el VAD no se mueve con la tasa de la LCE: lee su propia copia de la tasa')
    assert vad_10.vad_ajustado['N1'] == pytest.approx(_vad_a_mano(0.10, _frc_a_mano(0.10, 30), anios))
    assert vad_12.vad_ajustado['N1'] == pytest.approx(_vad_a_mano(0.12, _frc_a_mano(0.12, 30), anios))
    assert not vad_12.avisos and any('vad.frc' in a and '0.106079' in a for a in vad_10.avisos), vad_10.avisos
    assert vad_10.reglas['pit.tasa_actualizacion'] != vad_12.reglas['pit.tasa_actualizacion']
    red, demanda, _, trafo = _caso(VIGENTES)
    cambios = [_alta({**trafo, 'id': f'{trafo["id"]}-b'}, 'TP-SINT')]
    _, pit_12 = _una(red, demanda, VIGENTES, con_12, cambios)
    _, pit_10 = _una(red, demanda, VIGENTES, con_10, cambios)
    assert pit_12.completa and pit_10.completa, (pit_12.motivos, pit_10.motivos)
    assert pit_12.anualidad[MONEDA] == pytest.approx(CI * _frc_a_mano(0.12, 30))
    assert pit_10.anualidad[MONEDA] == pytest.approx(CI * _frc_a_mano(0.10, 30))
    assert pit_10.valor_presente[MONEDA] != pytest.approx(pit_12.valor_presente[MONEDA])


# -------------------------------------------------------------------------------------- remisiones mal formadas
@pytest.mark.parametrize('destino,texto', [('pit.no_registrada', 'que no está'),
                                           ('vad.tasa_actualizacion', 'circular'), ('', 'vacía')])
def test_una_remision_rota_se_nombra_y_no_incorpora(tmp_path, destino, texto):
    """107:RF-7, 108:RF-17 — una remisión a una clave que no está, circular o vacía no se resuelve en silencio:
    ``regla_remitida`` lanza RegistroError con la cadena, y el VAD no incorpora el PIDE y lo dice."""
    assert hasattr(pide_vad, 'regla_remitida'), 'el VAD no sigue las remisiones «mismas_que» del registro'
    reglas = [{'clave': c, 'valor': v, 'cita_literal': f'«{c}»', 'lineas': '1'} for c, v in (
        ('vad.frc', 1.25), ('vad.vida_util_anios', 1), ('vad.tasa_actualizacion', {'mismas_que': destino}),
        ('vad.pide.anios', 1), ('vad.formula.pide_ajustado', '(aVNR0 + OyM0 + suma(n, aDVNR)) / POT0'))]
    ruta = tmp_path / 'reg' / 'tdr.json'
    ruta.parent.mkdir()
    ruta.write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': 'vigente_comprobada', 'sha256': 'c' * 64,
        'vigencia_desde': '2001-01-01', 'reglas': reglas}]}), encoding='utf-8')
    registro = cargar_registro(ruta.parent)
    with pytest.raises(RegistroError, match=texto):
        pide_vad.regla_remitida(registro, 'vad.tasa_actualizacion')
    pide = pide_desde_dict({'contrato': CONTRATO, 'id': 'p', 'estado': 'aprobado', 'acto_aprobacion': 'a',
                            'periodo': '2041-2045', 'moneda': 'XUS', 'huella': 'e' * 64,
                            'niveles': {'N1': {'inversion': [1.0], 'oym': [1.0], 'demanda': [1.0]}}})
    r = incorporar_pide(registro, BASE, pide, **KW)
    assert not r.incorporado and 'vad.tasa_actualizacion' in r.avisos[0] and texto in r.avisos[0]


def test_un_mismas_que_con_datos_es_informativo():
    """107:RF-7 — solo remite un valor que es exactamente ``{"mismas_que": "<clave>"}``; una lista de equivalencias
    junto a otros datos (las fórmulas de pérdidas) es el valor propio de la regla y se devuelve tal cual."""
    assert hasattr(pide_vad, 'regla_remitida'), 'el VAD no sigue las remisiones «mismas_que» del registro'
    registro = cargar_registro(NORMATIVA, CONFIG_VAD)
    propia = pide_vad.regla_remitida(registro, 'vad.frc')
    assert propia.principal is propia.remision and propia.valor == 0.124144
    assert propia.huella() == registro.regla('vad.frc').huella()
    assert pide_vad.remite_a({'mismas_que': ['a', 'b'], 'integral': 'x'}) is None
    assert pide_vad.remite_a({'mismas_que': 'pit.tasa_actualizacion'}) == 'pit.tasa_actualizacion'


# ---------------------------------------------------------------- (d) UNA-TASA v2: una remisión, un solo resolvedor
def test_la_remision_se_resuelve_en_un_solo_sitio():
    """107:RF-7, 108:RF-9 — la remisión «mismas_que» la resuelve SOLO el registro (``regla_remitida`` de
    ``registro_normativo``): ningún otro módulo de ``src/`` lee esa clave, y el PIDE del VAD, el aVNR del SER, el
    capital de trabajo y la tasa «i» del Anexo 5 usan esa misma función, no una copia."""
    from convertersmartgrid import registro_normativo as rn
    from convertersmartgrid.vad import costos, coym, modelo_urbano
    lectores = set()
    for ruta in sorted(SRC.rglob('*.py')):
        arbol = ast.parse(ruta.read_text(encoding='utf-8'), filename=str(ruta))
        if any(isinstance(n, ast.Constant) and n.value == 'mismas_que' for n in ast.walk(arbol)):
            lectores.add(ruta.relative_to(SRC).as_posix())
    assert lectores == {'convertersmartgrid/registro_normativo.py'}, (
        f'la remisión «mismas_que» se resuelve en más de un sitio, o fuera del registro: {sorted(lectores)}')
    unico = getattr(rn, 'regla_remitida', None)
    distintos = sorted(m.__name__ for m in (pide_vad, costos, coym, modelo_urbano)
                       if unico is None or getattr(m, 'regla_remitida', None) is not unico)
    assert not distintos, f'estos módulos del VAD no siguen la remisión con el resolvedor del registro: {distintos}'


def test_el_vad_entero_sigue_la_tasa_de_la_lce(tmp_path):
    """107:RF-7, 108:RF-9, 108:RF-13 — con la tasa de la LCE cambiada al 10 % en una copia del registro, la «i» del
    Anexo 5, el contraste del capital de trabajo y el aVNR del SER leen el 10 %, no un 12 % propio: la «i» vale 0,10
    y sale de la regla de la LCE; el CCT (que el Anexo 7 calcula al 12 %) avisa de que no es la tasa de la LCE; y el
    aVNR del SER, cuyo FRC ya no cuadra con el 0,124144 que publica el TdR, se niega y nombra la tasa del 10 %. Con
    el registro real, los tres leen el 12 % de la LCE, sin aviso, y el aVNR cita la regla de la LCE."""
    from datetime import date

    from convertersmartgrid.vad import VadError, costos, coym, modelo_urbano
    normativa, vad = _copia_del_registro(tmp_path / 'r12')
    con_12 = cargar_registro(normativa, vad)
    normativa, vad = _copia_del_registro(tmp_path / 'r10', tasa=0.10)
    con_10 = cargar_registro(normativa, vad)

    i_12, i_10 = modelo_urbano.tasa_i(con_12), modelo_urbano.tasa_i(con_10)
    assert (i_12.tasa, i_10.tasa) == (pytest.approx(0.12), pytest.approx(0.10)), (
        f'la «i» del Anexo 5 no sigue la tasa de la LCE: con el 12 % y el 10 % da {i_12.tasa} y {i_10.tasa}')
    assert i_10.principal.regla.clave == 'pit.tasa_actualizacion' and i_10.vida_util == 30

    inicio = date(2026, 11, 1)
    saldos = [-100.0] * len(coym.dias_del_periodo(inicio))
    cct_12 = coym.capital_de_trabajo(saldos, con_12, inicio=inicio)
    cct_10 = coym.capital_de_trabajo(saldos, con_10, inicio=inicio)
    contraste = [a for a in cct_10.avisos if 'vad.tasa_actualizacion' in a]
    assert contraste and '0.1)' in contraste[0] and 'no es la de' in contraste[0], (
        f'el capital de trabajo no contrasta su tasa con la de la LCE: {cct_10.avisos}')
    assert not any('no es la de' in a or 'no se pudo contrastar' in a for a in cct_12.avisos), cct_12.avisos
    assert cct_10.reglas['vad.tasa_actualizacion'] != cct_12.reglas['vad.tasa_actualizacion']

    assert round(costos.ffr(0.0197, registro=con_12), 6) == 0.199494
    _vida, _frc, citas = costos._factores(con_12, None)
    assert 'pit.tasa_actualizacion' in citas and 'DL 25844' in citas['pit.tasa_actualizacion']['cita'], (
        f'el aVNR del SER no cita la tasa de la LCE a la que remite el TdR: {sorted(citas)}')
    with pytest.raises(VadError, match=r'\(0\.1\)'):
        costos.ffr(0.0197, registro=con_10)
