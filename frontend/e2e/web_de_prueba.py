"""111:RF-16 — web de prueba para los recorridos en navegador real, aislada y con la seguridad real.

La lanza ``preparar.mjs``; no forma parte del producto ni de la suite de Python.
- Carpeta temporal propia (runtime, caché, temporales, asistente y sesiones): no toca el perfil del usuario.
- Un espacio con un export SINTÉTICO sorteado (``tests/synthetic_export.py``, ``ExportSpec(seed=…)``), con un número de
  alimentadores dado y la disposición sorteada con la misma semilla; cargado con su georreferenciación y convertido con
  la vista previa, como lo haría el operador.
- Sin GPU. Las teselas de fondo siguen ``CSG_SALIDA_TESELAS`` del entorno; el navegador las sirve en local.
- Todo el arranque va dentro de ``main()``: la conversión abre procesos con «spawn» en Windows y cada hijo vuelve a
  importar este fichero; si el arranque estuviera a nivel de módulo, el hijo crearía otra sesión (la del padre deja de
  valer: 401) y otra web, y la conversión fallaría al arrancar el hijo.
Uso: python -I web_de_prueba.py <raíz del repositorio> <carpeta temporal> <puerto> <semilla> <alimentadores>
  → una línea «LISTA {json}» con la base, la url de entrada (con la sesión), el espacio y los alimentadores.
"""
import json
import os
import random
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path


def _entorno(raiz: Path, tmp: Path, puerto: int) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    for var, sub in (("CSG_RUNTIME_HOME", "runtime"), ("CSG_CACHE_HOME", "cache"), ("CSG_TEMP_HOME", "temp"),
                     ("CSG_ASISTENTE_DATA", "asistente"), ("CSG_WEB_SESIONES", "sesiones")):
        os.environ[var] = str(tmp / sub)
        (tmp / sub).mkdir(parents=True, exist_ok=True)
    # El perfil de la empresa también en la carpeta de la prueba: sin esto, «Cargar perfil» escribía el de la prueba en
    # config/perfil_empresa.json del checkout (en desarrollo, la carpeta local es el repositorio) y la corrida siguiente
    # estudiaba con los umbrales de la anterior.
    os.environ["CSG_PERFIL_EMPRESA"] = str(tmp / "perfil_empresa.json")
    os.environ["CSG_WEB_FRONTEND"] = str(raiz / "frontend" / "dist")
    os.environ["CSG_WEB_PUERTO"] = str(puerto)
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    sys.path[:0] = [str(raiz / "src"), str(raiz / "tests")]
    os.chdir(raiz)


def main() -> None:
    raiz, tmp = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    puerto, semilla, n_alim = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    _entorno(raiz, tmp, puerto)

    import uvicorn

    from synthetic_export import CRS_SINTETICO, ExportSpec, write_export
    from convertersmartgrid.dominio import sesion_web
    from convertersmartgrid.presentacion.web.app import create_app

    assert sesion_web.EXIGIR_SEGURIDAD, "la web de prueba corre con la seguridad encendida"
    sesion_web.crear_sesion(puerto)
    app = create_app(tmp / "web")
    base = f"http://127.0.0.1:{puerto}"
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True).start()
    for _ in range(240):
        if servidor.started:
            break
        time.sleep(0.25)

    def pedir(metodo, ruta, *, datos=None, cuerpo=None, tipo=None):
        cab = sesion_web.cabeceras_locales(base)
        if tipo:
            cab["Content-Type"] = tipo
        elif datos is not None:
            cab["Content-Type"] = "application/json"
        req = urllib.request.Request(base + ruta, method=metodo, headers=cab,
                                     data=cuerpo if cuerpo is not None else (json.dumps(datos).encode() if datos is not None else None))
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b"null")

    def subir(wid, slot, ruta):
        limite = uuid.uuid4().hex
        cuerpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{ruta.name}\"\r\n"
                  f"Content-Type: application/octet-stream\r\n\r\n").encode() + ruta.read_bytes() + f"\r\n--{limite}--\r\n".encode()
        return pedir("POST", f"/api/workspaces/{wid}/inputs/{slot}", cuerpo=cuerpo, tipo=f"multipart/form-data; boundary={limite}")

    def esperar(job):
        for _ in range(2400):
            j = pedir("GET", f"/api/jobs/{job['id']}")
            if j["status"] not in ("queued", "running"):
                return j
            time.sleep(0.25)
        raise TimeoutError(job)

    disposicion = random.Random(semilla).choice(("reducido", "completo"))
    wid = pedir("POST", "/api/workspaces")["id"]
    red, cargas, equipo = write_export(ExportSpec(feeders=n_alim, seed=semilla, layout=disposicion), tmp / "export")
    for slot, ruta in (("red", red), ("loads", cargas), ("equipment", equipo)):
        subir(wid, slot, ruta)
    pedir("PUT", f"/api/workspaces/{wid}/options", datos={"include_geography": True, "source_crs": CRS_SINTETICO, "write_preview": True})
    carga = esperar(pedir("POST", f"/api/workspaces/{wid}/load"))
    assert carga["status"] == "done", carga
    alimentadores = [f["feeder"] for f in pedir("GET", f"/api/workspaces/{wid}/feeders")["feeders"]]
    conv = esperar(pedir("POST", f"/api/workspaces/{wid}/convert", datos={"feeders": alimentadores}))
    assert conv["status"] in ("done", "parcial"), conv
    print("LISTA " + json.dumps({"base": base, "entrada": sesion_web.url_de_entrada(f"{base}/?espacio={wid}"), "espacio": wid,
                                 "alimentadores": alimentadores, "disposicion": disposicion, "conversion": conv["status"]},
                                ensure_ascii=False), flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
