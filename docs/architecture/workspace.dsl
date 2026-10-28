workspace "Conversor IGEA-DGS" "Arquitectura C4 navegable desde fuentes hasta entregables" {
    model {
        operador = person "Operador electrico" "Selecciona el alcance, confirma planes y decide con evidencia." {
            url "http://127.0.0.1:8765/"
            tags "Person"
        }

        fuentes = softwareSystem "Fuentes electricas" "TXT IGEA/CYMDIST, MDB/Access, VNR-GIS y libros de medicion." {
            url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/tree/lectura-de-las-dos-disposiciones/src/igea_dgs/sources"
            tags "External"
        }

        powerfactory = softwareSystem "DIgSILENT PowerFactory 2024" "Motor nativo propietario para aceptar, calibrar y estudiar la red." {
            url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/tools/powerfactory_acceptance.py"
            tags "Native"
        }

        conversor = softwareSystem "Conversor IGEA-DGS" "Convierte, valida, acepta y documenta redes de distribucion." {
            url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/README.md"

            frontend = container "Frontend web" "Interfaz, seleccion, progreso, resultados y confirmacion." "React + TypeScript" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/tree/lectura-de-las-dos-disposiciones/frontend/src"
                tags "Web"
            }

            api = container "API y orquestacion" "Expone REST/WebSocket, valida pedidos y coordina trabajos." "FastAPI / Python 3.12" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/web/app.py"
                tags "API"
            }

            jobs = container "Colas de trabajo" "Serializa engine, powerfactory y asistente." "Python threads/queues" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/web/jobs.py"
                tags "Queue"
            }

            custody = container "Custodia de fuentes" "Crea source runs inmutables con alcance y huellas." "Filesystem + SHA-256" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/web/source_runs.py"
                tags "Store"
            }

            engine = container "Motor de conversion" "Adapta, reconstruye, aplica reglas y construye FeederModel." "Python" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/batch.py"
                tags "Engine"
            }

            oracle = container "Preflight consultivo" "Informa conectividad y convergencia antes de importar a PowerFactory; sus avisos no omiten el DGS." "pandapower" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/oraculo.py"
                tags "Engine"
            }

            dgs = container "Escritor y validador DGS" "Escribe con esquema versionado, valida y publica atomicamente." "Python + DGS schema" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/dgs.py"
                tags "Engine"
            }

            nativeRunner = container "Ejecutor PowerFactory" "Lanza tools/*_pf.py con plan JSON y recibe informe JSON." "Python 3.12 / PowerFactory API" {
                url "https://github.com/Mac-Tapia/ConversorIGEA_DGS/blob/lectura-de-las-dos-disposiciones/src/igea_dgs/web/services.py"
                tags "Native"
            }

            twin = container "Gemelo digital" "Captura episodios y ofrece oraculos radial, mallado, PINN-GNN y GRU." "Python + PyTorch" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/igea_dgs/digital_twin"
                tags "AI"
            }

            optimizer = container "PIDE y optimizacion" "Evalua alternativas con GA, NSGA-II y evolucion diferencial." "Python + NumPy" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/igea_dgs/digital_twin/evolutivo.py"
                tags "AI"
            }

            assistant = container "Asistente" "Interpreta ordenes, muestra el plan y ejecuta solo tras confirmacion." "Reglas + Transformer + Ollama local" {
                url "file:///D:/converter/ConversorIGEA_DGS/src/igea_dgs/asistente"
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
                url "file:///D:/converter/ConversorIGEA_DGS/src/igea_dgs/digital_twin/buffer.py"
                tags "Store"
            }
        }

        operador -> frontend "Usa" "HTTP local"
        fuentes -> api "Entrega archivos o rutas" "Upload/path"
        frontend -> api "Invoca y consulta" "REST + WebSocket"
        api -> jobs "Encola trabajos"
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
                }
                ui = deploymentNode "Frontend compilado" "frontend/dist" "Static files" {
                    containerInstance frontend
                }
                pf = infrastructureNode "PowerFactory 2024" "Proceso nativo exclusivo"
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
            frontend -> api "1. Solicitar operacion"
            api -> jobs "2. Encolar en powerfactory"
            jobs -> nativeRunner "3. Lanzar proceso aislado"
            nativeRunner -> oracle "4. Consultar preflight pandapower"
            oracle -> nativeRunner "5. Informar avisos sin omitir DGS"
            nativeRunner -> powerfactory "6. Importar/verificar/calibrar/estudiar"
            powerfactory -> nativeRunner "7. Guardar, reabrir, releer y recalcular"
            nativeRunner -> workspaceStore "8. Conservar informe y binding"
            workspaceStore -> frontend "9. Presentar evidencia"
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
