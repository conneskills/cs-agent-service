# ADR-003: Integración de Paradigmas Ultra-Ligeros (Inspirado en ZeroClaw) para Nodos de Baja Latencia

**Status:** Proposed  
**Date:** 2026-02-22  
**Autores:** Aldemar  
**Relacionado:** ADR-001-arquitectura-agentes.md, ADR-002-mejoras-slm-orchestration.md  

---

## Contexto

El **ADR-001** estableció la base del sistema usando Python y Google ADK en Cloud Run.
El **ADR-002** introdujo el routing inteligente y el uso de SLMs (Azure OpenAI) para reducir drásticamente los costos de inferencia y mantener la capacidad de *scale-to-zero* de Cloud Run.

Sin embargo, el tiempo de inicialización (*cold start*) de un contenedor Python con el framework ADK sigue siendo de varios segundos, y su huella en memoria (RAM) oscila en el orden de cientos de megabytes. Para ciertas tareas operativas, de altísima frecuencia y requerimientos de tiempo real (parsing masivo, formateo de logs, clasificación inmediata o health-checks semánticos), este *overhead* de la infraestructura Python es subóptimo.

Durante la investigación de tecnologías emergentes, se identificó **ZeroClaw** — un *kernel* de agentes escrito 100% en Rust. ZeroClaw demuestra que es posible ejecutar agentes autónomos con un binario de apenas ~3.4MB y un consumo de 5MB de RAM, reduciendo el cold start a milisegundos.

Este ADR propone incorporar los paradigmas arquitectónicos de ZeroClaw al ecosistema de `cs-agent-service` para crear una arquitectura de dos niveles (Tiers).

---

## Decisión 1: Arquitectura de Agentes en Dos Niveles (Two-Tier Architecture)

### Principio Clave
No todos los agentes necesitan el peso de un framework completo en Python (ADK). Dividiremos los tipos de despliegues en dos ecosistemas que se comunican de forma transparente a través de la red (A2A).

1.  **Tier 1: Nodos Cognitivos (Python / Google ADK)**
    *   **Propósito:** Razonamiento complejo, orquestador principal (routing), workflows de múltiples pasos, RAG denso.
    *   **Infra:** Cloud Run estándar, latencia de arranque aceptable (2-5 segundos).
2.  **Tier 2: Nodos Tácticos (Rust / Paradigma ZeroClaw)**
    *   **Propósito:** Tareas atómicas, determinísticas y de latencia ultra baja. Parsing, extracción de entidades, validación de reglas, ejecución de herramientas peligrosas (código) en sandboxes rígidos.
    *   **Infra:** Binario compilado (Rust) en Cloud Run, arranque casi instantáneo (<50ms), consumo de memoria marginal.

```mermaid
graph TD
    User([Usuario / Trigger]) --> Router[Orquestador ADK (Python)]
    Router -- "Razonamiento Complejo" --> ADK_Ag[Agentes de Dominio ADK]
    Router -- "Tarea Simple / Extracción" --> ZC_Ag[Agentes Tácticos ZeroClaw]
    Router -- "Ejecución de Código" --> ZC_Ag
    
    subgraph Tier 1: Python
        Router
        ADK_Ag
    end
    
    subgraph Tier 2: Rust / ZeroClaw
        ZC_Ag
    end
```

---

## Decisión 2: Seguridad y Sandboxing Estricto (Workspace Scoping)

En el ADR-002 se plantea usar SLMs (ej. Qwen-Coder) para escribir scripts que el agente luego ejecuta. Un contenedor Python genérico expone una mayor superficie de ataque si el LLM genera código hostil.

**ZeroClaw Approach:**
Adoptaremos el modelo de seguridad "Secure by Default" de ZeroClaw para los Nodos Tácticos:
*   **Workspace Scoping:** El agente tiene acceso **únicamente** a un directorio virtual efímero (`/workspace`). Carece de acceso de lectura a `/etc` o variables de entorno del host.
*   **Allow-lists de comandos:** La herramienta de ejecución de consola (`CommandTool`) solo permite comandos explícitamente registrados, bloqueando operaciones de red arbitrarias (`curl`, `wget`) a menos que estén *whitelisted*.

### Idea de Código (Inspiración Rust)
Ejemplo de configuración de una herramienta en un entorno seguro tipo ZeroClaw:

```rust
// Ejemplo en Rust de una Tool segura basada en Traits
use zeroclaw::tools::{Tool, ToolContext, ExecutionResult};

pub struct SandboxCodeExecutor {
    workdir: String,
    allowed_commands: Vec<String>,
}

impl Tool for SandboxCodeExecutor {
    fn name(&self) -> &str {
        "execute_python_script"
    }

    fn apply(&self, input: &str, ctx: &ToolContext) -> ExecutionResult {
        // Validación de seguridad estricta antes de la ejecución
        if !self.is_safe_code(input) {
            return ExecutionResult::Error("Security Policy Violation".into());
        }
        
        // Ejecución en un entorno contenido (chroot / namespace limitado)
        zeroclaw::sandbox::run_in_jail(&self.workdir, "python3", &["-c", input])
    }
}
```

---

## Decisión 3: Memoria Vectorial Embebida Ligera

Actualmente se depende de la infraestructura del Registry o de bases de datos externas pesadas para operaciones de memoria persistente. Para los "Nodos Tácticos", o incluso para abaratar el uso en los agentes Python pequeños, adoptaremos el modelo de memoria de ZeroClaw.

**Decisión:** Utilizar SQLite con extensiones vectoriales (`sqlite-vec` o equivalente) para la memoria efímera de corto plazo (Short-Term Memory).

*   **Ventaja:** Elimina la latencia de red (`http://...`) hacia la base de datos central en cada *recall* de memoria. El agente maneja su propio vector-store como un archivo local (`memory.db`), que se sincroniza subiendo a un bucket local al finalizar la sesión.

### Idea de Código (Memoria basada en SQLite)

```rust
// Ejemplo de sistema de memoria integrado tipo ZeroClaw
use zeroclaw::memory::{MemoryStore, VectorDB};
use sqlite_vec::SQLiteVectorIndex;

pub struct EphemeralSQLiteMemory {
    db: SQLiteVectorIndex,
}

impl MemoryStore for EphemeralSQLiteMemory {
    fn store(&mut self, text: &str, embedding: &[f32]) {
        self.db.insert_vector(embedding, text.to_string());
    }

    fn recall(&self, query_embedding: &[f32], limit: usize) -> Vec<String> {
        self.db.search_nearest(query_embedding, limit)
    }
    
    fn forget(&mut self, text_id: &str) {
        self.db.delete(text_id);
    }
}
```

---

## Decisión 4: Diseño Basado en Traits / Interfaces Unificadas

El **ADR-002** introdujo el `Unified Tool Calling` en Python. Este es un principio fundamental que refleja el uso de "Traits" (interfaces) de Rust presentes en ZeroClaw.

Cualquier componente (llámese `Provider`, `Memory`, `Tool` o `Channel`) debe implementar una única interfaz. Esto permite que cambiar de un proveedor OpenAI a Ollama, o de memoria en RAM a memoria en SQLite, sea un simple cambio en el archivo de configuración, **sin alterar la lógica central del agente**.

### Idea de Código (El "Trait" Provider)

```rust
#[async_trait]
pub trait ModelProvider {
    /// Genera una respuesta basada en el sistema, historial y tools disponibles
    async fn generate(&self, 
        system_prompt: &str, 
        history: &[Message], 
        tools: &[Arc<dyn Tool>]
    ) -> ProviderResponse;
}

// Implementación transparente e intercambiable
pub struct AzureOpenAIProvider { ... }
pub struct OllamaLocalProvider { ... }

// El kernel del agente solo conoce el trait
pub struct ZeroClawAgent {
    provider: Box<dyn ModelProvider>,
    memory: Box<dyn MemoryStore>,
    tools: Vec<Box<dyn Tool>>,
}
```

---

## Consecuencias y Siguientes Pasos

### Beneficios
1.  **Eficiencia de Costos y Latencia:** Los nodos escritos en Rust (inspiración ZeroClaw) arrancarán instantáneamente, haciendo que Cloud Run facture centavos por miles de ejecuciones simples.
2.  **Seguridad Real:** Ejecutar código generado por el LLM en un binario de bajo nivel diseñado para seguridad (scoping) reduce los vectores de ataque.
3.  **Filosofía Modular:** Afianza el `Unified Tool Calling` propuesto en el ADR-002, demostrando que implementaciones *pluggables* (vía traits/interfaces) son la mejor práctica en la industria.

### Siguientes Pasos
- [ ] Explorar un caso de uso piloto ("Proof of Concept") de un servicio en Cloud Run que resuelva consultas triviales (Parsing o RAG ligero) usando un binario compilado en Rust.
- [ ] Validar la extensión `sqlite-vec` en Python como punto intermedio para replicar la eficiencia de la "memoria local" sin abandonar la pila ADK inmediata.
