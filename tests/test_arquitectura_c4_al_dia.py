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
             "docs/ARQUITECTURA_CATALOGO.md", "docs/architecture/subsistemas.json", "docs/architecture/pseudocodigo.md")
PSEUDO = ROOT / "docs" / "architecture" / "pseudocodigo.md"


@pytest.fixture(scope="module")
def c4():
    return cargar_herramienta("generar_c4.py", "generar_c4_rf19")


@pytest.fixture
def copia(tmp_path):
    """El DSL, la página, el catálogo, el mapa y las specs en una raíz aparte, para sembrar defectos."""
    for rel in _FICHEROS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    # 090:RF-23: el comprobador mira que cada función citada por el pseudocódigo exista; la copia lleva esos ficheros.
    for rel in {r for r, _ in re.findall(r"((?:src|tools)/[\w/]+\.py)::(\w+)", PSEUDO.read_text(encoding="utf-8"))}:
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


# ====================================================================== 090:RF-20 a RF-26
def _ast_de(ruta: str):
    import ast
    return ast.parse((ROOT / ruta).read_text(encoding="utf-8"))


def _motores_del_codigo() -> list[str]:
    import ast
    for nodo in _ast_de("src/convertersmartgrid/adaptadores/digital_twin/motores_flujo.py").body:
        if isinstance(nodo, ast.AnnAssign) and getattr(nodo.target, "id", None) == "MOTORES":
            return [ast.literal_eval(k) for k in nodo.value.keys]
    raise AssertionError("motores_flujo.py sin MOTORES")


def _carriles_del_codigo() -> list[str]:
    import ast
    for nodo in _ast_de("src/convertersmartgrid/presentacion/web/jobs.py").body:
        if isinstance(nodo, ast.Assign) and getattr(nodo.targets[0], "id", None) == "LANES":
            return list(ast.literal_eval(nodo.value))
    raise AssertionError("jobs.py sin LANES")


def test_090_rf20_cada_motor_abierto_en_el_dsl_y_en_la_pagina():
    """090:RF-20 — un «Motor <nombre>» y un nodo motor_<nombre> por cada motor de MOTORES, y el contenedor relacionado."""
    dsl, html = DSL.read_text(encoding="utf-8"), HTML.read_text(encoding="utf-8")
    motores = _motores_del_codigo()
    assert motores, "MOTORES vacío"
    assert sorted(m for m in motores if f'"Motor {m}" ' not in dsl) == []
    assert sorted(m for m in motores if not re.search(rf"^\s*motor_{m}: \{{ label:", html, re.M)) == []
    for usuario in ("calibration", "oracle", "pit", "vad", "gisEditor", "twin"):
        assert re.search(rf"^\s*{usuario} -> flowEngines ", dsl, re.M), f"{usuario} no usa los motores abiertos en el DSL"
    assert 'data-view="engines"' in html


@pytest.mark.parametrize("prefijo, nombre, pagina", [("Motor", "newton", "motor"), ("Carril", "red", "lane")])
def test_090_rf20_rf22_el_comprobador_nombra_el_que_falta_o_sobra(c4, copia, capsys, prefijo, nombre, pagina):
    """090:RF-20, RF-22 — sin su propiedad en el DSL, sin su nodo en la página o con uno de más, --comprobar sale con 2."""
    dsl, html = copia / _FICHEROS[0], copia / _FICHEROS[1]
    original_dsl, original_html = dsl.read_text(encoding="utf-8"), html.read_text(encoding="utf-8")
    sin = re.sub(rf'^\s*"{prefijo} {nombre}" .*\n', "", original_dsl, count=1, flags=re.M)
    assert sin != original_dsl
    dsl.write_text(sin, encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 2
    salida = capsys.readouterr().out
    assert f"'{nombre}'" in salida and "faltan" in salida
    dsl.write_text(original_dsl.replace(f'"{prefijo} {nombre}" ', f'"{prefijo} fantasma" "x"\n                    "{prefijo} {nombre}" ', 1),
                   encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 2
    assert "'fantasma'" in capsys.readouterr().out
    dsl.write_text(original_dsl, encoding="utf-8")
    html.write_text(re.sub(rf"^\s*{pagina}_{nombre}: \{{ label:.*\n", "", original_html, count=1, flags=re.M), encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 2
    assert f"'{nombre}'" in capsys.readouterr().out


def test_090_rf21_vnr_de_la_guia_aparte_del_vnr_gis_y_del_vad():
    """090:RF-21 — tres contenedores distintos, cada uno con su grupo de subsistemas y su vista de componentes."""
    dsl = DSL.read_text(encoding="utf-8")
    grupos = {c["nombre"]: c["grupos"] for c in _componentes(dsl).values()}
    assert grupos["VNR de la Guía"] == ["Motor: VNR de la Guía 232-2017 (spec 108)"]
    assert grupos["VAD"] == ["Motor: VAD (estudio de costos de la empresa modelo, spec 108)"]
    assert grupos["VNR-GIS"] == ["VNR-GIS: `adaptadores/entrada/vnr/`"]
    for contenedor, vista in (("vnrGuia", "Componentes-VNR-Guia"), ("vad", "Componentes-VAD"),
                              ("flowEngines", "Componentes-Motores-abiertos")):
        assert re.search(rf"^\s*{contenedor} = container ", dsl, re.M)
        assert f'component {contenedor} "{vista}"' in dsl
    mapa = json.loads(MAPA.read_text(encoding="utf-8"))["grupos"]
    vnr_guia = next(g for g in mapa if g["titulo"].startswith("Motor: VNR de la Guía"))["ficheros"]
    vad = next(g for g in mapa if g["titulo"].startswith("Motor: VAD"))["ficheros"]
    assert vnr_guia and all("vnr" in f for f in vnr_guia) and not any("vnr" in f for f in vad)


def test_090_rf22_cada_carril_del_codigo_en_el_dsl_y_en_la_vista_carriles():
    """090:RF-22 — un «Carril <nombre>» con lo que corre y un nodo lane_<nombre> en la vista «Carriles»."""
    dsl, html = DSL.read_text(encoding="utf-8"), HTML.read_text(encoding="utf-8")
    carriles = _carriles_del_codigo()
    assert sorted(re.findall(r'^\s*"Carril ([^"]+)" "[^"]+"', dsl, re.M)) == sorted(carriles)
    vista = re.search(r"^ {8}lanes: \{(.*?)^ {8}\},", html, re.M | re.S)
    assert vista, "la página sin la vista «lanes»"
    assert sorted(re.findall(r"n\('lane_(\w+)'", vista.group(1))) == sorted(carriles)
    assert 'data-view="lanes"' in html


def test_090_rf23_cada_funcion_citada_por_el_pseudocodigo_existe(c4):
    """090:RF-23 — los diez flujos, cada uno con citas que existen; una cita inventada se nombra."""
    texto = PSEUDO.read_text(encoding="utf-8")
    bloques = c4.pseudocodigo(texto)
    assert [i for i, _, _ in bloques] == ["conversion", "powerfactory", "calibracion", "con-proyecto", "motores", "pit",
                                         "vad", "vnr-guia", "carriles", "asistente"]
    for ident, _, codigo in bloques:
        assert c4.citas(codigo), f"el bloque {ident} no cita ninguna función"
    assert c4.citas_sin_codigo(texto, ROOT) == []
    sembrado = texto + "\n`src/convertersmartgrid/aplicacion/batch.py::no_existe` y `tools/no_hay.py::main`\n"
    assert c4.citas_sin_codigo(sembrado, ROOT) == ["src/convertersmartgrid/aplicacion/batch.py::no_existe",
                                                   "tools/no_hay.py::main"]
    metodo = "`src/convertersmartgrid/presentacion/web/jobs.py::JobManager.no_existe`"
    assert c4.citas_sin_codigo(metodo, ROOT) == ["src/convertersmartgrid/presentacion/web/jobs.py::JobManager.no_existe"]


def test_090_rf23_rf24_comprobar_falla_con_una_cita_rota_o_una_pagina_con_otro_pseudocodigo(c4, copia, capsys):
    """090:RF-23, RF-24 — la página lleva el pseudocódigo del fichero; tocado a mano, --comprobar sale con 1 y --escribir lo repone."""
    html, pseudo = copia / _FICHEROS[1], copia / _FICHEROS[4]
    original = html.read_text(encoding="utf-8")
    for ident, _, _ in c4.pseudocodigo(pseudo.read_text(encoding="utf-8")):
        assert f'<details id="pseudo-{ident}" class="c4-pseudo-block">' in original
    assert "pseudo: ['motores']" in original and "openPseudo(view.pseudo" in original
    html.write_text(original.replace("resolver_con", "resolver_otro", 1), encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 1
    assert "python tools/generar_c4.py --escribir" in capsys.readouterr().out
    assert c4.main(["--escribir", "--raiz", str(copia)]) == 0
    assert html.read_text(encoding="utf-8") == original
    texto = pseudo.read_text(encoding="utf-8")
    pseudo.write_text(texto.replace("::resolver_con", "::resolver_otro", 1), encoding="utf-8")
    assert c4.main(["--comprobar", "--raiz", str(copia)]) == 2
    assert "resolver_otro" in capsys.readouterr().out


def test_090_rf25_arquitectura_dice_los_carriles_del_codigo_y_enlaza_el_pseudocodigo():
    """090:RF-25 — la cifra de los carriles y sus nombres son los de LANES; motores, PIT, VAD y VNR explicados."""
    texto = (ROOT / "docs" / "ARQUITECTURA.md").read_text(encoding="utf-8")
    carriles = _carriles_del_codigo()
    palabras = {4: "Cuatro", 5: "Cinco", 6: "Seis", 7: "Siete", 8: "Ocho"}
    vineta = re.search(r"^- \*\*(\w+) carriles\*\*, cada uno con un hilo:(.*?)(?=^- )", texto, re.M | re.S)
    assert vineta and vineta.group(1) == palabras[len(carriles)], "la cifra de carriles de ARQUITECTURA.md no es la del código"
    assert sorted(re.findall(r"`(\w+)` \(", vineta.group(2))) == sorted(carriles)
    seccion = texto.split("## Motores abiertos, módulos regulatorios, carriles y pseudocódigo", 1)
    assert len(seccion) == 2, "ARQUITECTURA.md sin la sección de motores, módulos regulatorios y pseudocódigo"
    for termino in ("architecture/pseudocodigo.md", "Motores abiertos de flujo", "**PIT**", "**VAD**", "VNR de la Guía 232-2017"):
        assert termino in seccion[1], termino


def test_090_rf26_exportacion_del_c4_con_una_pagina_por_vista_y_por_bloque(c4):
    """090:RF-26 — cada pestaña tiene su vista, y el PDF versionado tiene una portada, una página por vista y otra por bloque."""
    from pypdf import PdfReader

    pagina = HTML.read_text(encoding="utf-8")
    assert c4.vistas_sin_pestana(pagina) == []
    assert c4.vistas_sin_pestana(pagina.replace("        lanes: {\n", "        carriles_x: {\n", 1)) == ["lanes"]
    assert (ROOT / "frontend" / "scripts" / "exportar-c4.mjs").is_file()
    vistas = list(dict.fromkeys(re.findall(r'data-view="([^"]+)"', pagina)))
    bloques = c4.pseudocodigo(PSEUDO.read_text(encoding="utf-8"))
    pdf = PdfReader(str(ROOT / "docs" / "architecture" / "plano_flujo_arquitectura_converter_smart_grid.pdf"))
    assert len(pdf.pages) == 1 + len(vistas) + len(bloques), "el PDF no se regeneró con node frontend/scripts/exportar-c4.mjs"
    # El 25-11 el PDF tenía sus 21 páginas y las vistas en blanco: solo el icono de imagen rota, de 14 px. Cada vista
    # lleva su imagen con el ancho de una vista dibujada.
    sin_imagen = [i for i in range(1, 1 + len(vistas)) if max((im.image.width for im in pdf.pages[i].images), default=0) < 600]
    assert sin_imagen == [], f"páginas de vista del PDF sin imagen: {sin_imagen}"
    texto = " ".join(p.extract_text() or "" for p in pdf.pages)
    for _, titulo, _ in bloques:
        assert titulo.split(" ")[0] in texto
    for vista in vistas:
        assert (ROOT / "docs" / "architecture" / f"c4_vista_{vista}.png").is_file(), vista
