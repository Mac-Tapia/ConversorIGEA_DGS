"""Utilidades comunes de ``convertersmartgrid.util`` (spec 001, T2).

Estaban copiadas hasta en siete sitios (diagnóstico del 2026-10-07, B5). Además de su
comportamiento, aquí se prueba que no vuelvan a copiarse: el detector compara el árbol
sintáctico normalizado de cada función de ``src/`` con el de las de ``util``.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from convertersmartgrid import util
from convertersmartgrid.util import (
    finite_or_none, importar_opcional, nombre_seguro, sha256_file, write_json_atomic,
)

SRC = Path(__file__).resolve().parents[1] / 'src'


# --- SHA-256 ---------------------------------------------------------------------------

@pytest.mark.parametrize('tamano', [0, 1, (1 << 20) - 1, 1 << 20, (1 << 20) + 7, 3 * (1 << 20)])
def test_sha256_file_igual_que_hashlib_en_los_bordes_de_bloque(tmp_path, tamano):
    """001:RF-4 — el hash por bloques coincide con el del contenido entero."""
    datos = bytes((i * 31 + 7) % 256 for i in range(tamano))
    ruta = tmp_path / 'f.bin'
    ruta.write_bytes(datos)
    assert sha256_file(ruta) == hashlib.sha256(datos).hexdigest()
    assert sha256_file(str(ruta)) == hashlib.sha256(datos).hexdigest()


# --- JSON atómico ----------------------------------------------------------------------

def test_write_json_atomic_formato_y_carpetas(tmp_path):
    """001:RF-5 — crea las carpetas, conserva acentos y termina en salto de línea."""
    ruta = tmp_path / 'a' / 'b' / 'manifiesto.json'
    write_json_atomic(ruta, {'nombre': 'Señal Ñ', 'ruta': Path('x/y')})
    texto = ruta.read_text(encoding='utf-8')
    assert texto == json.dumps({'nombre': 'Señal Ñ', 'ruta': str(Path('x/y'))}, indent=2,
                               ensure_ascii=False) + '\n'
    assert not list(ruta.parent.glob('*.tmp'))


def test_write_json_atomic_reemplaza_el_anterior(tmp_path):
    """001:RF-5 — sobrescribe un fichero existente sin dejar el temporal."""
    ruta = tmp_path / 'm.json'
    write_json_atomic(ruta, {'v': 1})
    write_json_atomic(ruta, {'v': 2})
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'v': 2}
    assert [p.name for p in tmp_path.iterdir()] == ['m.json']


def test_write_json_atomic_no_toca_el_anterior_si_falla(tmp_path):
    """001:RF-5 — si no se puede serializar, el fichero anterior queda intacto."""
    ruta = tmp_path / 'm.json'
    write_json_atomic(ruta, {'v': 1})
    circular: dict = {}
    circular['yo'] = circular
    with pytest.raises(ValueError):
        write_json_atomic(ruta, circular)
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'v': 1}
    assert [p.name for p in tmp_path.iterdir()] == ['m.json']


# --- Número finito ---------------------------------------------------------------------

@pytest.mark.parametrize('valor, esperado', [
    ('1.5', 1.5), (3, 3.0), ('-0', 0.0), (' 2 ', 2.0),
    ('nan', None), ('inf', None), ('-inf', None), (float('nan'), None),
    (None, None), ('', None), ('x', None), ([], None),
])
def test_finite_or_none(valor, esperado):
    """001:T2 — número finito, o ``None`` para todo lo demás."""
    assert finite_or_none(valor) == esperado


# --- Nombre seguro ---------------------------------------------------------------------

@pytest.mark.parametrize('texto, maximo, esperado', [
    ('Red Sur/1', None, 'Red_Sur_1'),
    ('ÁREA-2_b', None, 'ÁREA-2_b'),
    ('', None, 'GRUPO'),
    ('a' * 80, 60, 'a' * 60),
    ('x.y', 2, 'x_'),
])
def test_nombre_seguro(texto, maximo, esperado):
    """001:T2 — solo letras, dígitos, guion y guion bajo; nunca vacío."""
    assert nombre_seguro(texto, maximo=maximo) == esperado


# --- Dependencia opcional --------------------------------------------------------------

def test_importar_opcional_devuelve_el_modulo():
    """001:T3 — si está instalado, devuelve el módulo."""
    assert importar_opcional('json', RuntimeError('no')) is json


def test_importar_opcional_lanza_el_error_de_quien_llama():
    """001:T3 — cada vía conserva su excepción (DownloadError, ArcGISError…)."""
    class ErrorPropio(RuntimeError):
        pass

    with pytest.raises(ErrorPropio, match='falta X') as info:
        importar_opcional('modulo_que_no_existe_csg', ErrorPropio('falta X'))
    assert isinstance(info.value.__cause__, ImportError)


# --- Detector de copias ----------------------------------------------------------------

class _Normaliza(ast.NodeTransformer):
    """Quita nombres, anotaciones y docstrings: dos copias con otras variables coinciden."""

    def __init__(self) -> None:
        self.nombres: dict[str, str] = {}

    def _marca(self, nombre: str) -> str:
        return self.nombres.setdefault(nombre, f'v{len(self.nombres)}')

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id=self._marca(node.id), ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg=self._marca(node.arg)), node)


def _huella(funcion: ast.FunctionDef) -> str:
    cuerpo = list(funcion.body)
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
        cuerpo = cuerpo[1:]
    copia = ast.Module(body=[ast.parse(ast.unparse(n)).body[0] for n in cuerpo], type_ignores=[])
    return ast.dump(_Normaliza().visit(copia))


def _funciones(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding='utf-8'))
    return [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)]


@pytest.mark.parametrize('paquete', ['convertersmartgrid', 'convertersmartgrid/adaptadores/entrada/vnr'])
def test_ninguna_utilidad_esta_copiada(paquete):
    """001:RF-4, 001:RF-5 — las utilidades viven solo en ``convertersmartgrid.util``."""
    ruta_util = Path(util.__file__)
    propias = {_huella(f): f.name for f in _funciones(ruta_util) if not f.name.startswith('_')}
    copias = [
        f'{ruta.relative_to(SRC).as_posix()}:{f.lineno} {f.name} = util.{propias[h]}'
        for ruta in sorted((SRC / paquete).rglob('*.py')) if ruta != ruta_util
        for f in _funciones(ruta) if (h := _huella(f)) in propias
    ]
    assert not copias, copias


# --- Cerrojos de fichero (019:RF-4, 106:RF-2) -------------------------------------------------------------------

def _envejecer(ruta: Path, segundos: float) -> None:
    import os
    import time
    viejo = time.time() - segundos
    os.utime(ruta, (viejo, viejo))


def _restos(carpeta: Path) -> list[str]:
    return sorted(p.name for p in carpeta.iterdir() if '.muerto-' in p.name or p.name.endswith('.nuevo'))


def test_crear_exclusivo_nace_entero_y_no_pisa_al_que_existe(tmp_path):
    """019:RF-4, 106:RF-2 — el cerrojo aparece con el contenido entero; el segundo no lo pisa ni deja temporales."""
    ruta = tmp_path / 'c.lock'
    assert util.crear_exclusivo(ruta, '{"pid": 1}')
    assert not util.crear_exclusivo(ruta, '{"pid": 2}')
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': 1}
    assert _restos(tmp_path) == []


def test_sin_enlaces_duros_recurre_a_o_excl(tmp_path, monkeypatch):
    """019:RF-4, 106:RF-2 — un volumen sin enlaces duros (Drive, FAT) crea el cerrojo con O_EXCL, sin temporales."""
    def sin_enlaces(*_a, **_k):
        raise OSError(1, 'Función incorrecta')

    monkeypatch.setattr(util.os, 'link', sin_enlaces)
    ruta = tmp_path / 'c.lock'
    assert util.crear_exclusivo(ruta, '{"pid": 1}')
    assert not util.crear_exclusivo(ruta, '{"pid": 2}')
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': 1}
    assert _restos(tmp_path) == []
    # El respaldo sí tiene un instante a medias: uno ilegible y reciente se espera, uno antiguo se libera.
    ruta.write_text('{"pid"', encoding='utf-8')
    avisos = []
    assert util.intentar_cerrojo(ruta, '{"pid": 3}', valido=bool, aviso=avisos.append)[0] == 'espera'
    _envejecer(ruta, util.GRACIA_CERROJO_S + 5)
    assert util.intentar_cerrojo(ruta, '{"pid": 3}', valido=bool, aviso=avisos.append)[0] == 'tomado'
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': 3}
    assert any('se libera' in a for a in avisos) and _restos(tmp_path) == []


def test_cerrojo_ilegible_reciente_se_espera_y_antiguo_se_libera_con_aviso(tmp_path):
    """019:RF-4, 106:RF-2 — truncado y reciente: puede estar escribiéndose; truncado y antiguo: se libera diciéndolo."""
    ruta = tmp_path / 'c.lock'
    ruta.write_text('{"pid": 12', encoding='utf-8')
    avisos = []
    estado, motivo = util.intentar_cerrojo(ruta, '{"pid": 1}', valido=bool, aviso=avisos.append)
    assert estado == 'espera' and 'ilegible' in motivo and avisos == []
    assert ruta.read_text(encoding='utf-8') == '{"pid": 12'
    _envejecer(ruta, 3600)
    assert util.intentar_cerrojo(ruta, '{"pid": 1}', valido=bool, aviso=avisos.append) == ('tomado', None)
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': 1}
    assert len(avisos) == 1 and 'ilegible de hace' in avisos[0] and 'se libera' in avisos[0]
    assert '{"pid": 12' in avisos[0], 'el aviso guarda lo que era'
    assert _restos(tmp_path) == []


def test_dueno_legible_nunca_se_libera_por_antiguo(tmp_path):
    """019:RF-4, 106:RF-2 — un dueño legible lo decide quien llama; la antigüedad no lo libera."""
    ruta = tmp_path / 'c.lock'
    ruta.write_text('{"pid": 12}', encoding='utf-8')
    _envejecer(ruta, 3600)
    assert util.intentar_cerrojo(ruta, '{"pid": 1}', valido=bool, aviso=pytest.fail) == ('ocupado', {'pid': 12})
    assert ruta.read_text(encoding='utf-8') == '{"pid": 12}'


def test_dos_hilos_sobre_un_cerrojo_truncado_y_antiguo_solo_uno_lo_toma(tmp_path):
    """019:RF-4, 106:RF-2 — solo libera quien lo renombra; el otro ve al nuevo dueño. Veinte rondas."""
    import threading
    import time

    for ronda in range(20):
        ruta = tmp_path / f'c{ronda}.lock'
        ruta.write_text('{"pid": 12', encoding='utf-8')
        _envejecer(ruta, 3600)
        salida = threading.Barrier(2)
        resultados = []

        def tomar(n, ruta=ruta, salida=salida, resultados=resultados):
            salida.wait()
            while (r := util.intentar_cerrojo(ruta, json.dumps({'pid': n}), valido=bool,
                                             aviso=lambda _m: None))[0] in ('otra_vez', 'espera'):
                time.sleep(0.001)               # 'espera': no se dejó leer mientras el otro lo sustituía
            resultados.append((n, r[0]))

        hilos = [threading.Thread(target=tomar, args=(n,)) for n in (1, 2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(10)
        ganadores = [n for n, r in resultados if r == 'tomado']
        assert len(ganadores) == 1, resultados
        assert sorted(r for _n, r in resultados) == ['ocupado', 'tomado']
        assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': ganadores[0]}
    assert _restos(tmp_path) == []


def test_quien_llega_tarde_no_se_lleva_el_cerrojo_nuevo_del_otro(tmp_path, monkeypatch):
    """019:RF-4, 106:RF-2 — A y B ven el viejo; A lo libera y entra; B renombra el NUEVO de A: lo devuelve entero."""
    ruta = tmp_path / 'c.lock'
    ruta.write_text('{"pid": 12', encoding='utf-8')
    _envejecer(ruta, 3600)
    leer = util.leer_cerrojo

    def a_se_adelanta(r):
        visto = leer(r)                         # B ya observó el viejo (identidad y contenido)
        nuevo = tmp_path / 'a.nuevo'
        nuevo.write_text('{"pid": 1}', encoding='utf-8')
        util.os.replace(nuevo, ruta)            # A lo libera y publica el suyo antes de que B renombre
        return visto

    monkeypatch.setattr(util, 'leer_cerrojo', a_se_adelanta)
    avisos = []
    assert util.intentar_cerrojo(ruta, '{"pid": 2}', valido=bool, aviso=avisos.append)[0] == 'otra_vez'
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': 1}, 'el cerrojo de A sigue en su sitio'
    assert avisos == [] and _restos(tmp_path) == []


def test_si_otro_entra_mientras_se_devuelve_se_avisa_fuerte(tmp_path, monkeypatch):
    """019:RF-4, 106:RF-2 — robado uno vivo y ocupado el nombre antes de devolverlo: aviso grave, nada se pisa."""
    ruta = tmp_path / 'c.lock'
    ruta.write_text('{"pid": 12', encoding='utf-8')
    visto = util.identidad_fichero(ruta)
    ruta.unlink()
    ruta.write_text('{"pid": 1}', encoding='utf-8')     # A ya entró: otra identidad
    identidad = util.identidad_fichero

    def c_entra(r):
        if '.muerto-' in Path(r).name and not ruta.exists():
            ruta.write_text('{"pid": 3}', encoding='utf-8')
        return identidad(r)

    monkeypatch.setattr(util, 'identidad_fichero', c_entra)
    avisos = []
    assert util.apartar_cerrojo(ruta, visto, avisos.append) is None
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'pid': 3}
    assert len(avisos) == 1 and 'AVISO GRAVE' in avisos[0] and _restos(tmp_path) == []
