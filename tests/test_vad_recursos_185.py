"""Tarjeta RN-IMP (specs 107 y 108): los recursos de reconsideración contra la RCD 185-2026-OS/CD (VAD 2026-2030,
grupo 1). La norma sigue vigente y obligatoria (TUO de la LPAG, DS 006-2026-JUS, art. 216.1), pero lo impugnado se
avisa, SOLO en los conceptos que impugna el recurso de cada empresa, y el aviso llega al estudio del VAD y a su
expediente (``estudio.json``).

Las pruebas con el registro real leen ``config/normativa`` y eligen a cada recurrente por su RUC, que es público;
el nombre de la empresa lo da el registro, nunca la prueba. Las de forma usan un registro sintético. Los ayudantes
devuelven un valor vacío ante RegistroError: así cada prueba falla en el rojo por su propia aserción.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from convertersmartgrid.dominio.perfil_empresa import PerfilEmpresa
from convertersmartgrid.dominio.registro_normativo import RegistroError, cargar_registro
from convertersmartgrid.aplicacion.vad import estudio as vad_estudio

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
R185 = 'RCD 185-2026-OS/CD'
DS006 = 'DS 006-2026-JUS'
NO_SUSPENDE = 'lpag.recurso.no_suspende_ejecucion'
FE = 'vad.perdidas.factores_expansion'
COEF = 'vad.reajuste.coeficientes'
HOY = '2026-11-15'
H = 'c' * 64
#: RUC de las recurrentes que usan las pruebas (escritos publicados por Osinergmin): la de 14 petitorios, la que
#: impugna la TIR, el factor de cubrimiento BT y el COyM, la de dos escritos (que excluye los FE), la del SDT2 (que
#: impugna el FE de MT) y el tercero.
RUC_14_PETITORIOS = '20331898008'
RUC_TIR_COYM = '20106156400'
RUC_DOS_ESCRITOS = '20281512502'
RUC_SDT2 = '20178344952'
RUC_TERCERO = '20613581066'


@pytest.fixture(scope='module')
def registro():
    return cargar_registro(NORMATIVA)


def _avisos(registro, empresa, usados, fecha=HOY):
    try:
        return [a.texto() for a in registro.avisos_de_recurso(empresa, usados, fecha)]
    except (RegistroError, AttributeError):
        return []


def _recurso(registro, ruc):
    try:
        impugnada = registro.norma(R185).impugnada
    except (RegistroError, AttributeError):
        return {}
    return next((r for r in impugnada if r.get('ruc') == ruc), {})


def _empresa(registro, ruc):
    """El nombre de la recurrente en las tablas de la 185, según el registro; '' si no está."""
    return _recurso(registro, ruc).get('empresa', '')


def _no_recurre(registro):
    """Una empresa de la 185 que no recurre, según el registro."""
    recurrentes = {r.get('empresa') for r in getattr(registro.norma(R185), 'impugnada', ())}
    return sorted(set(registro.norma(R185).reglas[0].valor['empresas']) - recurrentes)[0]


def test_concepto_impugnado_lleva_su_aviso_con_la_cita(registro):
    """108:RF-9, 107:RF-8 — el COyM técnico que impugna la recurrente de 14 petitorios (petitorio 11) lleva su aviso,
    con el concepto, la cita y el estado «pendiente de resolución»."""
    avisos = _avisos(registro, _empresa(registro, RUC_14_PETITORIOS), ['COyM técnico'])
    assert len(avisos) == 1, f'el COyM técnico impugnado tendría que llevar un aviso: {avisos}'
    assert 'COyM técnico' in avisos[0] and 'petitorio 11' in avisos[0], avisos[0]
    assert 'pendiente de resolución' in avisos[0] and R185 in avisos[0], avisos[0]


def test_tabla_no_impugnada_de_la_recurrente_no_lleva_aviso(registro):
    """108:RF-9 — la recurrente que impugna la TIR, el factor de cubrimiento BT y el COyM: su tabla de FE y sus
    coeficientes de reajuste, que no impugna, no llevan aviso; su COyM sí."""
    empresa = _empresa(registro, RUC_TIR_COYM)
    assert _avisos(registro, empresa, ['COyM']), 'el COyM impugnado tendría que avisarse'
    assert _avisos(registro, empresa, [FE, COEF, 'pérdidas estándar']) == []


def test_empresa_que_no_recurre_no_lleva_aviso(registro):
    """108:RF-9 — una empresa de la 185 que no recurre: su COyM, su cargo fijo y su VAD no llevan aviso, cuando los de
    la recurrente de 14 petitorios sí (su VNR y su SICODI sí lo llevan, por el tercero: prueba aparte)."""
    usados = ['COyM', 'cargo fijo', 'VAD']
    assert _avisos(registro, _empresa(registro, RUC_14_PETITORIOS), usados), 'la recurrente tendría que llevarlos'
    assert _avisos(registro, _no_recurre(registro), usados) == []


def test_alcance_no_determinado_da_el_aviso_generico(tmp_path, registro):
    """108:RF-9 — un escrito cuyo alcance no se conoce da el aviso genérico de su recurrente, aunque lo usado no
    coincida con nada (hueco nombrado), sintético; la recurrente de dos escritos, ya leídos, no lo lleva."""
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'N-SINT', 'titulo': 'Fijación sintética', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
        'impugnada': [{'recurrente': 'Empresa Sintética', 'condicion': 'empresa_norma', 'empresa': 'Empresa Sintética',
                       'alcance_no_determinado': [{'escrito': 'escrito 1', 'motivo': 'sin leer'}],
                       'fuente': {'documento': 'hoja.pdf', 'sha256': H}, 'estado': 'pendiente de resolución'}]}]}
    (tmp_path / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    avisos = _avisos(cargar_registro(tmp_path / 'r.json'), 'Empresa Sintética', ['tabla cualquiera'])
    assert avisos and avisos[0].startswith(
        'recurso de Empresa Sintética con alcance no determinado (pendiente de resolución)'), avisos
    rec = _recurso(registro, RUC_DOS_ESCRITOS)
    assert rec and 'alcance_no_determinado' not in rec, 'los dos escritos ya están leídos: alcance determinado'


def test_fe_de_mt_impugnado_con_aviso_y_el_de_bt_sin_el(registro):
    """108:RF-9 — la recurrente del SDT2 impugna solo el PPMT y el PEMT: su FE de MT (o la tabla entera) lleva aviso,
    con la cita del Anexo C; su FE de BT, no. Lo que pide es dato del recurso: la tabla sigue con el valor de la 185.
    Ya no lleva el aviso genérico, porque su alcance está determinado."""
    rec = _recurso(registro, RUC_SDT2)
    empresa = rec.get('empresa', '')
    mt = _avisos(registro, empresa, [f'{FE}.PPMT'])
    assert len(mt) == 1 and 'PPMT' in mt[0] and 'petitorio 3.c' in mt[0] and 'párr. 196' in mt[0], mt
    entera = _avisos(registro, empresa, [FE])
    assert len(entera) == 1 and 'PPMT' in entera[0] and 'PEMT' in entera[0], entera
    assert _avisos(registro, empresa, [f'{FE}.PPBT', f'{FE}.PEBT', COEF]) == []
    assert not any('alcance no determinado' in a for a in _avisos(registro, empresa, ['tabla cualquiera']))
    pedido = next((c.get('pedido') for c in rec.get('conceptos', ()) if 'pedido' in c), {})
    assert pedido.get('minimo') == {'PPMT': 1.0359, 'PEMT': 1.0392}, pedido
    assert registro.regla_de_empresa(FE, empresa, HOY).regla.valor['empresas'][empresa]['fe']['PPMT'] != 1.0359


def test_fe_excluido_expresamente_sin_aviso_y_sus_conceptos_con_el(registro):
    """108:RF-9 — la recurrente de dos escritos excluye los FE (pág. 4, V. Alcance): su FE va sin aviso, y sus
    petitorios (los factores de IGV de la Amazonía, la tercera pretensión) con él."""
    rec = _recurso(registro, RUC_DOS_ESCRITOS)
    empresa = rec.get('empresa', '')
    igv = _avisos(registro, empresa, ['factores de IGV de la Amazonía'])
    assert len(igv) == 1 and 'tercera pretensión principal' in igv[0], igv
    assert 'no son materia del recurso' in rec.get('nota', '')
    assert _avisos(registro, empresa, [FE, f'{FE}.PPMT']) == []


def test_el_aviso_llega_al_estudio_y_a_su_expediente(tmp_path, registro):
    """108:RF-9 — el estudio del VAD de la recurrente que impugna el COyM lleva su aviso, en el objeto y en su
    ``estudio.json``, al crearlo y al comprobarlo, y no lo lleva por su FE; el aviso no cambia la vigencia."""
    rec = _recurso(registro, RUC_TIR_COYM)
    perfil = PerfilEmpresa(nombre=rec.get('empresa') or 'sin recurrente', crs_origen='EPSG:32719')
    creado = vad_estudio.crear_estudio(tmp_path, perfil, grupo=1, periodo='2026-2030', version_tdr='tdr-x',
                                       registro=registro, usos={FE: ('pérdidas estándar', 'COyM')})
    ruta = tmp_path / 'vad' / creado.id / 'estudio.json'
    en_disco = json.loads(ruta.read_text(encoding='utf-8')).get('avisos') or []
    assert rec and any(rec['recurrente'] in a and 'operación y mantenimiento' in a for a in en_disco), en_disco
    comprobado = vad_estudio.comprobar_estudio(tmp_path, creado.id, registro, HOY)
    assert list(getattr(comprobado, 'avisos', ())) == en_disco
    assert json.loads(ruta.read_text(encoding='utf-8')).get('avisos') == en_disco
    assert not any('recurso' in m for m in comprobado.motivos), comprobado.motivos
    solo_fe = vad_estudio.crear_estudio(tmp_path / 'b', perfil, grupo=1, periodo='2026-2030', version_tdr='tdr-x',
                                        registro=registro, usos={FE: ('pérdidas estándar',)})
    assert getattr(solo_fe, 'avisos', None) == ()


def test_art_216_del_ds_006_2026_jus_y_la_185_sigue_obligatoria(registro):
    """107:RF-8 — la regla del art. 216 del TUO vigente (DS 006-2026-JUS), con su cita, y la 185-2026 sigue
    vigente_comprobada y obligatoria aunque esté impugnada; la tabla de FE de una recurrente también."""
    try:
        rv = registro.regla(NO_SUSPENDE, HOY)
    except RegistroError:
        rv = None
    assert rv is not None and rv.norma.acto == DS006 and rv.obligatoria, 'falta la regla del art. 216 obligatoria'
    assert rv.regla.articulo_o_anexo.startswith('art. 216')
    assert 'no suspenderá la ejecución del acto impugnado' in rv.regla.cita_literal
    assert rv.norma.vigencia_desde == '2026-05-01' and not rv.norma.vigente_en('2026-04-30')
    assert 'NO trae cláusula de vigencia propia' in rv.norma.nota and 'art. 109 de la Constitución' in rv.norma.nota
    assert 'H1437910' in rv.norma.version and 'NO es una huella estable' in rv.norma.nota
    r185 = registro.norma(R185)
    assert len(getattr(r185, 'impugnada', ())) == 6, 'la 185 tendría que traer los seis recurrentes'
    assert r185.estado_juridico == 'vigente_comprobada' and r185.obligatoria_en(HOY)
    assert registro.regla_de_empresa(FE, _empresa(registro, RUC_14_PETITORIOS), HOY).obligatoria


def test_tercero_con_su_nombre_literal_y_su_ruc_sin_casarlo(registro):
    """107:RF-8 — el tercero (RUC 20613581066) va con el nombre literal de la hoja informativa y su razón social,
    sin empresa; su aviso va en el SICODI de cualquier empresa de la 185 (aunque no recurra), y no en una de fuera."""
    tercero = _recurso(registro, RUC_TERCERO)
    assert tercero.get('recurrente') == 'ESDE Selva' and tercero.get('condicion') == 'tercero', tercero
    assert 'empresa' not in tercero
    assert 'EMPRESA DE SERVICIOS Y DESARROLLO ELECTRICO DE LA SELVA S.A.C.' in tercero.get('nota', '')
    sicodi = _avisos(registro, _no_recurre(registro), ['SICODI'])
    assert sicodi and all(f'ESDE Selva (RUC {RUC_TERCERO}), tercero' in a for a in sicodi), sicodi
    assert _avisos(registro, 'Distribuidora fuera de la 185', ['SICODI']) == []


def test_un_tercero_no_se_casa_con_una_empresa(tmp_path):
    """107:RF-8 — un recurso de tercero con «empresa» se rechaza al cargar el registro."""
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'N-SINT', 'titulo': 'Fijación sintética', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
        'impugnada': [{'recurrente': 'Tercero Sintético', 'condicion': 'tercero', 'empresa': 'Empresa Sintética',
                       'conceptos': [{'concepto': 'precios', 'cita': 'pág. 1', 'afecta': ['sicodi']}],
                       'fuente': {'documento': 'hoja.pdf', 'sha256': H}, 'estado': 'pendiente de resolución'}]}]}
    (tmp_path / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(RegistroError, match='tercero'):
        cargar_registro(tmp_path / 'r.json')
