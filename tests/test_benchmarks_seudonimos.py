"""Spec 112: patrones de privacidad del núcleo y seudónimos del benchmark (112:RF-2, RF-4).

Los patrones que tapaban rutas, correos, IP, códigos y nombres vivían solo en el paquete de soporte (086:RF-42). El
benchmark necesita los mismos, y copiarlos dejaría dos reglas que se separan con el tiempo (P5): están en
``privacidad.py``, y soporte los importa sin cambiar lo que hace.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from convertersmartgrid.dominio import privacidad as PR
from convertersmartgrid.presentacion.web import soporte as SP

# Líneas como las que deja el registro de la web: cada una con algo que identifica a alguien.
LINEAS = [
    r'No se pudo leer C:\Usuarios\operador\Entregas\red_ED.txt: falta la columna',
    'Fallo al abrir /home/ana/redes/norte/red.txt, se reintenta',
    'Avisar a jefe.redes@empresa-norte.com.pe del alimentador NO-101',
    'Servidor 10.20.30.40 no responde; el local 127.0.0.1 sí',
    'El cliente «Agrícola San Pedro» y la SET "Norte Grande" con SED AB1234',
    'Mensaje sin nada que tapar: 42 alimentadores, 3,5 MW',
]


def test_los_patrones_viven_en_el_nucleo_y_soporte_los_importa():
    """112:RF-2, RF-4 — una sola vía (P5): soporte usa los patrones y la función de ``privacidad``."""
    for nombre in ('RUTA_WINDOWS', 'RUTA_POSIX', 'CORREO', 'IP', 'CODIGO', 'ENTRECOMILLADO'):
        assert isinstance(getattr(PR, nombre), re.Pattern), nombre
    assert SP.anonimizar is PR.anonimizar
    fuente = Path(SP.__file__).read_text(encoding='utf-8')
    assert 're.compile(' not in fuente, 'soporte ya no define sus propios patrones'


@pytest.mark.parametrize('linea', LINEAS)
def test_anonimizar_conserva_el_comportamiento_de_soporte(linea):
    """112:RF-2 — mover los patrones no cambia el paquete de soporte (086:RF-42): misma salida, línea por línea."""
    esperado = {
        # Los dos puntos que siguen a la ruta son del mensaje, no de la ruta (086:RF-42, corregido en la 112 T1).
        LINEAS[0]: 'No se pudo leer <ruta>: falta la columna',
        LINEAS[1]: 'Fallo al abrir <ruta>, se reintenta',
        LINEAS[2]: 'Avisar a <correo> del alimentador <codigo>',
        LINEAS[3]: 'Servidor <ip> no responde; el local 127.0.0.1 sí',
        LINEAS[4]: 'El cliente <texto> y la SET <texto> con SED <codigo>',
        LINEAS[5]: LINEAS[5],
    }[linea]
    assert PR.anonimizar(linea) == esperado


def test_los_terminos_dados_se_tapan_del_mas_largo_al_mas_corto():
    """112:RF-2 — «Empresa Norte» se tapa entera antes que «Norte», sin importar mayúsculas."""
    salida = PR.anonimizar('empresa norte opera en Norte y en NORTE', {'Norte', 'Empresa Norte'})
    assert salida == '<nombre> opera en <nombre> y en <nombre>'


def test_terminos_del_perfil_lee_todos_los_textos(tmp_path):
    """112:RF-4 — los textos del perfil de la empresa sirven para buscar fugas; los cortos y los que no son texto, no."""
    perfil = tmp_path / 'perfil.json'
    perfil.write_text(json.dumps({'empresa': 'Empresa Norte', 'sed': {'prefijo': 'NX', 'zona': 'Valle Alto'},
                                  'alimentadores': ['NO-101', 'NO-102'], 'escala': 13.7}), encoding='utf-8')
    assert PR.terminos_del_perfil(perfil) == {'Empresa Norte', 'Valle Alto', 'NO-101', 'NO-102'}


def test_sin_perfil_no_hay_terminos_salvo_que_se_pida_uno(tmp_path):
    """112:RF-4 — si la empresa no tiene perfil, no hay términos que tapar; pero si se pidió uno y no está, se dice."""
    assert PR.terminos_del_perfil(tmp_path / 'no_existe.json') == set()
    with pytest.raises(PR.PerfilIlegible, match=r'no_existe\.json.*no existe'):
        PR.terminos_del_perfil(tmp_path / 'no_existe.json', obligatorio=True)


@pytest.mark.parametrize('contenido, causa', [
    (b'{esto no es json', 'no es JSON'),
    (b'{"empresa": "Empresa Norte",', 'no es JSON'),
    (b'{"empresa": "Empresa \xd1orte"}', 'UTF-8'),
    (b'', 'no es JSON'),
], ids=['basura', 'cortado', 'otra_codificacion', 'vacio'])
def test_un_perfil_ilegible_falla_con_su_causa_y_no_da_un_conjunto_vacio(tmp_path, contenido, causa):
    """112:RF-4 — un perfil que existe y no se puede leer no devuelve «ningún término»: eso dejaría pasar en silencio el
    nombre de la empresa. Falla con un error que nombra el fichero y la causa, para que quien lo pide decida."""
    roto = tmp_path / 'roto.json'
    roto.write_bytes(contenido)
    with pytest.raises(PR.PerfilIlegible, match='roto.json') as exc:
        PR.terminos_del_perfil(roto)
    assert causa in str(exc.value)
    assert isinstance(exc.value, ValueError) and exc.value.ruta == roto


def test_un_perfil_que_no_se_puede_abrir_falla(tmp_path):
    """112:RF-4 — una carpeta en lugar del fichero (o un fichero sin permiso) tampoco da un conjunto vacío."""
    carpeta = tmp_path / 'perfil.json'
    carpeta.mkdir()
    with pytest.raises(PR.PerfilIlegible, match='no se puede leer'):
        PR.terminos_del_perfil(carpeta)


def test_soporte_con_el_perfil_ilegible_no_filtra_de_menos(tmp_path):
    """112:RF-4, 086:RF-42 — si el perfil no se lee, soporte no sabe qué nombres tapar: el paquete sale igual, pero sin
    los registros ni los detalles del diagnóstico, y el LEAME dice por qué. Nunca con los nombres a la vista."""
    import zipfile
    registros = tmp_path / 'registros'
    registros.mkdir()
    (registros / 'web.log').write_text('Conectado a la base de Empresa Norte\n', encoding='utf-8')
    perfil = tmp_path / 'perfil.json'
    perfil.write_text('{"empresa": "Empresa Norte",', encoding='utf-8')
    informe = {'comprobaciones': [{'clave': 'c', 'nombre': 'Carpeta', 'ok': False, 'obligatoria': True,
                                   'detalle': 'Falta la carpeta de Empresa Norte', 'arreglo': 'Créela'}]}
    ruta = SP.crear_paquete(tmp_path / 'salida', carpeta_registros=registros, ruta_perfil=perfil, informe=informe)
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
        textos = {n: z.read(n).decode('utf-8') for n in nombres}
    assert not [n for n in nombres if n.startswith('registros/')]
    assert all('Empresa Norte' not in t for t in textos.values())
    assert 'perfil' in textos['LEAME.txt'] and 'ilegible' in textos['LEAME.txt']
    detalle = json.loads(textos['doctor.json'])['comprobaciones'][0]
    assert detalle['nombre'] == 'Carpeta' and detalle['ok'] is False
    assert json.loads(textos['perfil_forma.json'])['legible'] is False


def test_soporte_con_el_perfil_legible_sigue_igual(tmp_path):
    """086:RF-42 — con el perfil bien, los registros van, con los términos de la empresa tapados."""
    import zipfile
    registros = tmp_path / 'registros'
    registros.mkdir()
    (registros / 'web.log').write_text('Conectado a la base de Empresa Norte\n', encoding='utf-8')
    perfil = tmp_path / 'perfil.json'
    perfil.write_text(json.dumps({'empresa': 'Empresa Norte'}), encoding='utf-8')
    ruta = SP.crear_paquete(tmp_path / 'salida', carpeta_registros=registros, ruta_perfil=perfil,
                            informe={'comprobaciones': []})
    with zipfile.ZipFile(ruta) as z:
        log = z.read('registros/web.log').decode('utf-8')
        leame = z.read('LEAME.txt').decode('utf-8')
    assert log == 'Conectado a la base de <nombre>\n'
    assert 'ilegible' not in leame


@pytest.mark.parametrize('linea,esperado', [
    (r'Falta D:\datos\a.txt: no existe', 'Falta <ruta>: no existe'),
    (r'Unidad C:\ sin espacio', 'Unidad <ruta> sin espacio'),
    (r'Copia en \\servidor\compartido\redes\a.mdb: lista', 'Copia en <ruta>: lista'),
    (r'Copia en \\servidor\compartido\redes\a.mdb lista', 'Copia en <ruta> lista'),
])
def test_la_ruta_de_windows_no_se_come_los_dos_puntos_del_mensaje(linea, esperado):
    """112:RF-2; 086:RF-42 — «ruta: error» conserva «: error»; la unidad sola y las UNC se tapan enteras.

    Antes, la clase final del patrón admitía «:» y se comía el separador: el mensaje perdía su sentido.
    """
    assert PR.anonimizar(linea) == esperado


# --------------------------------------------------------------------------- T2: seudónimos (112:RF-2)

def _codigos_sorteados(semilla: int, n: int) -> list[str]:
    """Códigos con forma de red real (letras y cifras), sin relación con ninguna empresa."""
    import random
    r = random.Random(semilla)
    return [f'{r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")}{r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")}{r.randint(1, 999):03d}'
            for _ in range(n)]


def test_mismo_identificador_mismo_seudonimo_en_los_tres_ficheros():
    """112:RF-2 — un cliente de la CARGA y el mismo de la RED reciben el mismo seudónimo: el trío sigue cuadrando."""
    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa
    codigos = sorted(set(_codigos_sorteados(7, 40)))
    mapa = Mapa(semilla=123)
    for c in codigos:              # como si se leyera la RED…
        mapa.registrar('cliente', c)
    for c in reversed(codigos):    # …y luego la CARGA, en otro orden
        mapa.registrar('cliente', c)
    mapa.congelar()
    vistos = [mapa('cliente', c) for c in codigos]
    assert vistos == [mapa('cliente', c) for c in codigos]
    assert len(set(vistos)) == len(codigos), 'dos originales distintos nunca comparten seudónimo'
    assert all(s.startswith('BC') for s in vistos)
    assert not set(vistos) & set(codigos)


def test_los_tipos_no_se_mezclan_y_el_orden_original_no_se_filtra():
    """112:RF-2 — el número del seudónimo sale de una permutación sorteada, no del orden alfabético del original."""
    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa
    codigos = sorted(set(_codigos_sorteados(11, 60)))
    mapa = Mapa(semilla=5)
    for c in codigos:
        mapa.registrar('nodo', c)
        mapa.registrar('tramo', c)
    mapa.congelar()
    nodos = [mapa('nodo', c) for c in codigos]
    assert all(s.startswith('BN') for s in nodos) and all(mapa('tramo', c).startswith('BT') for c in codigos)
    assert nodos != sorted(nodos), 'con el orden alfabético se recuperaría el original por diccionario'


def test_misma_semilla_mismos_seudonimos_y_otra_semilla_otros():
    """112:RF-2 — reproducible con la misma semilla, sea cual sea el orden de registro; con otra, cambia."""
    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa
    codigos = sorted(set(_codigos_sorteados(3, 30)))

    def tabla(semilla, orden):
        m = Mapa(semilla=semilla)
        for c in orden:
            m.registrar('equipo', c)
        m.congelar()
        return [m('equipo', c) for c in codigos]

    assert tabla(9, codigos) == tabla(9, list(reversed(codigos)))
    assert tabla(9, codigos) != tabla(10, codigos)


def test_el_mapa_nunca_se_escribe():
    """112:RF-2 — el mapa vive solo en memoria: no se serializa ni se puede volcar a JSON."""
    import pickle

    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa
    mapa = Mapa(semilla=1)
    mapa.registrar('red', 'XX001')
    mapa.congelar()
    with pytest.raises(TypeError, match='vive solo en memoria'):
        pickle.dumps(mapa)
    with pytest.raises(TypeError):
        json.dumps(mapa)
    assert 'XX001' not in repr(mapa)


def test_valores_vacios_y_errores_de_uso():
    """112:RF-2 — lo vacío no se seudonimiza; un tipo desconocido o un valor sin registrar es un error claro."""
    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa
    mapa = Mapa(semilla=1)
    mapa.registrar('red', '')
    mapa.registrar('red', None)
    mapa.registrar('red', 'XX001')
    with pytest.raises(ValueError, match='tipo'):
        mapa.registrar('marciano', 'X')
    mapa.congelar()
    assert mapa('red', '') == '' and mapa('red', None) is None
    with pytest.raises(KeyError):
        mapa('red', 'YY999')
    with pytest.raises(RuntimeError):
        mapa.registrar('red', 'ZZ1')


def test_coordenadas_a_un_origen_neutro_conservan_las_distancias():
    """112:RF-2, RF-3 — se pierde dónde está la red (centroide al origen neutro, giro sorteado), no su forma."""
    import math
    import random

    from convertersmartgrid.dominio.benchmarks.seudonimos import (
        ORIGEN_NEUTRO,
        transformar_coordenadas,
    )
    r = random.Random(4)
    puntos = [(430000 + r.uniform(0, 9000), 8440000 + r.uniform(0, 9000)) for _ in range(50)]
    salida = transformar_coordenadas(puntos, semilla=77)
    cx = sum(x for x, _ in salida) / len(salida)
    cy = sum(y for _, y in salida) / len(salida)
    assert math.isclose(cx, ORIGEN_NEUTRO[0], abs_tol=1e-6) and math.isclose(cy, ORIGEN_NEUTRO[1], abs_tol=1e-6)
    for i in range(0, 50, 7):
        for j in range(1, 50, 11):
            d0 = math.dist(puntos[i], puntos[j])
            assert math.isclose(math.dist(salida[i], salida[j]), d0, rel_tol=1e-9, abs_tol=1e-6)
    assert transformar_coordenadas(puntos, semilla=77) == salida, 'misma semilla, mismos números'
    assert transformar_coordenadas(puntos, semilla=78) != salida
    assert transformar_coordenadas([], semilla=1) == []
