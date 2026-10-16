"""Spec 017: configuración, cálculos y redacción de los informes, sin DIgSILENT."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from igea_dgs.estudios_pf import Limites
from igea_dgs.informes import (
    ETAPAS, SOLICITUDES_VIGENTES, TRIFASICA, Caso, ConfigInforme, Devanado, Encabezado, Etapa, Extremo,
    InformeError, Potencia, Solicitud, antecedentes_factibilidad, asunto_propuesto, conclusiones_estudio,
    conclusiones_factibilidad, descripcion_factibilidad, etapa_recomendada, factor_de_carga, factor_de_perdidas, perdida_no_reconocida, perdidas_anuales,
    redactar_cargabilidad, redactar_tension, seguir_evaluando, texto_transformador,
    veredicto_factibilidad)
from igea_dgs.perfil_empresa import carpeta_perfiles, datos_perfil

COMPLETO = {
    'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100},
    'informes': {
        'modelo_factibilidad': 'modelos/factibilidad.docx',
        'modelo_estudio': 'modelos/estudio.docx',
        'bandas_tension_pct': [85, 90, 95, 105],
        'bandas_cargabilidad_pct': [80, 90, 95, 105, 150],
        'proyecto_transmision': 'TRANSMISION',
    },
}


def _modelos(tmp_path):
    (tmp_path / 'modelos').mkdir()
    for tipo in ('factibilidad', 'estudio'):
        (tmp_path / 'modelos' / f'{tipo}.docx').write_bytes(b'PK')


# --------------------------------------------------------------------------- RF-4, RF-5
def test_el_modelo_sale_del_perfil(tmp_path):
    """017:RF-4 — el modelo de cada tipo es el fichero del perfil, relativo a la raíz."""
    _modelos(tmp_path)
    config = ConfigInforme.de_perfil(COMPLETO, tmp_path)
    assert config.modelo('factibilidad') == tmp_path / 'modelos' / 'factibilidad.docx'
    assert config.modelo('estudio') == tmp_path / 'modelos' / 'estudio.docx'
    assert config.faltan('estudio') == []


def test_sin_modelo_no_hay_informe_y_se_dice_la_clave(tmp_path):
    """017:RF-5 — sin el modelo de un tipo, ese tipo no se genera y se nombra la clave."""
    _modelos(tmp_path)
    datos = json.loads(json.dumps(COMPLETO))
    del datos['informes']['modelo_estudio']
    config = ConfigInforme.de_perfil(datos, tmp_path)
    assert config.faltan('estudio') == ['informes.modelo_estudio']
    assert config.faltan('factibilidad') == []
    with pytest.raises(InformeError, match='informes.modelo_estudio'):
        config.modelo('estudio')


def test_modelo_que_no_existe(tmp_path):
    """017:RF-5 — una ruta del perfil que no existe es un error que dice cuál."""
    config = ConfigInforme.de_perfil(COMPLETO, tmp_path)
    with pytest.raises(InformeError, match='No existe el modelo'):
        config.modelo('factibilidad')


def test_sin_perfil_no_se_supone_nada(tmp_path):
    """017:RF-5 — sin perfil faltan modelo, bandas, banda de tensión y umbral."""
    config = ConfigInforme.de_perfil({}, tmp_path)
    assert config.limites is None and config.proyecto_transmision is None
    assert config.faltan('factibilidad') == [
        'informes.modelo_factibilidad', 'informes.bandas_tension_pct',
        'informes.bandas_cargabilidad_pct', 'estudios.tension_min_pu',
        'estudios.tension_max_pu', 'estudios.cargabilidad_max_pct']


# --------------------------------------------------------------------------- RF-13, RF-14
def test_banda_y_umbral_del_perfil(tmp_path):
    """017:RF-13 — la banda de tensión y el umbral salen de la clave «estudios» del perfil."""
    limites = ConfigInforme.de_perfil(COMPLETO, tmp_path).limites
    assert (limites.tension_min_pu, limites.tension_max_pu, limites.cargabilidad_max_pct) == (0.95, 1.05, 100)
    assert limites.origen == 'perfil'


def test_sin_banda_se_pide_sin_suponer(tmp_path):
    """017:RF-14 — sin banda o umbral en el perfil, se piden: nada se completa por defecto."""
    datos = {**COMPLETO, 'estudios': {'tension_min_pu': 0.9}}
    config = ConfigInforme.de_perfil(datos, tmp_path)
    assert config.limites is None
    assert config.faltan('estudio')[-2:] == ['estudios.tension_max_pu', 'estudios.cargabilidad_max_pct']
    a_medias = config.con_limites(tension_max_pu=1.1)
    assert a_medias.limites is None
    completa = a_medias.con_limites(cargabilidad_max_pct=90)
    assert completa.limites.tension_min_pu == 0.9          # el del perfil se conserva
    assert completa.limites.origen == 'operador'
    assert 'estudios.cargabilidad_max_pct' not in completa.faltan('estudio')


def test_banda_imposible_del_operador(tmp_path):
    """017:RF-14 — una banda que deja fuera 1 p.u. es un error, no se corrige."""
    config = ConfigInforme.de_perfil({}, tmp_path)
    with pytest.raises(InformeError, match='1 p.u.'):
        config.con_limites(tension_min_pu=1.02, tension_max_pu=1.05, cargabilidad_max_pct=100)


# --------------------------------------------------------------------------- RF-115
def test_bandas_de_coloreado_del_perfil(tmp_path):
    """017:RF-115 — las bandas de los dos coloreados salen del perfil, crecientes."""
    config = ConfigInforme.de_perfil(COMPLETO, tmp_path)
    assert config.bandas_tension_pct == (85, 90, 95, 105)
    assert config.bandas_cargabilidad_pct == (80, 90, 95, 105, 150)
    for malas in ([90, 85], [], [0, 10], ['a']):
        datos = {'informes': {'bandas_tension_pct': malas}}
        with pytest.raises(InformeError, match='bandas_tension_pct'):
            ConfigInforme.de_perfil(datos, tmp_path)


def test_electro_dunas_trae_las_bandas_del_modelo(tmp_path):
    """017:RF-115 — Electro Dunas hereda las bandas de su modelo EMAPICA; los ficheros no."""
    carpeta = tmp_path / 'perfiles'
    carpeta.mkdir()
    (carpeta / 'electro_dunas.json').write_text(
        (carpeta_perfiles() / 'electro_dunas.json').read_text(encoding='utf-8'), encoding='utf-8')
    activo = tmp_path / 'perfil_empresa.json'
    activo.write_text(json.dumps({'perfil': 'electro_dunas',
                                  'informes': {**COMPLETO['informes'], 'bandas_tension_pct': None}}),
                      encoding='utf-8')
    # La sección del perfil local pisa entera la heredada.
    assert datos_perfil(activo, carpeta=carpeta)['informes']['bandas_tension_pct'] is None
    activo.write_text(json.dumps({'perfil': 'electro_dunas'}), encoding='utf-8')
    config = ConfigInforme.de_perfil(datos_perfil(activo, carpeta=carpeta), tmp_path)
    assert config.bandas_tension_pct == (85, 90, 95, 105)
    assert config.bandas_cargabilidad_pct == (80, 90, 95, 105, 150)
    assert config.modelos == {'factibilidad': None, 'estudio': None}
    assert config.rotulos_cabecera == {'numero': 'INFORME TECNICO', 'referencia': 'REFERENCIA'}
    assert (config.norma, config.regulador) == ('NTCSE', 'Osinergmin')
    assert datos_perfil(tmp_path / 'no_existe.json') == {}


# --------------------------------------------------------------------------- T2: casos
LIMITES = Limites(0.95, 1.05, 100.0, origen='perfil')


def _caso(nombre='Sin proyecto', vmin=0.97, carga=60.0, **extra):
    datos = {'nombre': nombre, 'converge': True, 'fuente': {'kw': 2791, 'kvar': 999},
             'perdidas': {'kw': 40.10, 'kvar': 54.99},
             'tension_min': {'A': {'valor': vmin, 'donde': 'N1'}, 'B': {'valor': vmin + 0.01, 'donde': 'N2'},
                             'C': {'valor': vmin + 0.02, 'donde': 'N3'}},
             'tension_max': {'valor': 1.0, 'donde': 'CAB'},
             'cargabilidad_max': {'valor': carga, 'donde': 'L1'}}
    datos.update(extra)
    return Caso.desde_json(datos)


def test_datos_de_la_fuente():
    """017:RF-15 — kVA y factor de potencia de la fuente y de las pérdidas, como EMAPICA."""
    caso = _caso()
    assert round(caso.fuente.kva) == 2964 and round(caso.fuente.fp_pct, 2) == 94.15
    assert round(caso.perdidas.kva, 2) == 68.06 and round(caso.perdidas.fp_pct, 2) == 58.92
    assert Potencia(0, 0).fp_pct is None


def test_tension_minima_con_su_nodo_y_nodos_fuera():
    """017:RF-16 — la mínima es la menor de las fases, con su nodo; los nodos fuera se cuentan."""
    caso = _caso(vmin=0.93, nodos_fuera=12)
    assert caso.minima == Extremo(0.93, 'N1') and caso.nodos_fuera == 12


def test_desequilibrado_por_fase_equilibrado_trifasica():
    """017:RF-17, 017:RF-18 — tres fases en el desequilibrado; una sola «trifásica» en el equilibrado."""
    assert _caso().desequilibrado
    eq = _caso(tension_min={TRIFASICA: {'valor': 0.96, 'donde': 'N9'}})
    assert not eq.desequilibrado and eq.minima.donde == 'N9'
    with pytest.raises(InformeError, match='A, B y C'):
        _caso(tension_min={'A': {'valor': 0.96, 'donde': 'N9'}})


def test_cargabilidad_maxima_con_su_tramo():
    """017:RF-19 — la cargabilidad máxima con su tramo y los tramos sobre el umbral."""
    caso = _caso(carga=112.5, tramos_sobre=3)
    assert caso.cargabilidad_max == Extremo(112.5, 'L1') and caso.tramos_sobre == 3
    assert not caso.cumple(LIMITES)


def test_caso_sin_convergencia_no_trae_valores():
    """017:RF-24 — sin convergencia el caso no tiene valores y no cumple."""
    caso = Caso.desde_json({'nombre': 'Con proyecto', 'converge': False})
    assert caso.fuente is None and caso.minima is None and not caso.cumple(LIMITES)
    with pytest.raises(InformeError, match='mal formado'):
        Caso.desde_json({'converge': True})


# --------------------------------------------------------------------------- T2: etapas
def _etapa(clave, vmin):
    return Etapa(clave, caso=_caso(clave, vmin=vmin))


def test_estado_actual_que_cumple_no_evalua_obras():
    """017:RF-31 — con el estado actual en regla no se evalúa ninguna etapa."""
    actual = _caso()
    assert actual.cumple(LIMITES)
    assert not seguir_evaluando(actual, [], LIMITES, evaluar_todas=True)
    assert etapa_recomendada(actual, [], LIMITES).actual_cumple


def test_primera_etapa_que_cumple_y_se_para():
    """017:RF-32, 017:RF-33, 017:RF-43 — en orden, la primera que cumple se recomienda y se para."""
    actual = _caso(vmin=0.90)
    etapas = [_etapa('bancos_existentes', 0.92), _etapa('bancos_nuevos', 0.94)]
    assert seguir_evaluando(actual, etapas, LIMITES, evaluar_todas=False)
    etapas.append(_etapa('reguladores', 0.96))
    assert not seguir_evaluando(actual, etapas, LIMITES, evaluar_todas=False)
    assert seguir_evaluando(actual, etapas, LIMITES, evaluar_todas=True)
    etapas.append(_etapa('conductor', 0.98))
    rec = etapa_recomendada(actual, list(reversed(etapas)), LIMITES)
    assert rec.etapa.clave == 'reguladores'
    assert rec.cumplen == {'bancos_existentes': False, 'bancos_nuevos': False, 'reguladores': True,
                           'conductor': True}
    assert ETAPAS.index('reguladores') == 2


def test_ninguna_etapa_cumple():
    """017:RF-34 — si ninguna cumple no hay recomendación y quedan los resultados de todas."""
    actual = _caso(vmin=0.80)
    etapas = [_etapa(c, 0.85) for c in ETAPAS[:3]] + [Etapa('migracion', motivo='falta la SED')]
    rec = etapa_recomendada(actual, etapas, LIMITES)
    assert rec.etapa is None and len(rec.cumplen) == 3
    with pytest.raises(InformeError, match='caso o el motivo'):
        Etapa('conductor')


# --------------------------------------------------------------------------- T2: pérdidas
def test_formulas_de_perdidas_con_los_numeros_de_emapica():
    """017:RF-54, 017:RF-57, 017:RF-58 — energía, % y pérdida no reconocida como el modelo EMAPICA.

    La fila del modelo: 2791 kW, FC 0,74, 63 830 kWh de pérdidas, 0,79 % reconocido y
    0,2307 S/kWh dan 18 092 378,40 kWh, 0,35 % y −18 248,32 S/.
    """
    r = perdidas_anuales(2791, 63830 / 8760 / factor_de_perdidas(0.74), 0.74, 0.79, 0.2307)
    assert round(r.energia_kwh, 2) == 18092378.40
    assert round(r.perdidas_kwh) == 63830
    assert round(r.perdidas_pct, 2) == 0.35
    assert round(r.no_reconocida_soles, 2) == -18248.32
    # Estado proyectado del mismo modelo.
    assert round(perdida_no_reconocida(505500, 20958377.09, 0.79, 0.2307), 2) == 78421.58


def test_factor_de_perdidas_y_perdidas_tecnicas():
    """017:RF-55, 017:RF-56 — 0,3·FC + 0,7·FC² y pérdidas del flujo × 8760 h × factor de pérdidas."""
    assert factor_de_perdidas(0.5) == pytest.approx(0.325)
    assert perdidas_anuales(1000, 10, 0.5).perdidas_kwh == pytest.approx(10 * 8760 * 0.325)
    with pytest.raises(InformeError, match='entre 0 y 1'):
        factor_de_perdidas(1.2)


def test_perdidas_en_los_dos_estados_y_sin_libro():
    """017:RF-59, 017:RF-64 — las pérdidas de cada estado; sin libro, lo reconocido queda en None."""
    actual = perdidas_anuales(2791, 40.10, 0.74)
    proyectado = perdidas_anuales(3182, 49.86, 0.74)
    assert actual.no_reconocida_soles is None and proyectado.perdidas_kwh > actual.perdidas_kwh


def test_factor_de_carga_de_la_medicion_de_cabecera():
    """017:RF-60, 017:RF-61 — media entre máxima de la curva del mes; sin curva, None (se pide)."""
    curva = [(i, p, None) for i, p in enumerate([50, 100, 75, 75])]
    assert factor_de_carga(curva) == pytest.approx(0.75)
    assert factor_de_carga([]) is None
    assert factor_de_carga([(0, 0.0, None)]) is None


# --------------------------------------------------------------------------- T2: factibilidad
def test_factible_solo_si_alimentador_y_set_cumplen():
    """017:RF-71 — factible con el proyectado en regla y la SET por debajo de su capacidad."""
    trafo = [Devanado(10, 72.28, 73.87)]
    assert veredicto_factibilidad(_caso(), trafo, LIMITES).factible
    assert not veredicto_factibilidad(_caso(), None, LIMITES).factible


def test_no_factible_dice_que_limite_donde_y_cuanto():
    """017:RF-72 — cada límite superado con su sitio y su exceso."""
    v = veredicto_factibilidad(_caso(vmin=0.93, carga=110), [Devanado(10, 95, 101.5)], LIMITES)
    assert not v.factible
    assert any('0,930 p.u. en N1' in e and '0,020 p.u. por debajo' in e for e in v.excesos)
    assert any('110,0 % en L1' in e and '10,0 puntos' in e for e in v.excesos)
    assert any('10 kV' in e and '1,50 puntos' in e for e in v.excesos)
    sin_flujo = veredicto_factibilidad(Caso('Con proyecto', False), [Devanado(10, 1, 2)], LIMITES)
    assert sin_flujo.excesos == ('el flujo de carga del estado proyectado no converge',)


# --------------------------------------------------------------------------- T3: redacción
SOLICITUD = Solicitud(cliente='CLIENTE PRUEBA', ubicacion='el distrito de Parcona, Ica',
                      tipo_solicitud='Factibilidad y Punto de Diseño', potencia_kw=430,
                      fecha_solicitud=date(2026, 8, 1), alimentador='AL01', set_nombre='SET1',
                      tension_kv=10, transformador='50/30/30 MVA', expediente='EXP-1', en_concesion=True)


def test_textos_de_analisis_solo_con_lo_que_dicen_los_numeros():
    """017:RF-20 — la frase nombra mínima, nodo, banda y umbral, y no afirma un problema sin él."""
    bien = redactar_tension(_caso(), LIMITES, norma='NTCSE')
    assert '0,970 p.u.' in bien and 'N1' in bien and 'fase A' in bien and 'problemas' not in bien
    assert '±5 % de la tensión nominal' in bien and 'NTCSE' in bien
    mal = redactar_tension(_caso(vmin=0.91, nodos_fuera=7), LIMITES)
    assert '7 nodos se encuentran fuera' in mal and 'problemas de calidad de tensión' in mal
    assert 'dentro de los límites operativos' in redactar_cargabilidad(_caso(), LIMITES)
    assert 'problemas de cargabilidad' in redactar_cargabilidad(_caso(carga=120, tramos_sobre=2), LIMITES)
    assert 'no converge' in redactar_tension(Caso('X', False), LIMITES)


def test_sin_nada_propio_del_proyecto_ni_del_conversor():
    """017:RF-20 — ningún texto nombra los casos de DIgSILENT ni el orden de evaluación."""
    actual = _caso(nombre='Sin proyecto', vmin=0.90)
    etapas = [_etapa('bancos_nuevos', 0.96)]
    rec = etapa_recomendada(actual, etapas, LIMITES)
    textos = [redactar_tension(actual, LIMITES), redactar_cargabilidad(actual, LIMITES),
              redactar_tension(Caso('Con proyecto', False), LIMITES),
              *conclusiones_estudio(['AL01'], actual, rec, etapas, LIMITES)]
    for texto in textos:
        for palabra in ('Sin proyecto', 'Con proyecto', 'caso', 'etapa', 'variación', 'evaluada'):
            assert palabra not in texto, (palabra, texto)


def test_borrador_de_conclusiones_del_estudio():
    """017:RF-21 — como el modelo: lo que falla, las actividades y lo que se logra con ellas."""
    actual = _caso(vmin=0.90)
    obras = ({'tipo': 'banco', 'nodo': 'N7', 'kvar': 300},)
    etapas = [_etapa('bancos_existentes', 0.92),
              replace(_etapa('bancos_nuevos', 0.96), obras=obras),
              Etapa('migracion', motivo='la SED SE1 no está en el alimentador')]
    rec = etapa_recomendada(actual, etapas, LIMITES)
    texto = conclusiones_estudio(['AL01'], actual, rec, etapas, LIMITES, norma='NTCSE')
    assert '0,900 p.u.' in texto[0]
    # 017:RF-134: con dos etapas evaluadas, primero qué logra cada alternativa.
    assert texto[1].startswith('Alternativa 1') and texto[2].startswith('Alternativa 2')
    assert 'Se recomienda la alternativa 2' in texto[3]
    assert any('siguientes actividades' in t for t in texto)
    assert 'Instalar un banco de condensadores de 300 kvar en el nodo N7.' in texto
    assert '0,960 p.u.' in texto[-1] and 'NTCSE' in texto[-1]
    rec_ok = etapa_recomendada(_caso(), [], LIMITES)
    assert 'no se requieren obras' in conclusiones_estudio(['AL01'], _caso(), rec_ok, [], LIMITES)[0]


def test_encabezado_del_operador():
    """017:RF-22 — fecha, asunto, destinatario y antecedentes son los del operador."""
    e = Encabezado(date(2026, 8, 14), 'ASUNTO X', 'PROYECTOS Y OBRAS', 'Antecedente', lugar='Ica')
    assert e.fecha_texto == 'Ica, 14 de agosto de 2026'
    assert asunto_propuesto('estudio', ['CA101', 'PE104']).endswith('CA101, PE104')
    assert 'CLIENTE' in asunto_propuesto('factibilidad', ['AL01'], 'CLIENTE')


def test_solicitudes_vigentes():
    """017:RF-50 — las cargas en bloque se dicen «solicitudes vigentes»."""
    assert 'solicitudes que se encuentran vigentes' in SOLICITUDES_VIGENTES


def test_antecedentes_y_descripcion_con_las_frases_del_modelo():
    """017:RF-107, 017:RF-108 — fecha, expediente, potencia, alimentador, SET y fuentes."""
    a = antecedentes_factibilidad(SOLICITUD)
    assert '1 de agosto de 2026' in a[0] and 'EXP-1' in a[1] and '430 kW' in a[2]
    assert 'AL01' in a[3] and '50/30/30 MVA' in a[4]
    d = descripcion_factibilidad(SOLICITUD, ['mediciones de cabecera', 'el modelo de transmisión'])
    assert 'mediciones de cabecera, el modelo de transmisión' in d[0] and 'AL01' in d[1]


def test_texto_del_transformador():
    """017:RF-121 — cargabilidad sin y con proyecto y el caso de estudio de transmisión."""
    t = texto_transformador(SOLICITUD, Devanado(10, 72.28, 73.87), '2026', 'TRANSMISION')
    assert '72,28 %' in t and '73,87 %' in t and '«2026»' in t and 'por debajo' in t
    assert 'No se obtuvo' in texto_transformador(SOLICITUD, None, '', '')


def test_conclusiones_de_factibilidad_en_apartados():
    """017:RF-122 — a) solicitud y concesión, b) alimentador, c) SET, d) punto de diseño."""
    trafo = [Devanado(10, 72.28, 73.87)]
    ok = conclusiones_factibilidad(SOLICITUD, veredicto_factibilidad(_caso(), trafo, LIMITES),
                                   'COD 580224223', trafo[0])
    assert [c[:2] for c in ok] == ['a)', 'b)', 'c)', 'd)']
    assert 'dentro del área de concesión' in ok[0] and 'COD 580224223' in ok[3]
    no = conclusiones_factibilidad(SOLICITUD, veredicto_factibilidad(_caso(carga=130), trafo, LIMITES),
                                   'COD 1', trafo[0])
    assert 'no admite la carga' in no[1] and 'No se recomienda' in no[3]
    sin = Solicitud(**{**SOLICITUD.__dict__, 'en_concesion': None})
    assert 'A CONFIRMAR' in conclusiones_factibilidad(sin, veredicto_factibilidad(_caso(), trafo, LIMITES),
                                                      'C', trafo[0])[0]


# --------------------------------------------------------------------------- casos desde la web
MEDIDA = {'converge': True, 'barras': [['CAB', 1.0], ['N1', 0.93], ['N2', 0.96]],
          'elementos': [['L1', 'ElmLne', 104.0], ['L2', 'ElmLne', 50.0], ['T1', 'ElmTr2', 120.0]],
          'vm_min': 0.93, 'vm_min_barra': 'N1', 'vm_max': 1.0, 'vm_max_barra': 'CAB',
          'mas_cargado': 'T1', 'cargabilidad_max': 120.0, 'cabecera_kw': 2791.0, 'cabecera_kvar': 999.0,
          'perdidas_kw': 40.1, 'perdidas_kvar': 55.0, 'vm_min_fases': None}


def test_caso_desde_la_medida_de_los_estudios():
    """017:RF-15, 017:RF-16, 017:RF-18, 017:RF-19 — el caso sale de lo que guardó el paso de estudios."""
    caso = Caso.desde_medida('Sin proyecto', MEDIDA, LIMITES)
    assert caso.fuente == Potencia(2791.0, 999.0) and caso.perdidas == Potencia(40.1, 55.0)
    assert caso.tension_min == {TRIFASICA: Extremo(0.93, 'N1')} and caso.nodos_fuera == 1
    # La del conductor sale de los tramos; el transformador va aparte (CA101, TR_SE20701 al 518 %).
    assert caso.cargabilidad_max == Extremo(104.0, 'L1') and caso.tramos_sobre == 1
    assert caso.trafo_max == Extremo(120.0, 'T1')


def test_transformador_sobrecargado_no_es_un_tramo():
    """017:RF-19, 017:RF-20 — el transformador se nombra como tal; sin obras evaluadas no se dice que fallaron."""
    medida = {**MEDIDA, 'elementos': [['L1', 'ElmLne', 60.0], ['TR_SE1', 'ElmTr2', 518.4]]}
    caso = Caso.desde_medida('Sin proyecto', medida, LIMITES)
    texto = redactar_cargabilidad(caso, LIMITES)
    assert 'tramo L1' in texto and 'por debajo del 100 %' in texto
    assert 'El transformador TR_SE1 alcanza una cargabilidad de 518,4 %' in texto
    assert not caso.cumple_cargabilidad(LIMITES)
    rec = etapa_recomendada(caso, [], LIMITES)
    conclusiones = conclusiones_estudio(['AL01'], caso, rec, [], LIMITES)
    assert 'el transformador TR_SE1 al 518,4 %' in conclusiones[0]
    assert conclusiones[-1].startswith('Se requiere evaluar obras') and 'Ninguna' not in ' '.join(conclusiones)


def test_caso_desequilibrado_y_sin_convergencia_desde_la_medida():
    """017:RF-17, 017:RF-24 — por fase en el desequilibrado; sin convergencia, sin valores."""
    fases = {**MEDIDA, 'vm_min_fases': {'A': [0.93, 'N1'], 'B': [0.94, 'N2'], 'C': [0.95, 'N2']}}
    assert set(Caso.desde_medida('x', fases, LIMITES).tension_min) == {'A', 'B', 'C'}
    assert not Caso.desde_medida('x', {'converge': False}, LIMITES).converge
    sin_kvar = Caso.desde_medida('x', {**MEDIDA, 'perdidas_kvar': None}, LIMITES)
    assert sin_kvar.perdidas is None and sin_kvar.fuente is not None


def test_terna_y_enlace_son_la_etapa_de_refuerzo():
    """017:RF-126 — la terna y el enlace de «Con proyecto» son la etapa «refuerzo de la
    red», entre el cambio de conductor y la migración."""
    from igea_dgs.informes import ETAPAS, NOMBRE_ETAPA, etapa_de_obras

    assert ETAPAS.index('conductor') < ETAPAS.index('refuerzo') < ETAPAS.index('migracion')
    assert 'Refuerzo' in NOMBRE_ETAPA['refuerzo']
    assert etapa_de_obras([{'clase': 'terna'}]) == 'refuerzo'
    assert etapa_de_obras([{'clase': 'enlace'}]) == 'refuerzo'
    assert etapa_de_obras([{'clase': 'terna'}, {'clase': 'seccion'}]) == 'refuerzo'
    assert etapa_de_obras([{'clase': 'terna'}, {'clase': 'migracion'}]) == 'migracion'


def test_descripcion_de_la_terna_y_del_enlace():
    """017:RF-127 — la terna se describe con sus tramos y el enlace con su largo, su
    conductor y sus dos extremos, como se aplicó."""
    from igea_dgs.informes import describir_obra, obra_para_informe

    terna = obra_para_informe({'clase': 'terna', 'alimentador': 'TA225',
                               'tramos': ['SEC_1', 'SEC_2']})
    assert 'SEC_1' in describir_obra(terna) and 'SEC_2' in describir_obra(terna)
    assert 'terna' in describir_obra(terna)
    enlace = obra_para_informe({
        'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111',
        'tipo': {'nombre': 'AA12003D_22_9kV'},
        'enlace': {'largo_m': 3625.6, 'origen': {'barra_final': '15232'},
                   'destino': {'barra_final': 'ENLACE_C_IN111'},
                   'trazado': {'por_via': True, 'servicio': 'osrm'}}})
    texto = describir_obra(enlace)
    for parte in ('3,63 km', 'AA12003D_22_9kV', '15232', 'ENLACE_C_IN111', 'TA225', 'IN111', 'vía'):
        assert parte in texto, (parte, texto)
