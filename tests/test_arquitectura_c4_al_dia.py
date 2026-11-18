"""El C4 profesional al día con el catálogo generado (090:RF-19).

``docs/architecture/workspace.dsl`` y su página interactiva se escriben a mano, salvo sus cifras: las pone
``tools/generar_c4.py --escribir`` desde ``docs/ARQUITECTURA_CATALOGO.md`` y el Estado de cada spec, y la puerta la
regenera con el catálogo. Aquí se exige su ``--comprobar``, se siembra cada defecto en una copia para que el
comprobador no sea ciego, y se mira lo que la orden no escribe: un componente por grupo de ``subsistemas.json``, la
página con los mismos componentes que el DSL y los enlaces fijados a una sola revisión con rutas que existen.
Ningún número va fijo en la prueba.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from apoyo import cargar_herramienta

ROOT = Path(__file__).resolve().parents[1]
DSL = ROOT / "docs" / "architecture" / "workspace.dsl"
HTML = ROOT / "docs" / "architecture" / "arquitectura-interactiva-c4.html"
MAPA = ROOT / "docs" / "architecture" / "subsistemas.json"
_COMPONENTE = re.compile(r'(\w+) = component "([^"]+)" "([^"]*)" "[^"]*" \{(.*?)\n {16}\}', re.S)
_URL = re.compile(r'https://github\.com/[^/\s"]+/[^/\s"]+/(?:tree|blob)/([0-9a-f]+)/([^"\s]+)')
_FICHEROS = ("docs/architecture/workspace.dsl", "docs/architecture/arquitectura-interactiva-c4.html",
             "docs/ARQUITECTURA_CATALOGO.md", "docs/architecture/subsistemas.json")


@pytest.fixture(scope="module")
def c4():
    return cargar_herramienta("generar_c4.py", "generar_c4_rf19")


@pytest.fixture
def copia(tmp_path):
    """El DSL, la página, el catálogo, el mapa y las specs en una raíz aparte, para sembrar defectos."""
    for rel in _FICHEROS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    for spec in (ROOT / "specs").glob("[0-9][0-9][0-9]-*/spec.md"):
        destino = tmp_path / "specs" / spec.parent.name / "spec.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec, destino)
    return tmp_path


def _componentes(texto: str) -> dict[str, dict]:
    salida = {}
    for ident, nombre, descripcion, cuerpo in _COMPONENTE.findall(texto):
        sub = re.search(r'"Subsistemas" "([^"]+)"', cuerpo)
        n = re.search(r"\((\d+) ficheros\)", descripcion)
        salida[ident] = {"nombre": nombre, "grupos": sub.group(1).split(" | ") if sub else [],
                         "ficheros": int(n.group(1)) if n else None}
    return salida


def test_090_rf19_las_cifras_del_c4_las_pone_generar_c4(c4, capsys):
    rc = c4.main(["--comprobar", "--raiz", str(ROOT)])
    assert rc == 0, f"el C4 no está al día con el catálogo: {capsys.readouterr().out.strip()}"


def test_090_rf19_el_comprobador_ve_cada_cifra_desviada_y_escribir_la_arregla(c4, copia, capsys):
    """Recuento tocado a mano, fichero nuevo en el catálogo, spec que vuelve a abrirse y catálogo roto."""
    dsl, html = copia / _FICHEROS[0], copia / _FICHEROS[1]
    original = dsl.read_text(encoding="utf-8")
    componentes = _componentes(original)
    elegido = next(c for c in componentes.values() if c["ficheros"])
    dsl.write_text(original.replace(f'({elegido["ficheros"]} ficheros)', f'({elegido["ficheros"] + 7} ficheros)', 1), encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 1
    assert "python tools/generar_c4.py --escribir" in capsys.readouterr().out
    assert c4.main(["--escribir", "--raiz", str(copia)]) == 0
    assert dsl.read_text(encoding="utf-8") == original

    # Un fichero más en un grupo del catálogo: su componente y su nodo en la página suben en uno.
    grupo = elegido["grupos"][0]
    catalogo = copia / _FICHEROS[2]
    texto = catalogo.read_text(encoding="utf-8")
    cabecera = f"### {grupo}\n\n| Fichero | Capa | Specs | Papel |\n| --- | --- | --- | --- |\n"
    assert cabecera in texto, f"el catálogo no trae la tabla del grupo {grupo}"
    catalogo.write_text(texto.replace(cabecera, cabecera + "| `sembrado.py` | Dom | 090 | Sembrado. |\n", 1), encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 1
    assert c4.main(["--escribir", "--raiz", str(copia)]) == 0
    nuevo = {c["nombre"]: c["ficheros"] for c in _componentes(dsl.read_text(encoding="utf-8")).values()}
    assert nuevo[elegido["nombre"]] == elegido["ficheros"] + 1
    assert f"label: '{elegido['nombre']}', tech: '{elegido['ficheros'] + 1} ficheros'" in html.read_text(encoding="utf-8")

    # Una spec cumplida que se reabre: su elemento vuelve a «en implementación», con su propiedad «Estado».
    cumplidas = [s for s in re.findall(r'"Spec" "(\d{3})"', original)
                 if re.search(r"^Estado: *cumplida", next((copia / "specs").glob(f"{s}-*/spec.md")).read_text(encoding="utf-8"), re.M)]
    assert cumplidas, "ningún elemento del DSL cita una spec cumplida: el sembrado no puede probar la marca"
    spec = next((copia / "specs").glob(f"{cumplidas[0]}-*/spec.md"))
    spec.write_text(re.sub(r"^Estado: *cumplida", "Estado: aprobada", spec.read_text(encoding="utf-8"), count=1, flags=re.M),
                    encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 1
    assert c4.main(["--escribir", "--raiz", str(copia)]) == 0
    reabierto = dsl.read_text(encoding="utf-8")
    bloque = re.search(rf'tags "([^"]*)"\s*properties \{{([^}}]*)"Spec" "{cumplidas[0]}"', reabierto)
    assert bloque and "en implementación" in bloque.group(1) and '"Estado" "en implementación"' in bloque.group(2)
    # La leyenda da las specs como lista («107, 109») o, si son seguidas, como rango («107 a 111»).
    leyenda = re.search(r"en implementación \(specs ([^)]*)\)", html.read_text(encoding="utf-8")).group(1)
    rango = re.fullmatch(r"(\d+) a (\d+)", leyenda.strip())
    marcadas = set(range(int(rango[1]), int(rango[2]) + 1)) if rango else {int(x) for x in re.findall(r"\d+", leyenda)}
    assert int(cumplidas[0]) in marcadas, (cumplidas[0], leyenda)

    # Sin la sección de ficheros no inventa nada: sale con 2 y dice qué falta.
    catalogo.write_text("# catálogo sin ficheros\n", encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 2
    assert "## Ficheros" in capsys.readouterr().out


def test_090_rf19_cada_subsistema_en_un_solo_componente_del_c4():
    grupos = [g["titulo"] for g in json.loads(MAPA.read_text(encoding="utf-8"))["grupos"]]
    componentes = _componentes(DSL.read_text(encoding="utf-8"))
    asignados = Counter(g for c in componentes.values() for g in c["grupos"])
    assert sorted(set(grupos) - set(asignados)) == [], "grupos de subsistemas.json sin componente en workspace.dsl"
    assert sorted(g for g, n in asignados.items() if n > 1) == [], "grupos en más de un componente"
    assert sorted(set(asignados) - set(grupos)) == [], "«Subsistemas» que no es ningún grupo de subsistemas.json"
    assert sorted(c["nombre"] for c in componentes.values() if not c["grupos"]) == [], "componentes sin «Subsistemas»"


def test_090_rf19_pagina_interactiva_con_los_componentes_del_dsl():
    nodos = set(re.findall(r"^ +c[A-Z]\w*: \{ label: '([^']+)'", HTML.read_text(encoding="utf-8"), flags=re.M))
    dsl = {c["nombre"] for c in _componentes(DSL.read_text(encoding="utf-8")).values()}
    assert sorted(dsl - nodos) == [], f"componentes del DSL que faltan en la página: {sorted(dsl - nodos)}"
    assert sorted(nodos - dsl) == [], f"componentes de la página que no están en el DSL: {sorted(nodos - dsl)}"


def test_090_rf19_enlaces_fijados_a_una_sola_revision_con_rutas_que_existen():
    texto, html = DSL.read_text(encoding="utf-8"), HTML.read_text(encoding="utf-8")
    enlaces = _URL.findall(texto)
    assert enlaces, "workspace.dsl sin enlaces a una revisión"
    revisiones = sorted({r for r, _ in enlaces})
    assert len(revisiones) == 1 and len(revisiones[0]) == 40, f"revisiones fijadas: {revisiones}"
    assert sorted({ruta for _, ruta in enlaces if not (ROOT / ruta).exists()}) == [], "rutas enlazadas que no existen"
    corta = revisiones[0][:8]
    assert f"en la revisión {corta}" in texto.split("\n", 1)[0]
    assert f"(spec 090), revisión {corta}." in html
    # «output/web» es la carpeta de los espacios que crea el programa al correr; no está en el repositorio.
    accesos = sorted({p for p in re.findall(r"path: '([^']+)'", html) if not p.startswith(("http", "output/"))})
    assert [p for p in accesos if not (ROOT / p).exists()] == [], "accesos de la página que no existen"
