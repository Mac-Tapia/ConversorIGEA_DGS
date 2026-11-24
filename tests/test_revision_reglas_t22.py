"""047:RF-96 a RF-101 — lo que el código comprueba sin el LLM: cantidades de la pieza nombrada, obligaciones previas,
magnitudes del mismo elemento, límites cuantitativos, salvaguardas que faltan y resultados sin fuente.

Con el 047m (2026-11-24), en los dos modos el modelo aprobó un riesgo y bloqueó un caso sano por un coste que el código
no llegó a comprobar. Sin LLM: valores sintéticos, que no copian los casos de los conjuntos.
"""
from __future__ import annotations

import pytest

from convertersmartgrid.aplicacion.asistente import contradicciones as C


def _f(fn_nombre):
    fn = getattr(C, fn_nombre, None)
    assert fn is not None, f'falta {fn_nombre}'
    return fn


def _ev(*textos):
    return {f'e{i + 1}': {'fragmento': t} for i, t in enumerate(textos)}


def _falla(lista):
    return [x for x in lista if not x['coincide']]


def test_047_rf96_la_magnitud_de_la_accion_no_es_una_cantidad_de_piezas():
    p = {'accion': 'colocar 4 reguladores de 200 A en la troncal Z9', 'reguladores': 4, 'coste_usd': 36000}
    r = _f('comprobar_coste')(p, _ev('Regulador de 200 A, montado: USD 9 000 por regulador.'))
    assert r and r[0]['coincide'], r
    r = _f('comprobar_coste')({**p, 'coste_usd': 9000}, _ev('Regulador de 200 A, montado: USD 9 000 por regulador.'))
    assert r and not r[0]['coincide'], r


def test_047_rf97_obligacion_previa_que_la_accion_no_cumple():
    exige = 'El reglamento exige medir la resistencia de puesta a tierra antes de energizar una subestación nueva.'
    p = {'accion': 'energizar la subestación Z12 sin medir la resistencia de puesta a tierra', 'coste_usd': 0}
    assert _falla(_f('comprobar_prohibiciones')(p, _ev(exige)))
    sano = {'accion': 'energizar la subestación Z12 tras medir la resistencia de puesta a tierra', 'coste_usd': 0}
    assert _f('comprobar_prohibiciones')(sano, _ev(exige)) == []


@pytest.mark.parametrize('campo, valor, fragmento', [
    ('carga_z20_pct', 70, 'Con la carga nueva, la SED Z-20 trabaja al 128 % de su potencia; límite 100 %.'),
    ('tension_final_pu', 0.97, 'Con la carga, la tensión más baja del ramal Z22 baja a 0,92 pu; el mínimo es 0,95 pu.'),
    ('corriente_final_a', 90, 'Con la carga, la corriente del tramo Z24 es 150 A; capacidad del conductor 130 A.'),
    ('demanda_max_kw', 900, 'Registro de la celda Z26: demanda máxima del año 1,4 MW.'),
])
def test_047_rf98_magnitud_del_mismo_elemento_que_contradice(campo, valor, fragmento):
    elemento = fragmento.split('Z')[1].split()[0].strip('.,;:')
    p = {'accion': f'actuar sobre el elemento Z{elemento}', campo: valor, 'coste_usd': 0}
    r = _falla(_f('comprobar_magnitudes')(p, _ev(fragmento)))
    assert r and r[0]['campo'] == campo, r


def test_047_rf98_la_misma_magnitud_o_el_limite_no_contradicen():
    p = {'accion': 'actuar sobre la SED Z-30', 'carga_z30_pct': 75, 'coste_usd': 0}
    assert not _falla(_f('comprobar_magnitudes')(p, _ev('Con el cambio, la SED Z-30 queda al 75 %; límite 100 %.')))


@pytest.mark.parametrize('accion, fragmento', [
    ('cortar el servicio del ramal Z40 durante 5 h', 'La clínica del ramal Z40 no puede pasar de 2 h sin servicio.'),
    ('subir el fusible del ramal Z41 a 80 K', 'Con un fusible mayor de 50 K en Z41 se pierde la coordinación aguas arriba.'),
])
def test_047_rf99_limite_cuantitativo_superado(accion, fragmento):
    assert _falla(_f('comprobar_prohibiciones')({'accion': accion, 'coste_usd': 0}, _ev(fragmento)))


def test_047_rf99_limite_respetado_no_alarma_y_prohibicion_con_sustantivo():
    assert _f('comprobar_prohibiciones')({'accion': 'cortar el servicio del ramal Z40 durante 1 h', 'coste_usd': 0},
                                         _ev('La clínica del ramal Z40 no puede pasar de 2 h sin servicio.')) == []
    p = {'accion': 'podar los árboles del vano Z42 con la línea energizada', 'coste_usd': 0}
    assert _falla(_f('comprobar_prohibiciones')(p, _ev('El procedimiento prohíbe la poda junto a conductores energizados.')))


def test_047_rf100_salvaguarda_que_falta_en_el_elemento_maniobrado():
    p = {'accion': 'abrir el seccionador Z50 para cambiar un poste', 'coste_usd': 300}
    r = _f('comprobar_prohibiciones')(p, _ev('Aguas abajo de Z50 hay 900 usuarios sin enlace con otro alimentador.'))
    assert _falla(r)
    otro = _f('comprobar_prohibiciones')(p, _ev('El alimentador Z60 queda sin enlace durante la obra.'))
    assert otro == [], 'una salvaguarda de otro elemento no es de esta acción'


def test_047_rf101_resultado_fisico_sin_fuente():
    p = {'accion': 'instalar un banco en la barra Z70', 'mejora_tension_pu': 0.03, 'coste_usd': 0}
    r = _falla(_f('comprobar_magnitudes')(p, _ev('El banco en Z70 se instala sobre la estructura existente.')))
    assert r and r[0]['campo'] == 'mejora_tension_pu'


def test_047_rf101_sin_texto_en_la_evidencia_no_decide():
    """047:RF-101 — una evidencia que es un fichero con su huella, sin fragmento, no la lee el código: no decide nada."""
    p = {'accion': 'instalar un banco en la barra Z70', 'mejora_tension_pu': 0.03, 'coste_usd': 0}
    assert _f('comprobar_magnitudes')(p, {'e1': {'archivo': 'f.txt', 'sha256': '0' * 64}}) == []


@pytest.mark.parametrize('accion, fragmento', [
    ('cortar el ramal Z80 durante 3 horas', 'El contrato de la clínica admite como máximo 90 minutos de corte.'),
    ('cortar el ramal Z81 durante 50 min', 'La interrupción programada tiene un límite de 0,5 h.'),
    ('cargar la salida Z82 con 450 A', 'La salida admite a lo sumo 0,4 kA en régimen permanente.'),
    ('conectar 2,5 MW en la barra Z83', 'La barra no debe superar 2000 kW de carga nueva sin estudio.'),
    ('regular la barra Z84 a 0,93 pu', 'La tensión de servicio debe mantenerse como mínimo en 0,95 pu.'),
])
def test_047_rf99_una_sola_lectura_de_cotas_en_cualquier_redaccion_y_unidad(accion, fragmento):
    """047:RF-99 — con el 047n, «admite como máximo 2 horas» se escapaba: la cota se lee igual se escriba como se
    escriba, y las unidades se llevan a una base (90 min frente a 3 h; 0,4 kA frente a 450 A; 2000 kW frente a 2,5 MW)."""
    assert _falla(_f('comprobar_prohibiciones')({'accion': accion, 'coste_usd': 0}, _ev(fragmento))), fragmento


@pytest.mark.parametrize('accion, fragmento', [
    ('cortar el ramal Z80 durante 1 hora', 'El contrato de la clínica admite como máximo 90 minutos de corte.'),
    ('cargar la salida Z82 con 350 A', 'La salida admite a lo sumo 0,4 kA en régimen permanente.'),
    ('cortar el ramal Z85 durante 4 horas', 'El tramo Z85 mide 4 km y tiene 120 postes.'),
    ('construir 3 km de red hasta el caserío Z86', 'La red llega hasta 2 km del caserío por el camino viejo.'),
])
def test_047_rf99_la_cota_cumplida_o_una_cifra_sin_cota_no_alarman(accion, fragmento):
    assert _f('comprobar_prohibiciones')({'accion': accion, 'coste_usd': 0}, _ev(fragmento)) == [], fragmento


def test_047_rf100_permiso_restringido_a_un_agente():
    """047:RF-100 — «solo X puede …» prohíbe a los demás: la acción de otro agente sobre lo mismo no se aprueba sola."""
    regla = 'Únicamente el despacho puede autorizar el cierre de los enlaces entre alimentadores.'
    otro = {'accion': 'que el supervisor de zona cierre el enlace Z90 entre los alimentadores Z91 y Z92', 'coste_usd': 0}
    assert _falla(_f('comprobar_prohibiciones')(otro, _ev(regla)))
    propio = {'accion': 'que el despacho cierre el enlace Z90 entre los alimentadores Z91 y Z92', 'coste_usd': 0}
    assert _f('comprobar_prohibiciones')(propio, _ev(regla)) == []
    ajeno = {'accion': 'que el supervisor de zona cambie la cruceta del poste Z93', 'coste_usd': 0}
    assert _f('comprobar_prohibiciones')(ajeno, _ev(regla)) == []


def _revision(tmp_path, propuesta, fragmentos, decision='bloqueada'):
    import hashlib
    from types import SimpleNamespace
    from convertersmartgrid.aplicacion.asistente.revision_roles import revisar_propuesta
    evidencia = {}
    for clave, texto in fragmentos.items():
        fuente = tmp_path / f'{clave}.txt'
        fuente.write_text(texto, encoding='utf-8')
        evidencia[clave] = {'archivo': str(fuente), 'sha256': hashlib.sha256(fuente.read_bytes()).hexdigest(),
                            'proyecto': 'P1', 'fuente': 'abc', 'localizador': 'texto', 'fragmento': texto}
    vacio = {'decision': decision, 'evidencia_ids': sorted(evidencia), 'incertidumbres': [], 'contradicciones': []}
    return revisar_propuesta({**propuesta, 'restricciones_deterministas': {'plan_completo': True}}, evidencia,
                             contexto=SimpleNamespace(project='P1', source_fingerprint='abc'), max_rondas=2,
                             roles=('unico',), revisor=lambda *_a: dict(vacio))


def test_047_rf102_bloqueo_sin_hallazgo_tras_el_reintento_con_todo_respaldado(tmp_path):
    """047:RF-102 — con el 047o, el modelo bloqueó sanos sin decir por qué en las dos rondas: con todos los datos
    respaldados por el código, queda como observación y decide el código; sin todo respaldado, sigue sin respuesta."""
    sano = {'accion': 'colocar un banco de 150 kvar en la barra Z95', 'tension_final_pu': 0.98, 'coste_usd': 2100}
    frags = {'e1': 'Con el banco, la tensión de la barra Z95 queda en 0,98 pu.', 'e2': 'Banco montado: 2 100 USD en total.'}
    r = _revision(tmp_path, sano, frags)
    assert r['aprobada'], r['dictamenes'][-1]
    assert any('sin ningún hallazgo' in o for o in r['dictamenes'][-1].get('observaciones', []))
    r = _revision(tmp_path, {**sano, 'perdidas_evitadas_kw': 12}, frags)
    assert not r['aprobada'] and r['dictamenes'][-1].get('fallo_revisor'), 'sin todo respaldado sigue sin respuesta'


def test_047_rf102_coste_cero_respaldado_por_la_evidencia():
    p = {'accion': 'cerrar el enlace Z96 desde el centro de control', 'coste_usd': 0}
    r = _f('comprobar_coste')(p, _ev('El cierre del enlace se hace desde el centro de control, sin materiales.'))
    assert r and r[0]['coincide'], r
    assert _f('comprobar_coste')(p, _ev('El enlace Z96 une dos alimentadores.')) == []
