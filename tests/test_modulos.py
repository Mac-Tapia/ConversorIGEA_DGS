"""Registro de módulos enchufables: paquetes falsos instalados de verdad en ``tmp_path``."""
from __future__ import annotations

import json
import pickle
import threading
from pathlib import Path

import pytest

from convertersmartgrid import puertos, registro_modulos as rm
from convertersmartgrid.puertos import Modulo

RAIZ = Path(__file__).resolve().parents[1]

CLASE = '''
class Impl:
    mode = "falso"
    def load(self, snapshot, *, aliases): return None
'''


def instalar(raiz: Path, paquete: str, nombre: str, codigo: str) -> None:
    """Un paquete instalado de verdad: su módulo y su dist-info con el entry point."""
    (raiz / f'{paquete}.py').write_text(codigo, encoding='utf-8')
    info = raiz / f'{paquete}-1.0.dist-info'
    info.mkdir()
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {paquete}\nVersion: 1.0\n', encoding='utf-8')
    (info / 'entry_points.txt').write_text(f'[{rm.GRUPO}]\n{nombre} = {paquete}:MODULO\n', encoding='utf-8')


def modulo_de(nombre: str, *, version: str = '1.0', puerto: str = 'lector', clase: str = CLASE) -> str:
    return (f'from convertersmartgrid.puertos import Modulo\n{clase}\n'
            f'MODULO = Modulo({nombre!r}, {puerto!r}, {version!r}, Impl)\n')


def permitir(raiz: Path, *nombres: str) -> Path:
    ruta = raiz / rm.RUTA_PERMITIDOS
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps({'permitidos': list(nombres)}), encoding='utf-8')
    return raiz


@pytest.fixture
def sitio(tmp_path, monkeypatch):
    carpeta = tmp_path / 'sitio'
    carpeta.mkdir()
    monkeypatch.syspath_prepend(str(carpeta))
    return carpeta


def declarado(nombre, valor='p:M', distribucion='externo'):
    return rm.Declarado(nombre, valor, distribucion)


def test_los_cuatro_puertos_existen():
    """002:RF-7 — interfaces del núcleo con su versión."""
    for clase in (puertos.LectorDeRed, puertos.EscritorDeRed, puertos.Estudio, puertos.SesionPowerFactory):
        assert hasattr(clase, '__protocol_attrs__') or getattr(clase, '_is_protocol', False)
    assert set(puertos.PUERTOS) == {'lector', 'escritor', 'estudio', 'sesion'}


def test_paquete_instalado_y_permitido_se_descubre_sin_tocar_el_nucleo(sitio, tmp_path):
    """002:RF-8 — basta su entry point y la lista de permitidos."""
    instalar(sitio, 'pkg_bueno', 'lector-falso', modulo_de('lector-falso'))
    registro = rm.cargar(rm.resolver(permitir(tmp_path, 'lector-falso')))
    assert registro.modulos['lector-falso'].puerto == 'lector'
    assert registro.del_puerto('lector')


def test_lectores_y_escritor_propios_van_por_la_misma_via():
    """002:RF-9, 002:RF-27 — declarados en pyproject e importables como un módulo externo."""
    declarados = rm.declarados_en_pyproject(RAIZ)
    assert {'lector-txt', 'lector-mdb', 'lector-vnr', 'escritor-dgs'} <= set(declarados)
    propios = [rm.Declarado(n, v, rm.DISTRIBUCION_PROPIA) for n, v in declarados.items()]
    registro = rm.cargar(rm.resolver(RAIZ, propios))
    assert not registro.diagnostico, registro.diagnostico
    assert [m.nombre for m in registro.del_puerto('lector')] == ['lector-mdb', 'lector-txt', 'lector-vnr']
    assert [m.nombre for m in registro.del_puerto('escritor')] == ['escritor-dgs']


def test_orden_por_nombre_sin_depender_de_la_instalacion(tmp_path):
    """002:RF-10 — el orden declarado de instalación no cambia el resultado."""
    uno = [declarado('b'), declarado('a'), declarado('c')]
    permitir(tmp_path, 'a', 'b', 'c')
    assert rm.resolver(tmp_path, uno) == rm.resolver(tmp_path, list(reversed(uno)))
    assert [d.nombre for d in rm.resolver(tmp_path, uno).declarados] == ['a', 'b', 'c']


def test_modulo_roto_o_sin_metodos_se_excluye_y_se_nombra(sitio, tmp_path):
    """002:RF-11 — ninguno de los dos para al que sí funciona."""
    instalar(sitio, 'pkg_roto', 'roto', 'raise RuntimeError("desinstalado a medias")\n')
    instalar(sitio, 'pkg_incompleto', 'incompleto',
             modulo_de('incompleto', clase='class Impl:\n    mode = "x"\n'))
    instalar(sitio, 'pkg_sano', 'sano', modulo_de('sano'))
    registro = rm.cargar(rm.resolver(permitir(tmp_path, 'roto', 'incompleto', 'sano')))
    assert 'sano' in registro.modulos and not {'roto', 'incompleto'} & set(registro.modulos)
    texto = '\n'.join(registro.diagnostico)
    assert 'roto' in texto and 'desinstalado a medias' in texto
    assert 'incompleto' in texto and 'load' in texto


def test_mismo_nombre_rechaza_los_dos_y_nombra_ambos(sitio, tmp_path):
    """002:RF-12 — también si uno de los dos es interno."""
    instalar(sitio, 'pkg_uno', 'igual', modulo_de('igual'))
    instalar(sitio, 'pkg_dos', 'igual', modulo_de('igual'))
    resolucion = rm.resolver(permitir(tmp_path, 'igual'))
    assert not [d for d in resolucion.declarados if d.nombre == 'igual']
    aviso = next(d for d in resolucion.diagnostico if d.startswith('igual'))
    assert 'pkg_uno' in aviso and 'pkg_dos' in aviso
    interno = rm.resolver(tmp_path, [declarado('x', distribucion=rm.DISTRIBUCION_PROPIA), declarado('x')])
    assert not interno.declarados and 'convertersmartgrid' in interno.diagnostico[-1]


def test_escritor_recibe_el_modelo_preparado_y_auditado(tmp_path, monkeypatch):
    """002:RF-13 — pasa por preparar_dataset, aplicar_reglas y auditar_completitud antes de escribir."""
    from convertersmartgrid import escritores
    llamadas = []
    monkeypatch.setattr(escritores, 'preparar_dataset', lambda d, catalogo=None: llamadas.append('preparar'))
    monkeypatch.setattr(escritores, 'build_feeder_model', lambda d, r: llamadas.append('modelo') or 'modelo')
    monkeypatch.setattr(escritores, 'aplicar_reglas', lambda m, r: llamadas.append('reglas') or {'hecho': 1})
    monkeypatch.setattr(escritores, 'write_dgs', lambda m, ruta: llamadas.append('dgs auditoria'))
    monkeypatch.setattr(escritores, 'parse_dgs', lambda ruta: {'tablas': 1})
    monkeypatch.setattr(escritores, 'auditar_completitud',
                        lambda d, redes, m, t, i: llamadas.append(('auditar', redes, t, i)) or {'fallos': []})

    class Escritor:
        def escribir(self, modelo, destino, *, auditoria):
            llamadas.append('escribir')
            return modelo, destino, auditoria

    salida = escritores.entregar_al_escritor(Escritor(), object(), 'A', tmp_path / 'a.salida')
    assert llamadas == ['preparar', 'modelo', 'reglas', 'dgs auditoria',
                        ('auditar', ['A'], {'tablas': 1}, [{'hecho': 1}]), 'escribir']
    assert salida == ('modelo', tmp_path / 'a.salida', {'fallos': []})


def test_estudio_de_powerfactory_va_al_carril_unico():
    """002:RF-14 — estudio con PowerFactory y sesión, en el carril en serie."""
    class ConPf:
        usa_powerfactory = True
        def ejecutar(self, ctx, **k): ...

    class SinPf:
        usa_powerfactory = False
        def ejecutar(self, ctx, **k): ...

    assert rm.carril_de(Modulo('a', 'estudio', '1.0', ConPf)) == 'powerfactory'
    assert rm.carril_de(Modulo('b', 'sesion', '1.0', SinPf)) == 'powerfactory'
    assert rm.carril_de(Modulo('c', 'estudio', '1.0', SinPf)) == 'engine'


def test_la_web_no_instala_ni_edita_modulos(tmp_path):
    """002:RF-15, 002:RF-24 — ninguna ruta sube módulos ni toca la lista de permitidos."""
    from convertersmartgrid.web.app import create_app
    rutas = [getattr(r, 'path', '') for r in create_app(tmp_path / 'web').routes]
    assert rutas and not [r for r in rutas if 'modulos' in r or 'permitidos' in r or 'plugin' in r]
    fuente = (RAIZ / 'src/convertersmartgrid/web/app.py').read_text(encoding='utf-8')
    assert 'registro_modulos' not in fuente and 'modulos_permitidos' not in fuente


def test_externo_no_permitido_ni_se_importa(sitio, tmp_path):
    """002:RF-23 — si se importase, el fichero dejaría su marca."""
    marca = tmp_path / 'importado'
    instalar(sitio, 'pkg_ajeno', 'ajeno', f'open({str(marca)!r}, "w").close()\n' + modulo_de('ajeno'))
    registro = rm.cargar(rm.resolver(tmp_path))
    assert 'ajeno' not in registro.modulos and not marca.exists()
    assert any(d.startswith('ajeno') and 'modulos_permitidos' in d for d in registro.diagnostico)


@pytest.mark.parametrize('version,entra', [('2.0', False), ('1.3', True), ('1.0', True), ('0.9', False)])
def test_version_mayor_distinta_excluye_y_nombra_las_dos(sitio, tmp_path, version, entra):
    """002:RF-25 — una menor distinta entra, porque una menor solo añade."""
    paquete = 'pkg_v' + version.replace('.', '_')
    instalar(sitio, paquete, 'versionado', modulo_de('versionado', version=version))
    registro = rm.cargar(rm.resolver(permitir(tmp_path, 'versionado')))
    assert ('versionado' in registro.modulos) is entra
    if not entra:
        assert any(version in d and puertos.VERSION_PUERTOS in d for d in registro.diagnostico)


def test_dependencia_ausente_excluye_y_arranca_igual(sitio, tmp_path):
    """002:RF-26 — el módulo cuya dependencia falta no impide a los demás."""
    instalar(sitio, 'pkg_sin_dep', 'sin-dep', 'import paquete_que_no_existe_002\n' + modulo_de('sin-dep'))
    instalar(sitio, 'pkg_con_dep', 'con-dep', modulo_de('con-dep'))
    registro = rm.cargar(rm.resolver(permitir(tmp_path, 'sin-dep', 'con-dep')))
    assert 'con-dep' in registro.modulos and 'sin-dep' not in registro.modulos
    assert any('sin-dep' in d and 'paquete_que_no_existe_002' in d for d in registro.diagnostico)


def test_internos_sin_lista_y_externos_con_ella(tmp_path):
    """002:RF-27 — lo decide la distribución que lo declara, no el nombre."""
    resolucion = rm.resolver(tmp_path, [declarado('interno', distribucion=rm.DISTRIBUCION_PROPIA),
                                        declarado('externo')])
    assert [d.nombre for d in resolucion.declarados] == ['interno']


def test_lista_rota_no_permite_externos_y_lo_dice(tmp_path):
    """002:RF-23 — una lista ilegible no abre la puerta ni para el arranque."""
    (tmp_path / 'config').mkdir()
    (tmp_path / rm.RUTA_PERMITIDOS).write_text('{no es json', encoding='utf-8')
    resolucion = rm.resolver(tmp_path, [declarado('externo')])
    assert not resolucion.declarados and 'modulos_permitidos.json' in resolucion.diagnostico[0]


def test_desfase_pide_reinstalar():
    """002:RF-28 — una entrada que falta, sobra o cambia nombra el remedio."""
    propio = rm.DISTRIBUCION_PROPIA
    assert not rm.desfase_de_entry_points({'a': 'x:M'}, [rm.Declarado('a', 'x:M', propio), declarado('ext')])
    for instalados in ([], [rm.Declarado('a', 'y:M', propio)], [rm.Declarado('a', 'x:M', propio), rm.Declarado('b', 'z:M', propio)]):
        errores = rm.desfase_de_entry_points({'a': 'x:M'}, instalados)
        assert errores and all('pip install -e .' in e for e in errores)


def test_entry_points_instalados_coinciden_con_pyproject():
    """002:RF-28 — rojo con la orden que lo arregla si se actualizó el código sin reinstalar."""
    errores = rm.desfase_de_entry_points(rm.declarados_en_pyproject(RAIZ), rm._instalados())
    assert not errores, '\n'.join(errores)


def test_resolucion_cruza_a_un_hijo_y_da_el_mismo_orden(tmp_path):
    """002:RF-29 — los hijos usan lo que resolvió el principal, sin releer la lista."""
    resolucion = rm.resolver(permitir(tmp_path, 'a', 'b'), [declarado('b'), declarado('a')])
    assert pickle.loads(pickle.dumps(resolucion)) == resolucion
    rm.instalar_en_proceso(resolucion)
    try:
        assert rm.resolucion_del_proceso() is resolucion
    finally:
        rm.instalar_en_proceso(None)


def test_la_conversion_en_paralelo_pasa_la_resolucion_a_cada_hijo(monkeypatch):
    """002:RF-29 — el arranque del hijo recibe la resolución del principal."""
    import convertersmartgrid.batch as lote
    resolucion = rm.Resolucion(permitidos=('x',))
    try:
        lote._init_worker('dataset', 'opciones', resolucion)
        assert rm.resolucion_del_proceso() is resolucion
        assert lote._WORKER_STATE == ('dataset', 'opciones')
    finally:
        rm.instalar_en_proceso(None)
        monkeypatch.setattr(lote, '_WORKER_STATE', None)


def test_estudio_sin_powerfactory_es_un_trabajo_cancelable():
    """002:RF-30 — en cola, con progreso, y se cancela a mitad."""
    from convertersmartgrid.web.jobs import JobManager
    empezo, soltar = threading.Event(), threading.Event()

    class Largo:
        usa_powerfactory = False

        def ejecutar(self, ctx, **parametros):
            ctx.progress(1, 2, parametros['que'])
            empezo.set()
            soltar.wait(20)
            ctx.check_cancel()
            return 'terminó'

    trabajos = JobManager(lambda *a: None)
    try:
        trabajo = rm.lanzar_estudio(trabajos, 'w', Modulo('largo', 'estudio', '1.0', Largo), que='paso')
        assert trabajo.lane == 'engine' and empezo.wait(20)
        assert trabajos.cancel(trabajo.id)
        soltar.set()
        for _ in range(400):
            if trabajo.status not in ('queued', 'running'):
                break
            threading.Event().wait(0.05)
        assert trabajo.status == 'cancelled'
    finally:
        soltar.set()
        trabajos.shutdown()


def test_un_lector_no_se_lanza_como_estudio():
    """002:RF-30 — solo estudios y sesiones son trabajos de estudio."""
    with pytest.raises(ValueError, match='lector'):
        rm.lanzar_estudio(None, 'w', Modulo('l', 'lector', '1.0', object))
