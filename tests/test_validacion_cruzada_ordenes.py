"""075 — validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla.

Todo con un codificador falso sobre la CPU y frases inventadas para la prueba: ningún texto real del operador (P9), ni el
almacén real, ni GPU, ni DIgSILENT. La medida de verdad la lanza el integrador (T6).
"""
import importlib.util
import json
from pathlib import Path
import random

import pytest

torch = pytest.importorskip('torch')

from test_interprete_codificador import CodificadorFalso, _entrenado                   # noqa: E402

from convertersmartgrid.asistente import codificador_ordenes as co                     # noqa: E402
from convertersmartgrid.asistente import destilacion_integral as di                    # noqa: E402
from convertersmartgrid.asistente import ordenes_fijas as of                           # noqa: E402
from convertersmartgrid.asistente import prueba_sellada as ps                          # noqa: E402
from convertersmartgrid.asistente import transformer as tr                             # noqa: E402
from convertersmartgrid.asistente import validacion_cruzada as vc                      # noqa: E402
from convertersmartgrid.asistente.interprete import PUESTO_CHARLA, interpretar         # noqa: E402
from convertersmartgrid.asistente.maestro_real import CALIDAD, NINGUNA                 # noqa: E402
from convertersmartgrid.asistente.plan import resolver                                 # noqa: E402
from convertersmartgrid.asistente.tareas import TAREAS                                 # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CPU = torch.device('cpu')
ERRATAS = ('como va el avance', 'como va el avnace', 'coma va enl avance')
RECHAZO_BUENO = {'ejemplos': 200, 'rechazada': .95, 'se_cuela': .01}


def _orden(texto, tarea='estado', datos=()):
    return {'texto': texto, 'tarea': tarea, 'datos': [list(d) for d in datos], 'record_id': f'id:{texto}',
            'particion': 'prueba', 'quality': 'gold_human'}


def _plata(texto, tarea='estado', datos=()):
    return {'texto': texto, 'tarea': tarea, 'datos': [list(d) for d in datos], 'record_id': f'plata:{texto}',
            'particion': 'entrenamiento', 'quality': CALIDAD}


def _grupos(familias):
    return sorted(sorted(r['texto'] for r in f) for f in familias)


#: Órdenes inventadas, sin parecido entre sí: una por familia, de varias tareas.
SUELTAS = [('cuentame lo que tienes cargado', 'estado'), ('muestrame el resumen del espacio', 'estado'),
           ('exporta la red zeta', 'convertir'), ('genera el fichero para pasarlo', 'convertir'),
           ('lanza potencia sobre todo', 'flujo'), ('calcula el reparto de cargas', 'flujo'),
           ('dime tus proyectos importados', 'proyectos')]


def _humanas_varias():
    return [_orden(t, tarea) for t, tarea in SUELTAS] + [_orden(t) for t in ERRATAS]


# ------------------------------------------------------------------ familias

@pytest.mark.parametrize('a, b', [(ERRATAS[0], ERRATAS[1]), (ERRATAS[0], ERRATAS[2]), (ERRATAS[1], ERRATAS[2])])
def test_familia_las_erratas_caen_juntas(a, b):
    """075:RF-1 / 075:RF-3 — el caso que decide si la medida vale, cruzando letras y comiéndose espacios."""
    assert vc.misma_familia(vc.clave_de_familia(a), vc.clave_de_familia(b))
    assert _grupos(vc.agrupar_familias([_orden(a), _orden(b), _orden('corre obras en la zona')])) == [
        sorted([a, b]), ['corre obras en la zona']]


def test_familia_clave_marca_datos_codigos_y_tildes():
    """075:RF-2 — mismos signos, tildes, códigos y datos dan la misma clave, sin distinguir su tipo."""
    assert vc.clave_de_familia('¿Cómo va?') == vc.clave_de_familia('como va')
    assert vc.clave_de_familia('convierte AB101') == vc.clave_de_familia('convierte CD202') == 'convierte #'
    assert vc.clave_de_familia('calibra Ensayo Alfa', [(8, 19, 'proyecto')]) == 'calibra #'
    from convertersmartgrid.asistente.sinteticos import CORTESIAS
    assert vc.clave_de_familia(f'{CORTESIAS[0]} corre todo') == 'corre todo'


def test_familia_con_palabras_de_mas():
    """075:RF-4 — la misma orden con palabras añadidas y una errata; hacen falta al menos dos palabras con contenido."""
    corta = vc.clave_de_familia('revisa corriente')
    assert vc.misma_familia(corta, vc.clave_de_familia('dime si puedes revisa la corrinete de la red ahora mismo'))
    assert not vc.misma_familia(vc.clave_de_familia('corriente'), vc.clave_de_familia('dame la corriente de la red que tengo aqui'))


@pytest.mark.parametrize('a, b', [('flujo de AB101', 'obras de AB101'), ('convierte AB101', 'calibra AB101'),
                                  ('muestrame el estado', 'entrena el gemelo'), ('sigue', 'corre')])
def test_familia_ordenes_distintas_no_se_juntan(a, b):
    """075:RF-3 / 075:RF-4 — agrupar de más no da medidas falsas, pero juntarlo todo dejaría sin entrenamiento."""
    assert not vc.misma_familia(vc.clave_de_familia(a), vc.clave_de_familia(b))


def test_familia_es_transitiva_aunque_cambie_la_tarea():
    """075:RF-5 — a con b y b con c, sin a con c, y con tareas distintas: queda una familia."""
    a, b, c = 'pasa el resumen de carga', 'pasa el resumen de carga diaria', 'pasa el reparto de carga diaria'
    claves = [vc.clave_de_familia(t) for t in (a, b, c)]
    assert vc.misma_familia(claves[0], claves[1]) and vc.misma_familia(claves[1], claves[2])
    familias = vc.agrupar_familias([_orden(a, 'estado'), _orden(b, 'flujo'), _orden(c, 'convertir')])
    assert len(familias) == 1


# ------------------------------------------------------------------ reparto

def _sorteadas(semilla, n=40):
    """Órdenes de tres palabras al azar de 8 letras: sin parecido entre sí, cada una su propia familia."""
    rnd = random.Random(semilla)
    tareas = sorted(TAREAS)[:6]

    def palabra():
        return ''.join(rnd.choice('bcdfghjklmnprstvz') + rnd.choice('aeiou') for _ in range(4))
    return [_orden(' '.join(palabra() for _ in range(3)), rnd.choice(tareas)) for _ in range(n)]


def test_reparto_cada_familia_en_una_sola_vuelta():
    """075:RF-6 — cinco vueltas, ninguna vacía, y la unión es el total, sin repetir."""
    familias = vc.agrupar_familias(_sorteadas(3))
    vueltas = vc.repartir_en_vueltas(familias)
    assert vc.VUELTAS == 5 and len(vueltas) == 5 and all(vueltas)
    vistas = [_ for v in vueltas for f in v for _ in (r['texto'] for r in f)]
    assert len(vistas) == len(set(vistas)) == sum(len(f) for f in familias)


def test_reparto_determinista_sin_depender_del_orden():
    """075:RF-7 — la misma semilla con la entrada barajada da lo mismo; otra semilla puede cambiarlo."""
    filas = _sorteadas(5)
    def reparto(entrada, semilla):
        return [sorted(sorted(r['texto'] for r in f) for f in v)
                for v in vc.repartir_en_vueltas(vc.agrupar_familias(entrada), semilla=semilla)]
    barajadas = filas[::-1]
    random.Random(1).shuffle(barajadas)
    assert reparto(filas, 75) == reparto(barajadas, 75)
    assert any(reparto(filas, 75) != reparto(filas, s) for s in range(76, 90))


@pytest.mark.parametrize('semilla', [1, 2, 3])
def test_reparto_estratifica_por_tarea(semilla):
    """075:RF-8 — con familias de un texto, ninguna tarea se amontona: difieren como mucho en uno por vuelta."""
    filas = _sorteadas(semilla, 60)
    familias = vc.agrupar_familias(filas)
    assert len(familias) == len(filas)
    vueltas = vc.repartir_en_vueltas(familias)
    for tarea in {r['tarea'] for r in filas}:
        n = [sum(r['tarea'] == tarea for f in v for r in f) for v in vueltas]
        assert max(n) - min(n) <= 1, (tarea, n)


# ------------------------------------------------------------------ una ejecución con dobles

class CodificadorContado(CodificadorFalso):
    """Anota lo codificado en lotes: los de la caché; una predicción suelta es de una frase."""
    lotes: list = []

    def __call__(self, textos):
        if len(textos) > 1:
            CodificadorContado.lotes.extend(textos)
        return super().__call__(textos)


@pytest.fixture
def espia(monkeypatch):
    llamadas = []
    original = co.entrenar

    def entrenar(ejemplos, cfg=None, log=lambda _m: None, *, cache, dispositivo):
        llamadas.append({'ejemplos': list(ejemplos), 'semilla': cfg.semilla})
        return original(ejemplos, cfg, log, cache=cache, dispositivo=dispositivo)

    monkeypatch.setattr(co, 'entrenar', entrenar)
    return llamadas


CFG = co.Configuracion(epocas=1, lote_tarea=64, lote_etiquetas=64, oculta_tarea=8, oculta_etiquetas=8, semilla=7)


def _ejecutar(humanas, plata, vedadas=()):
    CodificadorContado.lotes = []
    return vc.ejecutar(humanas, plata, vedadas, cfg=CFG, cache=co.CacheCodificada(CodificadorContado(), lote=10_000), dispositivo=CPU)


PLATA = [_plata('corre el flujo', 'flujo'), _plata('convierte esto', 'convertir'), _plata('hay algo cargado', 'estado'),
         _plata('dime la lista completa', 'proyectos'), _plata('como va el avnace', 'estado'), _plata('cóma va, el avance', 'estado'),
         _plata('Exporta la red zeta', 'convertir'), _plata('sigue nomas', NINGUNA)]


def test_vuelta_no_entrena_con_lo_que_examina(espia):
    """075:RF-10 / 075:RF-12 / 075:RF-13 — ni la orden, ni su familia, ni su plata, ni una variante con erratas."""
    humanas = _humanas_varias()
    v = _ejecutar(humanas, PLATA)
    assert v.medida is not None and len(espia) == 6                                     # cinco vueltas y el final
    vueltas = vc.repartir_en_vueltas(vc.agrupar_familias(humanas))
    for llamada, vuelta in zip(espia, vueltas, strict=False):
        examinadas = [r for f in vuelta for r in f]
        tocadas = vc.Claves(vc.clave_de_familia(r['texto']) for r in examinadas)
        assert not [e.texto for e in llamada['ejemplos'] if tocadas.toca(vc.clave_de_familia(e.texto, e.datos))]
    # La familia de las tres erratas cae entera en una vuelta, y en esa vuelta su plata no entrena.
    con_erratas = [i for i, v_ in enumerate(vueltas) if any(r['texto'] == ERRATAS[0] for f in v_ for r in f)]
    assert len(con_erratas) == 1
    assert not {'como va el avnace', 'cóma va, el avance'} & {e.texto for e in espia[con_erratas[0]]['ejemplos']}
    otra = next(i for i in range(5) if i != con_erratas[0])
    assert {'como va el avnace'} & {e.texto for e in espia[otra]['ejemplos']}


def test_vuelta_reutiliza_la_cache_y_el_codificador(monkeypatch):
    """075:RF-11 — cada frase de entrenamiento se codifica una vez, y el codificador se abre una sola."""
    aperturas = []
    monkeypatch.setattr(co, 'FABRICA', lambda *_a: aperturas.append(1) or CodificadorContado())
    monkeypatch.setattr(co, '_abiertos', {})
    cod = co.obtener_codificador('x', 'y', CPU)
    CodificadorContado.lotes = []
    vc.ejecutar(_humanas_varias(), PLATA, (), cfg=CFG, cache=co.CacheCodificada(cod, lote=10_000), dispositivo=CPU)
    assert len(aperturas) == 1 and CodificadorContado.lotes
    assert len(CodificadorContado.lotes) == len(set(CodificadorContado.lotes))


def test_vuelta_peso_de_las_confirmadas(espia):
    """075:RF-14 — repetida y con variantes deterministas, con el dato intacto en su nuevo sitio."""
    assert (vc.REPETICIONES_CONFIRMADA, vc.VARIANTES_CONFIRMADA) == (8, 8)
    orden = _orden('convierte AB101 ahora mismo', 'convertir', [(10, 15, 'alimentadores')])
    uno, dos = vc.ejemplos_de_confirmadas([orden]), vc.ejemplos_de_confirmadas([orden])
    assert uno == dos and len(uno) == 16 and sum(e.texto == orden['texto'] for e in uno) >= 8
    for e in uno:
        (a, b, tipo), = e.datos
        assert e.texto[a:b] == 'AB101' and tipo == 'alimentadores' and e.tarea == 'convertir'


def test_vuelta_cada_orden_se_examina_una_vez():
    """075:RF-17 / 075:RF-20 — las predicciones son una por orden, y cada vuelta da sus cuentas, sin ningún texto."""
    humanas = _humanas_varias()
    v = _ejecutar(humanas, PLATA)
    assert set(v.medida.predicciones) == {r['texto'] for r in humanas}
    resumen = v.informe['vueltas']
    assert sum(x['examinadas'] for x in resumen) == len(humanas) and len(resumen) == 5
    for x in resumen:
        assert set(x) == {'vuelta', 'examinadas', 'familias', 'confirmadas_que_entrenan', 'filas_que_entrenan', 'plata_apartada', 'tareas_sin_filas'}
        assert x['confirmadas_que_entrenan'] == len(humanas) - x['examinadas']
    assert sum(x['plata_apartada'] for x in resumen) >= 2 and resumen[0]['tareas_sin_filas']


def test_vuelta_pocas_familias_no_se_miden(espia):
    """075:RF-9 — sin bastantes familias no hay vueltas; el modelo final se entrena igual, y se dice por qué."""
    v = _ejecutar([_orden(t) for t in ERRATAS] + [_orden('exporta la red zeta', 'convertir')], PLATA)
    assert v.medida is None and v.informe['medida'] is False and '2 familias' in v.informe['motivo'] and len(espia) == 1
    d = di.decidir_promocion({'acierto_tarea': 1., 'f1_datos': 1., 'ejemplos': 9}, {'ejemplos': 0}, {}, None, RECHAZO_BUENO)
    assert d['status'] == 'BLOQUEADO_POR_DATOS' and not d['gates']['approved']


# ------------------------------------------------------------------ tareas sin independencia

def test_independencia_motivo_de_cada_caso():
    """075:RF-23 — un solo texto; una familia de varios textos; y familias que chocan con lo que se mide."""
    humanas = [_orden('corre el estudio de hoy', 'flujo'), *[_orden(t) for t in ERRATAS],
               _orden('exporta la red zeta', 'convertir'), _orden('genera el fichero para pasarlo', 'convertir')]
    entrenables = [r for r in humanas if r['tarea'] != 'convertir']
    e = vc.estado_por_tarea(vc.agrupar_familias(humanas), entrenables)
    assert e['flujo']['estado'] == e['estado']['estado'] == e['convertir']['estado'] == 'sin_independencia'
    assert 'un solo texto' in e['flujo']['motivo'] and 'una sola familia' in e['estado']['motivo'] and 'chocan' in e['convertir']['motivo']
    assert e['estado']['textos'] == 3 and e['estado']['familias'] == 1
    assert vc.estado_por_tarea(vc.agrupar_familias(humanas), humanas)['convertir']['estado'] == 'medida'


def test_independencia_no_recibe_visto_bueno_aunque_acierte():
    """075:RF-24 / 075:RF-19 — su ``cumple`` es nulo con un acierto perfecto, y las demás sí se comparan con la puerta."""
    estados = {'flujo': {'estado': 'sin_independencia', 'motivo': 'un solo texto'}, 'estado': {'estado': 'medida', 'motivo': ''},
               'convertir': {'estado': 'medida', 'motivo': ''}}
    r = vc.resumen_por_tarea({'flujo': {'acierto_tarea': 1., 'f1_datos': 1., 'ejemplos': 1},
                              'estado': {'acierto_tarea': 1., 'f1_datos': 1., 'ejemplos': 4},
                              'convertir': {'acierto_tarea': .5, 'f1_datos': 1., 'ejemplos': 2}}, estados, acierto_minimo=.98, f1_minimo=.95)
    assert r['flujo']['cumple'] is None and r['estado']['cumple'] is True and r['convertir']['cumple'] is False
    assert r['convertir']['ejemplos'] == 2 and r['flujo']['motivo'] == 'un solo texto'


def test_independencia_cuenta_en_el_agregado():
    """075:RF-25 / 075:RF-18 — su fallo baja la medida y su fila no sale del denominador."""
    filas = [_orden('corre el estudio de hoy', 'flujo'), _orden('exporta la red zeta', 'convertir')]
    fallo = {'tarea': 'estado', 'confianza': .9, 'alternativas': [], 'datos': {}, 'modelo': 'x', 'version': ''}
    medida = vc.FueraDeGrupo({'corre el estudio de hoy': fallo, 'exporta la red zeta': {**fallo, 'tarea': 'convertir'}})
    m = di.evaluar_alumno(medida, filas)
    assert m['ejemplos'] == 2 and m['acierto_tarea'] == .5 and m['familias']['flujo']['ejemplos'] == 1


# ------------------------------------------------------------------ el protocolo entero

@pytest.fixture(scope='module')
def corrida(tmp_path_factory):
    """El protocolo real con codificador falso, una vez: varias pruebas leen lo mismo."""
    import convertersmartgrid.model_registry as mr
    tmp = tmp_path_factory.mktemp('cruzada')
    llamadas, decisiones = [], []
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('CSG_ASISTENTE_DATA', str(tmp / 'almacen'))
        mp.setattr(tr, 'dispositivo_de_calculo', lambda: CPU)
        mp.setattr(tr, 'liberar_gpu', lambda: None)
        mp.setattr(tr, '_cache', {})
        mp.setattr(co, 'FABRICA', CodificadorFalso)
        mp.setattr(co, '_abiertos', {})
        mp.setattr(mr, 'reabrir_en_subproceso', lambda *_a, **_k: {'ok': True})
        original, decidir = co.entrenar, di.decidir_promocion

        def entrenar(ejemplos, cfg=None, log=lambda _m: None, *, cache, dispositivo):
            llamadas.append({'textos': {e.texto for e in ejemplos}, 'ejemplos': list(ejemplos), 'semilla': cfg.semilla})
            return original(ejemplos, cfg, log, cache=cache, dispositivo=dispositivo)

        def espia_decision(*a, **k):
            decisiones.append(a)
            return decidir(*a, **k)

        mp.setattr(co, 'entrenar', entrenar)
        mp.setattr(di, 'decidir_promocion', espia_decision)
        sellada = 'a ver que tienes abierto'
        humanas = [{'texto': t, 'tarea': tarea, 'datos': [], 'origen': 'confirmado'} for t, tarea in SUELTAS]
        humanas += [{'texto': t, 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'} for t in ERRATAS]
        # Iguales o casi a la prueba sellada, a un mensaje reservado y a una fija de prueba: examinan y no entrenan.
        humanas += [{'texto': sellada, 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'},
                    {'texto': 'a ver que tienes abiertu', 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'},
                    {'texto': 'un mensaje secreto de charla reservada', 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'},
                    {'texto': 'una fija de prueba que esta vedada', 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'}]
        reservados = [f'un mensaje secreto de charla reservada {i}' for i in range(120)]
        filas, meta = di.preparar_corpus({}, humanas, por_familia=1, ninguna=['charla uno de mas', 'charla dos de mas'], ninguna_reservada=reservados)
        di.guardar_corpus(tmp / 'corpus', filas, meta, reservados)
        antes = (tmp / 'corpus' / 'corpus.json').read_bytes()
        r = di.entrenar_destilacion(tmp / 'corpus', tmp / 'run', cfg=co.Configuracion(epocas=1, lote_tarea=64, lote_etiquetas=64, oculta_tarea=8, oculta_etiquetas=8),
                                    semillas=(11,), registro=tmp / 'reg', log=lambda *_a, **_k: None, validacion_cruzada=True,
                                    vedadas_extra=['una fija de prueba que esta vedada'])
        despues = (tmp / 'corpus' / 'corpus.json').read_bytes()
        yield {'r': r, 'tmp': tmp, 'llamadas': llamadas, 'decisiones': decisiones, 'humanas': humanas, 'filas': filas, 'meta': meta,
               'antes': antes, 'despues': despues}


def test_final_entrena_con_todas_las_que_pueden(corrida):
    """075:RF-27 / 075:RF-16 — el último entrenamiento lleva todas las que pueden; vueltas y final, método y semilla del ganador."""
    r, llamadas = corrida['r'], corrida['llamadas']
    assert len(llamadas) == 2 + 5 + 1
    final = llamadas[-1]['textos']
    assert {t for t, _ in SUELTAS} <= final and set(ERRATAS) <= final
    assert {x['semilla'] for x in llamadas[2:]} == {r['elegido']['semilla']}
    # El ganador «destilado» o «supervisado» entrena sus filas: lo del maestro va o no va en todas, igual.
    maestro = {x['texto'] for x in corrida['filas'] if x['particion'] == 'entrenamiento' and x['del_maestro']}
    assert bool(maestro & final) == (r['elegido']['metodo'] == 'destilado')
    assert r['validacion_cruzada']['confirmadas_que_entrenan'] == len(SUELTAS) + len(ERRATAS)
    assert Path(r['elegido']['path']).name == 'con-confirmadas'


def test_final_lo_que_mide_no_entrena(corrida):
    """075:RF-28 / 075:RF-29 — ni la sellada, ni lo casi igual a ella, a un reservado o a una fija; se examinan y se cuentan."""
    r, llamadas = corrida['r'], corrida['llamadas']
    vedadas = {'a ver que tienes abierto', 'a ver que tienes abiertu', 'un mensaje secreto de charla reservada', 'una fija de prueba que esta vedada'}
    for x in llamadas:
        assert not vedadas & x['textos']
    assert r['validacion_cruzada']['confirmadas_que_no_entrenan'] == len(vedadas)
    assert r['humanas']['ejemplos'] == len(corrida['humanas'])
    selladas = {x['texto'] for x in corrida['filas'] if x.get('conjunto') == ps.CONJUNTO}
    separadas = {x['texto'] for x in corrida['filas'] if x['particion'] in ('seleccion', 'calibracion')} | selladas
    for x in llamadas:
        assert not separadas & x['textos']
    # 079:RF-45: decide la sellada nueva; la anterior se informa con su huella.
    decisoras = sum(x.get('conjunto') == 'sellada_079' for x in corrida['filas'])
    assert r['sinteticas']['ejemplos'] == decisoras and r['prueba_sellada']['huella'] == 'df5e1db88595d378'


def test_final_medida_humana_no_decide(corrida):
    """075:RF-30 / 075:RF-21 / 075:RF-18 — decide la agregada fuera de grupo; la del final se da marcada."""
    r = corrida['r']
    bloque, _, humanas_decision, *_ = (r['validacion_cruzada'], None, corrida['decisiones'][0][1])
    final = bloque['humanas_modelo_final']
    assert final['independiente'] is False and final['decide'] is False
    assert humanas_decision['ejemplos'] == bloque['humanas_fuera_de_grupo']['ejemplos'] == len(corrida['humanas'])
    assert humanas_decision['acierto_tarea'] == bloque['humanas_fuera_de_grupo']['acierto_tarea'] == r['humanas']['acierto_tarea']
    assert 'independiente' not in humanas_decision and 'decide' not in humanas_decision


def test_final_por_tarea_con_denominadores(corrida):
    """075:RF-19 / 075:RF-20 — acierto, F1 y denominador por tarea, que suman el total."""
    por_tarea = corrida['r']['validacion_cruzada']['por_tarea']
    assert sum(d['ejemplos'] for d in por_tarea.values()) == len(corrida['humanas'])
    assert all({'acierto_tarea', 'f1_datos', 'ejemplos', 'textos', 'familias', 'estado', 'cumple'} <= set(d) for d in por_tarea.values())
    assert len(corrida['r']['validacion_cruzada']['vueltas']) == 5


def test_final_corpus_intacto(corrida):
    """075:RF-15 / 075:RF-33 — el corpus guardado sigue igual, y las huellas de fijas y sellada también."""
    assert corrida['antes'] == corrida['despues']
    assert corrida['meta']['prueba_sellada']['huella'] == 'df5e1db88595d378' == ps.HUELLA
    assert of.huella(of.generar({})) == '41f7ab110ac35c0b'
    assert [x['particion'] for x in corrida['filas'] if x['quality'] == 'gold_human'] == ['prueba'] * len(corrida['humanas'])


def test_final_sin_textos_en_el_informe_ni_el_registro(corrida):
    """075:RF-34 — ni una orden confirmada en el JSON de salida ni en el registro, solo cifras y huellas."""
    salida = json.dumps(corrida['r'], ensure_ascii=False, default=str)
    registro = ''.join(p.read_text(encoding='utf-8') for p in (corrida['tmp'] / 'reg').rglob('*.json'))
    for h in corrida['humanas']:
        assert h['texto'] not in salida and h['texto'] not in registro


def test_final_confirmacion_y_cuenta_de_humanas(corrida):
    """075:RF-31 / 075:RF-32 — sigue pidiendo confirmación; ni plata ni variantes cuentan como órdenes humanas."""
    d = corrida['r']['decision']
    if d['status'] != 'ERROR_ENTORNO':
        assert d['confirmacion_obligatoria'] is True and d['alcance'] == 'asistido'
    assert d['ordenes_humanas'] == len(corrida['humanas']) == corrida['meta']['ordenes_humanas_independientes']
    assert not d.get('muestra_humana_amplia')


def test_final_protocolo_antes_de_las_vueltas(corrida):
    """075:RF-46 — las vueltas, la semilla, los umbrales y el peso quedan en el protocolo y en el registro."""
    protocolo = json.loads((corrida['tmp'] / 'run' / 'protocolo.json').read_text(encoding='utf-8'))
    assert protocolo['validacion_cruzada'] == {'vueltas': 5, 'semilla': vc.SEMILLA, 'ediciones_frase': .25, 'ediciones_palabra': .34,
                                               'repeticiones_confirmada': 8, 'variantes_confirmada': 8}
    assert 'validacion_cruzada.py' in protocolo['codigo_hashes'] and (corrida['tmp'] / 'run' / 'codigo' / 'validacion_cruzada.py').is_file()


# ------------------------------------------------------------------ decisión

def _medida(acierto=1., f1=1., n=42):
    return {'acierto_tarea': acierto, 'f1_datos': f1, 'ejemplos': n}


def _sinteticas():
    familias = {t: {'ejemplos': 8, 'acierto_tarea': 1., 'f1_datos': 1.} for t in TAREAS}
    return _medida(n=200), familias, dict(familias)


@pytest.mark.parametrize('humanas, aprueba', [(_medida(), True), (_medida(41 / 42), False), (_medida(.98, .95), True), (_medida(1., .949), False)])
def test_decision_puerta_humana_sin_bajar(humanas, aprueba):
    """075:RF-21 — 0,98 y 0,95 sobre la agregada: de 42 textos, una fallada ya no pasa."""
    s, f, ref = _sinteticas()
    d = di.decidir_promocion(s, humanas, f, ref, RECHAZO_BUENO)
    assert d['gates']['approved'] is aprueba


@pytest.mark.parametrize('cambio', [lambda s, f, r: f['estado'].update(acierto_tarea=.9499), lambda s, f, r: f['estado'].update(f1_datos=.8499),
                                    lambda s, f, r: r.update(rechazada=.8999), lambda s, f, r: r.update(se_cuela=.0201)])
def test_decision_demas_puertas_sin_excepcion(cambio):
    """075:RF-22 — sintéticas por familia y rechazo, como estaban."""
    s, f, ref = _sinteticas()
    f = {t: dict(v) for t, v in f.items()}
    rechazo = dict(RECHAZO_BUENO)
    cambio(s, f, rechazo)
    d = di.decidir_promocion(s, _medida(), f, ref, rechazo)
    assert not d['gates']['approved']


def test_decision_nombra_sin_independencia_sin_puerta_nueva(corrida):
    """075:RF-26 — las nombra con su motivo, y ningún fallo de la decisión viene de ellas."""
    d = corrida['r']['decision']
    assert d['tareas_sin_independencia'] and 'proyectos' in d['tareas_sin_independencia']
    assert 'un solo texto' in d['tareas_sin_independencia']['proyectos']
    assert not [x for x in d['fallos'] if 'independencia' in x]


# ------------------------------------------------------------------ opción de la herramienta

def _herramienta():
    spec = importlib.util.spec_from_file_location('herramienta_entrenar_075', RAIZ / 'tools/asistente_entrenar.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize('opcion, esperada', [([], False), (['--validacion-cruzada'], True)])
def test_opcion_solo_si_se_pide(tmp_path, monkeypatch, opcion, esperada):
    """075:RF-35 — la llamada de siempre no la hace, y las fijas de prueba quedan vedadas solo si se pide."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    vistos = {}

    def falso_entrenar(*_a, **k):
        vistos.update(k)
        return {'candidato': {'status': 'RECHAZADO'}}

    monkeypatch.setattr(di, 'entrenar_destilacion', falso_entrenar)
    monkeypatch.setattr(di, 'preparar_corpus', lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(di, 'guardar_corpus', lambda *_a, **_k: None)
    from convertersmartgrid.asistente import modelos_en_uso
    monkeypatch.setattr(modelos_en_uso, 'aplicar_decision', lambda *_a, **_k: {})
    codigo = _herramienta().main(['--output-json', str(tmp_path / 'salida.json'), '--integral', '--solo', 'ordenes', *opcion])
    assert codigo == 0
    assert vistos['validacion_cruzada'] is esperada and bool(vistos['vedadas_extra']) is esperada


def test_opcion_no_se_combina_con_la_via_antigua(tmp_path):
    """075:RF-35 — la vía antigua no tiene vueltas: se dice, en vez de ignorarla."""
    with pytest.raises(SystemExit) as e:
        _herramienta().main(['--output-json', str(tmp_path / 's.json'), '--validacion-cruzada', '--destilar'])
    assert e.value.code == 2


def test_opcion_sin_pedirla_las_confirmadas_solo_examinan(tmp_path, monkeypatch):
    """075:RF-36 — sin la opción, ninguna confirmada entrena y la medida es la de siempre, sin bloque de vueltas."""
    import convertersmartgrid.model_registry as mr
    llamadas = []
    original = co.entrenar

    def entrenar(ejemplos, cfg=None, log=lambda _m: None, *, cache, dispositivo):
        llamadas.append({e.texto for e in ejemplos})
        return original(ejemplos, cfg, log, cache=cache, dispositivo=dispositivo)

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    monkeypatch.setattr(tr, 'dispositivo_de_calculo', lambda: CPU)
    monkeypatch.setattr(tr, 'liberar_gpu', lambda: None)
    monkeypatch.setattr(co, 'FABRICA', CodificadorFalso)
    monkeypatch.setattr(co, '_abiertos', {})
    monkeypatch.setattr(mr, 'reabrir_en_subproceso', lambda *_a, **_k: {'ok': True})
    monkeypatch.setattr(co, 'entrenar', entrenar)
    humanas = [{'texto': t, 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'} for t in ERRATAS]
    filas, meta = di.preparar_corpus({}, humanas, por_familia=1)
    di.guardar_corpus(tmp_path / 'corpus', filas, meta, [])
    r = di.entrenar_destilacion(tmp_path / 'corpus', tmp_path / 'run', cfg=co.Configuracion(epocas=1, lote_tarea=64, lote_etiquetas=64, oculta_tarea=8, oculta_etiquetas=8),
                                semillas=(11,), registro=tmp_path / 'reg', log=lambda *_a, **_k: None)
    assert r['validacion_cruzada'] is None and r['humanas']['ejemplos'] == 3 and len(llamadas) == 2
    assert not any(set(ERRATAS) & x for x in llamadas)
    assert Path(r['elegido']['path']).name != 'con-confirmadas'


# ------------------------------------------------------------------ Ollama

class Modelo:
    """Duda en lo que se le dice, y pone «ninguna» en el lugar que se le dice."""
    umbral = .85

    def __init__(self, tarea='estado', confianza=.4, puesto=2):
        self.r = {'tarea': tarea, 'confianza': confianza, 'datos': {}, 'alternativas': [('flujo', .1)], 'version': 'v1'}
        self.puesto, self.preguntas = puesto, 0

    def predecir(self, _t):
        return self.r

    def puesto_ninguna(self, _t):
        self.preguntas += 1
        return self.puesto


class Ollama:
    modelo = 'doble'
    revisar_transformer = False

    def __init__(self, tarea='estado', confianza=1.):
        self.llamadas = 0
        self.r = {'tarea': tarea, 'confianza': confianza, 'datos': {}, 'modelo': 'ollama:doble', 'razon': ''}

    def interpretar(self, _texto, **_k):
        self.llamadas += 1
        return self.r


@pytest.mark.parametrize('puesto', [1, PUESTO_CHARLA])
def test_ollama_no_impone_tarea_en_lo_que_el_modelo_ve_como_charla(puesto):
    """075:RF-37 — «muchas gracias» bajo el umbral: Ollama ni se consulta, y no hay tarea."""
    assert PUESTO_CHARLA == 2
    ollama = Ollama()
    i = interpretar('muchas gracias', transformer=Modelo(puesto=puesto), ollama=ollama)
    assert i.tarea is None and ollama.llamadas == 0 and i.modelo == 'ninguno'


def test_ollama_se_pregunta_al_operador_con_las_alternativas():
    """075:RF-38 — no se queda sin atender en silencio: el plan pide la tarea y ofrece lo que el modelo veía."""
    i = interpretar('corre todo eso que te dije', transformer=Modelo(), ollama=Ollama())
    assert i.alternativas == [('estado', .4), ('flujo', .1)]
    assert any(c.startswith('sin Ollama') for c in i.consultados) and not any(c.startswith('Ollama') for c in i.consultados)
    plan = resolver(i, {})
    assert plan.tarea is None and not plan.listo
    assert any('la tarea' in f and 'estado (40%)' in f and 'flujo (10%)' in f for f in plan.faltan)
    assert any('sin Ollama' in r for r in plan.razonamiento)


def test_ollama_con_ninguna_lejos_se_consulta_como_siempre():
    """075:RF-39 — una orden que el modelo no ve como charla sigue llegando a Ollama."""
    ollama = Ollama('flujo', .9)
    i = interpretar('lanza eso por favor', transformer=Modelo(puesto=3), ollama=ollama)
    assert i.tarea == 'flujo' and ollama.llamadas == 1 and i.modelo == 'ollama:doble'


def test_ollama_regla_no_aplica_si_el_modelo_llega_a_su_umbral():
    """075:RF-40 — con confianza no se pregunta el lugar de ninguna, y la revisión de Ollama sigue igual."""
    modelo, ollama = Modelo('flujo', .95, puesto=2), Ollama('flujo', .9)
    i = interpretar('corre el flujo', transformer=modelo, ollama=ollama)
    assert i.tarea == 'flujo' and i.modelo == 'transformer' and modelo.preguntas == 0 and ollama.llamadas == 0
    revisor = Ollama('flujo', .9)
    revisor.revisar_transformer = True
    i = interpretar('corre el flujo', transformer=modelo, ollama=revisor)
    assert revisor.llamadas == 1 and modelo.preguntas == 0 and i.tarea == 'flujo'


def test_ollama_umbral_por_tarea_cuenta_como_duda():
    """075:RF-40 / 027:RF-38 — el umbral de la tarea, si lo hay, es el que dice si el modelo duda."""
    ollama = Ollama()
    i = interpretar('muchas gracias', transformer=Modelo('estado', .9), ollama=ollama, umbrales={'estado': .95})
    assert i.tarea is None and ollama.llamadas == 0


def test_ollama_modelo_sin_clase_ninguna_consulta_como_siempre():
    """075:RF-41 — sin el método, o con un modelo que no tiene la clase, no opina."""
    class Heredado:
        def predecir(self, _t):
            return {'tarea': 'estado', 'confianza': .4, 'datos': {}, 'alternativas': [], 'version': 'v0'}

    ollama = Ollama('flujo', .9)
    assert interpretar('corre eso', transformer=Heredado(), ollama=ollama).tarea == 'flujo' and ollama.llamadas == 1
    ollama = Ollama('flujo', .9)
    assert interpretar('corre eso', transformer=Modelo(puesto=None), ollama=ollama).tarea == 'flujo' and ollama.llamadas == 1
    m = _entrenado(epocas=2)
    assert m.puesto_ninguna('hola') in range(1, len(m.tareas) + 1)
    m.tareas = [t for t in m.tareas if t != NINGUNA]
    assert m.puesto_ninguna('hola') is None


def test_ollama_puesto_del_modelo_real_sale_de_sus_opciones():
    """075:RF-37 — si gana una tarea y ninguna es la segunda, el puesto es 2; 069:RF-2: ``predecir`` no cambia de campos."""
    m = _entrenado(epocas=2)
    z = torch.zeros(len(m.tareas))
    z[m.tareas.index('estado')], z[m.tareas.index(NINGUNA)] = 2., 1.
    m.logits_tarea = lambda _t: z.unsqueeze(0)
    assert m.puesto_ninguna('hola') == 2
    assert set(m.predecir('hola')) == {'tarea', 'confianza', 'alternativas', 'datos', 'modelo', 'version'}


class ModeloDeMedida:
    """Según el texto: «gana» la tarea con confianza alta o baja, o «ninguna», con su puesto."""
    umbral = .85

    def predecir(self, t):
        c = {'seguro': .9, 'duda2': .4, 'duda3': .4, 'charla': .9}[t.split()[0]]
        return {'tarea': NINGUNA if t.startswith('charla') else 'estado', 'confianza': c, 'datos': {}, 'alternativas': []}

    def puesto_ninguna(self, t):
        return 2 if t.startswith('duda2') else 3


def _textos(**cuantos):
    return [f'{k} {i}' for k, n in cuantos.items() for i in range(n)]


def test_ollama_medida_cuenta_sin_consultarlo():
    """075:RF-42 — con selección y reservados; la cota de lo que llega a Ollama, sin que se le llame."""
    seleccion = [{'texto': t} for t in _textos(seguro=96, duda2=3, duda3=1)]
    m = di.medir_regla_ollama(ModeloDeMedida(), seleccion, _textos(charla=90, duda2=9, duda3=1))
    assert m['ollama_consultado'] is False
    assert m['ordenes_seleccion'] == {'ejemplos': 100, 'dudosas': 4, 'frenadas': 3, 'a_ollama': 1}
    assert m['mensajes_reservados'] == {'ejemplos': 100, 'dudosas': 10, 'frenadas': 9, 'a_ollama': 1}
    assert m['reservados_a_ollama'] == .01 and m['ordenes_frenadas'] == .03 and m['cumple'] is True


@pytest.mark.parametrize('duda3, cumple', [(2, True), (3, False)])
def test_ollama_medida_reservados_al_dos_por_ciento(duda3, cumple):
    """075:RF-43 — hasta el 2 % de los reservados puede llegar a Ollama."""
    m = di.medir_regla_ollama(ModeloDeMedida(), [{'texto': 'seguro 0'}], _textos(charla=100 - duda3, duda3=duda3))
    assert m['cumple'] is cumple


@pytest.mark.parametrize('duda2, cumple', [(5, True), (6, False)])
def test_ollama_medida_ordenes_al_cinco_por_ciento(duda2, cumple):
    """075:RF-44 — hasta el 5 % de las órdenes de selección puede frenarse; sin reservados, no se da por cumplida."""
    seleccion = [{'texto': t} for t in _textos(seguro=100 - duda2, duda2=duda2)]
    assert di.medir_regla_ollama(ModeloDeMedida(), seleccion, _textos(charla=100))['cumple'] is cumple
    assert di.medir_regla_ollama(ModeloDeMedida(), seleccion, None)['cumple'] is False


def test_ollama_medida_en_el_informe_no_decide(corrida):
    """075:RF-45 / 075:RF-42 — va en el informe y en el registro con sus denominadores, y no entra en la decisión."""
    r = corrida['r']
    regla = r['regla_ollama']
    assert regla['decide'] is False and regla['mensajes_reservados']['ejemplos'] == 120
    assert regla['ordenes_seleccion']['ejemplos'] == sum(x['particion'] == 'seleccion' for x in corrida['filas'])
    assert not [x for x in r['decision']['fallos'] if 'ollama' in x.lower()]
    assert 'un mensaje secreto' not in json.dumps(regla, ensure_ascii=False)
