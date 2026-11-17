"""Spec 107: el registro normativo REAL del PIT (config/normativa): normas, estados, cuadros oficiales y vigencia
(107:RF-7, 107:RF-8, 107:RF-9, 107:RF-11). Movidas desde test_registro_normativo.py en la reestructura RN; las
genéricas del módulo, con registros sintéticos, están en test_registro_normativo.py (tarjeta RN).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema
import pytest

from convertersmartgrid.registro_normativo import (
    RegistroError,
    ReglaAmbigua,
    cargar_registro,
)

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = json.loads((RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json')
                     .read_text(encoding='utf-8'))
H = 'b' * 64
#: Prefijos de las claves con que el registro acompaña cada cambio de FE entre el IT 716 y la RCD 223-2023.
CAUSA = 'vad.perdidas.causa_del_cambio.'
SIN_CAUSA = 'vad.perdidas.sin_causa_localizada.'
#: NOMBRES-REG: los nombres reales de empresa y de SET viven solo en config; las pruebas los leen de allí y, cuando
#: necesitan fijar cuál es, comparan su huella (sha256 de los textos tal cual están en la transcripción, unidos por
#: «|»), que no escribe el nombre. Cada huella se calculó sobre la transcripción del registro (config/normativa).
HUELLA_FE_SIN_CAMBIO = '2b5f15f335ef6d416e8eb66f35dd8d6a9969c8f7b72b4a9439308bfb7490a5c7'  # las 2 de la 223-2023
HUELLA_CAUSA_IT815 = 'b63ee954fb4c0c6159a812dc996d8737d5c6acfc0592368a6ed8c18ca98626b2'  # la empresa del IT 815
# PIT-ANON-ELEMENTOS: el par de huellas (titular|SET) de la fila del Cuadro 6.5; los nombres, solo en la lista local.
HUELLA_187_2026_RESERVA = '62e25abd02e5e1b10b6d6ca7c56200859dca1d2fe3103e3be590c32db7b7ffe4'


def _huella(*partes: str) -> str:
    """sha256 de los textos unidos por «|»: fija un nombre de config sin escribirlo en la prueba."""
    return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()


def _claves(registro, acto: str | None = None) -> set[str]:
    """Las claves de las reglas del registro (de todas sus normas, o solo de ``acto``)."""
    return {r.clave for n in registro.normas.values() if acto in (None, n.acto) for r in n.reglas}


# --------------------------------------------------------------------------- T2: el registro real del PIT
NORMATIVA = RAIZ / 'config' / 'normativa'
CUADROS_PIT = ('pit.cuadro.nuevas', 'pit.cuadro.bajas', 'pit.cuadro.retirados')
#: Una referencia a otra norma (``modifica`` / ``modificada_por``) que no está en el registro tiene que ser inequívoca.
#: Las RCD, RM, DS y RD se numeran por año: llevan el suyo («RCD 187-2023-OS/CD», «DS 009-99-EM»). Los decretos
#: legislativos y las leyes llevan una numeración de serie única, sin año («DL 1221», «Ley 31937»): decisión del
#: auditor c3 en FIX-PUNTA (RN-AMB, condición de 28).
REF_CON_ANIO = re.compile(r'(?:RCD|RM|DS|RD) \d{1,3}-(?:\d{4}|\d{2})-[A-Z]+(?:[/-][A-Z]+)*')
REF_DE_SERIE = re.compile(r'(?:DL|Ley) \d{1,5}')


def _referencia_inequivoca(ref: str) -> bool:
    return bool(REF_CON_ANIO.fullmatch(ref) or REF_DE_SERIE.fullmatch(ref))


def test_registro_real_valida_contra_el_esquema():
    """107:RF-7 — cada fichero de config/normativa cumple el esquema común."""
    ficheros = sorted(NORMATIVA.glob('*.json'))
    assert ficheros, 'config/normativa está vacío'
    for f in ficheros:
        jsonschema.validate(json.loads(f.read_text(encoding='utf-8')), ESQUEMA)


def test_registro_real_cada_regla_con_pagina_y_cita():
    """107:RF-7, 107:RF-9 — ninguna regla supuesta: cada una con su página, sus líneas y su cita literal."""
    registro = cargar_registro(NORMATIVA)
    reglas = [(n, r) for n in registro.normas.values() for r in n.reglas]
    assert reglas
    for norma, regla in reglas:
        assert regla.citada and regla.pagina and regla.articulo_o_anexo, (norma.acto, regla.clave)
        assert norma.sha256 and norma.url and norma.fecha_consulta, norma.acto


def test_registro_real_normas_del_pit_con_su_estado():
    """107:RF-7, 107:RF-8 — las normas del PIT con su estado comprobado y sus modificatorias enlazadas en los dos
    sentidos (107 T3: la 199-2026, leída en su edición oficial, modifica la 112-2024 y la 149-2024)."""
    registro = cargar_registro(NORMATIVA)
    for acto in ('RCD 217-2013-OS/CD', 'RCD 112-2024-OS/CD', 'RCD 149-2024-OS/CD', 'RCD 199-2026-OS/CD'):
        assert registro.norma(acto).sha256, acto
    assert 'RCD 149-2024-OS/CD' in registro.norma('RCD 217-2013-OS/CD').modificada_por + \
        registro.norma('RCD 112-2024-OS/CD').modificada_por
    for norma in registro.normas.values():
        for modificada in norma.modifica:
            if modificada in registro.normas:
                assert norma.acto in registro.norma(modificada).modificada_por, (norma.acto, modificada)


def test_modificatoria_199_2026_leida_con_su_objeto():
    """107:RF-7, 107:RF-8 (107 T3) — la 199-2026 comprobada: objeto, área que modifica y consolidación, citados; el
    detalle de sus elementos sale del IT 655-2026-GRT, con su huella, y se dice que antes daba 404."""
    registro = cargar_registro(NORMATIVA)
    norma = registro.norma('RCD 199-2026-OS/CD')
    assert norma.estado_juridico == 'vigente_comprobada' and norma.fecha_publicacion
    assert set(norma.modifica) == {'RCD 112-2024-OS/CD', 'RCD 149-2024-OS/CD'}
    # RN-AMB v2 (condición 1 de 28): sin cláusula de vigencia propia, rige por el art. 109 de la Constitución desde el
    # día siguiente a su publicación (14-11-2026); antes se exigía que no tuviera vigencia_desde.
    assert (norma.fecha_publicacion, norma.vigencia_desde) == ('2026-11-14', '2026-11-15')
    assert 'art. 109' in norma.nota and 'no tiene cláusula de vigencia' in norma.nota
    # RN-AMB: la 199-2026 ya no es la única modificación vigente (la 186-2026, la 187-2026 y la 189-2026 se suman,
    # cada una de su área): estas claves se piden con reglas_vigentes y se comprueba la de la 199-2026 entre todas.
    areas = {v.norma.acto: v.regla.valor
             for v in registro.reglas_vigentes('pit.modificacion_2025_2029.areas_modificadas')}
    assert areas.get('RCD 199-2026-OS/CD') == [9]
    consolidacion = registro.reglas_vigentes('pit.modificacion_2025_2029.consolidacion')
    assert 'RCD 199-2026-OS/CD' in {v.norma.acto for v in consolidacion}
    assert {v.regla.valor for v in consolidacion} == {'resolucion_complementaria'}
    oportunidad = registro.regla('pit.modificacion_2025_2029.oportunidad_por_area').regla.valor
    areas = sorted(a for tramo in oportunidad for a in tramo['areas'])
    assert areas == list(range(1, 15)), 'cada área de demanda, una sola vez'
    assert 'IT 655-2026-GRT' in norma.nota and '404' in norma.nota and 'aec882cf' in norma.nota


def test_reserva_094_2022_transcrita():
    """107:RF-16 (107 T24) — el procedimiento de transformadores de reserva, con sus criterios y sus formatos citados."""
    registro = cargar_registro(NORMATIVA)
    norma = registro.norma('RCD 094-2022-OS/CD')
    assert norma.estado_juridico == 'vigente_comprobada' and norma.sha256
    claves = {r.clave for r in norma.reglas}
    for clave in ('pit.reserva.tipo', 'pit.reserva.beneficio_costo_minimo', 'pit.reserva.horizonte_pns_anios',
                  'pit.reserva.costo_ens_falla', 'pit.reserva.metodo_duracion_interrupciones',
                  'pit.reserva.formato.tabla_1', 'pit.reserva.formato.tabla_2', 'pit.reserva.formato.tabla_3'):
        assert clave in claves, clave
    assert registro.regla('pit.reserva.beneficio_costo_minimo').regla.valor == 1
    horizonte = registro.regla('pit.reserva.horizonte_pns_anios').regla.valor
    assert horizonte == 10
    falla = registro.regla('pit.reserva.costo_ens_falla').regla.valor
    assert falla['factor_numerador_usd_mwh'] > falla['factor_denominador_usd_mwh'] > 0
    tabla_1 = registro.regla('pit.reserva.formato.tabla_1').regla.valor['columnas']
    assert len([c for c in tabla_1 if c.startswith('PNS')]) == horizonte, 'un año de PNS por año del horizonte'
    assert registro.regla('pit.reserva.formato.tabla_2').regla.valor['columnas'][0] == 'Nodo'
    assert registro.regla('pit.reserva.formato.tabla_3').regla.valor['items']


def test_cuadros_oficiales_transcritos_o_declarados_sin_transcribir():
    """107:RF-9 — los cuadros del PIT tienen sus columnas transcritas; los formatos sin leer lo dicen."""
    registro = cargar_registro(NORMATIVA)
    for clave in CUADROS_PIT:
        valor = registro.regla(clave).regla.valor
        assert valor['titulo'] and valor['columnas'], clave
    formatos = registro.regla('pit.formatos_217').regla.valor
    if not formatos['transcrito']:
        return
    assert (NORMATIVA / formatos['fichero']).is_file(), formatos['fichero']


def _codigos_de_la_tabla_1(grupos):
    """«F-101 a F-124» → F-101 … F-124; «F-401» → F-401. Sale de la regla registrada, no de una lista fija."""
    codigos = []
    for rango in grupos:
        extremos = [int(x.strip()[2:]) for x in rango.split(' a ')]
        codigos += [f'F-{n:03d}' for n in range(extremos[0], extremos[-1] + 1)]
    return codigos


def test_formatos_217_transcritos_hoja_por_hoja():
    """107:RF-9, 107:RF-18 (107 T19 y T26) — cada formato de la tabla 1 de la Norma Tarifas tiene su plantilla
    transcrita de su libro oficial, con su título, su hoja y su huella; el F-208 trae las fallas y los índices."""
    registro = cargar_registro(NORMATIVA)
    formatos = registro.regla('pit.formatos_217').regla.valor
    assert formatos['transcrito'] is True
    codigos = _codigos_de_la_tabla_1(formatos['grupos'])
    assert len(codigos) == len(set(codigos))
    for codigo in codigos:
        regla = registro.regla(f'pit.formato.{codigo}').regla
        assert regla.citada and regla.pagina.endswith(f'hoja {codigo}'), codigo
        valor = regla.valor
        assert valor['codigo'] == codigo and valor['titulo'] and len(valor['sha256_libro']) == 64, codigo
        assert valor['filas'] and valor['filas'][0]['fila'] == 1, codigo
    norma = registro.norma('RCD 217-2013-OS/CD')
    extra = {r.clave for r in norma.reglas if r.clave.startswith('pit.formato.')} - {f'pit.formato.{c}' for c in codigos}
    assert not extra, f'formatos fuera de la tabla 1: {sorted(extra)}'
    f208 = registro.regla('pit.formato.F-208').regla.valor
    texto = ' '.join(v for fila in f208['filas'] for v in fila['celdas'].values())
    for rotulo in ('INTERRUPCIONES', 'ENS', 'SAIFI', 'SAIDI', 'Tipo de'):
        assert rotulo in texto, rotulo


def test_registro_real_no_obliga_sin_vigencia_comprobada():
    """107:RF-8 — una norma modificada sin fecha de vigencia comprobada no obliga: se usa como referencia. Cambiada en
    RN-VIG2: la 018-2018 tiene ya su vigencia comprobada en el SPIJ, así que su ``pit.n1_demanda_min_mw`` pasa a
    obligar y sale de la lista de las de referencia; se comprueba aquí mismo que ahora obliga."""
    registro = cargar_registro(NORMATIVA)
    for clave in ('pit.vida_util_anios', 'pit.cuadro.nuevas'):
        assert not registro.regla(clave).obligatoria, clave
    assert registro.regla('pit.n1_demanda_min_mw').obligatoria


def test_factores_vigentes_del_vad_2023_2027_y_su_comprobacion_cruzada():
    """107:RF-7, 107:RF-8 (T19b 3a) — la 223-2023 fija los FE vigentes de las 11 empresas y modifica la 187-2023; la
    comprobación cruzada con el IT 716 nombra qué empresas cambiaron (dos no). Cambiada en VAD-FE26: con la 185-2026
    en el registro la clave va por dos fijaciones, así que se pide en una fecha en que solo rige la 223-2023 (el
    2026-10-31, víspera de la 185). NOMBRES-REG: las dos que no cambian se leen del registro (las que no llevan causa
    ni hueco) y se fijan por su huella, sin escribir sus nombres."""
    registro = cargar_registro(NORMATIVA)
    vigente = registro.regla('vad.perdidas.factores_expansion', '2026-10-31')
    assert vigente.norma.acto == 'RCD 223-2023-OS/CD' and vigente.obligatoria
    assert 'RCD 223-2023-OS/CD' in registro.norma('RCD 187-2023-OS/CD').modificada_por
    previa = registro.regla('vad.perdidas.factores_expansion_it716').regla.valor['empresas']
    actual = vigente.regla.valor['empresas']
    assert set(previa) == set(actual) and len(actual) == 11
    cambiaron = {e for e in actual if actual[e]['fe'] != previa[e]['fe']}
    sin_cambio = set(actual) - cambiaron
    acompanadas = {c.removeprefix(p) for c in _claves(registro) for p in (CAUSA, SIN_CAUSA) if c.startswith(p)}
    assert sin_cambio == set(actual) - acompanadas and len(sin_cambio) == 2
    assert _huella(*sorted(sin_cambio)) == HUELLA_FE_SIN_CAMBIO, 'no son las dos de la tabla de la 223-2023'
    assert all(f >= 1 for e in actual.values() for f in e['fe'].values())


def test_cada_empresa_cuyo_factor_cambio_lleva_su_causa_o_su_hueco():
    """107:RF-7, 107:RF-8 (delta13) — toda empresa cuyos FE cambian entre el IT 716 y la RCD 223-2023 lleva la causa
    citada en el informe técnico de su reconsideración o, si ese informe no acepta nada de pérdidas técnicas, un «sin
    causa localizada» citado; las que no cambian no llevan ninguna. Cambiada en VAD-FE26: la tabla de la 223-2023 se
    pide el 2026-10-31, cuando es la única fijación vigente con esa clave."""
    registro = cargar_registro(NORMATIVA)
    previa = registro.regla('vad.perdidas.factores_expansion_it716').regla.valor['empresas']
    actual = registro.regla('vad.perdidas.factores_expansion', '2026-10-31').regla.valor['empresas']
    cambiaron = {e for e in actual if actual[e]['fe'] != previa[e]['fe']}
    claves = {r.clave for n in registro.normas.values() for r in n.reglas}
    for empresa in sorted(actual):
        con = f'vad.perdidas.causa_del_cambio.{empresa}' in claves
        sin = f'vad.perdidas.sin_causa_localizada.{empresa}' in claves
        if empresa in cambiaron:
            assert con != sin, (empresa, 'una y solo una: causa citada o hueco citado')
        else:
            assert not (con or sin), (empresa, 'no cambia y no debe llevar causa')
    # NOMBRES-REG: la empresa se halla por el acto que cita su causa (el IT 815-2023-GRT), no por su nombre escrito.
    de_815 = [c.removeprefix(CAUSA) for c in _claves(registro, 'IT 815-2023-GRT') if c.startswith(CAUSA)]
    assert len(de_815) == 1 and de_815[0] in cambiaron and _huella(de_815[0]) == HUELLA_CAUSA_IT815
    causa = registro.regla(CAUSA + de_815[0])
    assert causa.norma.acto == 'IT 815-2023-GRT' and 'aisladores_mt' in causa.regla.valor['componentes']


def test_rotulo_y_llamada_a_nota_separados_en_todos_los_formatos():
    """107:RF-9 (delta17, frentes w0 y w1 de cc) — en la transcripción de los formatos de la 217-2013, cada celda con una
    llamada a nota en superíndice guarda su texto literal y, aparte, el rótulo sin la llamada; rótulo y llamada
    rehacen el literal (la llamada puede ir en medio o antes de «:», con o sin paréntesis). Los exponentes (r², mm²)
    quedan literales y la plantilla de F-101 dice «Total Sistema 1», no «Total Sistema 12»."""
    from convertersmartgrid.pit.plantillas import _plantilla
    registro = cargar_registro(NORMATIVA)
    llamadas, exponentes = {}, {}
    for norma in registro.normas.values():
        for regla in norma.reglas:
            if not regla.clave.startswith('pit.formato.'):
                continue
            codigo = regla.clave.split('.')[-1]
            for fila in regla.valor['filas']:
                for letra, ll in (fila.get('llamadas') or {}).items():
                    literal = fila['celdas'][letra].replace(' ', '')
                    rotulo = ll['rotulo'].replace(' ', '')
                    llamada = ll['llamada']
                    rehechos = {rotulo[:i] + x + rotulo[i:] for x in (llamada, llamada.strip('()'))
                                for i in range(len(rotulo) + 1)}
                    assert literal in rehechos, (codigo, fila['fila'], letra, fila['celdas'][letra], ll)
                    llamadas[(codigo, f'{letra}{fila["fila"]}')] = ll
                for letra in fila.get('exponentes') or {}:
                    exponentes[(codigo, f'{letra}{fila["fila"]}')] = fila['celdas'][letra]
    assert {('F-101', 'A8'), ('F-002', 'M9')} <= set(llamadas), 'la transcripción no separa las llamadas a nota'
    assert llamadas[('F-101', 'A8')] == {'rotulo': 'Total Sistema 1', 'llamada': '(2)'}
    assert llamadas[('F-002', 'M9')]['llamada'] == '(3)'
    assert set(exponentes) == {('F-106', 'A45'), ('F-107', 'A45'), ('F-002', 'J9'), ('F-002', 'T9'),
                               ('F-206', 'F10'), ('F-206', 'P10')}
    celdas, _ = _plantilla(registro, 'F-101', None)
    assert celdas[(8, 'A')] == 'Total Sistema 1'


# --------------------------------------------------------------------------- RN-VIG2: vigencias comprobadas en el SPIJ
R217 = 'RCD 217-2013-OS/CD'


def _norma(acto):
    """La norma del registro real, o None si no está (así la prueba falla por su propia aserción)."""
    try:
        return cargar_registro(NORMATIVA).norma(acto)
    except RegistroError:
        return None


def _regla(clave):
    try:
        return cargar_registro(NORMATIVA).regla(clave)
    except RegistroError:
        return None


def test_018_2018_vigente_comprobada_en_el_spij():
    """107:RF-7, 107:RF-8 (RN-VIG2) — la 018-2018, sin notas de modificación en el SPIJ (H1200701), está
    «vigente_comprobada», publicada el 2018-02-17, rige desde el día siguiente y modifica la 217-2013 (5.8.2 y 12.3)."""
    norma = _norma('RCD 018-2018-OS/CD')
    assert norma is not None and norma.estado_juridico == 'vigente_comprobada'
    assert (norma.fecha_publicacion, norma.vigencia_desde) == ('2018-02-17', '2018-02-18')
    assert norma.modifica == (R217,) and 'H1200701' in norma.version and '5.8.2' in norma.nota and '12.3' in norma.nota
    assert 'Artículo 3°. - La presente resolución entrará en vigencia' in norma.nota and not norma.vigencia_hasta_motivo


def test_rm_496_2005_modificada_y_su_tabla_01_obliga_con_el_mismo_valor():
    """107:RF-7, 107:RF-8 (RN-VIG2) — la RM 496-2005 está «modificada» por la RM 102-2010 (SPIJ H905941) con su vigencia
    desde el 1 de enero de 2006 por su propio art. 3; la Tabla N° 01 sigue con ±0,3 y ±0,7 % y ahora obliga."""
    norma = _norma('RM 496-2005-MEM/DM')
    assert norma is not None and norma.estado_juridico == 'modificada'
    assert norma.modificada_por == ('RM 102-2010-MEM-DM',)
    assert (norma.fecha_publicacion, norma.vigencia_desde) == ('2005-12-14', '2006-01-01') and 'H905941' in norma.version
    assert 'entrará en vigencia a partir del 1 de enero de 2006' in norma.nota, 'su propia cláusula (art. 3)'
    regla = _regla('medida.error_admisible_por_clase')
    assert regla is not None and regla.norma.acto == 'RM 496-2005-MEM/DM'
    assert regla.regla.valor == {'0.2S': 0.3, '0.5S': 0.7} and regla.obligatoria


def test_rm_102_2010_no_toca_la_tabla_01():
    """107:RF-7 (RN-VIG2) — la RM 102-2010 modifica la RM 496-2005 sin reglas y dice que no toca la Tabla 01."""
    norma = _norma('RM 102-2010-MEM-DM')
    assert norma is not None and norma.modifica == ('RM 496-2005-MEM/DM',) and not norma.reglas
    assert norma.fecha_publicacion == '2010-03-05' and 'NO toca la Tabla 01' in norma.nota and '6.5.3' in norma.nota


def test_transitorias_177_2021_y_147_2017_agotadas():
    """107:RF-7, 107:RF-8 (RN-VIG2) — la 177-2021 (Cuarta transitoria, PIT 2021-2025) y la 147-2017 (Tercera, PIT
    2017-2021) modifican la 217-2013, sin reglas y con su transitoria agotada; la 217 las enlaza."""
    for acto, transitoria, pit, publicada in (('RCD 177-2021-OS/CD', 'Cuarta', 'PIT 2021-2025', '2021-07-15'),
                                             ('RCD 147-2017-OS/CD', 'Tercera', 'PIT 2017-2021', '2017-06-29')):
        norma = _norma(acto)
        assert norma is not None, acto
        assert norma.modifica == (R217,) and not norma.reglas and norma.fecha_publicacion == publicada, acto
        assert transitoria in norma.nota and pit in norma.nota and 'agotada' in norma.nota, acto
        assert acto in _norma(R217).modificada_por, acto
    vigente = _norma('RCD 177-2021-OS/CD')
    assert vigente.estado_juridico == 'vigente_comprobada' and vigente.vigencia_desde == '2021-07-16'
    assert 'H1287522' in vigente.url


def test_242_2021_comprobada_con_su_texto_y_solo_para_las_reasignadas():
    """107:RF-7, 107:RF-8 (RN-VIG2) — la 242-2021, leída entera en El Peruano: comprobada, vigente desde el día siguiente
    a su publicación, y sus reglas solo alcanzan a las SCT reasignadas por el DS 018-2021-EM."""
    norma = _norma('RCD 242-2021-OS/CD')
    assert norma is not None and norma.fecha_publicacion == '2021-12-18' and norma.vigencia_desde == '2021-12-19'
    assert norma.estado_juridico == 'vigente_comprobada' and 'H1089476' in norma.nota
    assert {r.clave for r in norma.reglas} == {'pit.reasignadas.alcance', 'pit.reasignadas.faxc'}
    assert all(r.citada and r.clave.startswith('pit.reasignadas.') for r in norma.reglas)


# ------------------------------------------------------------------------ RN-AMB: las modificaciones del PIT 2025-2029
MODIF = 'pit.modificacion_2025_2029.'
R186, R187, R188, R189, R199 = (f'RCD {n}-2026-OS/CD' for n in (186, 187, 188, 189, 199))


def _vigentes(registro, clave, fecha=None):
    """Las reglas vigentes de la clave, o () si el registro no las da (para que la prueba falle por su aserción)."""
    try:
        return registro.reglas_vigentes(clave, fecha)
    except RegistroError:
        return ()


def test_modificaciones_del_pit_2025_2029_se_suman_por_area():
    """107:RF-7, 107:RF-8 (RN-AMB) — las RCD 186, 187, 189 y 199-2026 modifican cada una su área y se suman: ``regla()``
    es ambigua y ``reglas_vigentes`` las da todas, con las Áreas 1, 3, 9 y 13; la 188-2026 desestima la del Área 12 y
    no modifica el plan."""
    registro = cargar_registro(NORMATIVA)
    assert {R186, R187, R188, R189} <= set(registro.normas), 'faltan las RCD 186 a 189-2026'
    with pytest.raises(ReglaAmbigua, match='reglas_vigentes'):
        registro.regla(MODIF + 'areas_modificadas', '2026-11-15')
    vigentes = _vigentes(registro, MODIF + 'areas_modificadas', '2026-11-15')
    areas = {v.norma.acto: v.regla.valor for v in vigentes}
    assert areas == {R186: [1], R187: [3], R189: [13], R199: [9]}
    assert all(v.obligatoria for v in vigentes)
    desestimadas = _vigentes(registro, MODIF + 'solicitudes_desestimadas', '2026-11-15')
    assert [(v.norma.acto, [s['area'] for s in v.regla.valor]) for v in desestimadas] == [(R188, [12])]
    assert not registro.norma(R188).modifica, 'la 188-2026 desestima: no modifica el plan'
    assert sorted([a for v in areas.values() for a in v] + [12]) == [1, 3, 9, 12, 13]
    consolidan = {v.norma.acto for v in _vigentes(registro, MODIF + 'consolidacion', '2026-11-15')}
    assert consolidan == {R186, R187, R189, R199}
    elementos = {v.norma.acto: v.regla.valor['area'] for v in _vigentes(registro, MODIF + 'elementos', '2026-11-15')}
    assert elementos == {R186: 1, R187: 3, R189: 13, R199: 9}
    for acto in (R186, R187, R189):
        for modificada in ('RCD 112-2024-OS/CD', 'RCD 149-2024-OS/CD'):
            assert modificada in registro.norma(acto).modifica and acto in registro.norma(modificada).modificada_por


def test_vigencia_de_las_186_a_189_por_el_articulo_109():
    """107:RF-7 (RN-AMB) — ninguna de las cuatro tiene cláusula de vigencia propia: rigen desde el día siguiente a su
    publicación en El Peruano (19-10-2026), por el art. 109 de la Constitución, y la nota lo dice con su cita. La
    199-2026, publicada el 14-11-2026, rige desde el 15-11-2026 por la misma regla (RN-AMB v2): el 19-10-2026 no rige
    ninguna modificación de área, del 20-10-2026 al 14-11-2026 las tres de octubre y desde el 15-11-2026 las cuatro."""
    registro = cargar_registro(NORMATIVA)
    for acto in (R186, R187, R188, R189):
        norma = registro.normas.get(acto)
        assert norma is not None, acto
        assert (norma.fecha_publicacion, norma.vigencia_desde) == ('2026-10-19', '2026-10-20'), acto
        assert 'art. 109' in norma.nota and 'no tiene cláusula de vigencia' in norma.nota, acto
    assert [v.norma.acto for v in _vigentes(registro, MODIF + 'areas_modificadas', '2026-10-19')] == []
    assert [v.norma.acto for v in _vigentes(registro, MODIF + 'areas_modificadas', '2026-11-14')] == [R186, R187, R189]
    assert [v.norma.acto for v in _vigentes(registro, MODIF + 'areas_modificadas', '2026-11-15')] == [
        R186, R187, R189, R199]


def test_187_2026_transformador_de_reserva_compartida_del_area_3():
    """107:RF-7, 107:RF-16 (RN-AMB) — la 187-2026 agrega en el Área 3 el transformador de reserva compartida de
    60/22,9/10 kV y 30 MVA en una SET para 2029 (Cuadro 6.5 del IT 601-2026-GRT); la regla anota la incoherencia del
    original (60/23/10 kV en el párrafo) y la de la 189-2026, el pie erróneo del IT 597-2026-GRT. NOMBRES-REG: el
    titular se coteja con los «Titulares» de la nota de la norma y el par titular|SET se fija por su huella
    (PIT-ANON-ELEMENTOS: el registro guarda solo las huellas de los nombres)."""
    registro = cargar_registro(NORMATIVA)
    elementos = {v.norma.acto: v.regla for v in _vigentes(registro, MODIF + 'elementos', '2029-01-01')}
    assert R187 in elementos and R189 in elementos
    agregan = elementos[R187].valor['cuadros']['6.5 agregan']
    assert len(agregan) == 1 and set(agregan[0]) == {'anio', 'titular_huella', 'instalacion_tipo', 'instalacion_huella',
                                                     'elemento'}
    fila = agregan[0]
    assert fila['anio'] == '2029' and fila['elemento'] == 'Transformador de reserva compartida de 60/22,9/10 kV de 30 MVA'
    assert fila['instalacion_tipo'] == 'SET' and len(fila['instalacion_huella']) == 16
    titulares = registro.norma(R187).nota.split('Titulares:', 1)[1].split('Informe', 1)[0]
    assert f'[{fila["titular_huella"]}]' in titulares, 'el titular del cuadro es uno de los de la norma'
    assert _huella(fila['titular_huella'], fila['instalacion_huella']) == HUELLA_187_2026_RESERVA,         'no es la fila del Cuadro 6.5'
    assert elementos[R187].valor['informe'] == 'IT 601-2026-GRT'
    assert '60/23/10 kV' in elementos[R187].interpretacion
    assert '2021-2025' in elementos[R189].interpretacion


def test_actos_con_el_mismo_numero_y_otro_anio_no_se_confunden(tmp_path):
    """107:RF-7 (RN-AMB, condición de 28) — conviven la RCD 187-2026-OS/CD (PIT, Área 3) y la RCD 187-2023-OS/CD (VAD):
    las dos existen y son distintas, ninguna referencia de ``modifica`` o ``modificada_por`` cruza la una con la otra
    ni deja de llevar el año, ningún texto de config/normativa cita una RCD sin su año (ni un número repetido tras
    «la» o «y»), y el cargador falla si un acto se repite en otro fichero."""
    registro = cargar_registro(NORMATIVA)
    assert {'RCD 187-2026-OS/CD', 'RCD 187-2023-OS/CD'} <= set(registro.normas)
    pit, vad = registro.norma('RCD 187-2026-OS/CD'), registro.norma('RCD 187-2023-OS/CD')
    assert pit.sha256 != vad.sha256 and pit.url != vad.url and pit.titulo != vad.titulo
    assert vad.acto not in pit.modifica + pit.modificada_por and pit.acto not in vad.modifica + vad.modificada_por
    for norma in registro.normas.values():
        for ref in norma.modifica + norma.modificada_por:
            assert ref in registro.normas or _referencia_inequivoca(ref), (norma.acto, ref)
    numeros: dict[str, set[str]] = {}
    for acto in registro.normas:
        m = re.match(r'RCD (\d{2,3})-(\d{4})', acto)
        if m:
            numeros.setdefault(m.group(1), set()).add(m.group(2))
    repetidos = sorted(n for n, anios in numeros.items() if len(anios) > 1)
    assert '187' in repetidos
    # RN-AMB v2: ningún texto cita una RCD por su número sin el año, se repita o no el número (las notas generadas
    # de vad_2023_2027_reconsideraciones.json decían «La RCD 223»); con «la», «y»… se miran los números repetidos.
    rcd_sin_anio = re.compile(r'\b(?:RCD|Resoluci[oó]n)\s+(?:N[°º]\s*)?\d{1,3}\b(?!\s*[-‐‑–]\s*\d{4})')
    for f in sorted(NORMATIVA.glob('*.json')):
        texto = f.read_text(encoding='utf-8')
        sin_anio = rcd_sin_anio.search(texto)
        assert sin_anio is None, (f.name, texto[max(0, sin_anio.start() - 40):sin_anio.end() + 20])
        for n in repetidos:
            sin_anio = re.search(r'\b(?:RCD|Resoluci[oó]n|N[°º]|la|las|y|e)\s+' + n + r'\b(?!\s*[-‐‑–]\s*\d{4})', texto)
            assert sin_anio is None, (f.name, texto[max(0, sin_anio.start() - 40):sin_anio.end() + 20])
    otro = tmp_path / 'otro'
    otro.mkdir()
    (otro / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'RCD 187-2026-OS/CD', 'titulo': 'repetida', 'estado_juridico': 'no_verificada'}]}), encoding='utf-8')
    with pytest.raises(RegistroError, match='RCD 187-2026-OS/CD está registrada dos veces'):
        cargar_registro(NORMATIVA, otro)


@pytest.mark.parametrize('ref, inequivoca', (
    ('DL 1221', True), ('Ley 31937', True), ('RCD 187-2023-OS/CD', True), ('DS 009-99-EM', True),
    ('RM 102-2010-MEM-DM', True), ('RD 270-2015-MEM/DGE', True),
    ('RCD 187', False), ('RM 129', False), ('DS 009-EM', False), ('DL', False), ('Ley 31937-2023', False),
), ids=lambda x: str(x))
def test_referencia_por_serie_sin_anio_y_por_anio_con_el_suyo(ref, inequivoca):
    """107:RF-7 (RN-AMB, decisión de c3) — los DL y las leyes se citan por su serie, sin año; las RCD, RM, DS y RD,
    siempre con el suyo: «RCD 187» confundiría la 187-2023 del VAD con la 187-2026 del PIT."""
    assert _referencia_inequivoca(ref) is inequivoca
