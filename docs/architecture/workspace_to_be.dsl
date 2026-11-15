workspace extends workspace.dsl {

    // C4 TO-BE de ConverterSmartGrid (034:RF-34, F-20 del Plan Maestro V1, 2026-11-14).
    // Extiende el modelo AS-IS de workspace.dsl: no redefine ninguno de sus elementos, solo declara las fronteras
    // nuevas o cambiadas, y cada elemento nuevo cita el ADR de docs/architecture/adr/ que lo decide (034:RF-37).
    // Lo que existe, o tiene spec aprobada en implementación, sigue en el AS-IS (Aclaración de 034:RF-31).
    // Los enlaces se fijan a la revisión 00d30651, base de esta TO-BE; nunca a main ni a una ruta de la máquina.
    // Limitación: sin Java ni Docker en la máquina, el DSL no se ha validado con Structurizr; se valida con el AS-IS.

    model {
        oda = softwareSystem "Convertidor DWG del operador" "Convertidor de DXF a DWG que el operador ya tiene instalado (ODA File Converter u otro que declare la configuración); el conversor solo lo detecta, no lo distribuye." {
            url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/00d306517047c7588f18adcdc1a017becccfb175/specs/107-plan-de-inversiones-en-transmision/spec.md"
            tags "External,TO-BE"
            properties {
                "ADR" "ADR-006"
                "Estado" "pendiente"
            }
        }

        !element conversor {
            cadWriter = container "Planos y unifilares en DXF" "Escribe en DXF los planos A3 y los unifilares de cada alternativa y año; el DXF es la entrega garantizada y el DWG, un añadido si hay convertidor." "Python + ezdxf" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/00d306517047c7588f18adcdc1a017becccfb175/specs/107-plan-de-inversiones-en-transmision/spec.md"
                tags "Engine,TO-BE"
                properties {
                    "ADR" "ADR-006"
                    "Spec" "107, 072"
                }
            }
        }

        !element api {
            cmpFachadaServicios = component "Fachada de servicios" "web/services.py como fachada estable: delega cada caso de uso y no gana lógica; se retira cuando no quede consumidor." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/00d306517047c7588f18adcdc1a017becccfb175/specs/002-arquitectura-por-capas/tasks.md"
                tags "API,TO-BE"
                properties {
                    "ADR" "ADR-002"
                    "Spec" "002 T7, T9"
                }
            }
            cmpCasosDeUso = component "Casos de uso por subsistema" "Un módulo de aplicación por caso de uso, sacado de la fachada de uno en uno, con respuestas REST y DGS idénticos byte a byte." "Python" {
                url "https://github.com/Mac-Tapia/ConverterSmartGrid/blob/00d306517047c7588f18adcdc1a017becccfb175/specs/002-arquitectura-por-capas/spec.md"
                tags "API,TO-BE"
                properties {
                    "ADR" "ADR-002"
                    "Spec" "002"
                }
            }
        }

        // ------------------------------------------------------------------ relaciones nuevas
        cmpWeb -> cmpFachadaServicios "Llama como hasta hoy"
        cmpFachadaServicios -> cmpCasosDeUso "Delega, un caso de uso por commit"
        cmpCasosDeUso -> cmpEntrada "Carga y convierte por los puertos"
        cmpCasosDeUso -> cmpEstudios "Lanza estudios por el carril de su cola"
        planning -> cadWriter "Pide planos A3 de las obras"
        pit -> cadWriter "Pide unifilares por alternativa y año"
        cadWriter -> workspaceStore "Publica el DXF, de forma duradera, en el expediente"
        cadWriter -> oda "Convierte a DWG solo si lo detecta; si no, avisa cómo obtenerlo"
        gisEditor -> cmpSalida "Lee el GeoJSON del mismo modelo; sin grafo propio"
    }

    views {
        container conversor "ToBe-Contenedores" "TO-BE: contenedores con las fronteras nuevas (DXF) y sus ADR" {
            include *
            autoLayout lr
        }

        component api "ToBe-Componentes-Web" "TO-BE: la fachada de servicios delega en casos de uso (ADR-002)" {
            include *
            autoLayout lr
        }

        component dgs "ToBe-Componentes-Salida" "TO-BE: el editor del plano lee la salida del mismo modelo (ADR-009)" {
            include *
            autoLayout lr
        }

        styles {
            element "TO-BE" {
                border dashed
                stroke #b4591d
                strokeWidth 4
            }
        }
    }
}
