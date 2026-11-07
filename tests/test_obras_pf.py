"""Spec 011, T10: lo que las obras de mejora deciden sin DIgSILENT (``obras_pf``)."""

from __future__ import annotations

import copy
import random

import pytest

from convertersmartgrid import obras_pf as op
from convertersmartgrid.estudios_pf import CON_PROYECTO, SIN_PROYECTO
from convertersmartgrid.naming import nombre_con_tension

#: Semillas de los sorteos: alimentadores, tensiones, tramos, tipos y orden de las obras.
SEMILLAS = (7, 19, 43, 88)


# --------------------------------------------------------------------------- sorteos
def _red(rng, alimentador: str, kv: float, tipos: dict[str, op.Tipo]) -> op.RedAlimentador:
    """Un alimentador con barras de media a ``kv``, barras de baja, tramos y SED."""
    lineas = [t for t in tipos.values() if t.clase == 'TypLne']
    trafos = [t for t in tipos.values() if t.clase == 'TypTr2']
    n = rng.randint(3, 12)
    barras = {f'{alimentador}_N{i}': kv for i in range(n)}
    barras.update({f'{alimentador}_BT{i}': 0.38 for i in range(rng.randint(1, 4))})
    tramos = {f'{alimentador}_L{i}': op.Tramo(f'{alimentador}_L{i}', rng.choice(lineas).nombre,
                                              rng.randint(1, 2))
              for i in range(n - 1)}
    troncal = tuple(sorted(rng.sample(sorted(tramos), rng.randint(1, len(tramos)))))
    sed = {f'{alimentador}_T{i}': rng.choice(trafos).nombre for i in range(rng.randint(1, 5))}
    return op.RedAlimentador(alimentador=alimentador, kv=kv, barras=barras, tramos=tramos,
                             troncal=troncal, trafos=sed)


def _biblioteca(rng, kv: float) -> dict[str, op.Tipo]:
    tipos = {}
    for s in rng.sample([35, 50, 70, 120, 240], rng.randint(2, 4)):
        nombre = f'AAAC_{s}'
        tipos[nombre] = op.Tipo(nombre, 'TypLne', {'uline': kv, 'qurs': float(s),
                                                    'sline': 0.003 * s, 'rline': 30.0 / s})
    for p in rng.sample([25, 50, 100, 160, 250], rng.randint(1, 3)):
        nombre = f'TR{p}'
        tipos[nombre] = op.Tipo(nombre, 'TypTr2', {'strn': p / 1000, 'utrn_h': kv, 'utrn_l': 0.38})
    return tipos


def _escenario(semilla):
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 13.2, 22.9])
    tipos = _biblioteca(rng, kv)
    alims = sorted({f'AL{rng.randint(100, 999)}' for _ in range(rng.randint(1, 4))})
    redes = {a: _red(rng, a, kv, tipos) for a in alims}
    return rng, kv, tipos, redes


def _obra(**datos) -> op.Obra:
    datos.setdefault('casos', [SIN_PROYECTO, CON_PROYECTO])
    return op.validar_obra(datos)


# --------------------------------------------------------------------------- validación
def test_cada_clase_de_obra_se_valida_y_vuelve_igual_del_espacio():
    """011:RF-56 — cada obra se valida al definirla y su forma de diccionario la reconstruye
    igual (la que guardará el espacio de trabajo)."""
    obras = [
        _obra(clase='condensador', alimentador='A1', barra='N3', q_kvar=600, escalones=3),
        _obra(clase='condensador', alimentador='A1', barra='N3', q_kvar=300, escalones=1,
              consigna_pu=1.0, casos=[SIN_PROYECTO, CON_PROYECTO]),
        _obra(clase='reconectador', alimentador='A1', tramo='L2'),
        _obra(clase='regulador', alimentador='A1', tramo='L2', consigna_pu=1.0, rango_pct=10,
              pasos=16, tipo={'nombre': 'VR', 'clase': 'TypVoltreg'}),
        _obra(clase='seccion', alimentador='A1', tipo={'nombre': 'AAAC_240', 'clase': 'TypLne'}),
        _obra(clase='terna', alimentador='A1', tramos=['L1', 'L2']),
        _obra(clase='tension', alimentador='A1', kv_destino=22.9, casos=[CON_PROYECTO]),
    ]
    for obra in obras:
        assert op.validar_obra(obra.a_dict()) == obra


@pytest.mark.parametrize('datos, falta', [
    ({'clase': 'puente', 'alimentador': 'A1'}, 'clase'),
    ({'clase': 'terna'}, 'alimentador'),
    ({'clase': 'condensador', 'alimentador': 'A1', 'barra': 'N1', 'q_kvar': -5, 'escalones': 1},
     'potencia'),
    ({'clase': 'condensador', 'alimentador': 'A1', 'barra': 'N1', 'q_kvar': 300, 'escalones': 0},
     'escalones'),
    ({'clase': 'condensador', 'alimentador': 'A1', 'q_kvar': 300, 'escalones': 1}, 'barra'),
    ({'clase': 'reconectador', 'alimentador': 'A1'}, 'tramo'),
    ({'clase': 'regulador', 'alimentador': 'A1', 'tramo': 'L1', 'rango_pct': 10, 'pasos': 16,
      'tipo': {'nombre': 'VR', 'clase': 'TypVoltreg'}}, 'consigna'),
    ({'clase': 'seccion', 'alimentador': 'A1'}, 'tipo'),
    ({'clase': 'seccion', 'alimentador': 'A1', 'tipo': {'nombre': 'X', 'clase': 'TypTr2'}}, 'TypLne'),
    ({'clase': 'tension', 'alimentador': 'A1'}, 'tensión'),
    ({'clase': 'tension', 'alimentador': 'A1', 'kv_destino': 0}, 'tensión'),
    ({'clase': 'terna', 'alimentador': 'A1', 'casos': []}, 'caso'),
    ({'clase': 'terna', 'alimentador': 'A1', 'casos': ['Otro']}, 'caso'),
])
def test_una_obra_incompleta_se_rechaza_diciendo_que_falta(datos, falta):
    """011:RF-56 — una obra sin lo que necesita no se acepta; el mensaje lo nombra."""
    datos.setdefault('casos', [SIN_PROYECTO, CON_PROYECTO])
    with pytest.raises(op.ObrasError, match=falta):
        op.validar_obra(datos)


def test_ninguna_obra_se_activa_en_el_caso_base():
    """011:RF-58 — el «Caso base» no se puede elegir para una obra."""
    with pytest.raises(op.ObrasError, match='Caso base'):
        op.validar_obra({'clase': 'terna', 'alimentador': 'A1', 'casos': ['Caso base']})


def test_la_tension_de_origen_es_la_del_alimentador_y_la_de_destino_la_del_operador():
    """011:RF-85 — sin tensiones fijas: el origen sale de la red leída y el destino de la obra.

    Se sortean las dos, y una migración a la misma tensión que ya tiene se rechaza.
    """
    for semilla in SEMILLAS:
        rng, kv, tipos, redes = _escenario(semilla)
        a = next(iter(redes))
        destino = rng.choice([x for x in (6.6, 10.0, 13.2, 22.9, 33.0) if x != kv])
        plan = op.plan_simulacion([_obra(clase='tension', alimentador=a, kv_destino=destino)],
                                  redes, tipos.values())
        assert not plan[0]['error']
        assert plan[0]['kv_origen'] == kv and plan[0]['kv_destino'] == destino
        igual = op.plan_simulacion([_obra(clase='tension', alimentador=a, kv_destino=kv)],
                                   redes, tipos.values())
        assert 'ya está' in igual[0]['error']


# --------------------------------------------------------------------------- nombres
def test_variaciones_con_nombre_de_obra_y_alimentador_sin_repetir():
    """011:RF-56 — una variación por obra, con la obra y el alimentador en el nombre y sin
    repetir el de una variación existente (sin distinguir mayúsculas, como DIgSILENT); la
    misma obra pedida dos veces lleva otro nombre."""
    for semilla in SEMILLAS:
        rng, kv, tipos, redes = _escenario(semilla)
        a = next(iter(redes))
        obra = _obra(clase='terna', alimentador=a)
        existentes = {f'obra_terna_{a}'.upper()} if rng.random() < 0.5 else set()
        plan = op.plan_simulacion([obra, obra], redes, tipos.values(), variaciones=existentes)
        nombres = [p['variacion'] for p in plan]
        assert all('terna' in n and a in n for n in nombres)
        assert len({n.lower() for n in nombres} | {e.lower() for e in existentes}) == \
            len(nombres) + len(existentes)
        assert all(len(n) <= op.LARGO_MAXIMO for n in nombres)


def test_bancos_y_reguladores_propuestos_en_su_variacion_solo_en_con_proyecto():
    """017:RF-40d — un banco y un regulador propuestos van cada uno en su variación, con
    su clase en el nombre, y se piden solo para «Con proyecto»."""
    banco = _obra(clase='condensador', alimentador='AL01', barra='N3', q_kvar=300, escalones=1,
                  casos=[CON_PROYECTO])
    regulador = _obra(clase='regulador', alimentador='AL01', tramo='L4', consigna_pu=1.0,
                      rango_pct=10, pasos=16, tipo={'nombre': 'VR', 'clase': 'TypVoltreg'},
                      casos=[CON_PROYECTO])
    assert banco.casos == regulador.casos == (CON_PROYECTO,)
    ocupadas: list[str] = []
    for obra in (banco, regulador, banco):
        ocupadas.append(op.nombre_variacion(obra, ocupadas))
    assert len({n.lower() for n in ocupadas}) == 3
    assert 'condensador' in ocupadas[0] and 'regulador' in ocupadas[1]


def test_nombre_libre_respeta_el_largo_de_digsilent():
    """011:RF-56 — el sufijo que desempata no hace pasar de 40 caracteres."""
    base = 'X' * 40
    assert op.nombre_libre(base, {base}) == 'X' * 38 + '_2'
    assert op.nombre_libre('Obra-1.a/b', set()) == 'Obra-1_a_b'


def test_copia_de_tipo_con_el_sufijo_de_tension_del_conversor():
    """011:RF-61 — la copia lleva el nombre del original y el cambio; la tensión con el
    sufijo del conversor, sin acumular el de la tensión de origen."""
    assert op.nombre_copia('AAAC_70', kv=22.9) == nombre_con_tension('AAAC_70', 22.9)
    assert op.nombre_copia('AAAC_70_10kV', kv=22.9, kv_origen=10.0) == 'AAAC_70_22_9kV'
    assert op.nombre_copia('VR', cambio='10pct_16p') == 'VR_10pct_16p'
    largo = op.nombre_copia('N' * 45, kv=22.9)
    assert len(largo) == op.LARGO_MAXIMO and largo.endswith('_22_9kV')


# --------------------------------------------------------------------------- tipos
def test_igualdad_de_tipos_por_sus_datos():
    """011:RF-62, 011:RF-63 — dos tipos son el mismo si tienen los mismos datos; un dato de
    más o distinto los separa, y una diferencia de redondeo no."""
    a = {'uline': 22.9, 'qurs': 70.0, 'sline': 0.21}
    assert op.mismos_datos(a, dict(a))
    assert op.mismos_datos(a, {**a, 'uline': 22.9 + 1e-12})
    assert not op.mismos_datos(a, {**a, 'uline': 10.0})
    assert not op.mismos_datos(a, {**a, 'rline': 0.4})


def test_copia_reutilizada_o_con_otro_nombre():
    """011:RF-62, 011:RF-63 — se reutiliza la copia con el mismo nombre y datos; con el mismo
    nombre y otros datos se crea con otro nombre libre y se dice."""
    datos = {'uline': 22.9, 'qurs': 70.0}
    proyecto = {'AAAC_70_22_9kV': op.Tipo('AAAC_70_22_9kV', 'TypLne', dict(datos))}
    nombre, reutiliza, aviso = op.resolver_copia('AAAC_70_22_9kV', 'TypLne', datos, proyecto)
    assert (nombre, reutiliza, aviso) == ('AAAC_70_22_9kV', True, '')
    otros = {**datos, 'qurs': 95.0}
    nombre, reutiliza, aviso = op.resolver_copia('AAAC_70_22_9kV', 'TypLne', otros, proyecto)
    assert nombre == 'AAAC_70_22_9kV_2' and not reutiliza
    assert 'AAAC_70_22_9kV' in aviso and 'otros datos' in aviso


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_ninguna_obra_cambia_un_tipo_existente(semilla):
    """011:RF-59 — el plan nunca cambia un tipo del proyecto: cada tipo que nombra es nuevo
    o se reutiliza tal cual, y la biblioteca leída queda intacta."""
    rng, kv, tipos, redes = _escenario(semilla)
    antes = copy.deepcopy(tipos)
    destino = 33.0 if kv != 33.0 else 22.9
    seccion = rng.choice([t for t in tipos.values() if t.clase == 'TypLne'])
    obras = []
    for a in redes:
        obras.append(_obra(clase='tension', alimentador=a, kv_destino=destino))
        obras.append(_obra(clase='seccion', alimentador=a,
                           tipo={'nombre': seccion.nombre, 'clase': 'TypLne'}))
        obras.append(_obra(clase='terna', alimentador=a))
    rng.shuffle(obras)
    plan = op.plan_simulacion(obras, redes, tipos.values())
    assert tipos == antes
    for p in plan:
        assert not p['error'], p
        for t in p['tipos']:
            assert t['reutiliza'] or t['nombre'].lower() not in {n.lower() for n in antes}


# --------------------------------------------------------------------------- simulación
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_simulacion_dice_elementos_tipos_y_variacion_de_cada_obra(semilla):
    """011:RF-69 — por obra: los elementos que cambiaría, los tipos que copiaría y el nombre
    de su variación, sin escribir nada (las redes y los tipos leídos quedan iguales)."""
    rng, kv, tipos, redes = _escenario(semilla)
    a = rng.choice(sorted(redes))
    red = redes[a]
    redes_antes = copy.deepcopy(redes)
    barra = rng.choice(sorted(b for b, v in red.barras.items() if v == kv))
    tramo = rng.choice(sorted(red.tramos))
    vr = op.Tipo('VR', 'TypVoltreg', {'Un': kv, 'In': 0.2, 'pcReg': 10.0, 'ntapmax': 16,
                                      'ntapmin': -16}, origen='global')
    obras = [
        _obra(clase='condensador', alimentador=a, barra=barra, q_kvar=600, escalones=3),
        _obra(clase='reconectador', alimentador=a, tramo=tramo),
        _obra(clase='regulador', alimentador=a, tramo=tramo, consigna_pu=1.0, rango_pct=10,
              pasos=32, tipo={'nombre': 'VR', 'clase': 'TypVoltreg', 'origen': 'global'}),
        _obra(clase='terna', alimentador=a, tramos=[tramo]),
    ]
    plan = op.plan_simulacion(obras, redes, [*tipos.values(), vr])
    assert redes == redes_antes
    assert [p['clase'] for p in plan] == ['condensador', 'reconectador', 'regulador', 'terna']
    cond, rec, reg, terna = plan
    assert [e['clase'] for e in cond['elementos']] == ['ElmShnt'] and not cond['tipos']
    assert barra in cond['elementos'][0]['elemento']
    assert {e['clase'] for e in rec['elementos']} == {'StaSwitch'}            # 011:RF-73
    assert {e['clase'] for e in reg['elementos']} == {'ElmTerm', 'ElmVoltreg', 'StaCubic'}
    # El regulador global se copia al proyecto con el rango y los pasos pedidos (RF-76, RF-92).
    assert len(reg['tipos']) == 1 and reg['tipos'][0]['datos']['ntapmax'] == 32
    assert reg['tipos'][0]['nombre'] == 'VR_10pct_32p'
    n = red.tramos[tramo].nlnum
    assert terna['elementos'] == [{'elemento': tramo, 'clase': 'ElmLne', 'cambio': f'nlnum {n} → {n + 1}'}]
    assert len({p['variacion'] for p in plan}) == len(plan)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_simulacion_de_la_migracion_copia_un_tipo_por_original(semilla):
    """011:RF-69, 011:RF-85 — la migración lista las barras de media (las de la tensión de
    origen, no las de baja), una copia por tipo de línea y de SED a la tensión nueva, y en
    las SED solo cambia la alta."""
    rng, kv, tipos, redes = _escenario(semilla)
    a = rng.choice(sorted(redes))
    red = redes[a]
    destino = rng.choice([x for x in (10.0, 22.9, 33.0) if x != kv])
    p = op.plan_simulacion([_obra(clase='tension', alimentador=a, kv_destino=destino)],
                           redes, tipos.values())[0]
    barras = {e['elemento'] for e in p['elementos'] if e['clase'] == 'ElmTerm'}
    assert barras == {b for b, v in red.barras.items() if v == kv}
    usados_lne = {t.tipo for t in red.tramos.values()}
    usados_tr = set(red.trafos.values())
    copias = {t['desde']: t for t in p['tipos']}
    assert set(copias) == usados_lne | usados_tr
    for nombre in usados_tr:
        datos = copias[nombre]['datos']
        assert datos['utrn_h'] == destino
        assert (datos['utrn_l'], datos['strn']) == (tipos[nombre].datos['utrn_l'], tipos[nombre].datos['strn'])
    for nombre in usados_lne:
        assert copias[nombre]['datos']['uline'] == destino
        assert copias[nombre]['nombre'] == nombre_con_tension(nombre, destino)


def test_migracion_rechazada_si_la_cabecera_la_comparte_otro_alimentador():
    """011:RF-69 — la simulación ya dice que la migración no se puede aplicar, y por qué."""
    rng, kv, tipos, redes = _escenario(SEMILLAS[0])
    a = next(iter(redes))
    redes = {**redes, a: op.RedAlimentador(**{**vars(redes[a]), 'cabecera_compartida_con': ('OTRO',)})}
    p = op.plan_simulacion([_obra(clase='tension', alimentador=a, kv_destino=99.0)],
                           redes, tipos.values())[0]
    assert 'OTRO' in p['error'] and not p['elementos']


def test_obra_sobre_lo_que_no_existe_se_rechaza_en_la_simulacion():
    """011:RF-69 — un alimentador, barra, tramo o tipo que no está en lo leído se rechaza en
    esa obra, con su nombre, sin tirar las demás."""
    rng, kv, tipos, redes = _escenario(SEMILLAS[1])
    a = next(iter(redes))
    obras = [
        _obra(clase='terna', alimentador='NO_ESTA'),
        _obra(clase='condensador', alimentador=a, barra='NO_BARRA', q_kvar=100, escalones=1),
        _obra(clase='reconectador', alimentador=a, tramo='NO_TRAMO'),
        _obra(clase='seccion', alimentador=a, tipo={'nombre': 'NO_TIPO', 'clase': 'TypLne'}),
        _obra(clase='terna', alimentador=a),
    ]
    plan = op.plan_simulacion(obras, redes, tipos.values())
    for p, falta in zip(plan, ('NO_ESTA', 'NO_BARRA', 'NO_TRAMO', 'NO_TIPO')):
        assert falta in p['error'] and not p['elementos']
    assert not plan[-1]['error'] and plan[-1]['elementos']


def test_seccion_fuera_de_la_troncal_se_cambia_y_se_anota():
    """011:RF-69 — la simulación de una sección en un tramo que no es de la troncal lo
    cambia igual y lo anota (RF-87)."""
    rng, kv, tipos, redes = _escenario(SEMILLAS[2])
    a = next(iter(redes))
    red = redes[a]
    fuera = sorted(set(red.tramos) - set(red.troncal))
    if not fuera:
        pytest.skip('el sorteo puso todos los tramos en la troncal')
    destino = next(t for t in tipos.values() if t.clase == 'TypLne')
    p = op.plan_simulacion([_obra(clase='seccion', alimentador=a, tramos=[fuera[0]],
                                  tipo={'nombre': destino.nombre, 'clase': 'TypLne'})],
                           redes, tipos.values())[0]
    assert any(fuera[0] in av and 'troncal' in av for av in p['avisos'])


def test_seccion_de_otra_tension_se_copia_a_la_del_alimentador():
    """011:RF-61, 011:RF-69 — un tipo de línea elegido a otra tensión se copia a la del
    alimentador, con el sufijo del conversor; uno de otra biblioteca se trae al proyecto."""
    rng, kv, tipos, redes = _escenario(SEMILLAS[3])
    a = next(iter(redes))
    ajeno = op.Tipo('XLPE_240', 'TypLne', {'uline': kv * 3, 'qurs': 240.0}, origen='otro',
                    proyecto='OtroPrj')
    p = op.plan_simulacion(
        [_obra(clase='seccion', alimentador=a,
               tipo={'nombre': 'XLPE_240', 'clase': 'TypLne', 'origen': 'otro', 'proyecto': 'OtroPrj'})],
        redes, [*tipos.values(), ajeno])[0]
    assert not p['error']
    (copia,) = p['tipos']
    assert copia['nombre'] == nombre_con_tension('XLPE_240', kv)
    assert copia['datos']['uline'] == kv and copia['origen'] == 'otro'


def test_consigna_de_cabecera_dentro_del_perfil_y_solo_con_proyecto():
    """019:RF-11 / 019:RF-12 — la consigna de cabecera es una clase registrada: dentro de los
    límites del perfil (0,95 a 1,05 por defecto), solo en «Con proyecto»."""
    obra = op.validar_obra({'clase': 'consigna', 'alimentador': 'A1',
                            'casos': [CON_PROYECTO], 'consigna_pu': 1.05})
    assert obra.consigna_pu == 1.05 and obra.casos == (CON_PROYECTO,)
    assert 'consigna' in op.VALIDADORES and 'consigna' in op.CLASES
    with pytest.raises(op.ObrasError, match='entre 0.95 y 1.05'):
        op.validar_obra({'clase': 'consigna', 'alimentador': 'A1', 'casos': [CON_PROYECTO],
                         'consigna_pu': 1.08})
    with pytest.raises(op.ObrasError, match='solo en «Con proyecto»'):
        op.validar_obra({'clase': 'consigna', 'alimentador': 'A1',
                         'casos': [SIN_PROYECTO, CON_PROYECTO], 'consigna_pu': 1.02})


# --------------------------------------------------------------------------- 042:RF-98 a RF-101
def _red_terna(rng, kv):
    """Tramos aéreos delgados y gruesos y cables, con los tipos de una empresa ficticia (P13)."""
    tipos = {n: op.Tipo(n, 'TypLne', {'uline': kv, 'sline': a / 1000, 'cohl_': c})
             for n, a, c in (('AX050', 150, 1), ('AX120', 300, 1), ('AX240', 450, 1), ('CX070', 200, 0), ('CX120', 320, 0))}
    tramos = {}
    for i in range(rng.randint(4, 9)):
        cable = rng.random() < 0.3
        tipo = rng.choice(['CX070', 'CX120'] if cable else ['AX050', 'AX120', 'AX240'])
        tramos[f'L{i}'] = op.Tramo(f'L{i}', tipo, rng.randint(1, 2), cable, rng.uniform(100, 900))
    red = op.RedAlimentador(alimentador='A1', kv=kv, barras={'N0': kv}, tramos=tramos, troncal=tuple(sorted(tramos)))
    return tipos, red


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_conductor_terna_en_la_simulacion(semilla):
    """042:RF-98, 042:RF-99, 042:RF-100 — con el conductor de la obra, el tramo más delgado pasa a él y suma la terna;
    el de igual o más corriente suma la de su tipo, con aviso; sin conductor de cable, el cable es como antes."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    tipos, red = _red_terna(rng, kv)
    con_cable = rng.random() < 0.5
    datos = {'clase': 'terna', 'alimentador': 'A1', 'casos': [CON_PROYECTO],
             'tipo': {'nombre': 'AX120', 'clase': 'TypLne'},
             **({'tipo_cable': {'nombre': 'CX120', 'clase': 'TypLne'}} if con_cable else {})}
    obra = op.validar_obra(datos)
    assert op.validar_obra(obra.a_dict()) == obra
    (fila,) = op.plan_simulacion([obra], {'A1': red}, tipos.values())
    assert not fila['error'], fila
    por_tramo = {e['elemento']: e for e in fila['elementos']}
    assert set(por_tramo) == set(red.tramos)
    for nombre, t in red.tramos.items():
        e = por_tramo[nombre]
        assert e['cambio'].endswith(f'nlnum {t.nlnum} → {t.nlnum + 1}')
        nuevo = ('CX120' if con_cable else None) if t.cable else 'AX120'
        cambia = nuevo is not None and tipos[t.tipo].datos['sline'] < tipos[nuevo].datos['sline']
        assert e.get('tipo') == (nuevo if cambia else None), (nombre, t, e)
        if not cambia and nuevo is not None:
            assert any(nombre in a and '042:RF-99' in a for a in fila['avisos'])
        if t.cable and not con_cable:
            assert any(nombre in a and '042:RF-100' in a for a in fila['avisos'])


def test_conductor_terna_una_obra_guardada_sin_tipo_se_abre_igual():
    """042:RF-101 — la terna guardada antes de RF-98, sin tipo, se valida y simula igual: una terna más, sin avisos."""
    rng = random.Random(42101)
    tipos, red = _red_terna(rng, 22.9)
    guardada = {'clase': 'terna', 'alimentador': 'A1', 'casos': [CON_PROYECTO], 'tramos': ['L0', 'L1']}
    obra = op.validar_obra(guardada)
    assert obra.tipo is None and obra.tipo_cable is None and obra.a_dict() == guardada
    (fila,) = op.plan_simulacion([obra], {'A1': red}, tipos.values())
    assert fila['elementos'] == [{'elemento': n, 'clase': 'ElmLne',
                                  'cambio': f'nlnum {red.tramos[n].nlnum} → {red.tramos[n].nlnum + 1}'}
                                 for n in ('L0', 'L1')]
    assert not fila['avisos']


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_la_mitad_partida_por_una_carga_nueva_es_su_tramo_entero(semilla):
    """098:RF-38 — con las cargas nuevas apartadas al grabar, la mitad «(1)» que dejó una carga al partir un tramo no
    existe: la obra la toma como el tramo entero, una vez. CA101 (2026-11-07): «SEC_1091_1081392(1) no es del
    alimentador» y toda terna por ahí salía «no cumple» sin medirse."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    tipos, red = _red_terna(rng, kv)
    entero = rng.choice(sorted(red.tramos))
    datos = {'clase': 'terna', 'alimentador': 'A1', 'casos': [CON_PROYECTO],
             'tramos': [entero, f'{entero}(1)'], 'tipo': {'nombre': 'AX120', 'clase': 'TypLne'}}
    (fila,) = op.plan_simulacion([op.validar_obra(datos)], {'A1': red}, tipos.values())
    assert not fila['error'], fila
    assert [e['elemento'] for e in fila['elementos']] == [entero]
    (otra,) = op.plan_simulacion([op.validar_obra({**datos, 'tramos': ['NO_EXISTE(1)']})], {'A1': red}, tipos.values())
    assert 'no es del alimentador' in otra['error']
