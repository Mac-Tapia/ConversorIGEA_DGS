"""Spec 108 T3 — las tablas del estudio se validan contra los formatos del anexo 2, sin rellenar nada (108:RF-2, RF-3).

Las tablas de entrada son sintéticas y se sortean (``seed``); los formatos son los transcritos en
``config/vad/anexo2_formatos.json`` con su cita.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from convertersmartgrid.vad.anexo2 import cargar_formatos, costo_reconocible, validar_tablas

RAIZ = Path(__file__).resolve().parents[1]
FORMATOS = RAIZ / 'config' / 'vad' / 'anexo2_formatos.json'
SEMILLAS = (3, 11, 29)


def _tabla(formato, semilla, periodo='2025'):
    """Una tabla completa del formato, con valores sorteados y las unidades del anexo. Las filas de grupo (solo
    rótulo) no van y las celdas que no aplican quedan vacías, como en el formato (VAD-A5)."""
    rnd = random.Random(semilla)

    def filas():
        return {f.id: {'unidad': f.unidad, **{c.id: round(rnd.uniform(0, 1e4), 3) for c in formato.columnas
                                               if c.id not in f.no_aplica}}
                for f in formato.filas if f.tipo != 'grupo'}

    tabla = {'formato': formato.id, 'periodo': periodo, 'unidades': {c.id: c.unidad for c in formato.columnas}}
    if formato.forma == 'larga':
        claves = {'Empresa': 'E1', 'Sistema': 'S1', 'Año': periodo, 'Sector Típico': 'ST1'}
        tabla['bloques'] = [{'claves': {k: (mes if k == 'Mes' else claves.get(k, 'X')) for k in formato.claves_de_fila},
                             'filas': filas()} for mes in range(1, 13)]
    else:
        tabla['filas'] = filas()
    return tabla


def _completas(formatos, semilla):
    return {f.id: _tabla(f, semilla + i) for i, f in enumerate(formatos.transcritos())}


def test_los_formatos_estan_transcritos_con_su_cita():
    """108:RF-2 — cada formato del anexo 2 lleva su cita (líneas o página); el que no se pudo leer lo dice."""
    formatos = cargar_formatos(FORMATOS)
    assert formatos.transcritos(), 'al menos un formato transcrito'
    for f in formatos.todos():
        assert f.lineas or f.pagina, f.id
        if f.transcrito:
            assert f.filas and f.columnas and all(c.unidad for c in f.columnas), f.id
        else:
            assert f.motivo, f'{f.id}: un formato sin transcribir dice por qué'
    datos = json.loads(FORMATOS.read_text(encoding='utf-8'))
    assert datos['fuente']['acto'] and datos['fuente']['sha256_texto']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tablas_completas_no_dejan_huecos_y_no_cambian(semilla):
    """108:RF-2 — con todas las tablas transcritas y sus unidades, no hay huecos y la salida es la entrada."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, semilla)
    entrada = copy.deepcopy(tablas)
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert not [h for h in res.huecos if h.tipo != 'sin_transcribir'], res.huecos
    assert res.tablas == entrada
    assert tablas == entrada, 'la validación no toca la entrada'


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tabla_obligatoria_que_falta(semilla):
    """108:RF-3 — una tabla obligatoria que falta se nombra y no se crea."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, semilla)
    quitada = random.Random(semilla).choice(sorted(tablas))
    del tablas[quitada]
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert any(h.tabla == quitada and h.tipo == 'falta_tabla' for h in res.huecos), res.huecos
    assert quitada not in res.tablas


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_campo_vacio_y_unidad_distinta_por_tabla_y_campo(semilla):
    """108:RF-3 — un campo vacío y una unidad distinta se dicen por tabla y campo, sin rellenar el valor."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, semilla)
    rnd = random.Random(semilla)
    t1, t2 = rnd.sample(sorted(n for n in tablas if formatos.formato(n).forma == 'ancha'), 2)
    formato = formatos.formato(t1)
    elegida = rnd.choice(sorted((f for f in formato.filas if f.obligatoria and f.tipo != 'grupo'), key=lambda f: f.id))
    fila = elegida.id
    columna = rnd.choice(sorted(c.id for c in formato.columnas if c.obligatoria and c.id not in elegida.no_aplica))
    tablas[t1]['filas'][fila][columna] = None
    otra = rnd.choice(sorted(tablas[t2]['unidades']))
    tablas[t2]['unidades'][otra] = 'unidad-inventada'
    res = validar_tablas(tablas, formatos, periodo='2025')
    vacio = [h for h in res.huecos if h.tipo == 'campo_vacio' and h.tabla == t1]
    assert any(h.campo == f'{fila}.{columna}' for h in vacio), res.huecos
    assert res.tablas[t1]['filas'][fila][columna] is None, 'no se rellena'
    assert any(h.tipo == 'unidad_distinta' and h.tabla == t2 and h.campo == otra for h in res.huecos), res.huecos
    salida = json.dumps(res.tablas, sort_keys=True)
    assert salida == json.dumps({k: v for k, v in tablas.items()}, sort_keys=True), 'ningún valor nuevo'


def test_fila_que_falta_y_periodo_distinto():
    """108:RF-2, 108:RF-3 — una fila del formato que falta y una tabla de otro periodo se nombran."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, 5)
    t = sorted(tablas)[0]
    fila = sorted(f.id for f in formatos.formato(t).filas if f.obligatoria and f.tipo != 'grupo')[0]
    del tablas[t]['filas'][fila]
    t2 = sorted(tablas)[-1]
    tablas[t2]['periodo'] = '2019'
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert any(h.tipo == 'falta_campo' and h.tabla == t and h.campo == fila for h in res.huecos), res.huecos
    assert any(h.tipo == 'periodo_distinto' and h.tabla == t2 for h in res.huecos), res.huecos


def test_formato_sin_transcribir_se_nombra_y_no_se_valida():
    """108:RF-3 — un formato que el anexo no deja leer en la copia local no se da por validado."""
    formatos = cargar_formatos(FORMATOS)
    pendientes = [f.id for f in formatos.todos() if not f.transcrito]
    res = validar_tablas(_completas(formatos, 1), formatos, periodo='2025')
    assert {h.tabla for h in res.huecos if h.tipo == 'sin_transcribir'} == set(pendientes)
    assert res.completo is (not pendientes)


# --- VAD-A5 (108:RF-2, RF-3): celdas que no aplican, filas de grupo y de total, y llamadas con sus notas ---------------

def _sintetico(tmp_path):
    """Un formato sintético con una celda gris («no_aplica»), una fila de grupo, una de total y una llamada a nota."""
    datos = {
        'esquema': 'vad_anexo2_v1',
        'fuente': {'acto': 'sintetico', 'sha256_texto': '0' * 64},
        'formatos': [{
            'id': 'X-1', 'titulo': 'Formato sintético', 'categoria': 'comercial', 'obligatorio': True,
            'transcrito': True, 'pagina': '1', 'lineas': '1-9',
            'notas': {'1': 'nota uno del formato'},
            'columnas': [{'id': 'a', 'nombre': 'Col a', 'unidad': 'MW.h'}, {'id': 'b', 'nombre': 'Col b', 'unidad': 'kW'}],
            'filas': [
                {'id': 'G', 'nombre': 'GRUPO', 'unidad': '', 'tipo': 'grupo'},
                {'id': 'R1', 'nombre': 'Fila uno', 'unidad': 'u', 'no_aplica': ['b'], 'llamada': '1'},
                {'id': 'R2', 'nombre': 'Fila dos', 'unidad': 'u'},
                {'id': 'T', 'nombre': 'TOTAL', 'unidad': 'u', 'tipo': 'total'},
            ]}]}
    ruta = tmp_path / 'anexo2_sintetico.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return cargar_formatos(ruta)


def _tabla_sintetica(**filas):
    base = {'R1': {'unidad': 'u', 'a': 1.0}, 'R2': {'unidad': 'u', 'a': 2.0, 'b': 3.0}, 'T': {'unidad': 'u', 'a': 3.0, 'b': 3.0}}
    base.update(filas)
    return {'X-1': {'formato': 'X-1', 'periodo': '2025', 'unidades': {'a': 'MW.h', 'b': 'kW'}, 'filas': base}}


def test_celda_que_no_aplica_no_se_exige(tmp_path):
    """108:RF-3 (VAD-A5) — una celda gris del formato («no aplica») vacía no es un hueco."""
    res = validar_tablas(_tabla_sintetica(), _sintetico(tmp_path), periodo='2025')
    assert [h.linea() for h in res.huecos] == []
    assert res.completo


def test_celda_que_no_aplica_con_dato_da_un_aviso(tmp_path):
    """108:RF-3 (VAD-A5) — un dato en una celda gris se avisa por tabla y campo, sin borrarlo ni contarlo como hueco."""
    tablas = _tabla_sintetica(R1={'unidad': 'u', 'a': 1.0, 'b': 9.0})
    res = validar_tablas(tablas, _sintetico(tmp_path), periodo='2025')
    assert [(a.tabla, a.campo, a.tipo) for a in res.avisos] == [('X-1', 'R1.b', 'dato_en_no_aplica')]
    assert res.tablas['X-1']['filas']['R1']['b'] == 9.0, 'el dato no se toca'
    assert not res.huecos


def test_celda_que_aplica_sigue_siendo_obligatoria(tmp_path):
    """108:RF-3 (VAD-A5) — la columna que sí aplica en la misma fila sigue exigiéndose."""
    tablas = _tabla_sintetica(R1={'unidad': 'u'})
    res = validar_tablas(tablas, _sintetico(tmp_path), periodo='2025')
    assert [(h.campo, h.tipo) for h in res.huecos] == [('R1.a', 'campo_vacio')]


def test_fila_de_grupo_es_rotulo_y_la_de_total_se_exige(tmp_path):
    """108:RF-2 (VAD-A5) — la fila de grupo es solo rótulo (no se pide en la tabla); la de total es una fila del formato
    y, si falta, se nombra."""
    formatos = _sintetico(tmp_path)
    tipos = {f.id: f.tipo for f in formatos.formato('X-1').filas}
    assert tipos == {'G': 'grupo', 'R1': 'dato', 'R2': 'dato', 'T': 'total'}
    tablas = _tabla_sintetica()
    del tablas['X-1']['filas']['T']
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert [(h.campo, h.tipo) for h in res.huecos] == [('T', 'falta_campo')]


def test_llamada_a_nota_de_la_fila(tmp_path):
    """108:RF-2 (VAD-A5) — la llamada de una fila remite a la nota del formato, con su texto."""
    formato = _sintetico(tmp_path).formato('X-1')
    r1 = next(f for f in formato.filas if f.id == 'R1')
    assert r1.llamada == '1', r1
    assert formato.notas.get('1') == 'nota uno del formato', formato.notas


def test_a_v_1_y_a_vi_tal_cual_el_tdr_vigente():
    """108:RF-2 (VAD-A5) — el A-V-1 copia el original del TdR vigente (pdf 90): el BT6 dice «Pesión Fija» (sic, errata
    por «Pensión Fija»; nunca «Potencia Fija»), y BT5C-AP y BT6 llevan sus llamadas (1) y (2) con su nota. En el A-VI
    (pdf 93), la (47) es energía (MW.h) y la (48) un porcentaje."""
    formatos = cargar_formatos(FORMATOS)
    v1 = formatos.formato('A-V-1')
    filas = {f.id: f for f in v1.filas}
    assert filas['BT6'].nombre == '1P-BT, Pesión Fija'
    assert (filas['BT5C-AP'].llamada, filas['BT6'].llamada) == ('1', '2')
    assert v1.notas.get('1') == 'De conformidad al artículo 184º del Reglamento de la Ley de Concesiones Eléctricas'
    assert v1.notas.get('2') == 'Energía = Potencia x NHUBT'
    vi = {f.id: f.unidad for f in formatos.formato('A-VI').filas}
    assert (vi['(47)'], vi['(48)']) == ('MW.h', '%')


def _letras(fila):
    return sorted(c.split('.')[0] for c in fila.no_aplica)


def test_a_v_2_tiene_su_estructura_propia():
    """108:RF-2 (VAD-A5) — el A-V-2 ya no repite el V-1: sus grupos son «VENTAS A NIVEL GENERACIÓN-TRANSMISIÓN» y
    «VENTAS A NIVEL DISTRIBUCIÓN», y sus códigos BT5C y BT6NR (TdR vigente, pdf 91). V-1 y V-2 traen los 8 rangos del
    BT5B como filas propias."""
    formatos = cargar_formatos(FORMATOS)
    v1 = [f.id for f in formatos.formato('A-V-1').filas]
    v2 = [f.id for f in formatos.formato('A-V-2').filas]
    assert v1 != v2
    assert {'BT5C', 'BT6NR'} <= set(v2) and not {'BT5C-AP', 'BT6'} & set(v2)
    assert {'VENTAS A NIVEL GENERACIÓN-TRANSMISIÓN', 'VENTAS A NIVEL DISTRIBUCIÓN', 'TOTAL VENTAS'} <= set(v2)
    for fid in ('A-V-1', 'A-V-2'):
        rangos = [f for f in formatos.formato(fid).filas if f.rango_de == 'BT5B']
        assert len(rangos) == 8, fid
    grupos = {f.id: f.tipo for f in formatos.formato('A-V-2').filas}
    assert grupos['VENTAS A NIVEL DISTRIBUCIÓN'] == 'grupo' and grupos['TOTAL VENTAS'] == 'total'


def test_celdas_grises_del_tdr_vigente():
    """108:RF-3 (VAD-A5) — el mapa de celdas grises sale del original (pdf 90 a 92): la (d) no aplica en MAT1; en
    BT6 no aplican (b), (c), (e) ni (f). La incoherencia del propio TdR se conserva: en el V-3, BT5C-AP lleva la (d)
    en gris y en el V-1 no."""
    formatos = cargar_formatos(FORMATOS)
    v1 = {f.id: f for f in formatos.formato('A-V-1').filas}
    v3 = {f.id: f for f in formatos.formato('A-V-3').filas}
    assert _letras(v1['MAT1']) == ['d']
    assert _letras(v1['BT6']) == ['b', 'c', 'e', 'f']
    assert 'd' in _letras(v3['BT5C-AP']) and 'd' not in _letras(v1['BT5C-AP'])


def _v3(formatos, semilla=7):
    return _tabla(formatos.formato('A-V-3'), semilla)


def test_a_v_3_forma_larga_completa_sin_huecos():
    """108:RF-2 (VAD-A5) — el A-V-3 deja de ser hueco: es de forma larga, con un bloque por empresa, sistema y mes, y
    doce meses completos no dejan ningún hueco."""
    formatos = cargar_formatos(FORMATOS)
    v3 = formatos.formato('A-V-3')
    assert v3.transcrito and v3.forma == 'larga'
    assert v3.claves_de_fila == ('Empresa', 'Sistema', 'Mes', 'Año', 'Sector Típico')
    res = validar_tablas({'A-V-3': _v3(formatos)}, formatos, periodo='2025')
    assert [h.linea() for h in res.huecos if h.tabla == 'A-V-3'] == []


def test_a_v_3_mes_que_falta_bloque_repetido_y_clave_vacia():
    """108:RF-3 (VAD-A5) — en la forma larga, un mes que falta se nombra con su empresa y sistema, un bloque repetido
    y una clave vacía también; no se crea ningún bloque."""
    formatos = cargar_formatos(FORMATOS)
    assert formatos.formato('A-V-3').forma == 'larga', 'el A-V-3 es de forma larga'
    tabla = _v3(formatos)
    julio = tabla['bloques'].pop(6)
    tabla['bloques'].append(copy.deepcopy(tabla['bloques'][0]))
    sin_sistema = copy.deepcopy(tabla['bloques'][0])
    sin_sistema['claves']['Sistema'] = ''
    tabla['bloques'].append(sin_sistema)
    res = validar_tablas({'A-V-3': tabla}, formatos, periodo='2025')
    tipos = [(h.tipo, h.campo) for h in res.huecos if h.tabla == 'A-V-3']
    assert ('falta_bloque', 'E1 / S1 / 2025 / ST1') in tipos, tipos
    assert any(t == 'bloque_repetido' for t, _ in tipos), tipos
    assert ('campo_vacio', 'bloque 13.Sistema') in tipos, tipos
    falta = next(h for h in res.huecos if h.tipo == 'falta_bloque' and h.campo == 'E1 / S1 / 2025 / ST1')
    assert '[7]' in falta.detalle and julio['claves']['Mes'] == 7
    assert len(res.tablas['A-V-3']['bloques']) == 13, 'no se crea ni se quita ningún bloque'


def test_equivalencias_de_codigos_cubren_los_formatos_v():
    """108:RF-2 (VAD-A5) — la tabla de equivalencias (decisión anotada) une cada código de V-1, V-2 y V-3 con los
    demás, sin cambiarlo en su formato: cada fila de dato está en su columna y cada código de la tabla existe."""
    formatos = cargar_formatos(FORMATOS)
    assert formatos.equivalencias
    for fid in ('A-V-1', 'A-V-2', 'A-V-3'):
        datos = {f.id for f in formatos.formato(fid).filas if f.tipo == 'dato'}
        en_tabla = {e[fid] for e in formatos.equivalencias if e.get(fid)}
        assert datos == en_tabla, (fid, sorted(datos ^ en_tabla))
    assert {e['A-V-1'] for e in formatos.equivalencias if e['A-V-3'] == 'BT5BNR'} == {'BT5NR'}
    assert {e['A-V-2'] for e in formatos.equivalencias if e['A-V-1'] == 'BT6'} == {'BT6NR'}


# --- VAD-A5 ampliada (108:RF-2, RF-3): el resto del anexo 2 desde el TdR vigente (z1 y z7 de cc) ----------------------

def test_ya_no_queda_ningun_formato_sin_transcribir():
    """108:RF-2 (VAD-A5 ampliada) — III-1, IV-1 a IV-4, VIII-1/2 e IX-1/2 están transcritos del vigente (pdf 85 a 98)
    con su fuente; los bloques «sin transcribir» desaparecen y no hay ningún VII-2, que el anexo no tiene."""
    formatos = cargar_formatos(FORMATOS)
    ids = [f.id for f in formatos.todos()]
    nuevos = ['A-III-1', 'A-IV-1', 'A-IV-2', 'A-IV-3', 'A-IV-4', 'A-VIII-1', 'A-VIII-2', 'A-IX-1', 'A-IX-2']
    assert [i for i in nuevos if i not in ids] == []
    assert [f.id for f in formatos.todos() if not f.transcrito] == []
    assert not [i for i in ids if 'VII-2' in i or 'restantes' in i]
    datos = {f['id']: f for f in json.loads(FORMATOS.read_text(encoding='utf-8'))['formatos']}
    assert all(datos[i].get('fuente_vigente', {}).get('sha256', '').startswith('fb534170') for i in nuevos)


def test_a_i_1_desglose_del_subtotal_de_baja_tension_y_sus_grupos():
    """108:RF-2 (VAD-A5 ampliada) — el A-I-1 (pdf 82) trae, detrás del «Sub Total Red Baja Tensión», sus 4 filas de
    desglose, y las 7 filas de grupo del original; «Red Aérea» es dato en Media Tensión y grupo en Baja Tensión."""
    filas = list(cargar_formatos(FORMATOS).formato('A-I-1').filas)
    ids = [f.id for f in filas]
    i = ids.index('BT.subtotal')
    assert ids[i + 1:i + 5] == ['BT.subtotal.servicio_particular', 'BT.subtotal.alumbrado_publico',
                                'BT.subtotal.luminarias', 'BT.subtotal.equipos_de_control']
    assert all(f.tipo == 'total' for f in filas[i + 1:i + 5])
    assert len([f for f in filas if f.tipo == 'grupo']) == 7
    tipo = {f.id: f.tipo for f in filas}
    assert (tipo['MT.red_aerea'], tipo.get('grupo.red_aerea.16')) == ('dato', 'grupo')


def test_notas_literales_del_i_2_del_ii_y_del_vii_1():
    """108:RF-2 (VAD-A5 ampliada) — el I-2 lleva sus 3 notas, el II sus 2 y el VII-1 sus 4, con la llamada de cada
    columna del VII-1: Otros (1), Otros (2), PTU (3) y Total (4)."""
    formatos = cargar_formatos(FORMATOS)
    assert [len(formatos.formato(i).notas) for i in ('A-I-2', 'A-II', 'A-VII-1')] == [3, 2, 4]
    v7 = formatos.formato('A-VII-1')
    assert {c.id: c.llamada for c in v7.columnas if c.llamada} == {'rem.otros': '1', 'ap.otros': '2', 'ap.ptu': '3',
                                                                   'total': '4'}
    assert 'retiro' in v7.notas.get('3', '')


def _fila_vii_1(formato, ptu):
    fila = {c.id: 1000.0 for c in formato.columnas}
    fila['cantidad'] = 3
    fila['ap.ptu'] = ptu
    return fila


def test_la_ptu_se_informa_y_no_suma_en_el_costo_reconocible():
    """108:RF-3 (VAD-A5 ampliada) — por la nota (3) del A-VII-1 y el TdR 6.14, la PTU se pide para retirarla: el costo
    reconocible es la suma de las demás remuneraciones y aportes y no cambia con la PTU; es el Total (4) menos la PTU.
    Una columna que suma y viene vacía se nombra y el costo no se da."""
    v7 = cargar_formatos(FORMATOS).formato('A-VII-1')
    suman = v7.reconocible.get('suman') or []
    assert len(suman) == 11 and 'ap.ptu' not in suman and v7.reconocible.get('no_suman') == ['ap.ptu']
    sin_ptu = costo_reconocible(v7, _fila_vii_1(v7, 0.0))
    con_ptu = costo_reconocible(v7, _fila_vii_1(v7, 987654.0))
    assert sin_ptu == (11000.0, [])
    assert con_ptu == sin_ptu, 'la PTU no suma'
    fila = _fila_vii_1(v7, 500.0)
    total = sum(fila[c] for c in suman) + fila['ap.ptu']
    assert costo_reconocible(v7, fila)[0] == total - fila['ap.ptu']
    fila['ap.cts'] = None
    assert costo_reconocible(v7, fila) == (None, ['ap.cts'])


def test_las_limitaciones_del_vii_1_se_avisan():
    """108:RF-3 (VAD-A5 ampliada) — las horas extra (excluidas por el 6.14, sin columna) y lo cargado a inversiones
    (nota (4)) no se pueden separar con el formato: se avisan al validar el A-VII-1, sin contarlas como hueco."""
    formatos = cargar_formatos(FORMATOS)
    tabla = _tabla(formatos.formato('A-VII-1'), 3)
    res = validar_tablas({'A-VII-1': tabla}, formatos, periodo='2025')
    limitaciones = [a for a in res.avisos if a.tabla == 'A-VII-1' and a.tipo == 'limitacion_del_formato']
    assert len(limitaciones) == 2, res.avisos
    assert any('HORAS EXTRA' in a.detalle.upper() for a in limitaciones)
    assert any('INVERSIONES' in a.detalle.upper() for a in limitaciones)


def test_actividades_del_ix_casan_por_rotulo():
    """108:RF-2 (VAD-A5 ampliada) — el IX usa A12 y A13 con otro sentido que III-1, IV-4 y VIII: por rótulo (decisión
    anotada), IX.A13 «Apoyo en Postes» es A12 y IX.A12 «Asesoría a Terceros» va dentro de A13 «Otros Servicios»."""
    datos = json.loads(FORMATOS.read_text(encoding='utf-8'))
    eq = datos.get('equivalencias_de_actividades') or {}
    assert eq.get('del_ix_al_resto') == {'A12': 'A13', 'A13': 'A12'}
    formatos = cargar_formatos(FORMATOS)
    ix = {c.id: c.nombre for c in formatos.formato('A-IX-1').columnas}
    iii = {f.id: f.nombre for f in formatos.formato('A-III-1').filas}
    assert 'Apoyo en Postes' in ix['A13'] and iii['A12'] == 'Apoyo en Postes'
    assert 'Asesoría a Terceros' in ix['A12'] and iii['A13'] == 'Otros Servicios'


def test_los_codigos_del_ix_casados_por_rotulo_se_explican_y_se_avisan():
    """108:RF-3 (VAD-A5 v3) — la inclusión «IX.A12 ⊂ A13» se explica en la config con la cita de las páginas de los dos
    lados (IX, pdf 97 y 98; III-1, IV-4 y VIII, pdf 85, 89 y 95), y validar el IX-1 o el IX-2 avisa de que sus
    códigos se casan por rótulo, sin contarlo como hueco."""
    datos = json.loads(FORMATOS.read_text(encoding='utf-8'))
    explicacion = (datos.get('equivalencias_de_actividades') or {}).get('explicacion_de_la_inclusion') or {}
    paginas = {c.get('pagina_pdf') for c in explicacion.get('citas') or ()}
    assert {85, 89, 95, 97, 98} <= paginas, paginas
    assert 'Otros Servicios' in explicacion.get('texto', '') and 'no se inventa' in explicacion.get('texto', '')
    formatos = cargar_formatos(FORMATOS)
    for fid in ('A-IX-1', 'A-IX-2'):
        res = validar_tablas({fid: _tabla(formatos.formato(fid), 5)}, formatos, periodo='2025')
        avisos = [a for a in res.avisos if a.tabla == fid and a.tipo == 'codigos_casados_por_rotulo']
        assert len(avisos) == 1 and 'casados por rótulo' in avisos[0].detalle, (fid, res.avisos)
        assert not [h for h in res.huecos if h.tabla == fid], 'el aviso no es un hueco'
