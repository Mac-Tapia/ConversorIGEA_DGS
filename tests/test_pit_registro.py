"""Spec 107: el registro normativo REAL del PIT (config/normativa): normas, estados, cuadros oficiales y vigencia
(107:RF-7, 107:RF-8, 107:RF-9, 107:RF-11). Movidas desde test_registro_normativo.py en la reestructura RN; las
genéricas del módulo, con registros sintéticos, están en test_registro_normativo.py (tarjeta RN).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from convertersmartgrid.registro_normativo import (
    cargar_registro,
)

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = json.loads((RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json')
                     .read_text(encoding='utf-8'))
H = 'b' * 64


# --------------------------------------------------------------------------- T2: el registro real del PIT
NORMATIVA = RAIZ / 'config' / 'normativa'
CUADROS_PIT = ('pit.cuadro.nuevas', 'pit.cuadro.bajas', 'pit.cuadro.retirados')


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
    detalle de sus elementos (IT 655-2026-GRT) no se supone."""
    registro = cargar_registro(NORMATIVA)
    norma = registro.norma('RCD 199-2026-OS/CD')
    assert norma.estado_juridico == 'vigente_comprobada' and norma.fecha_publicacion
    assert set(norma.modifica) == {'RCD 112-2024-OS/CD', 'RCD 149-2024-OS/CD'}
    assert not norma.vigencia_desde, 'la resolución no fija vigencia: no se supone'
    assert registro.regla('pit.modificacion_2025_2029.areas_modificadas').regla.valor == [9]
    assert registro.regla('pit.modificacion_2025_2029.consolidacion').regla.valor == 'resolucion_complementaria'
    oportunidad = registro.regla('pit.modificacion_2025_2029.oportunidad_por_area').regla.valor
    areas = sorted(a for tramo in oportunidad for a in tramo['areas'])
    assert areas == list(range(1, 15)), 'cada área de demanda, una sola vez'
    assert 'IT 655-2026-GRT' in norma.nota and '404' in norma.nota


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
    """107:RF-8 — una norma modificada sin fecha de vigencia comprobada no obliga: se usa como referencia."""
    registro = cargar_registro(NORMATIVA)
    for clave in ('pit.vida_util_anios', 'pit.n1_demanda_min_mw', 'pit.cuadro.nuevas'):
        assert not registro.regla(clave).obligatoria, clave


def test_factores_vigentes_del_vad_2023_2027_y_su_comprobacion_cruzada():
    """107:RF-7, 107:RF-8 (T19b 3a) — la 223-2023 fija los FE vigentes de las 11 empresas y modifica la 187-2023; la
    comprobación cruzada con el IT 716 nombra qué empresas cambiaron (Electrosur y Seal, no)."""
    registro = cargar_registro(NORMATIVA)
    vigente = registro.regla('vad.perdidas.factores_expansion')
    assert vigente.norma.acto == 'RCD 223-2023-OS/CD' and vigente.obligatoria
    assert 'RCD 223-2023-OS/CD' in registro.norma('RCD 187-2023-OS/CD').modificada_por
    previa = registro.regla('vad.perdidas.factores_expansion_it716').regla.valor['empresas']
    actual = vigente.regla.valor['empresas']
    assert set(previa) == set(actual) and len(actual) == 11
    cambiaron = {e for e in actual if actual[e]['fe'] != previa[e]['fe']}
    assert {e for e in actual} - cambiaron == {'Electrosur', 'Seal'}
    assert all(f >= 1 for e in actual.values() for f in e['fe'].values())


def test_cada_empresa_cuyo_factor_cambio_lleva_su_causa_o_su_hueco():
    """107:RF-7, 107:RF-8 (delta13) — toda empresa cuyos FE cambian entre el IT 716 y la RCD 223-2023 lleva la causa
    citada en el informe técnico de su reconsideración o, si ese informe no acepta nada de pérdidas técnicas, un «sin
    causa localizada» citado; las que no cambian no llevan ninguna."""
    registro = cargar_registro(NORMATIVA)
    previa = registro.regla('vad.perdidas.factores_expansion_it716').regla.valor['empresas']
    actual = registro.regla('vad.perdidas.factores_expansion').regla.valor['empresas']
    cambiaron = {e for e in actual if actual[e]['fe'] != previa[e]['fe']}
    claves = {r.clave for n in registro.normas.values() for r in n.reglas}
    for empresa in sorted(actual):
        con = f'vad.perdidas.causa_del_cambio.{empresa}' in claves
        sin = f'vad.perdidas.sin_causa_localizada.{empresa}' in claves
        if empresa in cambiaron:
            assert con != sin, (empresa, 'una y solo una: causa citada o hueco citado')
        else:
            assert not (con or sin), (empresa, 'no cambia y no debe llevar causa')
    causa = registro.regla('vad.perdidas.causa_del_cambio.Electrocentro')
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
