"""Spec 004, T27: importar un ``.pfd`` y diagnosticarlo en solo lectura, con el doble ``fake_pf`` (004:RF-81 a RF-102).

Los proyectos son sintéticos y sorteados: nombres, número de redes, alimentadores, cargas, casos, escenarios,
variaciones y fechas salen de una semilla, que va en cada mensaje de fallo. Ningún nombre de empresa ni de fichero real.
"""
from __future__ import annotations

import json
import random
import re
import string

import fake_pf
import pytest
from apoyo import cargar_herramienta

SEMILLA = random.randrange(1 << 30)
AÑO = 365 * 24 * 3600
T0 = 1_700_000_000


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('pfd_diagnostico.py', 'pfd_diagnostico_t27', tools_en_path=True)


def _nombre(rnd: random.Random, n=None) -> str:
    return ''.join(rnd.choice(string.ascii_uppercase + string.digits) for _ in range(n or rnd.randint(3, 8)))


def _carpeta(padre, nombre, tipo):
    c = padre.CreateObject('IntPrjfolder', nombre)
    c.iopt_typ = tipo
    return c


def construir(app, padre, rnd: random.Random, *, casos=None, escenarios=None, variaciones=None, extra_casos=0):
    """Un proyecto como lo trae un ``.pfd``: redes, alimentadores en «Feeders», cargas, casos, escenarios y
    variaciones con altas, bajas y cambios. Devuelve el proyecto y lo que se sabe de él para comprobar."""
    prj = fake_pf.Obj(app, 'IntPrj', 'PRJ_' + _nombre(rnd), padre)
    padre._hijos.append(prj)
    modelo = _carpeta(prj, 'Network Model', 'netmod')
    datos = _carpeta(modelo, 'Network Data', 'netdat')
    feeders = datos.CreateObject('IntFolder', 'Feeders')
    lib = _carpeta(prj, 'Library', 'lib')
    equip = _carpeta(lib, 'Equipment Type Library', 'equip')
    tipos = [equip.CreateObject('TypLne', 'TL_' + _nombre(rnd)) for _ in range(rnd.randint(1, 3))]
    tipos_tr = [equip.CreateObject('TypTr2', 'TT_' + _nombre(rnd)) for _ in range(rnd.randint(0, 2))]
    saber = {'redes': {}, 'cargas': {}, 'lineas': [], 'tipos': {'TypLne': len(tipos), 'TypTr2': len(tipos_tr)}}
    usados = set()
    for r in range(rnd.randint(1, 3)):
        net = datos.CreateObject('ElmNet', f'NET{r}_' + _nombre(rnd))
        saber['redes'][net.loc_name] = []
        for _f in range(rnd.randint(1, 3)):
            nombre_f = f'AL{r}{_f}_' + _nombre(rnd)
            alim = fake_pf.Alimentador(app, nombre_f, feeders)
            feeders._hijos.append(alim)
            saber['redes'][net.loc_name].append(nombre_f)
            barras = [net.CreateObject('ElmTerm', f'{nombre_f}_B{i}') for i in range(rnd.randint(2, 4))]
            cub = barras[0].CreateObject('StaCubic', 'c_cab')
            object.__setattr__(alim, 'obj_id', cub)       # cabecera: así se llega a su red, como en DIgSILENT
            alim._objs.extend(barras)
            for i in range(1, len(barras)):
                ln = net.CreateObject('ElmLne', f'{nombre_f}_L{i}')
                ln.typ_id = rnd.choice(tipos)
                usados.add(id(ln.typ_id))
                alim._objs.append(ln)
                saber['lineas'].append(ln)
                carga = net.CreateObject('ElmLod', f'{nombre_f}_C{i}')
                carga.mode_inp = 'PQ'
                carga.plini, carga.qlini = round(rnd.uniform(0.01, 2), 4), round(rnd.uniform(0, 0.5), 4)
                alim._objs.append(carga)
                saber['cargas'][carga.loc_name] = (nombre_f, carga)
    saber['tipos_usados'] = len(usados)
    # Características en una carga cualquiera.
    nombre_c, (_, con_cha) = rnd.choice(sorted(saber['cargas'].items()))
    ref = con_cha.CreateObject('ChaRef', 'plini')
    ref.typ_id = fake_pf.Obj(app, 'ChaTime', 'CH_' + _nombre(rnd), lib)
    saber['caracteristica'] = (nombre_c, ref.typ_id.loc_name)

    estudio = _carpeta(prj, 'Study Cases', 'study')
    n_casos = rnd.randint(2, 4) if casos is None else casos
    lista_casos = [estudio.CreateObject('IntCase', f'CASO{i}_' + _nombre(rnd)) for i in range(n_casos + extra_casos)]
    for i, c in enumerate(lista_casos):
        c.iStudyTime = T0 + (i + 1) * AÑO
    n_esc = rnd.randint(1, 3) if escenarios is None else escenarios
    lista_esc = []
    if n_esc:
        carpeta_esc = _carpeta(prj, 'Operation Scenarios', 'scen')
        for i in range(n_esc):
            e = carpeta_esc.CreateObject('IntScenario', f'ESC{i}_' + _nombre(rnd))
            # Cada escenario guarda su P de cada carga: los casos difieren por su escenario.
            for _n, (_f, carga) in saber['cargas'].items():
                e._datos[id(carga)] = {'_p': round(rnd.uniform(0.01, 2), 4), '_q': round(rnd.uniform(0, .5), 4),
                                       '_cos': 1.0, '_s': 1.0}
            lista_esc.append(e)
    app.escenario_manda = True
    n_var = rnd.randint(1, 3) if variaciones is None else variaciones
    lista_var, etapas = [], []
    if n_var:
        carpeta_var = _carpeta(modelo, 'Variations', 'scheme')
        for i in range(n_var):
            v = carpeta_var.CreateObject('IntScheme', f'VAR{i}_' + _nombre(rnd))
            s = v.CreateObject('IntSstage', f'ETAPA{i}_' + _nombre(rnd))
            s.tAcTime = T0 + rnd.randint(1, n_casos + 1) * AÑO - 1
            net = next(o for o in datos.GetContents('*.ElmNet', 1))
            alta = net.CreateObject('ElmLod', f'NUEVA{i}_' + _nombre(rnd))
            alta.mode_inp, alta.plini, alta.qlini = 'PQ', 0.5, 0.1
            object.__setattr__(alta, 'etapa_creacion', s)
            s._creados.append(alta)
            linea = rnd.choice(saber['lineas'])
            s._deltas[id(linea)] = fake_pf.Delta(s, linea)
            s._deltas[id(linea)]._attrs['dline'] = 2.0
            baja = rnd.choice(sorted(saber['cargas']))
            fake_pf.baja_en_etapa(s, saber['cargas'][baja][1])
            lista_var.append(v)
            etapas.append({'var': v, 'etapa': s, 'alta': alta.loc_name, 'cambio': linea.loc_name, 'baja': baja})
    for c in lista_casos:
        c._estado.escenario = rnd.choice(lista_esc) if lista_esc else None
        c._estado.variaciones = [v for v in lista_var if rnd.random() < .6]
    object.__setattr__(prj, '_ultimo_caso', rnd.choice(lista_casos + [None]) if lista_casos else None)
    saber.update(casos=lista_casos, escenarios=lista_esc, variaciones=lista_var, etapas=etapas, datos=datos)
    return prj, saber


def _app_con_previo(rnd):
    """DIgSILENT con otro proyecto activo, con su caso, que el diagnóstico tiene que devolver (004:RF-100)."""
    app = fake_pf.App()
    previo = fake_pf.Obj(app, 'IntPrj', 'PREVIO_' + _nombre(rnd), app.usuario)
    app.usuario._hijos.append(previo)
    casos = previo.CreateObject('IntPrjfolder', 'Study Cases')
    caso = casos.CreateObject('IntCase', 'CP_' + _nombre(rnd))
    object.__setattr__(previo, '_ultimo_caso', caso)
    previo.Activate()
    app.escrituras.clear()
    app.creados.clear()
    return app, previo, caso


def _pfd(tmp_path, nombre, contenido=b'x', sub='a'):
    d = tmp_path / sub
    d.mkdir(exist_ok=True)
    f = d / nombre
    f.write_bytes(contenido)
    return f


def _correr(guion, monkeypatch, app, pfd, tmp_path, *extra, salida='d.json'):
    from convertersmartgrid import pf_arnes
    monkeypatch.setattr(pf_arnes, 'conectar', lambda _g, **_k: app)
    rc = guion.main(['--pfd', str(pfd), '--output-json', str(tmp_path / salida), '--carpeta', 'CSG_PFD', *extra])
    return rc, json.loads((tmp_path / salida).read_text(encoding='utf-8'))


def _preparar(rnd, tmp_path, **kw):
    app, previo, caso_previo = _app_con_previo(rnd)
    pfd = _pfd(tmp_path, _nombre(rnd) + '.pfd', _nombre(rnd, 30).encode())
    saber = {}

    def crear(app_, destino):
        prj, s = construir(app_, destino, random.Random(SEMILLA), **kw)
        saber.update(s, prj=prj)
        return [prj]

    app.pfd_contenidos[str(pfd.resolve())] = crear
    return app, previo, caso_previo, pfd, saber


# --------------------------------------------------------------------------- importar
def test_importa_en_proyecto_nuevo_con_la_huella(guion, monkeypatch, tmp_path):
    """004:RF-81 — ComPfdimport con g_file y g_target, el proyecto con la huella en el nombre dentro de la carpeta."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path)
    assert rc == 0, (SEMILLA, d['errores'])
    assert d['modo'] == 'importado' and len(d['proyectos']) == 1
    com = app.importados_pfd[0]
    assert com.g_file == str(pfd.resolve()) and com.activatePrj == 0
    carpeta = guion.asegurar_carpeta(app.usuario, 'CSG_PFD')
    prj = saber['prj']
    assert prj.GetParent() is carpeta, SEMILLA
    assert d['sha256'][:10] in prj.loc_name and len(prj.loc_name) <= 40
    # La carpeta provisional se borró y el comando también.
    assert [o.GetClassName() for o in carpeta.GetContents()] == ['IntPrj']
    assert com in app.borrados
    assert guion.marca_de(prj)['sha256'] == d['sha256']


def test_misma_huella_se_reutiliza(guion, monkeypatch, tmp_path):
    """004:RF-82 — con la misma huella y sin cambios, se diagnostica el ya importado y no se importa otra vez."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, _s = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    app.creados.clear()
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path, salida='d2.json')
    assert rc == 0 and d['modo'] == 'reutilizado', (SEMILLA, d)
    assert len(app.importados_pfd) == 1 and not app.creados
    assert d['proyectos'][0]['cambio_tras_importar'] is False and not d['avisos']


def test_cambio_en_digsilent_se_avisa_y_no_se_importa_encima(guion, monkeypatch, tmp_path):
    """004:RF-83 — si el proyecto cambió después de importarlo, aviso, sin importar otra vez ni tocarlo."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    net = next(o for o in saber['datos'].GetContents('*.ElmNet', 1))
    net.CreateObject('ElmLne', 'A_MANO_' + _nombre(rnd))          # el operador añade un tramo en DIgSILENT
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path, salida='d2.json')
    assert rc == 0 and d['modo'] == 'reutilizado', SEMILLA
    assert len(app.importados_pfd) == 1
    assert d['proyectos'][0]['cambio_tras_importar'] is True
    assert any('cambió en DIgSILENT' in a for a in d['avisos'])


def test_reimportar_crea_otro_proyecto_con_sufijo(guion, monkeypatch, tmp_path):
    """004:RF-84 — reimportar crea siempre un proyecto nuevo con su sufijo y deja el anterior como estaba."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    primero = saber['prj']
    nombre, desc = primero.loc_name, list(primero.desc)
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path, '--reimportar', salida='d2.json')
    assert rc == 0 and d['modo'] == 'reimportado', (SEMILLA, d['errores'])
    segundo = saber['prj']
    assert segundo is not primero and segundo.loc_name == nombre + '_2'
    assert primero.loc_name == nombre and list(primero.desc) == desc and primero not in app.borrados


def _nueva_version(app, saber, tmp_path, pfd, sub, rnd, **kw):
    """Otro fichero con el mismo nombre y otro contenido, que el doble importa con ``construir``."""
    f = _pfd(tmp_path, pfd.name, b'otra version ' + sub.encode() + _nombre(rnd, 20).encode(), sub=sub)

    def crear(app_, destino):
        prj, s = construir(app_, destino, random.Random(SEMILLA), **kw)
        saber.update(s, prj=prj)
        return [prj]

    app.pfd_contenidos[str(f.resolve())] = crear
    return f


ANTERIOR = re.compile(r'_anterior_([0-9a-f]{10})_(\d{8}-\d{6})$')


def test_version_nueva_proyecto_nuevo_y_que_cambio(guion, monkeypatch, tmp_path):
    """004:RF-101 / 004:RF-102 — mismo nombre y otra huella: proyecto nuevo y qué cambió frente a la versión anterior."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path, casos=2)
    _rc, d1 = _correr(guion, monkeypatch, app, pfd, tmp_path)
    anterior = saber['prj']
    nuevo_pfd = _nueva_version(app, saber, tmp_path, pfd, 'b', rnd, casos=2, extra_casos=1)
    rc, d = _correr(guion, monkeypatch, app, nuevo_pfd, tmp_path, salida='d2.json')
    assert rc == 0 and d['modo'] == 'version_nueva', (SEMILLA, d['errores'])
    nuevo = saber['prj']
    assert nuevo is not anterior and d['sha256'][:10] in nuevo.loc_name and d1['sha256'] != d['sha256']
    cambios = d['proyectos'][0]['version_anterior']['cambios']
    assert cambios['casos']['nuevos'] == [saber['casos'][-1].loc_name], SEMILLA
    assert set(cambios) == {'casos', 'escenarios', 'variaciones', 'cargas_por_alimentador', 'recuento'}


def test_version_anterior_se_renombra_y_se_conserva(guion, monkeypatch, tmp_path):
    """004:RF-103 / 004:RF-104 / 004:RF-105 — la versión anterior pasa a «_anterior_<sha10>_<sello>» y sigue en la
    carpeta, con su contenido y su marca; el nuevo toma el nombre base, sin sufijo."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _rc, d1 = _correr(guion, monkeypatch, app, pfd, tmp_path)
    anterior = saber['prj']
    carpeta, hijos, sha_ant = anterior.GetParent(), list(anterior._hijos), d1['sha256']
    nuevo_pfd = _nueva_version(app, saber, tmp_path, pfd, 'b', rnd)
    rc, d = _correr(guion, monkeypatch, app, nuevo_pfd, tmp_path, salida='d2.json')
    assert rc == 0, (SEMILLA, d['errores'])
    m = ANTERIOR.search(anterior.loc_name)
    assert m and m.group(1) == sha_ant[:10] and len(anterior.loc_name) <= 40, anterior.loc_name
    assert anterior.GetParent() is carpeta and anterior._hijos == hijos and anterior not in app.borrados
    assert guion.marca_de(anterior)['sha256'] == sha_ant
    nuevo = saber['prj']
    assert nuevo.loc_name == guion.nombre_base(pfd.name, d['sha256'], 0, 1), SEMILLA
    assert sorted(p.loc_name for p in carpeta.GetContents('*.IntPrj')) == sorted([anterior.loc_name, nuevo.loc_name])


def test_version_anterior_solo_se_renombra_una_vez(guion, monkeypatch, tmp_path):
    """004:RF-103 / 004:RF-105 — con una tercera versión se renombra la segunda; la primera conserva su nombre."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    primera = saber['prj']
    _correr(guion, monkeypatch, app, _nueva_version(app, saber, tmp_path, pfd, 'b', rnd), tmp_path, salida='d2.json')
    segunda, nombre_primera = saber['prj'], primera.loc_name
    rc, _d = _correr(guion, monkeypatch, app, _nueva_version(app, saber, tmp_path, pfd, 'c', rnd), tmp_path,
                     salida='d3.json')
    assert rc == 0 and primera.loc_name == nombre_primera, SEMILLA
    assert ANTERIOR.search(segunda.loc_name) and not ANTERIOR.search(saber['prj'].loc_name)
    assert len(guion.asegurar_carpeta(app.usuario, 'CSG_PFD').GetContents('*.IntPrj')) == 3
    assert all(b.GetClassName() != 'IntPrj' for b in app.borrados)


def test_version_anterior_activa_se_desactiva_antes(guion, monkeypatch, tmp_path):
    """004:RF-106 — si la versión anterior está activa, se desactiva antes de renombrarla y se dice; al terminar se
    vuelve a dejar activa, como estaba (004:RF-100)."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    anterior = saber['prj']
    anterior.Activate()
    nombres_al_desactivar = []
    original = anterior.Deactivate

    def desactivar(*a):
        nombres_al_desactivar.append(anterior.loc_name)
        return original(*a)

    object.__setattr__(anterior, 'Deactivate', desactivar)
    nombre = anterior.loc_name
    rc, d = _correr(guion, monkeypatch, app, _nueva_version(app, saber, tmp_path, pfd, 'b', rnd), tmp_path,
                    salida='d2.json')
    assert rc == 0, (SEMILLA, d['errores'])
    assert nombres_al_desactivar and nombres_al_desactivar[0] == nombre
    assert ANTERIOR.search(anterior.loc_name)
    assert any('estaba activo' in a and nombre in a for a in d['avisos'])
    assert app.activo is anterior


def test_informe_nombra_los_dos_proyectos(guion, monkeypatch, tmp_path):
    """004:RF-107 — el JSON y el informe de texto dan el proyecto nuevo y el anterior, con su nombre de antes y de ahora."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    anterior = saber['prj']
    antes = anterior.loc_name
    rc, d = _correr(guion, monkeypatch, app, _nueva_version(app, saber, tmp_path, pfd, 'b', rnd), tmp_path,
                    salida='d2.json')
    assert rc == 0
    assert d['renombrados'] == [{'antes': antes, 'ahora': anterior.loc_name,
                                 'sha256': guion.marca_de(anterior)['sha256'], 'estaba_activo': False}]
    va = d['proyectos'][0]['version_anterior']
    assert va['proyecto'] == anterior.loc_name and va['nombre_antes'] == antes
    assert d['proyectos'][0]['proyecto'] == saber['prj'].loc_name
    texto = (tmp_path / 'd2.txt').read_text(encoding='utf-8')
    assert antes in texto and anterior.loc_name in texto and saber['prj'].loc_name in texto


def test_importacion_fallida_no_renombra_la_anterior(guion, monkeypatch, tmp_path):
    """004:RF-105 — si la versión nueva no se importa, la anterior se queda con su nombre."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    anterior = saber['prj']
    nombre = anterior.loc_name
    nuevo_pfd = _nueva_version(app, saber, tmp_path, pfd, 'b', rnd)
    app.fallar_pfd = True
    rc, _d = _correr(guion, monkeypatch, app, nuevo_pfd, tmp_path, salida='d2.json')
    assert rc == 4 and anterior.loc_name == nombre and anterior not in app.borrados


def test_comparar_versiones_por_partes(guion):
    """004:RF-102 — casos, escenarios, variaciones, totales por alimentador y recuento, cada uno con su cambio."""
    antes = {'casos': ['A', 'B'], 'escenarios': ['E'], 'variaciones': {'V': ['s1']},
             'cargas_por_alimentador': {'A': {'F': {'p_mw': 1.0, 'q_mvar': .1, 'cargas': 2}}}, 'recuento': {'ElmLne': 3}}
    ahora = {'casos': ['B', 'C'], 'escenarios': ['E', 'E2'], 'variaciones': {'V': ['s1', 's2'], 'W': ['t']},
             'cargas_por_alimentador': {'A': {'F': {'p_mw': 1.5, 'q_mvar': .1, 'cargas': 3}}}, 'recuento': {'ElmLne': 4}}
    c = guion.comparar_versiones(antes, ahora)
    assert c['casos'] == {'nuevos': ['C'], 'quitados': ['A']}
    assert c['escenarios'] == {'nuevos': ['E2'], 'quitados': []}
    assert c['variaciones'] == {'nuevas': ['W'], 'quitadas': [], 'con_otras_etapas': ['V']}
    assert c['cargas_por_alimentador'][0]['p_mw_ahora'] == 1.5
    assert c['recuento'] == {'ElmLne': {'antes': 3, 'ahora': 4}}


@pytest.mark.parametrize('nombre,contenido,codigo', [('x.txt', b'1', 2), ('falta.pfd', None, 2)])
def test_uso_sin_digsilent(guion, monkeypatch, tmp_path, nombre, contenido, codigo):
    """004:RF-98 — un fichero que no es .pfd o no existe sale con 2, sin conectar, y deja su JSON."""
    from convertersmartgrid import pf_arnes
    monkeypatch.setattr(pf_arnes, 'conectar', lambda *_a, **_k: pytest.fail('no debía conectar'))
    f = tmp_path / nombre
    if contenido is not None:
        f.write_bytes(contenido)
    assert guion.main(['--pfd', str(f), '--output-json', str(tmp_path / 'd.json')]) == codigo
    d = json.loads((tmp_path / 'd.json').read_text(encoding='utf-8'))
    assert d['codigo'] == codigo and d['errores']
    assert (tmp_path / 'd.txt').is_file()


def test_ayuda_sin_digsilent(guion, capsys):
    """004:RF-98 — ``--help`` sin DIgSILENT, con los códigos de salida en el docstring."""
    with pytest.raises(SystemExit) as e:
        guion.main(['--help'])
    assert e.value.code == 0 and '--pfd' in capsys.readouterr().out
    assert 'Códigos de salida' in guion.__doc__


def test_importacion_que_falla_da_4(guion, monkeypatch, tmp_path):
    """004:RF-99 — si ComPfdimport falla, código 4 con el error en el JSON y nada en la carpeta."""
    rnd = random.Random(SEMILLA)
    app, previo, caso_previo, pfd, _s = _preparar(rnd, tmp_path)
    app.fallar_pfd = True
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path)
    assert rc == 4 and 'ComPfdimport' in d['errores'][0]
    assert not guion.asegurar_carpeta(app.usuario, 'CSG_PFD').GetContents()
    assert app.activo is previo and app.caso is caso_previo


# ------------------------------------------- borrados de importar (084:RF-27, BORRADOS['temporal'] de test_seis_reglas)
def _importar_con_ajenos(guion, tmp_path, rnd):
    """La carpeta destino con dos objetos AJENOS: una carpeta con el MISMO patrón de nombre que la provisional
    (``_csg_pfd_<sha8>``) y un proyecto de otro. Devuelve todo para comprobar qué se borró."""
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    import hashlib
    sha = hashlib.sha256(pfd.read_bytes()).hexdigest()
    destino = guion.asegurar_carpeta(app.usuario, 'CSG_PFD')
    intruso = destino.CreateObject('IntFolder', f'_csg_pfd_{sha[:8]}')
    ajeno = destino.CreateObject('IntPrj', 'AJENO_' + _nombre(rnd))
    app.borrados.clear()
    return app, pfd, sha, destino, intruso, ajeno, saber


def test_importar_borra_solo_su_comando_y_su_carpeta_por_referencia(guion, tmp_path):
    """084:RF-27, 004:RF-81 — importar borra SOLO lo que creó esta ejecución: su ComPfdimport y su carpeta provisional,
    por la referencia que guardó al crearlos. Un objeto ajeno con el mismo patrón de nombre y un proyecto ajeno se
    quedan, y el proyecto importado se mueve, nunca se borra (memorias «borrar solo en su proyecto» y «no tocar
    proyectos ya trabajados»)."""
    rnd = random.Random(SEMILLA)
    app, pfd, sha, destino, intruso, ajeno, saber = _importar_con_ajenos(guion, tmp_path, rnd)
    movidos = guion.importar(app, app.usuario, destino, pfd.resolve(), sha)
    com = app.importados_pfd[-1]
    provisionales = [o for o in app.borrados if o.GetClassName() == 'IntFolder']
    assert com in app.borrados, (SEMILLA, 'el comando creado por la ejecución no se borró')
    assert len(provisionales) == 1 and provisionales[0] is not intruso, (SEMILLA, [o.loc_name for o in provisionales])
    assert provisionales[0].loc_name != intruso.loc_name, (SEMILLA, 'la provisional tomó el nombre del intruso')
    assert set(map(id, app.borrados)) == {id(com), id(provisionales[0])}, (SEMILLA, [o.loc_name for o in app.borrados])
    assert intruso in destino.GetContents() and ajeno in destino.GetContents(), (SEMILLA, 'se tocó un objeto ajeno')
    assert movidos and all(p not in app.borrados and p.GetParent() is destino for p, _o in movidos), SEMILLA


def test_importar_no_borra_la_provisional_si_no_queda_vacia(guion, tmp_path, monkeypatch):
    """084:RF-27 — la carpeta provisional se borra SOLO si queda vacía: si el proyecto importado no se puede mover, la
    carpeta se queda con él dentro y no se borra nada más que el comando."""
    rnd = random.Random(SEMILLA)
    app, pfd, sha, destino, intruso, ajeno, saber = _importar_con_ajenos(guion, tmp_path, rnd)
    monkeypatch.setattr(type(destino), 'Move', lambda self, obj: 1, raising=False)
    with pytest.raises(guion.ErrorDeImportacion):
        guion.importar(app, app.usuario, destino, pfd.resolve(), sha)
    com = app.importados_pfd[-1]
    assert [o for o in app.borrados] == [com], (SEMILLA, [o.loc_name for o in app.borrados])
    assert saber['prj'] not in app.borrados and intruso not in app.borrados and ajeno not in app.borrados, SEMILLA


def test_importacion_fallida_no_borra_nada_ajeno(guion, tmp_path):
    """084:RF-27 — si ComPfdimport falla, se borran su comando y su carpeta provisional vacía, y nada ajeno."""
    rnd = random.Random(SEMILLA)
    app, pfd, sha, destino, intruso, ajeno, _saber = _importar_con_ajenos(guion, tmp_path, rnd)
    app.fallar_pfd = True
    with pytest.raises(guion.ErrorDeImportacion):
        guion.importar(app, app.usuario, destino, pfd.resolve(), sha)
    assert intruso not in app.borrados and ajeno not in app.borrados, (SEMILLA, [o.loc_name for o in app.borrados])
    assert intruso in destino.GetContents() and ajeno in destino.GetContents(), SEMILLA


# --------------------------------------------------------------------------- diagnóstico
@pytest.fixture
def corrida(guion, monkeypatch, tmp_path):
    rnd = random.Random(SEMILLA)
    app, previo, caso_previo, pfd, saber = _preparar(rnd, tmp_path)
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path)
    # Sin afirmar aquí: una aserción en la preparación es un ERROR de pytest; la comprueba cada prueba, con _bien.
    return app, previo, caso_previo, saber, {**d, '_rc': rc}, (d.get('proyectos') or [{}])[0]


def _bien(corrida):
    """La corrida terminó bien: la primera aserción de cada prueba que la usa."""
    d = corrida[4]
    assert d['_rc'] == 0 and d.get('proyectos'), (SEMILLA, d.get('errores'), d.get('traza'))


def test_solo_lectura(guion, monkeypatch, tmp_path):
    """004:RF-85 — al diagnosticar (reutilizando) no se escribe nada ni se calcula."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, saber = _preparar(rnd, tmp_path)
    _correr(guion, monkeypatch, app, pfd, tmp_path)
    app.escrituras.clear()
    app.creados.clear()
    n_borrados, n_movidos = len(app.borrados), len(app.movidos)
    rc, _d = _correr(guion, monkeypatch, app, pfd, tmp_path, salida='d2.json')
    assert rc == 0
    assert not app.escrituras and not app.creados, (SEMILLA, app.escrituras[:3])
    assert len(app.borrados) == n_borrados and len(app.movidos) == n_movidos
    assert all(not getattr(e, 'guardados', 0) for e in saber['escenarios'])


def test_redes_y_alimentadores(corrida):
    """004:RF-86 — cada red con sus alimentadores, que están en «Feeders» y no en la red."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    leidas = {r['red']: r['alimentadores'] for r in diag['red']['redes']}
    assert leidas == {k: sorted(v, key=str.lower) for k, v in saber['redes'].items()}, SEMILLA
    assert not diag['red']['alimentadores_sin_red']


def test_casos_con_escenario_variaciones_y_hora(corrida):
    """004:RF-87 — cada caso con su escenario, sus variaciones activas y su hora de estudio."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    leidos = {c['caso']: c for c in diag['casos']}
    assert set(leidos) == {c.loc_name for c in saber['casos']}, SEMILLA
    for caso in saber['casos']:
        c = leidos[caso.loc_name]
        esc = caso._estado.escenario
        assert c['escenario'] == (esc.loc_name if esc else None)
        assert c['variaciones_activas'] == sorted(v.loc_name for v in caso._estado.variaciones)
        assert c['hora_estudio'] == caso.iStudyTime and c['fecha_estudio']


def test_caso_activo_al_empezar(corrida):
    """004:RF-88 — el caso que el proyecto tenía activo; sin él, se dice y la referencia es el primero."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    inicial = saber['prj'].__dict__.get('_ultimo_caso')
    # El proyecto se activó por primera vez con el caso que DIgSILENT recordaba.
    casos = sorted(saber['casos'], key=lambda c: c.loc_name.lower())
    esperado = inicial.loc_name if inicial is not None else None
    assert diag['caso_activo'] == esperado, SEMILLA
    assert diag['caso_referencia'] == (esperado or casos[0].loc_name)


def test_escenarios_con_sus_casos(corrida):
    """004:RF-89 — cada escenario con los casos que lo tienen activo."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    for e in diag['escenarios']:
        assert sorted(e['casos']) == sorted(c.loc_name for c in saber['casos']
                                            if c._estado.escenario is not None
                                            and c._estado.escenario.loc_name == e['escenario']), SEMILLA


def test_variaciones_etapas_fecha_y_cambios(corrida):
    """004:RF-90 / 004:RF-91 — cada etapa con su fecha y año, y lo que da de alta, de baja o cambia."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    por_nombre = {v['variacion']: v for v in diag['variaciones']}
    assert set(por_nombre) == {v.loc_name for v in saber['variaciones']}, SEMILLA
    for e in saber['etapas']:
        etapa = por_nombre[e['var'].loc_name]['etapas'][0]
        assert etapa['etapa'] == e['etapa'].loc_name and etapa['instante'] == e['etapa'].tAcTime
        assert etapa['anio'] == int(etapa['fecha'][:4])
        cambios = {(c['tipo'], c['clase'], c['nombre']) for c in etapa['cambios']}
        assert cambios == {('alta', 'ElmLod', e['alta']), ('cambio', 'ElmLne', e['cambio']),
                           ('baja', 'ElmLod', e['baja'])}, SEMILLA
        assert (etapa['altas'], etapa['bajas'], etapa['cambiados']) == (1, 1, 1)


def test_donde_se_estudia_cada_etapa(corrida):
    """004:RF-92 — una etapa se estudia en los casos con su variación activa y su fecha dentro de la hora de estudio,
    con el escenario de cada uno."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    por_nombre = {v['variacion']: v for v in diag['variaciones']}
    for e in saber['etapas']:
        etapa = por_nombre[e['var'].loc_name]['etapas'][0]
        esperado = sorted(
            (c.loc_name, c._estado.escenario.loc_name if c._estado.escenario else None) for c in saber['casos']
            if e['var'] in c._estado.variaciones and e['etapa'].tAcTime <= c.iStudyTime)
        assert sorted((x['caso'], x['escenario']) for x in etapa['estudiada_en']) == esperado, SEMILLA


def test_cargas_por_caso(corrida):
    """004:RF-93 — en cada caso, sus cargas con P y Q de su escenario, escala, característica y alimentador."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    for caso in saber['casos']:
        c = next(x for x in diag['casos'] if x['caso'] == caso.loc_name)
        por = {x['carga']: x for x in c['cargas']}
        esc = caso._estado.escenario
        for nombre, (alim, carga) in saber['cargas'].items():
            assert por[nombre]['alimentador'] == alim, SEMILLA
            p = esc._datos[id(carga)]['_p'] if esc else carga.__dict__['_p']
            assert por[nombre]['p_mw'] == pytest.approx(p) and por[nombre]['escala'] == 1.0
        # Las altas de las variaciones activas en el caso, también.
        nuevas = {e['alta'] for e in saber['etapas'] if e['var'] in caso._estado.variaciones}
        assert nuevas <= set(por), SEMILLA
        nombre_c, cha = saber['caracteristica']
        assert por[nombre_c]['caracteristicas'] == [{'parametro': 'plini', 'caracteristica': cha, 'clase': 'ChaTime'}]


def test_totales_por_alimentador_y_proyecto(corrida):
    """004:RF-94 — los totales de P y Q por alimentador suman el del proyecto."""
    _bien(corrida)
    _app, _p, _c, _saber, _d, diag = corrida
    for c in diag['casos']:
        t = c['totales']
        assert sum(x['p_mw'] for x in t['por_alimentador'].values()) == pytest.approx(t['proyecto']['p_mw'])
        assert sum(x['cargas'] for x in t['por_alimentador'].values()) == t['proyecto']['cargas'] == len(c['cargas'])
        assert t['proyecto']['p_mw'] == pytest.approx(sum(x['p_mw'] for x in c['cargas']))


def test_diferencias_entre_casos(guion):
    """004:RF-95 — cargas solo en uno de los casos y P o Q distintas, frente a la referencia."""
    def carga(n, p, q):
        return {'carga': n, 'ruta': 'r/' + n, 'p_mw': p, 'q_mvar': q}
    ref = {'caso': 'R', 'cargas': [carga('a', 1.0, .1), carga('b', 2.0, .2)]}
    otro = {'caso': 'O', 'cargas': [carga('a', 1.0, .1), carga('c', 1.0, .0)]}
    otro['cargas'].append(carga('b', 2.5, .2))
    d = guion.diferencias(ref, otro)
    assert d['solo_en_el_caso'] == ['c'] and d['solo_en_la_referencia'] == []
    assert d['distintas'] == [{'carga': 'b', 'magnitud': 'p_mw', 'referencia': 2.0, 'caso': 2.5}]


def test_diferencias_en_la_corrida(corrida):
    """004:RF-95 — una diferencia por cada caso que no es la referencia."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    assert sorted(x['caso'] for x in diag['diferencias']) == sorted(
        c.loc_name for c in saber['casos'] if c.loc_name != diag['caso_referencia']), SEMILLA


def test_recuento_por_clase_y_tipos(corrida):
    """004:RF-96 — elementos de red por clase y tipos Typ* de la biblioteca, sin listas fijas."""
    _bien(corrida)
    _app, _p, _c, saber, _d, diag = corrida
    rec = diag['recuento']
    assert rec['elementos']['ElmLne'] == len(saber['lineas']), SEMILLA
    assert rec['elementos']['ElmNet'] == len(saber['redes'])
    assert rec['elementos']['ElmFeeder'] == sum(len(v) for v in saber['redes'].values())
    assert rec['tipos'] == {k: v for k, v in saber['tipos'].items() if v}
    assert rec['tipos_usados'] == {'TypLne': saber['tipos_usados']}


def test_aviso_de_exportacion_reducida(guion, monkeypatch, tmp_path):
    """004:RF-97 — un caso, sin escenarios ni variaciones: aviso, y nada inventado."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, _s = _preparar(rnd, tmp_path, casos=1, escenarios=0, variaciones=0)
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path)
    diag = d['proyectos'][0]
    assert rc == 0 and diag['exportacion_reducida'] is True
    assert diag['escenarios'] == [] and diag['variaciones'] == []
    assert any('exportación reducida' in a for a in diag['avisos'])


def test_sin_aviso_de_reducida_con_lo_completo(corrida):
    """004:RF-97 — con varios casos no hay aviso."""
    _bien(corrida)
    assert corrida[5]['exportacion_reducida'] is False


def test_json_e_informe_legible(corrida, tmp_path):
    """004:RF-98 — el JSON de la corrida y su informe de texto, que nombra casos, etapas y totales."""
    _bien(corrida)
    _app, _p, _c, saber, d, _diag = corrida
    texto = (tmp_path / 'd.txt').read_text(encoding='utf-8')
    assert d['esquema'] == 'csg-pfd-diagnostico-v1' and d['codigo'] == 0
    for c in saber['casos']:
        assert f'Caso {c.loc_name}' in texto, SEMILLA
    for e in saber['etapas']:
        assert e['etapa'].loc_name in texto and e['alta'] in texto


def test_informe_parcial_si_falla_una_llamada(guion, monkeypatch, tmp_path):
    """004:RF-99 / 004:RF-100 — si una llamada falla a mitad, el JSON lleva lo leído y el error, y quedan activos el
    proyecto y el caso de antes."""
    rnd = random.Random(SEMILLA)
    app, previo, caso_previo, pfd, _s = _preparar(rnd, tmp_path)
    llamadas = []

    def falla(patron):
        llamadas.append(patron)
        if len(llamadas) > 1:
            raise RuntimeError('DIgSILENT no responde')
        return fake_pf.App.GetCalcRelevantObjects(app, patron)

    monkeypatch.setattr(app, 'GetCalcRelevantObjects', falla)
    rc, d = _correr(guion, monkeypatch, app, pfd, tmp_path)
    assert rc == 1 and 'DIgSILENT no responde' in d['errores'][0] and d['traza']
    diag = d['proyectos'][0]
    assert diag['red']['redes'] and len(diag['casos']) == 1, SEMILLA
    assert 'DIgSILENT no responde' in (tmp_path / 'd.txt').read_text(encoding='utf-8')
    assert app.activo is previo and app.caso is caso_previo


def test_informe_si_el_proceso_revienta(guion, monkeypatch, tmp_path):
    """004:RF-99 — aunque el proceso reviente con algo que no es Exception, el JSON queda escrito con lo leído."""
    rnd = random.Random(SEMILLA)
    app, _previo, _cp, pfd, _s = _preparar(rnd, tmp_path)

    class Revienta(BaseException):
        """Algo que ningún ``except Exception`` recoge, como un corte del proceso."""

    def corta(_patron):
        raise Revienta

    monkeypatch.setattr(app, 'GetCalcRelevantObjects', corta)
    with pytest.raises(Revienta):
        _correr(guion, monkeypatch, app, pfd, tmp_path)
    d = json.loads((tmp_path / 'd.json').read_text(encoding='utf-8'))
    assert d['proyectos'][0]['red']['redes'], SEMILLA
    assert (tmp_path / 'd.txt').is_file()


def test_restaura_proyecto_y_caso_activos(corrida):
    """004:RF-100 — al terminar, el proyecto y el caso de antes; el importado vuelve a su caso inicial."""
    _bien(corrida)
    app, previo, caso_previo, saber, _d, diag = corrida
    assert app.activo is previo and app.caso is caso_previo, SEMILLA
    inicial = saber['prj'].__dict__.get('_ultimo_caso')
    assert (inicial.loc_name if inicial is not None else None) == diag['caso_activo']


def test_restaura_sin_proyecto_activo(guion, monkeypatch, tmp_path):
    """004:RF-100 — si no había proyecto activo, no queda ninguno."""
    rnd = random.Random(SEMILLA)
    app, previo, _cp, pfd, _s = _preparar(rnd, tmp_path)
    previo.Deactivate()
    rc, _d = _correr(guion, monkeypatch, app, pfd, tmp_path)
    assert rc == 0 and app.activo is None


def test_etapas_empatadas_se_avisan(guion):
    """004:RF-92 — con tres etapas vigentes de la misma fecha en un caso, aviso de que DIgSILENT no aplica ninguna."""
    etapa = lambda n: {'etapa': n, 'instante': 10, 'excluida': False}  # noqa: E731
    diag = {'casos': [{'caso': 'C', 'escenario': None, 'escenario_ruta': None, 'hora_estudio': 20,
                       'variaciones_rutas': ['v1', 'v2', 'v3'], 'cargas': []}],
            'escenarios': [], 'avisos': [], 'caso_activo': 'C',
            'variaciones': [{'variacion': f'V{i}', 'ruta': f'v{i}', 'etapas': [etapa(f's{i}')]} for i in (1, 2, 3)]}
    guion._completar(diag)
    assert any('3 etapas vigentes' in a for a in diag['avisos'])
