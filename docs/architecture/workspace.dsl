workspace "ConverterSmartGrid" "Arquitectura C4 navegable desde fuentes hasta entregables. Cifras del catálogo generado (spec 090) en la revisión ecad83ea, 17-11-2026: 450 módulos de Python en 37 subsistemas." {

    // Las relaciones de componentes no se suben solas a los contenedores: cada vista muestra solo lo declarado.
    !impliedRelationships false

    // Los enlaces apuntan a la revisión fijada ecad83ea, nunca a una ruta de la máquina.
    // 090:RF-19: cada componente nombra en «Subsistemas» los grupos de docs/architecture/subsistemas.json que reúne;
    // sus ficheros, las cifras de arriba y la marca «en implementación» las pone tools/generar_c4.py --escribir desde
    // docs/ARQUITECTURA_CATALOGO.md; tests/test_arquitectura_c4_al_dia.py exige su --comprobar. Cada grupo va en un solo componente.

    model {
        operador = person "Operador eléctrico" "Elige el alcance, confirma cada escritura y decide con evidencia." {
            url "http://127.0.0.1:8765/"
            tags "Person"
        }

        // ------------------------------------------------------------------ sistemas externos
        fuentes = softwareSystem "Fuentes de la distribuidora" "TXT de CYMDIST, base Access y libros de medición; cada fuente se carga por su ruta." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/sources"
            tags "External"
        }

        vnrGis = softwareSystem "Paquete VNR-GIS" "Base y capas del VNR publicadas por Osinergmin; las copias .bak se restauran en SQL Server Express." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/entrada/vnr"
            tags "External"
        }

        regulador = softwareSystem "Osinergmin / COES / MINEM" "Entes públicos: normas con su vigencia, costos oficiales y formatos del PIDE, del PIT y del VAD." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/README.md"
            tags "External"
        }

        powerfactory = softwareSystem "DIgSILENT PowerFactory" "Motor nativo propietario, 2021 o posterior: importa, verifica, calibra y estudia la red." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools/powerfactory_acceptance.py"
            tags "Native"
        }

        llm = softwareSystem "LLM local" "Ollama en esta máquina, para el asistente y su revisión; solo direcciones locales." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente/ollama.py"
            tags "External"
        }

        nube = softwareSystem "Nube del operador" "Google Drive y OneDrive con la cuenta del operador." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/109-fuentes-y-expedientes-en-la-nube-desde-la-web/spec.md"
            tags "External,en implementación"
            properties {
                "Estado" "en implementación"
                "Spec" "109"
            }
        }

        correo = softwareSystem "Correo del operador" "Gmail y Outlook con la cuenta del operador." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/110-envio-de-informes-por-correo-desde-la-web/spec.md"
            tags "External"
            properties {
                "Spec" "110"
            }
        }

        // ------------------------------------------------------------------ el sistema
        conversor = softwareSystem "ConverterSmartGrid" "Convierte, valida, calibra, estudia y documenta redes de distribución en la máquina del operador." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/README.md"

            frontend = container "Interfaz web" "Selección, seguimiento, confirmación y descarga; compilada en frontend/dist." "React + TypeScript" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src"
                tags "Web"
                cmpInterfaz = component "Interfaz común" "Compilación, cliente tipado de la API y piezas comunes de las pestañas (83 ficheros)." "React + TypeScript" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: compilación, cliente de la API y piezas comunes (`frontend/`)"
                    }
                }
                cmpInterfazConversion = component "Conversión y perfil" "Entradas, alimentadores, opciones, reconstrucción y perfil de la empresa (7 ficheros)." "React + TypeScript" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src/features/conversion"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: conversión y perfil de la empresa"
                    }
                }
                cmpInterfazEstudios = component "Cargas, estudios, obras e informes" "«Cargas en DIgSILENT», demanda, estudios, obras e informes (25 ficheros)." "React + TypeScript" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src/features/powerfactory"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: «Cargas en DIgSILENT», estudios, obras e informes"
                    }
                }
                cmpInterfazRegulatorio = component "Módulos regulatorios" "Pestañas del PIT, del VAD, del VNR y de la biblioteca normativa (4 ficheros)." "React + TypeScript" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src/features/pit"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: módulos regulatorios (PIT, VAD, VNR y biblioteca normativa)"
                    }
                }
                cmpInterfazNube = component "Nube y correo" "Elegir fuentes de la nube, publicar expedientes y ver versiones nuevas (5 ficheros)." "React + TypeScript" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src/features/nube"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: nube y correo"
                    }
                }
                cmpInterfazAsistente = component "Asistente en la web" "Órdenes, equipo, monitor, tarjeta del operador y aprendizaje (8 ficheros)." "React + TypeScript" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/src/features/asistente"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: asistente"
                    }
                }
                cmpInterfazPruebas = component "Pruebas de la interfaz" "Pruebas sin navegador de las pestañas y de la lógica (43 ficheros)." "Node test runner" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/frontend/test"
                    tags "Web"
                    properties {
                        "Subsistemas" "Interfaz: pruebas de `frontend/test/`"
                    }
                }
            }

            gisEditor = container "Editor sobre el plano" "Ver la red, elegir un equipo, proponer maniobras u obras y ver los resultados en el mismo trazo, sin tocar el Caso base." "React + Leaflet" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/111-editor-electrico-sobre-el-plano-gis/spec.md"
                tags "Web,en implementación"
                properties {
                    "Estado" "en implementación"
                    "Spec" "111"
                }
            }

            security = container "Puerta de seguridad" "Host, Origin, token de sesión, política de contenido, edición y salidas a la red." "Middleware ASGI" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/presentacion/web/seguridad.py"
                tags "API"
            }

            api = container "API web" "REST y WebSocket: 163 rutas y 13 del VNR-GIS. Valida pedidos y coordina trabajos; no calcula." "FastAPI / Python 3.12" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/presentacion/web/app.py"
                tags "API"
                cmpWeb = component "Web" "Rutas, servicios, colas, seguridad, custodia, doctor, soporte y las API del PIT, VAD, VNR, normativa, nube y correo (40 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/presentacion/web"
                    tags "API"
                    properties {
                        "Subsistemas" "Web: `web/`"
                    }
                }
            }

            jobs = container "Colas de trabajo" "Carriles engine, powerfactory, asistente, control, correo y red; el de control solo cancela." "Hilos y colas de Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/presentacion/web/jobs.py"
                tags "Queue"
            }

            custody = container "Custodia de fuentes" "Ejecuciones fuente inmutables con alcance y huellas, sin mezclar fuentes." "Ficheros + SHA-256" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/presentacion/web/source_runs.py"
                tags "Store"
            }

            cloudConn = container "Conector de nube" "Elige fuentes en la nube, avisa de cambios y sube expedientes; cada estudio usa una copia fija con huella." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/109-fuentes-y-expedientes-en-la-nube-desde-la-web/spec.md"
                tags "API,en implementación"
                properties {
                    "Estado" "en implementación"
                    "Spec" "109"
                }
                cmpNube = component "Nube" "Proveedores Google Drive y OneDrive, OAuth, cuentas, cofre y salida a la nube (11 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/nube"
                    tags "API"
                    properties {
                        "Subsistemas" "Nube: Google Drive y OneDrive (spec 109)"
                    }
                }
            }

            mailer = container "Envío de informes" "Envía el informe cerrado o un enlace privado a su expediente, con vista previa, confirmación y recibo." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/110-envio-de-informes-por-correo-desde-la-web/spec.md"
                tags "API"
                properties {
                    "Spec" "110"
                }
            }

            vnr = container "Adaptador VNR-GIS" "Descubre, valida y exporta el VNR al mismo modelo común; su DGS sale del mismo escritor." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/entrada/vnr"
                tags "Engine"
                cmpVnr = component "VNR-GIS" "Conectores, descubrimiento, GIS, validación y puente al modelo común (52 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/entrada/vnr"
                    tags "Engine"
                    properties {
                        "Subsistemas" "VNR-GIS: `adaptadores/entrada/vnr/`"
                    }
                }
            }

            engine = container "Motor de conversión" "Adapta, reconstruye, aplica reglas y construye FeederModel; hasta 4 procesos con el mismo DGS." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/batch.py"
                tags "Engine"
                cmpTransversales = component "Transversales" "Rutas de ejecución, nombres, perfil de empresa, privacidad, edición y salidas a la red (19 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/dominio/runtime_paths.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: transversales"
                    }
                }
                cmpEntrada = component "Entrada de datos" "Lectores TXT, MDB y VNR, contrato de fuente, copia fija, identificación e inventario (17 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/sources"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: entrada de datos"
                    }
                }
                cmpFachadas = component "Fachadas fuera del paquete" "Entrada de órdenes del VNR fuera del paquete (1 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/vnr_etl.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: fachadas fuera del paquete"
                    }
                }
                cmpReconstruccion = component "Reconstrucción y catálogo" "Completa lo que falta con el catálogo y anota cada supuesto (8 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/reconstruction_pipeline.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: reconstrucción y catálogo"
                    }
                }
                cmpModelo = component "Modelo y reglas" "FeederModel, reglas comunes, puentes, fases y capacidades (9 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/dominio/model.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: modelo y reglas"
                    }
                }
                cmpConversion = component "Conversión, red unida y oráculo" "Lote, red unida, enlaces, estructura y oráculo de convergencia (8 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/batch.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: conversión, red unida y oráculo"
                    }
                }
            }

            oracle = container "Preflight consultivo" "Informa conectividad y convergencia antes de importar a PowerFactory; sus avisos no omiten el DGS." "pandapower" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/oraculo.py"
                tags "Engine"
            }

            dgs = container "Escritor y validador DGS" "Escribe con esquema versionado, valida y publica de forma atómica." "Python + esquema DGS" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/dgs.py"
                tags "Engine"
                cmpSalida = component "Salida y módulos enchufables" "Esquemas versionados, escritor DGS, validación y módulos enchufables (18 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/dgs.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: salida y módulos enchufables"
                    }
                }
            }

            nativeRunner = container "Guiones de DIgSILENT" "Lanza tools/*_pf.py con plan JSON y turno exclusivo; recibe informe JSON. Importa, calibra, aplica obras y corre estudios." "Python / API de PowerFactory" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/presentacion/web/services.py"
                tags "Native"
                cmpEnlacePf = component "Enlace con DIgSILENT" "Arnés de turno exclusivo, entorno, metadatos y vínculo fuente-proyecto (9 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/pf_arnes.py"
                    tags "Native"
                    properties {
                        "Subsistemas" "Motor: enlace con DIgSILENT"
                    }
                }
                cmpGuiones = component "Guiones de DIgSILENT" "Importan, verifican, calibran, insertan cargas, aplican obras y corren estudios (38 ficheros)." "Python con el intérprete de PowerFactory" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools/powerfactory_acceptance.py"
                    tags "Native"
                    properties {
                        "Subsistemas" "Guiones de DIgSILENT: `tools/` (corren con su intérprete)"
                    }
                }
            }

            calibration = container "Demanda y calibración" "Libros por año, máxima coincidente y reparto de la demanda; el Caso base no se toca." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/demanda_medida.py"
                tags "Engine"
                cmpDemanda = component "Demanda y calibración" "Libros por año y libros nuevos, cabecera, cargas y reparto (19 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/demanda_medida.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: demanda y calibración"
                    }
                }
            }

            optimizer = container "Obras y optimización" "Escalera de bancos, sección y terna, Optuna y NSGA-II; DIgSILENT confirma cada obra." "Python + NumPy + Optuna" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/escalera_optima.py"
                tags "AI"
                cmpObras = component "Obras y optimización" "Escalera, troncal, perfil de tensión, reguladores, obras integrales y optimización (16 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/obras_pf.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Motor: obras y optimización"
                    }
                }
            }

            studies = container "Estudios eléctricos" "Flujo, N-1, protecciones y transferencia con los módulos nativos de DIgSILENT." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/estudios_pf.py"
                tags "Engine"
                cmpEstudios = component "Estudios" "Estudios de red, protecciones y transferencia (12 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/estudios_pf.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: estudios"
                    }
                }
            }

            reports = container "Informes" "Word, PDF, imágenes y libro Excel de estudio y factibilidad, con lo guardado por la corrida." "python-docx + COM" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/informes.py"
                tags "Engine"
                cmpInformes = component "Informes" "Word, libros, mapas del informe y mapa de cargas (15 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/informes.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: informes"
                    }
                }
            }

            normativa = container "Biblioteca normativa" "Normas nacionales e internacionales con su vigencia, sus modificaciones y la cita de cada regla; vale para toda empresa, estudio y módulo, y para el asistente." "Python + JSON con esquema" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/biblioteca_normativa.py"
                tags "Engine"
                cmpNormativa = component "Biblioteca normativa y fuentes de la empresa" "Registro normativo con esquema, huellas de términos, fuentes de la empresa y vínculos del .pfd (5 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/biblioteca_normativa.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: biblioteca normativa y fuentes de la empresa (107, 109)"
                    }
                }
            }

            planning = container "PIDE y planeamiento" "Largo plazo y PIDE de distribución: diagnóstico, obras, costos oficiales y formatos." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/pide.py"
                tags "Engine"
                cmpPide = component "PIDE y planeamiento" "PIDE, economía, proyecciones de mercado y estudio de planeamiento (14 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/dominio/estudio_planeamiento.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: PIDE y planeamiento"
                    }
                }
            }

            pit = container "Plan de inversiones en transmisión" "Producto aparte para la transmisión secundaria y complementaria; comparte red, motores, costos e informes, no el método." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/107-plan-de-inversiones-en-transmision/spec.md"
                tags "Engine,en implementación"
                properties {
                    "Estado" "en implementación"
                    "Spec" "107"
                }
                cmpPit = component "PIT" "Ámbito y red del área de demanda, demanda regulatoria, diagnóstico con la norma, alternativas, formatos, expediente e informe (30 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/dominio/pit"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: PIT (plan de inversiones en transmisión)"
                    }
                }
            }

            vad = container "Estudio de costos del VAD" "Empresa modelo eficiente en cuatro etapas y VNR según la Guía 232-2017 con el SICODI; la red real y la red óptima se calculan por separado." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/108-estudio-de-costos-del-vad/spec.md"
                tags "Engine,en implementación"
                properties {
                    "Estado" "en implementación"
                    "Spec" "108"
                }
                cmpVadVnr = component "VAD y VNR" "Caracterización, dimensionamiento, costos, COyM, modelos urbano y rural, VNR de la Guía, formatos y entregables (25 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/vad"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Motor: VAD y VNR (estudio de costos y Guía del VNR, spec 108)"
                    }
                }
            }

            twin = container "Gemelo digital" "Captura episodios y ofrece oráculos radial, mallado, PINN-GNN y GRU; filtra candidatos, DIgSILENT decide." "Python + PyTorch (CUDA)" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/digital_twin"
                tags "AI"
                cmpGemelo = component "Gemelo digital" "Episodios, búfer, captura, oráculos, temporal, pronóstico y evolutivos (30 ficheros)." "Python + PyTorch" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/digital_twin"
                    tags "AI"
                    properties {
                        "Subsistemas" "Gemelo digital: `digital_twin/`"
                    }
                }
            }

            forecast = container "Pronóstico de demanda" "Un módulo con datos que crecen cada mes: compiten modelos ingenuos, GRU, N-HiTS, TFT y PatchTST; ninguno se pone en uso solo." "Python + PyTorch" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/pronostico_demanda.py"
                tags "AI"
            }

            bench = container "Benchmarks anonimizados" "Datos de referencia desidentificados, solo en local, y protocolos por cohortes de empresa y de tiempo." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/specs/112-datasets-de-referencia-anonimizados-y-benchmarks/spec.md"
                tags "AI"
                properties {
                    "Spec" "112"
                }
                cmpBench = component "Benchmarks anonimizados" "Seudónimos, geometría pública, cohortes, series, control de reidentificación y reproducción (16 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/benchmarks"
                    tags "AI"
                    properties {
                        "Subsistemas" "Motor: benchmarks anonimizados"
                    }
                }
            }

            assistant = container "Asistente y su equipo" "64 tareas; interpreta órdenes, muestra el plan y ejecuta solo tras confirmación; revisan fuentes, física, coste y riesgo." "Reglas + codificador de órdenes + LLM local" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente"
                tags "AI"
                cmpAsisNucleo = component "Núcleo y operación" "Tareas, intérprete, plan, planes guardados, ejecutor y orquestador (17 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente/tareas.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Asistente: núcleo y operación"
                    }
                }
                cmpAsisModelos = component "Modelos de órdenes y documentos" "Transformer, codificador y clasificador de informes (9 ficheros)." "Python + PyTorch" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente/codificador_ordenes.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Asistente: modelos de órdenes y documentos"
                    }
                }
                cmpAsisDatos = component "Datos y entrenamiento" "Órdenes sintéticas, fijas y del maestro; currículos y destilación (24 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente/ordenes_maestro.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Asistente: datos y entrenamiento"
                    }
                }
                cmpAsisRag = component "Conocimiento y RAG" "Índice con el corpus normativo, vectores, reordenación y evaluación de la recuperación (12 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente/indice.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Asistente: conocimiento y RAG"
                    }
                }
            }

            modelGovernance = container "Gobierno de modelos" "Registro de candidatos, puertas, puntero en uso, un turno de GPU para toda la máquina y ciclo de aprendizaje." "Python + JSON + SHA-256" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/model_registry.py"
                tags "AI"
                cmpGobierno = component "Gobierno de modelos" "Registro, coordinador de entrenamiento, GPU, contratos de aprendizaje y arnés de evaluación (26 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/model_registry.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Motor: gobierno de modelos"
                    }
                }
            }

            mcp = container "MCP local" "Las lecturas del asistente para un cliente de esta máquina, entre ellas consultar_norma con su cita: solo stdio y solo lectura." "Python + MCP (opcional)" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools/mcp_conversor.py"
                tags "AI"
            }

            tooling = container "Herramientas de órdenes" "Operación, aceptación, entrenamientos y calidad desde la línea de órdenes." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools"
                tags "Engine"
                cmpHerrOperacion = component "Operación, datos y aceptación" "Flujo completo por la web, informes de casos guardados y aceptación nativa (33 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools/sistema_web.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Herramientas: operación, datos y aceptación"
                    }
                }
                cmpHerrModelos = component "Modelos, asistente y MADRL" "Entrenamientos y auditorías del gemelo, del asistente, del pronóstico y del piloto MADRL (37 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools/digital_twin_entrenar.py"
                    tags "AI"
                    properties {
                        "Subsistemas" "Herramientas: modelos, asistente y MADRL"
                    }
                }
                cmpHerrCalidad = component "Calidad y entrega" "Capas, arquitectura generada, contrato de la API, estado de specs, suite por tandas y candidato (18 ficheros)." "Python" {
                    url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/tools/arquitectura.py"
                    tags "Engine"
                    properties {
                        "Subsistemas" "Herramientas: calidad y entrega"
                    }
                }
            }

            workspaceStore = container "Espacios y entregables" "Entradas, planes, DGS, informes y descargas de cada espacio." "Ficheros" {
                url "http://127.0.0.1:8765/"
                properties {
                    "Local path" "output/web"
                }
                tags "Store"
            }

            episodeStore = container "Búfer de episodios" "JSON inmutable por huella, objetos e índice SQLite." "JSON + SQLite" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/adaptadores/digital_twin/buffer.py"
                tags "Store"
            }

            operationStore = container "Diario de operaciones y evidencia" "Estados por espacio, contexto inicial e informes custodiados; no promueve modelos." "SQLite + JSON + SHA-256" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/ecad83ea11a8ff4b9943ec22e57b427597c938fb/src/convertersmartgrid/aplicacion/asistente/observacion.py"
                tags "Store"
            }
        }

        // ------------------------------------------------------------------ relaciones entre contenedores
        operador -> frontend "Usa" "HTTP local"
        operador -> assistant "Confirma o rechaza"
        fuentes -> api "Entrega archivos o rutas" "Subida o ruta"
        vnrGis -> vnr "Entrega base y capas" "SQL Server Express"
        regulador -> normativa "Publica normas, modificaciones y su vigencia"
        regulador -> planning "Publica costos y formatos"
        frontend -> security "Invoca y consulta" "REST + WebSocket"
        frontend -> gisEditor "Abre el plano"
        frontend -> assistant "Envía órdenes"
        gisEditor -> security "Propone maniobras y obras" "REST"
        security -> api "Deja pasar lo de esta máquina"
        api -> jobs "Encola trabajos"
        api -> operationStore "Registra estados y consulta el monitor por espacio"
        api -> custody "Registra la ejecución fuente"
        api -> normativa "Consulta y actualiza la biblioteca"
        custody -> engine "Entrega la copia fija"
        custody -> vnr "Entrega el paquete VNR custodiado"
        vnr -> engine "Exporta al modelo común"
        jobs -> engine "Ejecuta en carril engine"
        jobs -> nativeRunner "Ejecuta en carril powerfactory"
        engine -> dgs "Escribe modelo con esquema versionado"
        dgs -> workspaceStore "Publica DGS, validación y manifiesto"
        dgs -> nativeRunner "Entrega el DGS validado"
        nativeRunner -> oracle "Solicita preflight informativo"
        oracle -> nativeRunner "Devuelve avisos; la importacion continua"
        nativeRunner -> powerfactory "Plan JSON / API nativa"
        powerfactory -> nativeRunner "Informe JSON y lectura posterior"
        nativeRunner -> workspaceStore "Guarda planes, informes y vínculo"
        nativeRunner -> calibration "Calibra con la máxima coincidente"
        nativeRunner -> studies "Corre los estudios"
        nativeRunner -> twin "Captura acción y copia del estado"
        calibration -> optimizer "Entrega la red calibrada"
        optimizer -> planning "Aporta alternativas"
        studies -> reports "Entrega casos y flujos guardados"
        reports -> workspaceStore "Publica Word, PDF y libro"
        planning -> workspaceStore "Publica formatos y entregables"
        planning -> pit "Comparte red, costos e informes"
        planning -> vad "Comparte red, demanda y trazas reales"
        normativa -> planning "Reglas vigentes y citadas"
        normativa -> pit "Reglas vigentes y citadas"
        normativa -> vad "Reglas vigentes y citadas"
        pit -> workspaceStore "Publica el expediente del PIT"
        vad -> workspaceStore "Publica el estudio del VAD y los formatos del VNR"
        twin -> episodeStore "Persiste episodio y métricas"
        episodeStore -> twin "Provee muestras entrenables"
        episodeStore -> bench "Datos de referencia desidentificados"
        twin -> optimizer "Evalúa candidatos"
        twin -> modelGovernance "Registra candidatos"
        forecast -> modelGovernance "Registra candidatos sin promover"
        optimizer -> assistant "Entrega propuestas con límites"
        assistant -> api "Ejecuta mediante endpoints existentes tras confirmar"
        assistant -> llm "Pide inferencia local"
        assistant -> modelGovernance "Consulta el modelo en uso"
        assistant -> operationStore "Consulta avances e informes sin activar pesos"
        assistant -> normativa "Consulta la norma con su cita"
        mcp -> assistant "Usa las lecturas del proyecto"
        tooling -> modelGovernance "Entrena y mide candidatos"
        workspaceStore -> frontend "Sirve resultados y entregables"
        workspaceStore -> cloudConn "Entrega expedientes cerrados"
        cloudConn -> nube "Sube, comparte y vigila cambios"
        cloudConn -> mailer "Entrega el enlace privado del expediente"
        mailer -> correo "Envía con recibo"

        // ------------------------------------------------------------------ relaciones entre componentes
        cmpInterfaz -> cmpWeb "Llama a la API"
        cmpInterfazConversion -> cmpInterfaz "Usa el cliente de la API"
        cmpInterfazEstudios -> cmpInterfaz "Usa el cliente de la API"
        cmpInterfazRegulatorio -> cmpInterfaz "Usa el cliente de la API"
        cmpInterfazNube -> cmpInterfaz "Usa el cliente de la API"
        cmpInterfazAsistente -> cmpInterfaz "Usa el cliente de la API"
        cmpInterfazPruebas -> cmpInterfaz "Prueba sin navegador"
        cmpWeb -> cmpNube "Sube expedientes"
        cmpWeb -> cmpEntrada "Carga y convierte"
        cmpWeb -> cmpNormativa "Consulta la biblioteca"
        cmpWeb -> cmpPit "Encola el diagnóstico y el expediente"
        cmpWeb -> cmpVadVnr "Encola el estudio del VAD y el VNR"
        cmpVnr -> cmpEntrada "Puente al modelo común"
        cmpFachadas -> cmpVnr "Órdenes del VNR"
        cmpEntrada -> cmpReconstruccion "Datos de la fuente"
        cmpReconstruccion -> cmpModelo "Red completada"
        cmpModelo -> cmpConversion "Red con reglas"
        cmpConversion -> cmpSalida "Red comprobada"
        cmpSalida -> cmpEnlacePf "DGS validado"
        cmpEnlacePf -> cmpGuiones "Turno exclusivo"
        cmpGuiones -> cmpDemanda "Calibra"
        cmpDemanda -> cmpObras "Red calibrada"
        cmpObras -> cmpEstudios "Obras aplicadas"
        cmpEstudios -> cmpInformes "Casos guardados"
        cmpObras -> cmpPide "Alternativas"
        cmpPide -> cmpPit "Base común"
        cmpPide -> cmpVadVnr "Base común"
        cmpNormativa -> cmpPit "Reglas citadas"
        cmpNormativa -> cmpVadVnr "Reglas citadas"
        cmpNormativa -> cmpPide "Reglas citadas"
        cmpNormativa -> cmpAsisRag "Corpus normativo"
        cmpGuiones -> cmpGemelo "Episodios"
        cmpGemelo -> cmpGobierno "Registra candidatos"
        cmpHerrModelos -> cmpGobierno "Entrena"
        cmpGemelo -> cmpBench "Datos de referencia"
        cmpGobierno -> cmpAsisNucleo "Modelo en uso"
        cmpAsisNucleo -> cmpAsisModelos "Interpreta órdenes"
        cmpAsisNucleo -> cmpAsisRag "Responde con citas"
        cmpAsisDatos -> cmpAsisModelos "Entrena"

        // ------------------------------------------------------------------ despliegue
        local = deploymentEnvironment "Local" {
            workstation = deploymentNode "Estación Windows" "Equipo local del operador" "Windows" {
                browser = infrastructureNode "Navegador" "http://127.0.0.1:8765"
                python = deploymentNode "Proceso web" "API, colas, motor e IA" "CPython 3.12" {
                    containerInstance api
                    containerInstance security
                    containerInstance jobs
                    containerInstance custody
                    containerInstance cloudConn
                    containerInstance mailer
                    containerInstance vnr
                    containerInstance engine
                    containerInstance oracle
                    containerInstance dgs
                    containerInstance calibration
                    containerInstance optimizer
                    containerInstance studies
                    containerInstance reports
                    containerInstance planning
                    containerInstance normativa
                    containerInstance pit
                    containerInstance vad
                    containerInstance twin
                    containerInstance forecast
                    containerInstance assistant
                    containerInstance modelGovernance
                    containerInstance workspaceStore
                    containerInstance episodeStore
                    containerInstance operationStore
                }
                pfProc = deploymentNode "Intérprete de PowerFactory" "Guiones y servidor que se cierra sin órdenes" "Python de DIgSILENT" {
                    containerInstance nativeRunner
                }
                cli = deploymentNode "Línea de órdenes" "Herramientas, entrenamientos y MCP" "CPython 3.12" {
                    containerInstance tooling
                    containerInstance mcp
                    containerInstance bench
                }
                ui = deploymentNode "Interfaz compilada" "frontend/dist" "Ficheros estáticos" {
                    containerInstance frontend
                    containerInstance gisEditor
                }
                pf = infrastructureNode "DIgSILENT PowerFactory" "Proceso nativo exclusivo, 2021 o posterior, con tools/pf_servidor.py"
                sqlServer = infrastructureNode "SQL Server Express" "Restaura copias .bak de VNR-GIS"
                ollama = infrastructureNode "Ollama" "Inferencia local del asistente, opcional"
                gpu = infrastructureNode "GPU CUDA" "Un turno para la suite y los entrenamientos"
            }
        }
    }

    views {
        systemContext conversor "SystemContext" "Quién usa el sistema y con qué sistemas se relaciona" {
            include *
            autoLayout lr
        }

        container conversor "Containers" "Interfaz, API, motor, guiones de DIgSILENT, IA y almacenes" {
            include *
            autoLayout lr
        }

        component frontend "Componentes-Interfaz" "Interfaz web" {
            include *
            autoLayout lr
        }

        component api "Componentes-Web" "API web, nube y correo" {
            include *
            autoLayout lr
        }

        component engine "Componentes-Motor" "Motor de conversión y adaptador VNR-GIS" {
            include *
            autoLayout lr
        }

        component nativeRunner "Componentes-DIgSILENT" "Enlace y guiones de DIgSILENT" {
            include *
            autoLayout lr
        }

        component planning "Componentes-Planeamiento" "PIDE y planeamiento" {
            include *
            autoLayout lr
        }

        component pit "Componentes-PIT" "Plan de inversiones en transmisión" {
            include *
            autoLayout lr
        }

        component vad "Componentes-VAD" "Estudio de costos del VAD y VNR" {
            include *
            autoLayout lr
        }

        component normativa "Componentes-Normativa" "Biblioteca normativa y fuentes de la empresa" {
            include *
            autoLayout lr
        }

        component cloudConn "Componentes-Nube" "Conector de nube" {
            include *
            autoLayout lr
        }

        component bench "Componentes-Benchmarks" "Benchmarks anonimizados" {
            include *
            autoLayout lr
        }

        component twin "Componentes-Gemelo" "Gemelo digital y benchmarks" {
            include *
            autoLayout lr
        }

        component modelGovernance "Componentes-Gobierno" "Gobierno de modelos" {
            include *
            autoLayout lr
        }

        component assistant "Componentes-Asistente" "Asistente y su equipo" {
            include *
            autoLayout lr
        }

        component tooling "Componentes-Herramientas" "Herramientas de órdenes" {
            include *
            autoLayout lr
        }

        dynamic conversor "Conversion" "De la fuente al DGS validado" {
            fuentes -> api "1. Ingresar fuente"
            api -> custody "2. Custodiar y fijar huellas"
            custody -> engine "3. Adaptar, reconstruir y modelar"
            engine -> dgs "4. Escribir con esquema versionado"
            dgs -> workspaceStore "5. Validar y publicar atómicamente"
            workspaceStore -> frontend "6. Mostrar y descargar"
            autoLayout lr
        }

        dynamic conversor "PowerFactory" "Del DGS a la aceptación nativa y los estudios" {
            frontend -> security "1. Solicitar operación"
            security -> api "2. Comprobar origen y token"
            api -> jobs "3. Encolar en powerfactory"
            jobs -> nativeRunner "4. Lanzar proceso aislado"
            nativeRunner -> oracle "5. Consultar preflight pandapower"
            oracle -> nativeRunner "6. Informar avisos sin omitir DGS"
            nativeRunner -> powerfactory "7. Importar, verificar, calibrar y estudiar"
            powerfactory -> nativeRunner "8. Guardar, reabrir, releer y recalcular"
            nativeRunner -> workspaceStore "9. Conservar informe y vínculo"
            workspaceStore -> frontend "10. Presentar evidencia"
            autoLayout lr
        }

        dynamic conversor "Inteligencia" "De una acción aceptada a una propuesta confirmada" {
            nativeRunner -> twin "1. Capturar episodio"
            twin -> episodeStore "2. Persistir evidencia"
            episodeStore -> twin "3. Entrenar y evaluar modelos"
            twin -> optimizer "4. Ordenar alternativas"
            optimizer -> assistant "5. Explicar propuesta"
            operador -> assistant "6. Confirmar o rechazar"
            assistant -> api "7. Ejecutar por la API existente"
            autoLayout lr
        }

        deployment conversor "Local" "Deployment" "Despliegue local y límites de proceso" {
            include *
            autoLayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #1d5d9b
                color #ffffff
            }
            element "External" {
                background #dceafa
                color #11263d
            }
            element "Web" {
                background #d9f1ee
                color #11263d
            }
            element "API" {
                background #e1f1e3
                color #11263d
            }
            element "Queue" {
                shape Pipe
                background #e1f1e3
                color #11263d
            }
            element "Engine" {
                background #e1f1e3
                color #11263d
            }
            element "Native" {
                background #fce8d4
                color #11263d
            }
            element "AI" {
                background #ede4f7
                color #11263d
            }
            element "Store" {
                shape Cylinder
                background #f4f7fa
                color #11263d
            }
            element "en implementación" {
                border dashed
                opacity 80
            }
            relationship "Relationship" {
                color #526579
                thickness 2
                routing Orthogonal
            }
        }
    }

    configuration {
        scope softwaresystem
    }
}
