"""001:RF-5 — los JSON del paquete se publican con la escritura atómica única.

``convertersmartgrid.util.write_json_atomic`` y ``publicar_duradero`` preparan el contenido fuera del destino, lo
sincronizan y lo sustituyen con ``replace``: un corte a mitad deja el fichero anterior entero. Una escritura directa
``ruta.write_text(json.dumps(...))`` deja un JSON truncado que la web, el lote o el siguiente entrenamiento leen roto.

La comprobación recorre ``src/convertersmartgrid`` con ``ast`` y falla ante cualquier ``write_text``/``write_bytes`` cuyo
contenido salga de ``json.dumps`` y no figure en ``EXCEPCIONES``. Falla también si una excepción ya no aparece o aparece
otro número de veces: la lista solo puede bajar, y cada baja se anota aquí.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

PAQUETE = Path(__file__).resolve().parents[1] / 'src' / 'convertersmartgrid'

_VERSION_NUEVA = ('carpeta de versión o candidato recién creada; nadie la lee hasta que la publica su puntero '
                  '(promovido.json, ultimo_checkpoint.json o el registro) tras la relectura')

#: ``'ruta/relativa.py::Funcion.anidada': (veces, motivo)``. Solo se añade una con un motivo de los de 001:RF-5:
#: un temporal que después se publica con ``replace``, un fichero dentro de una carpeta de staging o de versión
#: que se publica entera, o un módulo que no puede importar ``util`` por su capa o por un ciclo.
EXCEPCIONES: dict[str, tuple[int, str]] = {
    'adaptadores/entrada/vnr/exporters/dgs.py::DgsExporter.export':
        (2, 'informe y manifiesto dentro de la carpeta de staging_publicacion, que se publica entera con el DGS'),
    'asistente/clasificador.py::guardar_candidato': (2, _VERSION_NUEVA),
    'asistente/clasificador_vectores.py::guardar': (2, _VERSION_NUEVA),
    'asistente/destilacion_integral.py::_guardar_alumno': (1, _VERSION_NUEVA + ' (mkdir exist_ok=False)'),
    'asistente/destilacion_integral.py::entrenar_destilacion':
        (1, 'readback.json dentro de la carpeta del alumno candidato, antes de su decisión'),
    'asistente/evidencias_web.py::custodiar_trabajo':
        (1, 'temporal de staging_publicacion que registrar_evidencia copia de forma exclusiva (open "xb")'),
    'asistente/llm_destilacion.py::entrenar_epoca.guardar':
        (1, 'estado.json dentro del checkpoint recién creado; lo publica ultimo_checkpoint.json, atómico'),
    'asistente/llm_destilacion.py::exportar_fusionado':
        (2, ('config e índice de pesos en la carpeta de exportación recién creada; la valida exportacion.json, '
             'atómico y escrito el último')),
    'asistente/llm_destilacion.py::sellar_particiones':
        (1, 'particiones .jsonl en la carpeta recién creada; las custodia por hash dataset_manifest.json, atómico'),
    'asistente/transformer.py::guardar_pesos': (1, _VERSION_NUEVA),
    'digital_twin/adaptador_neuralforecast.py::AdaptadorNeuralForecast.guardar':
        (1, 'dentro del TemporaryDirectory que _empaquetar comprime en un zip, su único llamador'),
    'digital_twin/oraculo.py::entrenar': (1, 'readback.json del candidato, antes de _decidir_promocion'),
    'digital_twin/oraculo.py::guardar': (1, _VERSION_NUEVA),
    'digital_twin/oraculo.py::guardar_y_reabrir': (1, 'readback.json del candidato, que no se promueve aquí'),
    'digital_twin/temporal.py::GemeloGRUMultihorizonte.guardar':
        (1, 'dentro del TemporaryDirectory que _empaquetar comprime en un zip, su único llamador'),
    'digital_twin/temporal_entrenamiento.py::comparar_pronosticos':
        (1, 'ajustes.json dentro de candidato_<uuid>, que se registra entero como artefacto'),
    'libro_informe.py::rellenar_con_excel':
        (1, 'plan.json en un TemporaryDirectory que solo lee el guion de Excel'),
    'runtime_paths.py::temporal_administrado':
        (2, ('owner.json de la carpeta privada del temporal; util importa runtime_paths (ciclo) y '
             'publicar_duradero se apoya en este mismo temporal')),
    'web/operaciones_lentas.py::preparar_zip':
        (2, 'owner.json de la carpeta privada csg-job-* de la descarga, el mismo protocolo que temporal_administrado'),
    # services.py (integrador, H14 2026-11-14): las dos que quedan son excepciones legítimas.
    'web/services.py::perfil_guardar': (1, 'temporal de prueba en TemporaryDirectory: se valida y se descarta; lo publicado va por write_json_atomic'),
    'web/services.py::pide_custodiar_fuentes': (1, 'dentro de la carpeta stage que se publica entera con rename'),
}


def _es_dumps(nodo: ast.AST) -> bool:
    if not isinstance(nodo, ast.Call):
        return False
    funcion = nodo.func
    return ((isinstance(funcion, ast.Attribute) and funcion.attr == 'dumps'
             and isinstance(funcion.value, ast.Name) and funcion.value.id == 'json')
            or (isinstance(funcion, ast.Name) and funcion.id == 'dumps'))


_AMBITOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _es_dump(nodo: ast.AST) -> bool:
    """``json.dump(obj, f)`` o ``dump(obj, f)``: escribe en un fichero ya abierto."""
    if not isinstance(nodo, ast.Call):
        return False
    funcion = nodo.func
    return ((isinstance(funcion, ast.Attribute) and funcion.attr == 'dump'
             and isinstance(funcion.value, ast.Name) and funcion.value.id == 'json')
            or (isinstance(funcion, ast.Name) and funcion.id == 'dump'))


def _abre_para_escribir(nodo: ast.AST | None) -> bool:
    """``open(p, 'w')``, ``io.open(p, 'a')``, ``os.fdopen(fd, 'w')`` o ``Path.open('x')``: modo con w, a, x o +."""
    if not isinstance(nodo, ast.Call):
        return False
    funcion = nodo.func
    if ((isinstance(funcion, ast.Name) and funcion.id == 'open')
            or (isinstance(funcion, ast.Attribute) and funcion.attr == 'fdopen')):
        posicion = 1
    elif isinstance(funcion, ast.Attribute) and funcion.attr == 'open':
        modulo = isinstance(funcion.value, ast.Name) and funcion.value.id in ('io', 'codecs', 'builtins')
        posicion = 1 if modulo else 0                                   # Path.open(modo)
    else:
        return False
    modo = nodo.args[posicion] if len(nodo.args) > posicion else next(
        (k.value for k in nodo.keywords if k.arg == 'mode'), None)
    return (isinstance(modo, ast.Constant) and isinstance(modo.value, str)
            and any(letra in modo.value for letra in 'wax+'))


def _propios(ambito: ast.AST):
    """Los nodos del ámbito sin entrar en las funciones ni clases anidadas, que se cuentan aparte."""
    pendientes = list(ast.iter_child_nodes(ambito))
    while pendientes:
        nodo = pendientes.pop()
        yield nodo
        if not isinstance(nodo, _AMBITOS):
            pendientes.extend(ast.iter_child_nodes(nodo))


def _directas_del_ambito(ambito: ast.AST) -> int:
    nodos = list(_propios(ambito))
    abiertos = set()
    for nodo in nodos:
        if isinstance(nodo, (ast.With, ast.AsyncWith)):
            abiertos.update(item.optional_vars.id for item in nodo.items
                            if isinstance(item.optional_vars, ast.Name) and _abre_para_escribir(item.context_expr))
        elif isinstance(nodo, ast.Assign) and _abre_para_escribir(nodo.value):
            abiertos.update(t.id for t in nodo.targets if isinstance(t, ast.Name))
    total = 0
    for nodo in nodos:
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr in ('write_text', 'write_bytes') and nodo.args
                and any(_es_dumps(n) for n in ast.walk(nodo.args[0]))):
            total += 1
        elif _es_dump(nodo):
            destino = nodo.args[1] if len(nodo.args) > 1 else next(
                (k.value for k in nodo.keywords if k.arg == 'fp'), None)
            if (isinstance(destino, ast.Name) and destino.id in abiertos) or _abre_para_escribir(destino):
                total += 1
    return total


def escrituras_directas(raiz: Path = PAQUETE) -> Counter[str]:
    """Cuántas escrituras JSON directas hay en cada función de ``raiz``.

    Cuenta ``write_text``/``write_bytes`` de un ``json.dumps`` y ``json.dump(obj, f)`` con ``f`` abierto para escribir
    por ``open``, ``os.fdopen`` o ``Path.open``: en un ``with``, asignado o pasado directamente.
    """
    encontradas: Counter[str] = Counter()
    for fichero in sorted(raiz.rglob('*.py')):
        relativo = fichero.relative_to(raiz).as_posix()
        arbol = ast.parse(fichero.read_text(encoding='utf-8-sig'), filename=str(fichero))
        pendientes: list[tuple[ast.AST, tuple[str, ...]]] = [(arbol, ())]
        while pendientes:
            ambito, pila = pendientes.pop()
            if n := _directas_del_ambito(ambito):
                encontradas[f"{relativo}::{'.'.join(pila) or '<módulo>'}"] += n
            pendientes.extend((hijo, (*pila, hijo.name)) for hijo in _propios(ambito) if isinstance(hijo, _AMBITOS))
    return encontradas


_MODULO_DE_PRUEBA = '''\
import json, os
from convertersmartgrid.util import publicar_duradero, write_json_atomic
def una(p, d):
    p.write_text(json.dumps(d), encoding="utf-8")
class C:
    def otra(self, p, d):
        p.write_text(
            json.dumps(d, indent=2) + "\\n", encoding="utf-8")
        p.write_bytes(json.dumps(d).encode())
def con_open(p, d, fd):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f)
    with p.open("a") as g, open(p) as lectura:
        json.dump(d, g)
        json.load(lectura)
    h = open(p, mode="wb")
    json.dump(d, h)
    with os.fdopen(fd, "x") as k:
        json.dump(d, fp=k)
    json.dump(d, open(p, "w"))
def solo_lee(p, d, f):
    with open(p) as r, p.open("r") as s:
        json.dump(d, f)
        json.dumps([json.load(r), json.load(s)])
def buena(p, d):
    write_json_atomic(p, d)
    publicar_duradero(p, json.dumps(d))
    p.write_text("texto", encoding="utf-8")
    def anidada(q):
        with q.open("w") as f:
            json.dump(d, f)
'''


def test_detector_reconoce_las_formas_directas(tmp_path):
    """001:RF-5 — el detector ve write_text/write_bytes de un json.dumps y json.dump a un fichero abierto para
    escribir (with, asignado, os.fdopen, Path.open o directo), y no la publicación atómica ni las lecturas."""
    (tmp_path / 'm.py').write_text(_MODULO_DE_PRUEBA, encoding='utf-8')
    assert escrituras_directas(tmp_path) == Counter({'m.py::una': 1, 'm.py::C.otra': 2, 'm.py::con_open': 5,
                                                     'm.py::buena.anidada': 1})


def test_ningun_json_se_escribe_fuera_de_la_escritura_atomica_unica():
    """001:RF-5 — toda escritura directa nueva falla; las excepciones listadas siguen existiendo tal cual."""
    encontradas = escrituras_directas()
    nuevas = {k: n for k, n in encontradas.items() if k not in EXCEPCIONES}
    assert not nuevas, ('JSON escrito sin write_json_atomic/publicar_duradero (001:RF-5): '
                        f'{sorted(nuevas.items())}')
    retiradas = sorted(k for k in EXCEPCIONES if k not in encontradas)
    assert not retiradas, f'Excepciones que ya no existen; quítelas de EXCEPCIONES: {retiradas}'
    distintas = {k: (encontradas[k], EXCEPCIONES[k][0]) for k in EXCEPCIONES
                 if k in encontradas and encontradas[k] != EXCEPCIONES[k][0]}
    assert not distintas, f'Cambió el número de escrituras directas (hallado, listado): {distintas}'
    assert all(motivo.strip() for _veces, motivo in EXCEPCIONES.values())
