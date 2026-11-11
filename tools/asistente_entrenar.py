#!/usr/bin/env python
"""Entrena el Transformer de órdenes y el clasificador de informes del asistente (spec 026, T3 y T7).

En su propio proceso, como la PINN: si la GPU falla, cae este proceso y no la web. Cada
modelo se promueve solo si pasa sus puertas en un conjunto de prueba fijo y no acierta
menos que el que está en uso (RF-20); el anterior queda para volver a él.

    python tools/asistente_entrenar.py --output-json entrenamiento.json [--vocabulario vocab.json]
    python tools/asistente_entrenar.py --output-json evaluacion.json --evaluar
    python tools/asistente_entrenar.py --output-json entrenamiento.json --destilar

``--destilar`` (spec 027, RF-56 a RF-62): el modelo local de Ollama interpreta k veces las
órdenes que el operador no confirmó y el Transformer aprende de sus votos; se usa solo si
acierta al menos lo mismo que sin destilar.

``--vocabulario`` es un JSON ``{"alimentadores": [...], "proyecto": [...], "sistema": [...]}``
con los nombres reales del espacio; sin él se usan los que guardó la web la última vez.

Sin opciones, la vía gobernada por el registro, como ``--integral`` (070:RF-62): la vigilancia la lanza así.
``--destilar`` y ``--solo`` piden la vía antigua: corre con su turno de GPU, deja la decisión en el registro y no pone
ningún modelo en uso (070:RF-63, RF-64).

``--validacion-cruzada`` (075:RF-35), con la vía gobernada: las órdenes confirmadas entrenan en 5 vueltas, la puerta humana se
mide fuera de grupo y el modelo final se entrena con todas. Sin ella, las confirmadas solo examinan (070:RF-76).

``--afinar`` (079:RF-61), con la vía gobernada: afina las últimas capas del codificador junto con las cabezas, con parada por
selección. Sin ella, solo las cabezas (079:RF-2). Lee el codificador de la caché del proceso, sin red: ver 079:RF-58 en su plan.

``--arquitectura vectores`` (026:RF-36, RF-39), con ``--solo informes``: el clasificador de informes por vectores del
codificador preentrenado y regresión logística, con las mismas puertas y la misma reapertura. Sin ella, el de siempre.

    python tools/asistente_entrenar.py --output-json informes.json --solo informes --arquitectura vectores

Códigos de salida: 0 hecho, 2 sin PyTorch o sin GPU, 1 error.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO / 'src'))


def _log(mensaje: str) -> None:
    """El avance a quien escuche; si la web que lo lanzó ya no está, se entrena igual
    (con la salida rota, ``print`` daba «OSError 22» y se perdía el entrenamiento)."""
    try:
        print(mensaje, flush=True)
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Entrena el Transformer de órdenes y el clasificador de informes '
                                            'del asistente (spec 026)')
    p.add_argument('--output-json', required=True)
    p.add_argument('--vocabulario', type=Path, help='Nombres reales del espacio (JSON)')
    p.add_argument('--dataset-v2',type=Path,help='Particiones train/validation/test trazables; no usa datos legacy')
    p.add_argument('--registro',type=Path,help='Registro de candidatos de dataset v2; conserva los modelos activos')
    p.add_argument('--solo', choices=('ordenes', 'informes'), help='Entrenar solo uno de los dos modelos')
    p.add_argument('--destilar', action='store_true',
                   help='Destilar del modelo local de Ollama (maestro) al Transformer (spec 027, RF-56)')
    p.add_argument('--integral', action='store_true', help='Protocolo independiente del maestro de sesión (047 T5), con puesta en uso por el registro (067:RF-20)')
    p.add_argument('--semillas', default='11,23,37', help='Semillas de --integral')
    p.add_argument('--epocas', type=int, default=24, help='Épocas por candidato de --integral')
    p.add_argument('--maestro', choices=('claude', 'codex', 'ollama'), default=None,
                   help='Maestro de la destilación: las etiquetas de Claude, Codex o Ollama (027:RF-56)')
    p.add_argument('--modelo-codex', help='Modelo de Codex como maestro (por defecto, el de su configuración)')
    p.add_argument('--validacion-cruzada', action='store_true',
                   help='Con --integral: entrenar con las órdenes confirmadas en 5 vueltas y decidir con la medida fuera de grupo (075:RF-35)')
    p.add_argument('--afinar', action='store_true', help='Con --integral: afinar las últimas capas del codificador junto con las cabezas (079:RF-1)')
    p.add_argument('--afinar-capas', type=int, default=2, help='Cuántas últimas capas afinar (079:RF-5)')
    p.add_argument('--afinar-lote', type=int, default=32, help='Frases por lote al afinar; bájelo si falta memoria de GPU (079:RF-8)')
    p.add_argument('--afinar-epocas', type=int, default=8, help='Tope de épocas de afinado, con parada por selección (079:RF-12)')
    p.add_argument('--afinar-pasos', type=int, default=800, help='Pasos de cada época de afinado')
    p.add_argument('--codificador', choices=('base', 'large'), default='base',
                   help='Con --integral: el codificador de las órdenes, con su revisión fija (069:RF-33)')
    p.add_argument('--evaluar', action='store_true', help='No entrenar: medir los modelos en uso con la prueba fija')
    p.add_argument('--arquitectura', choices=('transformer', 'vectores'), default='transformer',
                   help='Con --solo informes: la arquitectura del clasificador de informes (026:RF-36)')
    args = p.parse_args(argv)
    salida = Path(args.output_json)
    salida.parent.mkdir(parents=True, exist_ok=True)
    # 070:RF-62: una llamada sin opciones de la vía antigua (la de la vigilancia) ya no promueve sin registro.
    if not (args.dataset_v2 or args.evaluar or args.destilar or args.solo or args.maestro or args.modelo_codex):
        args.integral = True
    if args.validacion_cruzada and not args.integral:
        p.error('--validacion-cruzada solo vale con --integral')
    if args.afinar and not args.integral:                                            # 079:RF-62
        p.error('--afinar solo vale con --integral')
    if args.arquitectura != 'transformer' and (args.solo != 'informes' or args.evaluar or args.dataset_v2):   # 026:RF-39
        p.error('--arquitectura solo vale con --solo informes')
    if args.afinar and min(args.afinar_capas, args.afinar_lote, args.afinar_epocas, args.afinar_pasos) < 1:
        p.error('las opciones de --afinar deben ser positivas')

    if args.dataset_v2:
        from convertersmartgrid.trabajadores_ml import fallo,escribir_informe,semillas_de
        if salida.exists():print('Informe existente conservado');return 2
        try:
            if args.integral or args.destilar or args.evaluar or args.solo is None:
                raise ValueError('--dataset-v2 requiere --solo y no combina modos legacy')
            from convertersmartgrid.asistente.entrenamiento_dataset import entrenar_dataset
            from convertersmartgrid.model_registry import RegistroModelo
            resultado=entrenar_dataset(args.dataset_v2,salida.parent,solo=args.solo,
                semillas=semillas_de(args.semillas),epocas=args.epocas,
                registro=RegistroModelo(args.registro) if args.registro else None)
            codigo=0
        except Exception as exc:resultado=fallo(exc);codigo=2
        escribir_informe(salida,resultado)
        return codigo

    if args.integral:
        try:
            if args.evaluar or args.destilar or args.solo == 'informes' or args.maestro not in (None, 'codex') or args.modelo_codex:
                raise ValueError('--integral usa el currículo local del maestro Codex; no combine con otros maestros/modos')
            if args.epocas < 1:
                raise ValueError('épocas positivas obligatorias')
            from convertersmartgrid.asistente import almacen, clasificador, transformer
            from convertersmartgrid.asistente.destilacion_integral import preparar_corpus, guardar_corpus, entrenar_destilacion
            from convertersmartgrid.training_coordinator import BloqueoGPU, ruta_guardia_gpu
            destino = salida.parent / (salida.stem + '_integral')
            vocab = (json.loads(args.vocabulario.read_text(encoding='utf-8')) if args.vocabulario
                     else almacen.leer_json('vocabulario') or {})
            from convertersmartgrid.asistente import codificador_ordenes
            from convertersmartgrid.asistente.maestro_real import leer_etiquetas, leer_ninguna
            ninguna, reservados = leer_ninguna(almacen.raiz())                             # 069:RF-28
            from convertersmartgrid.asistente import ordenes_maestro
            filas, meta = preparar_corpus(vocab, almacen.leer('ejemplos'),                 # 068:RF-33
                                          etiquetas_reales=leer_etiquetas(almacen.raiz())[0],
                                          ninguna=ninguna, ninguna_reservada=reservados,
                                          ordenes_maestro=ordenes_maestro.leer(almacen.raiz())[0])   # 085:RF-1
            guardar_corpus(destino / 'corpus', filas, meta, reservados)
            # 075:RF-28: una confirmada igual a una fija de prueba no entrena, como la plata (027:RF-66).
            from convertersmartgrid.asistente.ordenes_fijas import generar as generar_fijas, repartir as repartir_fijas
            fijas_de_prueba = [e.texto for e in repartir_fijas(generar_fijas(vocab))[1]] if args.validacion_cruzada else []
            lock = ruta_guardia_gpu()
            with BloqueoGPU(lock, 'asistente-integral-web'):
                resultado = entrenar_destilacion(destino / 'corpus', destino / 'entrenamiento',
                    cfg=codificador_ordenes.Configuracion(
                        epocas=args.epocas, codificador=args.codificador, **({'afinar_capas': args.afinar_capas, 'afinar_lote': args.afinar_lote,
                                                'afinar_epocas': args.afinar_epocas, 'pasos_por_epoca': args.afinar_pasos}
                                               if args.afinar else {})),
                    semillas=tuple(int(s) for s in args.semillas.split(',') if s.strip()),
                    registro=almacen.raiz() / 'model_registry',
                    validacion_cruzada=args.validacion_cruzada, vedadas_extra=fijas_de_prueba)
                # 067:RF-20, RF-24: lo que el registro aprobó pasa a uso; lo demás deja el modelo actual.
                from convertersmartgrid.asistente.modelos_en_uso import aplicar_decision
                from convertersmartgrid.model_registry import RegistroModelo
                uso = aplicar_decision('transformer', resultado['candidato'])
                resultado = {**resultado, **uso}
                informe = {'ordenes': resultado, 'training_completed': True}
                if args.solo != 'ordenes':                               # 067:RF-26
                    informe['informes'] = clasificador.entrenar_gobernado(
                        RegistroModelo(almacen.raiz() / 'model_registry'), destino, log=_log)
            codigo = 0
        except Exception as exc:
            informe, codigo = {'training_completed': False, 'status': 'ERROR_ENTORNO',
                                'error': str(exc), 'traza': traceback.format_exc()}, 2
        salida.write_text(json.dumps(informe, ensure_ascii=False, default=str), encoding='utf-8')
        return codigo

    try:
        from convertersmartgrid.asistente import almacen, clasificador, transformer
        from convertersmartgrid.digital_twin.oraculo import dispositivo

        dispositivo()
    except (ImportError, RuntimeError) as exc:
        salida.write_text(json.dumps({'entrenado': False, 'motivo': str(exc)}, ensure_ascii=False), encoding='utf-8')
        print(f'ERROR: {exc}')
        return 2
    if args.vocabulario:
        vocab = json.loads(args.vocabulario.read_text(encoding='utf-8'))
    else:
        vocab = almacen.leer_json('vocabulario') or {}
    out: dict = {}
    try:
        if args.evaluar:
            from convertersmartgrid.asistente.sinteticos import generar

            m = transformer.cargar()
            prueba = generar(vocab, por_tarea=20, semilla=transformer.SEMILLA_PRUEBA) + transformer.ejemplos_reales()[1]
            out['ordenes'] = transformer.evaluar(m, prueba) if m is not None else None
            c = clasificador.cargar()
            if c is not None:
                prueba_c = clasificador.generar(c.subtipos, por_subtipo=25, semilla=clasificador.SEMILLA_PRUEBA)
                out['informes'] = clasificador.evaluar(c, prueba_c)
            print(json.dumps(out, ensure_ascii=False))
        else:
            if args.solo in (None, 'ordenes'):
                kw = {}
                if args.destilar:
                    from convertersmartgrid.asistente.destilacion import Destilacion
                    from convertersmartgrid.asistente.ollama import cliente_configurado

                    from convertersmartgrid.asistente.destilacion import MaestroArchivo, MaestroCodex

                    maestro_nombre = args.maestro or 'claude'
                    maestro = {'claude': lambda: MaestroArchivo(), 'codex': lambda: MaestroCodex(vocab, modelo=args.modelo_codex),
                               'ollama': lambda: cliente_configurado(tiempo_max_s=60.0)}[maestro_nombre]()
                    # Codex fuera de la máquina: menos votos, cada uno es una llamada (RF-63).
                    kw = {'destilar': Destilacion(k=3 if maestro_nombre == 'codex' else 5), 'maestro': maestro}
                # 070:RF-63, RF-64: con su turno de GPU y sin tocar el puntero; la decisión queda en el registro.
                from convertersmartgrid.model_registry import RegistroModelo
                from convertersmartgrid.trabajadores_ml import turno_gpu

                registro = RegistroModelo(almacen.raiz() / 'model_registry')
                with turno_gpu('asistente-via-antigua'):
                    r = transformer.entrenar_y_promover(vocab, log=_log, promover_directo=False, **kw)
                c = registro.registrar_candidato(
                    'transformer', model_manifest={'algorithm': 'transformer_letra_a_letra', 'via': 'antigua',
                                                   'version': r.get('version'), 'training_completed': True},
                    dataset_manifest=r.get('dataset') or {}, metrics={k: v for k, v in r.items() if k != 'dataset'},
                    decision={'status': 'RECHAZADO', 'gates': {'approved': False},
                              'fallos': [*(r.get('fallos') or ()), 'la vía antigua no pone modelos en uso (070:RF-63)']},
                    smoke_reload={'ok': False, 'motivo': 'la vía antigua no se reabre: no se pone en uso'})
                out['ordenes'] = {**r, 'promovido': False, 'candidato': c}
            if args.solo in (None, 'informes'):
                from convertersmartgrid.model_registry import RegistroModelo
                from convertersmartgrid.trabajadores_ml import turno_gpu

                with turno_gpu('asistente-via-antigua'):
                    out['informes'] = clasificador.entrenar_gobernado(
                        RegistroModelo(almacen.raiz() / 'model_registry'), salida.parent / (salida.stem + '_informes'), log=_log,
                        arquitectura=args.arquitectura)
        codigo = 0
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito
        out, codigo = {'error': repr(exc), 'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(out, ensure_ascii=False, default=str), encoding='utf-8')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
