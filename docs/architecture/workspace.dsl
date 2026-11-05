workspace "ConverterSmartGrid" "Arquitectura C4 navegable desde fuentes hasta entregables" {
    model {
        operador = person "Operador electrico" "Selecciona el alcance, confirma planes y decide con evidencia." {
            url "http://127.0.0.1:8765/"
            tags "Person"
        }

        fuentes = softwareSystem "Fuentes electricas" "TXT CYMDIST, MDB/Access, VNR-GIS y libros de medicion." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/lectura-de-las-dos-disposiciones/src/convertersmartgrid/sources"
            tags "External"
        }

        powerfactory = softwareSystem "DIgSILENT PowerFactory 2024" "Motor nativo propietario para aceptar, calibrar y estudiar la red." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/tools/powerfactory_acceptance.py"
            tags "Native"
        }

        conversor = softwareSystem "ConverterSmartGrid" "Convierte, valida, acepta y documenta redes de distribucion." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/README.md"

            frontend = container "Frontend web" "Interfaz, seleccion, progreso, resultados y confirmacion." "React + TypeScript" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/tree/lectura-de-las-dos-disposiciones/frontend/src"
                tags "Web"
            }

            api = container "API y orquestacion" "Expone REST/WebSocket, valida pedidos y coordina trabajos." "FastAPI / Python 3.12" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/web/app.py"
                tags "API"
            }

            jobs = container "Colas de trabajo" "Serializa engine, powerfactory y asistente; el carril control solo cancela." "Python threads/queues" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/web/jobs.py"
                tags "Queue"
            }

            custody = container "Custodia de fuentes" "Crea source runs inmutables con alcance y huellas." "Filesystem + SHA-256" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/web/source_runs.py"
                tags "Store"
            }

            engine = container "Motor de conversion" "Adapta, reconstruye, aplica reglas y construye FeederModel." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/batch.py"
                tags "Engine"
            }

            oracle = container "Preflight consultivo" "Informa conectividad y convergencia antes de importar a PowerFactory; sus avisos no omiten el DGS." "pandapower" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/oraculo.py"
                tags "Engine"
            }

            dgs = container "Escritor y validador DGS" "Escribe con esquema versionado, valida y publica atomicamente." "Python + DGS schema" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/dgs.py"
                tags "Engine"
            }

            nativeRunner = container "Ejecutor PowerFactory" "Lanza tools/*_pf.py con plan JSON y turno exclusivo del motor; recibe informe JSON. Calibra, aplica obras y corre estudios." "Python 3.12 / PowerFactory API" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/lectura-de-las-dos-disposiciones/src/convertersmartgrid/web/services.py"
                tags "Native"
            }

            twin = container "Gemelo digital" "Captura episodios y ofrece oraculos radial, mallado, PINN-GNN y GRU." "Python + PyTorch" {
                url "file:///D:/converter/ConverterSmartGrid/src/convertersmartgrid/digital_twin"
                tags "AI"
            }

            optimizer = container "PIDE y optimizacion" "Ordena alternativas con escalera, Optuna, GA y NSGA-II; DIgSILENT confirma." "Python + NumPy + Optuna" {
                url "file:///D:/converter/ConverterSmartGrid/src/convertersmartgrid/digital_twin/evolutivo.py"
                tags "AI"
            }

            assistant = container "Asistente" "Interpreta ordenes, muestra el plan y ejecuta solo tras confirmacion." "Reglas + codificador de ordenes + Ollama local" {
                url "file:///D:/converter/ConverterSmartGrid/src/convertersmartgrid/asistente"
                tags "AI"
            }

            workspaceStore = container "Espacios y entregables" "Conserva entradas, planes, DGS, informes y descargas." "Filesystem" {
                url "http://127.0.0.1:8765/"
                properties {
                    "Local path" "output/web"
                }
                tags "Store"
            }

            episodeStore = container "Buffer de episodios" "JSON inmutable, snapshots y indice SQLite." "JSON + SQLite" {
                url "file:///D:/converter/ConverterSmartGrid/src/convertersmartgrid/digital_twin/buffer.py"
                tags "Store"
            }
            operationStore = container "Diario de operaciones y evidencia" "Estados por espacio, contexto inicial e informes custodiados; no promueve modelos." "SQLite + JSON + SHA-256" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/convertersmartgrid/asistente/observacion.py" // legado-058: ruta real del checkout existente
                tags "Store"
            }

            security = container "Puerta de seguridad" "Host, Origin, token de sesion, politica de contenido, edicion y salidas a la red." "Middleware ASGI" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/convertersmartgrid/web/seguridad.py" // legado-058: ruta real del checkout existente
                tags "API"
            }

            reports = container "Informes" "Word, PDF, imagenes y libro Excel de estudio y factibilidad, con lo guardado por la web." "python-docx + COM" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/convertersmartgrid/informes.py" // legado-058: ruta real del checkout existente
                tags "Engine"
            }

            planning = container "Planeamiento" "Largo plazo y PIDE: mercado, costos oficiales, formatos y entregables por modulo." "Python" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/convertersmartgrid/estudio_planeamiento.py" // legado-058: ruta real del checkout existente
                tags "Engine"
            }

            modelGovernance = container "Gobierno de modelos" "Registro de candidatos, puertas, puntero en uso, guardia de GPU y ciclo de aprendizaje." "Python + JSON + SHA-256" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/convertersmartgrid/model_registry.py" // legado-058: ruta real del checkout existente
                tags "AI"
            }

            mcp = container "MCP local" "Las lecturas del asistente para un cliente de esta maquina: solo stdio y solo lectura." "Python + MCP (opcional)" {
                url "file:///D:/converter/ConversorIGEA_DGS/tools/mcp_conversor.py" // legado-058: ruta real del checkout existente
                tags "AI"
            }
        }

        operador -> frontend "Usa" "HTTP local"
        fuentes -> api "Entrega archivos o rutas" "Upload/path"
        frontend -> security "Invoca y consulta" "REST + WebSocket"
        security -> api "Deja pasar lo de esta maquina"
        api -> jobs "Encola trabajos"
        api -> operationStore "Registra estados y consulta el monitor por espacio"
        assistant -> operationStore "Consulta avances e informes sin activar pesos"
        api -> custody "Registra la ejecucion fuente"
        custody -> engine "Entrega snapshot vinculado"
        jobs -> engine "Ejecuta en carril engine"
        engine -> dgs "Escribe modelo con esquema versionado"
        nativeRunner -> oracle "Solicita preflight informativo"
        oracle -> nativeRunner "Devuelve avisos; la importacion continua"
        dgs -> workspaceStore "Publica DGS, validacion y manifiesto"
        jobs -> nativeRunner "Ejecuta en carril powerfactory"
        nativeRunner -> powerfactory "Plan JSON / API nativa"
        powerfactory -> nativeRunner "Informe JSON y lectura posterior"
        nativeRunner -> workspaceStore "Guarda planes, informes y binding"
        nativeRunner -> twin "Captura accion y snapshot"
        twin -> episodeStore "Persiste episodio y metricas"
        episodeStore -> twin "Provee muestras entrenables"
        twin -> optimizer "Evalua candidatos"
        optimizer -> assistant "Entrega propuestas con limites"
        operador -> assistant "Confirma o rechaza"
        assistant -> api "Ejecuta mediante endpoints existentes"
        workspaceStore -> frontend "Sirve resultados y entregables"
        nativeRunner -> reports "Entrega casos y flujos guardados"
        reports -> workspaceStore "Publica Word, PDF y libro"
        optimizer -> planning "Aporta alternativas"
        nativeRunner -> planning "Mide cada periodo del horizonte"
        planning -> workspaceStore "Publica formatos y entregables"
        twin -> modelGovernance "Registra candidatos"
        assistant -> modelGovernance "Consulta el modelo en uso"
        mcp -> assistant "Usa las lecturas del proyecto"

        local = deploymentEnvironment "Local" {
            workstation = deploymentNode "Estacion Windows" "Equipo local del operador" "Windows" {
                browser = infrastructureNode "Navegador" "http://127.0.0.1:8765"
                python = deploymentNode "Python 3.12" "Motor, API, colas e IA" "CPython" {
                    containerInstance api
                    containerInstance jobs
                    containerInstance custody
                    containerInstance engine
                    containerInstance oracle
                    containerInstance dgs
                    containerInstance nativeRunner
                    containerInstance twin
                    containerInstance optimizer
                    containerInstance assistant
                    containerInstance workspaceStore
                    containerInstance episodeStore
                    containerInstance operationStore
                    containerInstance security
                    containerInstance reports
                    containerInstance planning
                    containerInstance modelGovernance
                    containerInstance mcp
                }
                ui = deploymentNode "Frontend compilado" "frontend/dist" "Static files" {
                    containerInstance frontend
                }
                pf = infrastructureNode "PowerFactory 2024" "Proceso nativo exclusivo, con tools/pf_servidor.py"
                sqlServer = infrastructureNode "SQL Server Express" "Restaura copias .bak de VNR-GIS"
                ollama = infrastructureNode "Ollama/GPU opcional" "Inferencia local del asistente"
            }
        }
    }

    views {
        systemContext conversor "SystemContext" "Quien usa el sistema y con que sistemas se relaciona" {
            include *
            autoLayout lr
        }

        container conversor "Containers" "Frontend, backend, motores, IA y almacenes" {
            include *
            autoLayout lr
        }

        dynamic conversor "Conversion" "De la fuente al DGS validado" {
            fuentes -> api "1. Ingresar fuente"
            api -> custody "2. Custodiar y fijar huellas"
            custody -> engine "3. Adaptar, reconstruir y modelar"
            engine -> dgs "4. Escribir con esquema versionado"
            dgs -> workspaceStore "5. Validar y publicar atomicamente"
            workspaceStore -> frontend "6. Mostrar y descargar"
            autoLayout lr
        }

        dynamic conversor "PowerFactory" "Del DGS a la aceptacion nativa y los estudios" {
            frontend -> security "1. Solicitar operacion"
            security -> api "2. Comprobar origen y token"
            api -> jobs "3. Encolar en powerfactory"
            jobs -> nativeRunner "4. Lanzar proceso aislado"
            nativeRunner -> oracle "5. Consultar preflight pandapower"
            oracle -> nativeRunner "6. Informar avisos sin omitir DGS"
            nativeRunner -> powerfactory "7. Importar/verificar/calibrar/estudiar"
            powerfactory -> nativeRunner "8. Guardar, reabrir, releer y recalcular"
            nativeRunner -> workspaceStore "9. Conservar informe y binding"
            workspaceStore -> frontend "10. Presentar evidencia"
            autoLayout lr
        }

        dynamic conversor "Inteligencia" "De una accion aceptada a una propuesta confirmada" {
            nativeRunner -> twin "1. Capturar episodio"
            twin -> episodeStore "2. Persistir evidencia"
            episodeStore -> twin "3. Entrenar/evaluar modelos"
            twin -> optimizer "4. Ordenar alternativas"
            optimizer -> assistant "5. Explicar propuesta"
            operador -> assistant "6. Confirmar o rechazar"
            assistant -> api "7. Ejecutar por API existente"
            autoLayout lr
        }

        deployment conversor "Local" "Deployment" "Despliegue local y limites de proceso" {
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
