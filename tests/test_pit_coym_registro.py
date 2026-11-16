"""Spec 107, P-REG — la tasa, la vida útil y el COyM del PIT desde el registro normativo REAL (107:RF-5, 107:RF-7,
107:RF-8 y sus aclaraciones): la tasa del art. 79 de la LCE con su verificación estructurada, la vida útil del
art. 24.2 de la Norma Tarifas, y los porcentajes del COyM de la RCD 163-2021-OS/CD por elemento, según su ubicación,
su nivel de tensión y el año, con su vigencia; un año sin porcentaje publicado es un hueco nombrado. La red, la
demanda y los costos son sintéticos y sorteados (``datos_pit``): ninguna cifra de una empresa."""
from __future__ import annotations

import copy

import pytest

from datos_pit import perfil_a
from test_pit_armado import _armar, _caso as _caso_armado
from test_pit_formatos import NORMATIVA

from convertersmartgrid.costos_fuentes import Costo, FuenteCostos, TablaCostos
from convertersmartgrid.pit.alternativas import evaluar
from convertersmartgrid.pit.ambito import areas_del_perfil, reunir
from convertersmartgrid.pit.diagnostico import agregar_demanda
from convertersmartgrid.pit.expediente import TIPO_DIAGNOSTICO, TIPO_ESTUDIO
from convertersmartgrid.pit.red_area import desde_ambito
from convertersmartgrid.registro_normativo import RegistroError, cargar_registro

MONEDA = 'XTS'
CI = 900.0
#: Lo que da el cuadro de la 163-2021 (sustituye el de la 080-2021), por ubicación y nivel: el dato que se comprueba.
CUADRO_163 = {'costa': {'MAT': 3.36, 'AT': 2.83, 'MT': 4.49}, 'sierra': {'MAT': 3.40, 'AT': 3.51, 'MT': 4.86},
              'selva': {'MAT': 3.49, 'AT': 3.54, 'MT': 4.65}}
#: Años con el cuadro vigente todo el año (01-05-2021 a 30-04-2027), y un horizonte cuyo segundo año es posterior a
#: abril de 2027.
VIGENTES = [2023, 2024, 2025]
CON_POSTERIOR = [2026, 2028]


def _regla(registro, clave, fecha=None):
    try:
        return registro.regla(clave, fecha)
    except RegistroError:
        return None


@pytest.fixture(scope='module')
def registro():
    return cargar_registro(NORMATIVA)


def _tablas():
    fuente = FuenteCostos('Módulos sintéticos', 'transmision', 'SINT-001', 2001, MONEDA, 'https://ejemplo.invalid',
                          '2001-01-01', 'f' * 64)
    filas = {(c, '', '', ''): Costo(c, '', '', '', f'Módulo {c}', {'total': CI}, fuente, unidad='u')
             for c in ('TP-SINT', 'CE-SINT')}
    return {'transmision': TablaCostos(fuente, filas)}


def _caso(anios, seed=19):
    """Red, demanda (llevada a ``anios``) y la SET y el transformador de la primera SET del caso sorteado."""
    caso = perfil_a(seed)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, caso['elementos']))
    demanda = agregar_demanda(area, red, caso['proyeccion'])
    s = caso['pistas']['sets'][0]
    trafo = next(e for e in red.de_tipo('trafo2') if e['set'] == s)
    return red, {n: demanda[o] for n, o in zip(anios, caso['anios'])}, s, trafo


def _alta(elemento, codigo):
    return {'accion': 'alta', 'elemento': elemento, 'costo': {'codigo': codigo, 'cantidad': 1, 'unidad': 'u'}}


def _una(red, demanda, anios, registro, cambios, ubicacion='costa'):
    comp = evaluar(red, [{'nombre': 'alt', 'cambios': cambios}], demanda, anios, registro, _tablas(),
                   ubicacion=ubicacion)
    return comp, comp.alternativas[0]


def test_las_tres_reglas_cargan_con_su_cita(registro):
    """107:RF-7 — la tasa (art. 79 de la LCE, en el SPIJ), la vida útil (art. 24.2 de la RCD 217-2013, pág. 41) y el
    cuadro del COyM (art. 1 de la RCD 163-2021, que sustituye el de la 080-2021) cargan con su norma y su cita."""
    tasa = _regla(registro, 'pit.tasa_actualizacion')
    assert tasa is not None, 'el registro no trae pit.tasa_actualizacion'
    assert tasa.regla.valor == 0.12 and tasa.norma.acto == 'DL 25844' and tasa.regla.articulo_o_anexo == 'art. 79'
    assert 'H756722' in tasa.regla.pagina and '12% real anual' in tasa.regla.cita_literal and tasa.regla.citada
    assert len(tasa.norma.sha256) == 64 and tasa.norma.url.startswith('https://spij.minjus.gob.pe/')
    assert tasa.obligatoria and tasa.norma.vigencia_desde == '1992-11-19'
    vida = _regla(registro, 'pit.vida_util_anios')
    assert vida is not None and vida.regla.valor == 30 and vida.norma.acto == 'RCD 217-2013-OS/CD'
    assert vida.regla.pagina == '41' and 'vida útil de 30 años' in vida.regla.cita_literal
    coym = _regla(registro, 'pit.coym_pct', '2025-06-01')
    assert coym is not None, 'el registro no trae pit.coym_pct vigente en 2025'
    assert coym.norma.acto == 'RCD 163-2021-OS/CD' and coym.obligatoria and coym.regla.citada
    assert 'RCD 080-2021-OS/CD' in coym.norma.modifica
    assert coym.regla.valor['porcentajes'] == CUADRO_163
    assert coym.regla.cita_literal.startswith('Artículo 1.- Sustituir el cuadro')
    assert 'lado primario' in coym.regla.cita_literal and 'celdas de Alimentadores' in coym.regla.cita_literal


def test_tasa_con_su_verificacion_estructurada(registro):
    """Aclaración de 107:RF-8 — la tasa lleva en el registro su verificación como dato, no en una nota: fecha,
    resultado «sin modificaciones posteriores a 2009» y sus fuentes (el SPIJ consolidado al 22-03-2026 con el sha del
    tramo del art. 79, la compilación del MINEM de 2009 y la RCD 184-2026-OS/CD que la aplica); no lleva pendiente, y
    la comparación la usa como obligatoria, sin aviso de pendiente y con la verificación junto a la regla."""
    tasa = _regla(registro, 'pit.tasa_actualizacion')
    verificacion = getattr(tasa.regla, 'verificacion', None) if tasa is not None else None
    assert verificacion, 'la tasa no trae su verificación estructurada'
    assert verificacion['fecha'] == '2026-11-15'
    assert verificacion['resultado'].startswith('sin modificaciones posteriores a 2009')
    fuentes = {f['url']: f for f in verificacion['fuentes']}
    spij = fuentes['https://spij.minjus.gob.pe/spij-ext-web/#/detallenorma/H756722']
    assert spij['sha256'].startswith('fd5fa63a') and spij['consolidado_hasta'] == '2026-03-22'
    assert any('RCD 184-2026-OS/CD' in f['documento'] and '(12%)' in f['cita'] for f in fuentes.values())
    assert any('Marzo 2009' in f['documento'] for f in fuentes.values())
    assert not tasa.regla.pendientes
    red, demanda, _, trafo = _caso(VIGENTES)
    comp, _ = _una(red, demanda, VIGENTES, registro, [_alta({**trafo, 'id': f'{trafo["id"]}-b'}, 'TP-SINT')])
    assert not [a for a in comp.avisos if 'pit.tasa_actualizacion' in a]
    regla = comp.reglas['pit.tasa_actualizacion']
    assert regla['obligatoria'] and regla['verificacion']['resultado'] == verificacion['resultado']


@pytest.mark.parametrize('zona', sorted(CUADRO_163))
def test_coym_por_elemento_segun_nivel_zona_y_vigencia(registro, zona):
    """Aclaración de 107:RF-5 — el COyM es el de cada elemento: su CI por el porcentaje de su ubicación y su nivel,
    del cuadro vigente en cada año; una celda de alimentador de MT dentro de la SET toma el MT, y la ubicación del
    elemento manda sobre la del área. El cuadro deja de regir después de abril de 2027."""
    red, demanda, s, trafo = _caso(VIGENTES)
    otra = next(z for z in sorted(CUADRO_163) if z != zona)
    cambios = [_alta({**trafo, 'id': 'T-n'}, 'TP-SINT'),
               _alta({'id': 'C-mat', 'tipo': 'celda', 'set': s, 'kv': 220.0, 'funcion': 'linea'}, 'CE-SINT'),
               _alta({'id': 'C-mt', 'tipo': 'celda', 'set': s, 'kv': 10.0, 'funcion': 'alimentador',
                      'ubicacion': otra}, 'CE-SINT')]
    comp, alt = _una(red, demanda, VIGENTES, registro, cambios, ubicacion=zona)
    assert alt.completa, alt.motivos
    por = {(d['anio'], d['elemento']): d for d in alt.coym_detalle}
    for anio in VIGENTES[1:]:
        assert por[(anio, 'T-n')]['nivel'] == 'AT' and por[(anio, 'T-n')]['pct'] == CUADRO_163[zona]['AT']
        assert por[(anio, 'C-mat')]['nivel'] == 'MAT' and por[(anio, 'C-mat')]['pct'] == CUADRO_163[zona]['MAT']
        assert por[(anio, 'C-mt')]['ubicacion'] == otra and por[(anio, 'C-mt')]['pct'] == CUADRO_163[otra]['MT']
        assert {d['norma'] for k, d in por.items() if k[0] == anio} == {'RCD 163-2021-OS/CD'}
    esperado = CI * (CUADRO_163[zona]['AT'] + CUADRO_163[zona]['MAT'] + CUADRO_163[otra]['MT']) / 100
    assert alt.coym_anual[MONEDA] == pytest.approx(esperado)
    assert all(alt.coym_por_anio[a][MONEDA] == pytest.approx(esperado) for a in VIGENTES[1:])
    coym = _regla(registro, 'pit.coym_pct', '2025-06-01')
    assert (coym.norma.vigencia_desde, coym.norma.vigencia_hasta) == ('2021-05-01', '2027-04-30')
    assert _regla(registro, 'pit.coym_pct', '2027-06-01') is None


def test_mt_que_no_es_celda_de_alimentador_y_area_sin_ubicacion_son_huecos(registro):
    """Aclaración de 107:RF-5 — el MT del cuadro es solo para celdas de alimentadores de MT dentro de las SET, y la
    ubicación no se inventa: sin ella en el elemento ni en el área, el COyM es un hueco nombrado y la alternativa
    queda incompleta."""
    red, demanda, s, trafo = _caso(VIGENTES)
    _, alt = _una(red, demanda, VIGENTES, registro,
                  [_alta({'id': 'C-x', 'tipo': 'celda', 'set': s, 'kv': 10.0, 'funcion': 'linea'}, 'CE-SINT')])
    assert not alt.completa
    assert any(h['elemento'] == 'C-x' and 'solo para celdas de alimentadores' in h['causa'] for h in alt.huecos)
    _, alt = _una(red, demanda, VIGENTES, registro, [_alta({**trafo, 'id': 'T-n'}, 'TP-SINT')], ubicacion='')
    assert not alt.completa and not alt.valor_presente
    assert any(h['elemento'] == 'T-n' and 'sin ubicación geográfica' in h['causa'] for h in alt.huecos)


def test_transformador_mayor_tension_y_elevador_avisa_la_discrepancia(registro):
    """Aclaración de 107:RF-5 (decisión aceptada por 28) — el transformador toma el nivel de su mayor tensión (17.3 de
    la RCD 217-2013); si es elevador, donde no coincide con el «lado primario» de la 163-2021, se usa igual la mayor
    tensión y la comparación avisa de la discrepancia entre las dos normas, con los dos porcentajes."""
    red, demanda, _, trafo = _caso(VIGENTES)
    comp, alt = _una(red, demanda, VIGENTES, registro, [_alta({**trafo, 'id': 'T-r'}, 'TP-SINT')])
    assert [d['nivel'] for d in alt.coym_detalle if d['elemento'] == 'T-r'][:1] == ['AT']
    assert not [a for a in comp.avisos if 'discrepancia' in a]
    comp, alt = _una(red, demanda, VIGENTES, registro,
                     [_alta({**trafo, 'id': 'T-e', 'funcion': 'elevador'}, 'TP-SINT')])
    assert alt.completa, alt.motivos
    assert {d['pct'] for d in alt.coym_detalle if d['elemento'] == 'T-e'} == {CUADRO_163['costa']['AT']}
    avisos = [a for a in comp.avisos if 'T-e' in a and 'discrepancia' in a]
    assert len(avisos) == 1 and 'lado primario' in avisos[0] and 'mayor tensión' in avisos[0]
    assert f'{CUADRO_163["costa"]["MT"]:g} %' in avisos[0] and f'{CUADRO_163["costa"]["AT"]:g} %' in avisos[0]


def _expediente(tmp_path, anios, ubicacion='costa'):
    """El expediente sintético de punta a punta (test_pit_armado) con el registro REAL solo, llevado a ``anios``."""
    x = _caso_armado(tmp_path)
    x['registro'] = cargar_registro(NORMATIVA)
    mapa = dict(zip(x['caso']['anios'], anios))
    x['caso'] = copy.deepcopy(x['caso'])
    x['caso']['proyeccion'] = [{**f, 'anio_calendario': mapa[f['anio_calendario']]}
                               for f in x['caso']['proyeccion'] if f['anio_calendario'] in mapa]
    x['anios'] = list(anios)
    for c in x['alternativas']['alternativas'][0]['cambios']:
        c['anio'] = anios[1]
    if ubicacion:
        x['perfil']['pit']['areas'][0]['ubicacion'] = ubicacion
    return _armar(x)


def test_anio_posterior_a_abril_2027_es_hueco_y_el_expediente_es_de_diagnostico(tmp_path):
    """Aclaración de 107:RF-5 — un año del PIT después de abril de 2027 no tiene porcentaje de COyM publicado: queda
    con su hueco nombrado, sin suponer ninguno, y el expediente sale «DE DIAGNÓSTICO» con ese pendiente."""
    r = _expediente(tmp_path, CON_POSTERIOR)
    assert r['tipo'] == TIPO_DIAGNOSTICO
    huecos = [p for p in r['pendientes'] if p.get('fichero') == 'alternativas.json']
    assert any(p['campo'].endswith(f'pit.coym_pct.{CON_POSTERIOR[1]}') and 'sin porcentaje de COyM publicado'
               in p['causa'] for p in huecos), r['pendientes']


def test_con_las_reglas_presentes_el_expediente_completo_deja_de_ser_de_diagnostico(tmp_path):
    """Aclaración de 107:RF-5 — con la tasa, la vida útil y el COyM en el registro real, y la ubicación del área en el
    perfil, el expediente sintético completo sale como estudio; sin la ubicación, sigue de diagnóstico y lo dice."""
    r = _expediente(tmp_path / 'con', VIGENTES[:2])
    assert r['tipo'] == TIPO_ESTUDIO, r['pendientes_del_armado']
    r = _expediente(tmp_path / 'sin', VIGENTES[:2], ubicacion='')
    assert r['tipo'] == TIPO_DIAGNOSTICO
    assert any('sin ubicación geográfica' in p['causa'] for p in r['pendientes'])
