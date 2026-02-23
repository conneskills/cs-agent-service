# ADR-002: Mejoras de Arquitectura - SLM Orchestration y Routing Inteligente

**Status:** Proposed  
**Date:** 2026-02-20  
**Autores:** Aldemar  
**Basado en:** Análisis de papers arXiv:2506.02153 y arXiv:2511.21689  
**Relacionado:** ADR-001-arquitectura-agentes.md  

---

## Resumen Ejecutivo

Este documento propone mejoras al ADR-001 basadas en investigación de papers de NVIDIA Labs y análisis del protocolo AG-UI:

1. **"Small Language Models are the Future of Agentic AI"** (2025)
2. **"ToolOrchestra: Elevating Intelligence via Efficient Model and Tool Orchestration"** (2025)
3. **AG-UI Protocol** - Protocolo estándar para interacción agente-usuario

Las mejoras principales son:
- Adopción de **modelos híbridos SLM/LLM** para optimizar costo y performance
- **Orchestrator dedicado** (SLM 8B) para routing inteligente
- **Unified tool calling** para tools + modelos bajo una interfaz común
- **Métricas de eficiencia** y cost-aware routing
- **AG-UI** para interfaz usuario-agente con integración ADK nativa

---

## Contexto

### Limitaciones Identificadas en ADR-001

1. **Costo impredecible**: Todos los agentes usan LLMs grandes por defecto
2. **Sin routing inteligente**: LiteLLM hace routing estático, no basado en complejidad de tarea
3. **Falta de granularidad**: No distingue entre tasks simples (parsing, formateo) vs complejos (razonamiento)
4. **No hay métricas de eficiencia**: Solo métricas de funcionalidad, no de costo/latencia

### Papers de Referencia

| Paper | Insight Principal | Relevancia |
|-------|-------------------|------------|
| SLMs Future | SLMs (<10B) son suficientes para 80% de tasks agentic | Reduce costos 10-30x |
| ToolOrchestra | Orchestrator 8B supera a GPT-5 con 2.5x eficiencia | Arquitectura probada |

---

## Decisión 0: Estrategia de Deployment de SLMs

### Principio Clave: Preservar Scale-to-Zero

Cloud Run tiene una ventaja crítica: **costo cero cuando no se usa**. Cualquier decisión de arquitectura debe preservar esta característica.

### Análisis de Opciones

| Opción | Descripción | Costo Fijo | Scale to Zero | Latencia |
|--------|-------------|------------|---------------|----------|
| **A. Azure OpenAI SLMs** | SLMs como servicio (Phi-3, Qwen-Coder) | $0 | ✅ Mantiene | ~200-500ms |
| **B. vLLM en Cloud Run + GPU** | Self-hosted con GPU L4/T4 | ~$136-252/mes | ❌ Perdido | ~50-100ms |
| **C. Vertex AI (GCP)** | Modelos de Google (Gemma, etc.) | $0 | ✅ Mantiene | ~200-500ms |

### Decisión: Opción A - Azure OpenAI SLMs

**Razón:** Mantiene la eficiencia de Cloud Run (scale-to-zero) mientras reduce costos de inferencia 10-30x.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA DE COSTOS                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  CLOUD RUN (Agente)                                                    │
│  ─────────────────────                                                 │
│  Sin uso: $0                                                           │
│  En uso: ~$0.000024/vCPU-second + $0.0000024/GiB-second               │
│  Ejemplo: 100 tareas/día × 5s × 1 vCPU = ~$0.36/mes                   │
│                                                                         │
│  AZURE OPENAI SLMs (Vía LiteLLM)                                       │
│  ──────────────────────────────                                        │
│  Phi-3-mini (3.8B):    $0.0001/1K tokens                               │
│  Qwen-Coder-7B:        $0.0003/1K tokens                               │
│  GPT-4o-mini:          $0.0015/1K tokens                               │
│  GPT-4o:               $0.01/1K tokens                                 │
│                                                                         │
│  EJEMPLO DE COSTO MENSUAL                                              │
│  ─────────────────────────                                             │
│  100 tareas/día × 2K tokens promedio × 30 días = 6M tokens/mes        │
│                                                                         │
│  • Solo LLM (GPT-4o):        6M × $0.01   = $60/mes                   │
│  • Híbrido (80% SLM):        4.8M × $0.0003 + 1.2M × $0.01 = $16/mes  │
│  • Ahorro:                                          $44/mes (73%)      │
│                                                                         │
│  vs                                                                    │
│                                                                         │
│  vLLM + GPU L4 (24/7):        $0.35/hr × 720hr = $252/mes             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Modelos SLM Recomendados (Azure OpenAI)

| Modelo | Tamaño | Precio/1K tokens | Use Case |
|--------|--------|------------------|----------|
| **Phi-3-mini** | 3.8B | $0.0001 | Orchestrator, tareas simples |
| **Phi-3.5-mini** | 3.8B | $0.0001 | General purpose, summarization |
| **Qwen2.5-Coder-7B** | 7B | $0.0003 | Code generation |
| **DeepSeek-Math-7B** | 7B | $0.0003 | Math reasoning |
| **GPT-4o-mini** | ~8B | $0.0015 | Tareas moderadas |

### Integración con Arquitectura Existente

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STACK ACTUAL (Sin cambios)                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Cloud Run                    LiteLLM                    Azure        │
│   ─────────                    ───────                    ─────        │
│   cs-agent-service  ────────►  Proxy  ───────────────►  OpenAI        │
│   (scale to zero)              (routing)                 (SLMs/LLMs)   │
│                                                                         │
│   ✅ Sin nuevo deployment                                              │
│   ✅ Solo configuración en LiteLLM                                    │
│   ✅ Scale to zero preservado                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Por Qué NO Self-Hosted en Cloud Run

| Factor | Self-hosted (GPU) | Azure OpenAI |
|--------|-------------------|--------------|
| Scale to zero | ❌ GPU cold start = 2-5 min | ✅ Instantáneo |
| Costo idle | ❌ $136-252/mes | ✅ $0 |
| Mantenimiento | ❌ Alto (patches, updates) | ✅ Cero |
| Disponibilidad | ❌ Single point of failure | ✅ 99.9% SLA |
| Flexibilidad | ✅ Control total | ⚠️ Limitado a modelos disponibles |

**Conclusión:** Self-hosted solo tiene sentido para:
- Workloads con uso continuo 24/7 (GPU siempre activa)
- Requerimientos de privacidad extrema (datos nunca salen de GCP)
- Modelos altamente especializados no disponibles como servicio

Para el caso de conneskills (uso intermitente, múltiples clientes), **Azure OpenAI SLMs es óptimo**.

---

## Decisión 1: Arquitectura Híbrida SLM/LLM

### Principio

No todos los tasks requieren LLMs grandes. Un sistema de agentes eficiente debe:

1. **Usar SLMs por defecto** para tasks rutinarios
2. **Escalar a LLMs selectivamente** para razonamiento complejo
3. **Tener orchestrator dedicado** que tome decisiones de routing

### Arquitectura Propuesta

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           RUNTIME LAYER                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    ORCHESTRATOR (SLM 8B)                        │  │
│   │                                                                 │  │
│   │   Responsabilidades:                                           │  │
│   │   - Analizar complejidad de task                               │  │
│   │   - Decidir: tool local / SLM expert / LLM generalista         │  │
│   │   - Balancear accuracy/cost/latency                            │  │
│   │   - Logging para fine-tuning futuro                            │  │
│   │                                                                 │  │
│   │   Modelo: phi-3-mini / nemotron-h-8b / qwen-2.5-7b             │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│                    ┌───────────────┼───────────────┐                   │
│                    ▼               ▼               ▼                   │
│   ┌────────────────────┐ ┌─────────────────┐ ┌─────────────────────┐  │
│   │   TOOLS LAYER      │ │  SLM EXPERTS    │ │  LLM GENERALISTAS   │  │
│   ├────────────────────┤ ├─────────────────┤ ├─────────────────────┤  │
│   │ • MCP Tools        │ │ • Code (7B)     │ │ • GPT-4o            │  │
│   │ • FunctionTools    │ │ • Math (7B)     │ │ • Claude 3.5        │  │
│   │ • Built-in         │ │ • RAG (7B)      │ │ • Gemini Pro        │  │
│   │                    │ │ • Summary (4B)  │ │                     │  │
│   │ Costo: ~$0         │ │ Costo: $        │ │ Costo: $$$          │  │
│   └────────────────────┘ └─────────────────┘ └─────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Integración con Google ADK

```python
from google.adk.agents import LlmAgent, BaseAgent
from google.adk.tools import FunctionTool
from enum import Enum

class TaskComplexity(Enum):
    TRIVIAL = "trivial"      # Parsing, formateo, extracción
    SIMPLE = "simple"        # Clasificación, resumen simple
    MODERATE = "moderate"    # Code gen, RAG queries
    COMPLEX = "complex"      # Razonamiento multi-step, análisis

class HybridOrchestrator(BaseAgent):
    def __init__(self, name: str):
        super().__init__(name=name)
        self.orchestrator_model = LlmAgent(
            name="router",
            model="litellm/phi-3-mini",  # SLM 8B como orchestrator
            instruction=self._get_router_prompt(),
            tools=[
                self._route_to_tool,
                self._route_to_slm,
                self._route_to_llm
            ]
        )
        
    def _get_router_prompt(self) -> str:
        return """
You are an intelligent router. Analyze the task and decide the most efficient path:

1. TOOL: Use for deterministic operations (search, db queries, calculations)
2. SLM_EXPERT: Use for specialized tasks (code generation, math, summarization)
3. LLM_GENERAL: Use for complex reasoning, creative tasks, multi-step analysis

Decision criteria:
- Complexity: trivial/simple → tool/slm, moderate/complex → llm
- Cost sensitivity: high → prefer slm
- Latency requirement: real-time → prefer slm/tool
- Accuracy requirement: critical → prefer llm

Output JSON: {"route": "TOOL|SLM_EXPERT|LLM_GENERAL", "target": "...", "reasoning": "..."}
"""

    async def _run_async_impl(self, ctx):
        task = ctx.state.get("current_task")
        complexity = await self._assess_complexity(task)
        
        if complexity in [TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE]:
            return await self._execute_slm_or_tool(task, ctx)
        elif complexity == TaskComplexity.MODERATE:
            return await self._execute_slm_expert(task, ctx)
        else:
            return await self._execute_llm_general(task, ctx)

    async def _assess_complexity(self, task: dict) -> TaskComplexity:
        # Heurísticas rápidas sin LLM
        text = task.get("input", "")
        word_count = len(text.split())
        has_code_request = "code" in text.lower() or "implement" in text.lower()
        has_multi_step = any(kw in text.lower() for kw in ["analyze", "compare", "evaluate", "design"])
        
        if word_count < 20 and not has_multi_step:
            return TaskComplexity.TRIVIAL
        elif has_code_request:
            return TaskComplexity.MODERATE
        elif has_multi_step:
            return TaskComplexity.COMPLEX
        return TaskComplexity.SIMPLE
```

---

## Decisión 2: Unified Tool Calling

### Concepto

Tratar tools, SLMs expertos y LLMs generalistas bajo una **interfaz uniforme**. El orchestrator no distingue entre ellos — todos son "herramientas ejecutables" con JSON schemas.

### Implementación

```python
from dataclasses import dataclass
from typing import Callable, Any
import json

@dataclass
class UnifiedTool:
    name: str
    description: str
    input_schema: dict  # JSON Schema
    executor: Callable
    cost_tier: str      # "free", "low", "medium", "high"
    avg_latency_ms: int
    capabilities: list[str]

class UnifiedToolRegistry:
    def __init__(self):
        self.tools: dict[str, UnifiedTool] = {}
        
    def register_tool(self, tool: UnifiedTool):
        self.tools[tool.name] = tool
        
    def get_tools_for_task(self, task_type: str) -> list[UnifiedTool]:
        return [t for t in self.tools.values() 
                if task_type in t.capabilities]

# Registro de herramientas unificadas
registry = UnifiedToolRegistry()

# Tool básico (MCP)
registry.register_tool(UnifiedTool(
    name="search_jira",
    description="Search Jira issues",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10}
        }
    },
    executor=mcp_jira_search,  # MCP tool
    cost_tier="free",
    avg_latency_ms=200,
    capabilities=["search", "jira"]
))

# SLM Expert (Code generation)
registry.register_tool(UnifiedTool(
    name="code_generator",
    description="Generate code for programming tasks",
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "language": {"type": "string"},
            "context": {"type": "string"}
        }
    },
    executor=slm_code_executor,  # SLM 7B fine-tuned
    cost_tier="low",
    avg_latency_ms=1500,
    capabilities=["code", "programming", "generation"]
))

# LLM Generalist
registry.register_tool(UnifiedTool(
    name="complex_reasoning",
    description="Complex multi-step reasoning and analysis",
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "context": {"type": "string"},
            "reasoning_type": {"type": "string", "enum": ["analysis", "synthesis", "evaluation"]}
        }
    },
    executor=llm_general_executor,  # GPT-4o / Claude
    cost_tier="high",
    avg_latency_ms=5000,
    capabilities=["reasoning", "analysis", "creative", "complex"]
))
```

### Schema de Tool en LiteLLM

```yaml
# Configuración en LiteLLM para tools unificados
model_list:
  # Orchestrator
  - model_name: orchestrator
    litellm_params:
      model: azure/phi-3-mini
      
  # SLM Experts
  - model_name: slm-code
    litellm_params:
      model: azure/qwen-2.5-coder-7b
      
  - model_name: slm-math
    litellm_params:
      model: azure/deepseek-math-7b
      
  # LLM Generalists
  - model_name: llm-premium
    litellm_params:
      model: azure/gpt-4o
      
  - model_name: llm-reasoning
    litellm_params:
      model: azure/o1-preview

# Routing rules
routing_rules:
  - condition:
      task_complexity: ["trivial", "simple"]
    route_to: ["tools", "slm-code", "slm-math"]
    
  - condition:
      task_complexity: ["moderate"]
    route_to: ["slm-code", "slm-math", "llm-premium"]
    
  - condition:
      task_complexity: ["complex"]
    route_to: ["llm-premium", "llm-reasoning"]
```

---

## Decisión 3: Cost-Aware Routing

### Objetivos de Routing

Según ToolOrchestra, el routing debe optimizar 3 dimensiones:

```
┌─────────────────────────────────────────────────────────┐
│                    ROUTING OBJECTIVES                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. OUTCOME REWARD (Correctitud)                       │
│     - ¿La tarea se completó correctamente?             │
│     - Métrica: success_rate                             │
│                                                         │
│  2. EFFICIENCY REWARD (Costo + Latencia)               │
│     - ¿Se usó el modelo más barato posible?            │
│     - ¿Se cumplió el SLA de latencia?                  │
│     - Métrica: cost_per_task, latency_p95              │
│                                                         │
│  3. PREFERENCE REWARD (User satisfaction)              │
│     - ¿El output cumple las preferencias del usuario?  │
│     - ¿Estilo, formato, nivel de detalle?              │
│     - Métrica: user_rating, nps                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Matriz de Decisión

| Task Type | Complexity | Route To | Cost Tier | Latency |
|-----------|------------|----------|-----------|---------|
| Data extraction | Trivial | Tool (MCP) | Free | <500ms |
| Text formatting | Trivial | SLM 4B | Low | <1s |
| Simple classification | Simple | SLM 4B | Low | <1s |
| Code generation | Moderate | SLM 7B (Code) | Low | 1-3s |
| Math reasoning | Moderate | SLM 7B (Math) | Low | 1-3s |
| RAG query | Moderate | SLM 7B + RAG | Medium | 2-4s |
| Document analysis | Complex | LLM General | High | 5-10s |
| Multi-step reasoning | Complex | LLM Reasoning | High | 10-30s |
| Creative generation | Complex | LLM General | High | 5-15s |

### Implementación del Router

```python
from dataclasses import dataclass
from typing import Optional
import asyncio

@dataclass
class RoutingDecision:
    target: str
    model: str
    reasoning: str
    estimated_cost: float
    estimated_latency_ms: int
    confidence: float

class CostAwareRouter:
    def __init__(self, config: dict):
        self.pricing = config.get("pricing", {})
        self.sla_latency_ms = config.get("sla_latency_ms", 10000)
        self.budget_per_task = config.get("budget_per_task", 0.10)
        
    async def route(self, task: dict, context: dict) -> RoutingDecision:
        complexity = await self._assess_complexity(task)
        user_preference = context.get("preference", "balanced")
        urgency = context.get("urgency", "normal")
        
        candidates = self._get_candidates(complexity)
        
        # Filtrar por constraints
        candidates = self._filter_by_latency(candidates, urgency)
        candidates = self._filter_by_budget(candidates)
        
        # Scoring
        scored = [(c, self._score(c, user_preference)) for c in candidates]
        best = max(scored, key=lambda x: x[1])
        
        return RoutingDecision(
            target=best[0].name,
            model=best[0].model,
            reasoning=f"Complexity: {complexity}, Preference: {user_preference}",
            estimated_cost=best[0].cost,
            estimated_latency_ms=best[0].latency_ms,
            confidence=best[1]
        )
    
    def _score(self, candidate, preference: str) -> float:
        weights = {
            "cost_optimized": {"accuracy": 0.3, "cost": 0.5, "speed": 0.2},
            "speed_optimized": {"accuracy": 0.3, "cost": 0.1, "speed": 0.6},
            "balanced": {"accuracy": 0.4, "cost": 0.3, "speed": 0.3},
            "quality_first": {"accuracy": 0.6, "cost": 0.1, "speed": 0.3}
        }
        w = weights.get(preference, weights["balanced"])
        
        return (
            w["accuracy"] * candidate.accuracy_score +
            w["cost"] * (1 - candidate.normalized_cost) +
            w["speed"] * (1 - candidate.normalized_latency)
        )
```

---

## Decisión 4: Modelos SLM Disponibles

### Catálogo de SLMs en Azure OpenAI

| Modelo | Tamaño | Precio/1K tokens | Capacidades | Use Cases |
|--------|--------|------------------|-------------|-----------|
| **Phi-3-mini** | 3.8B | $0.0001 | General, reasoning | Orchestrator, tasks simples |
| **Phi-3.5-mini** | 3.8B | $0.0001 | General, multilingual | Summarization, classification |
| **Qwen2.5-Coder-7B** | 7B | $0.0003 | Code generation | Implement features, debugging |
| **DeepSeek-Math-7B** | 7B | $0.0003 | Math reasoning | Calculations, formulas |
| **GPT-4o-mini** | ~8B | $0.0015 | General purpose | Tasks moderadas |

### Comparativa de Costos por Tipo de Tarea

| Tipo de Tarea | Tokens Avg | SLM Cost | LLM Cost | Ahorro |
|---------------|------------|----------|----------|--------|
| Simple classification | 500 | $0.00005 | $0.005 | 99% |
| Code generation | 2,000 | $0.0006 | $0.02 | 97% |
| Document summary | 3,000 | $0.0003 | $0.03 | 99% |
| Complex reasoning | 5,000 | $0.075 | $0.05 | -50% (usar LLM) |
| Multi-step analysis | 10,000 | $0.30 | $0.10 | -200% (usar LLM) |

**Regla práctica:** Usar SLM para tasks con <4K tokens y complejidad baja/moderada.

### Fine-tuning: Opcional y Avanzado

> **Nota:** Fine-tuning NO es necesario para el MVP. Los modelos base de Azure OpenAI ya son efectivos.
> Considerar fine-tuning solo después de 3-6 meses de producción con datos reales.

**Cuándo considerar fine-tuning:**
1. Datos propios específicos del dominio del cliente
2. Necesidad de estilo/tono muy específico
3. Performance insuficiente con modelos base
4. Costo-beneficio: $10-50 fine-tuning vs $100+ en tokens extra

**Pipeline si se necesita:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    FINE-TUNING PIPELINE (Opcional)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DATA COLLECTION (Desde producción)                         │
│     ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│     │ Production  │    │  Feedback   │    │  Corrected  │     │
│     │   Logs      │    │   Loops     │    │   Outputs   │     │
│     └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│            └──────────────────┼──────────────────┘             │
│                               ▼                                │
│  2. TRAINING (Azure OpenAI fine-tuning API)                   │
│     ┌─────────────────────────────────────────────────┐       │
│     │ Costo: $10-50 por modelo                        │       │
│     │ Tiempo: 1-4 horas                               │       │
│     │ No requiere infra propia                        │       │
│     └─────────────────────────────────────────────────┘       │
│                               │                                │
│                               ▼                                │
│  3. EVALUACIÓN                                                 │
│     ┌─────────────────────────────────────────────────┐       │
│     │ • Comparar vs baseline                          │       │
│     │ • A/B testing en producción                     │       │
│     │ • Medir ROI en ahorro de tokens                 │       │
│     └─────────────────────────────────────────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Decisión 5: Métricas y Observabilidad

### Dashboard de Métricas

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     AGENT EFFICIENCY DASHBOARD                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  │
│  │  COST PER TASK    │  │  LATENCY P95      │  │  SUCCESS RATE     │  │
│  │                   │  │                   │  │                   │  │
│  │   $0.023 avg      │  │   2.3 seconds     │  │   94.2%           │  │
│  │   ↓ 67% vs LLM    │  │   ↓ 45% vs LLM    │  │   ↑ 2% vs LLM     │  │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    MODEL DISTRIBUTION                           │  │
│  ├─────────────────────────────────────────────────────────────────┤  │
│  │                                                                 │  │
│  │   Tools (Free)     ████████████████████  45%                   │  │
│  │   SLM 7B (Low)     ████████████████      35%                   │  │
│  │   SLM 4B (Low)     ████████              12%                   │  │
│  │   LLM (High)       ████████               8%                   │  │
│  │                                                                 │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    COST TREND (30 days)                         │  │
│  ├─────────────────────────────────────────────────────────────────┤  │
│  │   $500 ┤                                                         │  │
│  │   $400 ┤ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─           │  │
│  │   $300 ┤                                                         │  │
│  │   $200 ┤ ████████████████████████████████                       │  │
│  │   $100 ┤ ████████████████████████████████████████████████       │  │
│  │        └───────────────────────────────────────────────         │  │
│  │           Week 1    Week 2    Week 3    Week 4                  │  │
│  │                                                                 │  │
│  │   - Baseline (LLM only): $1,200/month                          │  │
│  │   - Hybrid (SLM+LLM): $320/month                                │  │
│  │   - Savings: 73%                                                │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Métricas a Implementar

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import prometheus_client as prom

# Prometheus metrics
COST_COUNTER = prom.Counter(
    'agent_task_cost_dollars',
    'Cost per task in dollars',
    ['agent_id', 'model', 'task_type']
)

LATENCY_HISTOGRAM = prom.Histogram(
    'agent_task_latency_seconds',
    'Task latency in seconds',
    ['agent_id', 'model', 'task_type'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)

SUCCESS_COUNTER = prom.Counter(
    'agent_task_success_total',
    'Successful tasks',
    ['agent_id', 'model', 'task_type']
)

FAILURE_COUNTER = prom.Counter(
    'agent_task_failure_total',
    'Failed tasks',
    ['agent_id', 'model', 'task_type', 'error_type']
)

MODEL_DISTRIBUTION = prom.Counter(
    'agent_model_selection_total',
    'Model selection distribution',
    ['agent_id', 'model_tier', 'task_complexity']
)

@dataclass
class TaskMetrics:
    task_id: str
    agent_id: str
    task_type: str
    complexity: str
    model_used: str
    model_tier: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    success: bool
    error_type: Optional[str]
    timestamp: datetime
    
    def record(self):
        COST_COUNTER.labels(
            agent_id=self.agent_id,
            model=self.model_used,
            task_type=self.task_type
        ).inc(self.cost_usd)
        
        LATENCY_HISTOGRAM.labels(
            agent_id=self.agent_id,
            model=self.model_used,
            task_type=self.task_type
        ).observe(self.latency_ms / 1000)
        
        MODEL_DISTRIBUTION.labels(
            agent_id=self.agent_id,
            model_tier=self.model_tier,
            task_complexity=self.complexity
        ).inc()
        
        if self.success:
            SUCCESS_COUNTER.labels(
                agent_id=self.agent_id,
                model=self.model_used,
                task_type=self.task_type
            ).inc()
        else:
            FAILURE_COUNTER.labels(
                agent_id=self.agent_id,
                model=self.model_used,
                task_type=self.task_type,
                error_type=self.error_type or "unknown"
            ).inc()
```

### Alertas

```yaml
# Prometheus alerting rules
groups:
  - name: agent_efficiency
    rules:
      - alert: HighCostPerTask
        expr: |
          rate(agent_task_cost_dollars[5m]) > 0.10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High cost per task detected"
          description: "Average cost per task is ${{ $value }} over 5 minutes"
          
      - alert: HighLatencyP95
        expr: |
          histogram_quantile(0.95, rate(agent_task_latency_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High P95 latency"
          description: "P95 latency is {{ $value }}s"
          
      - alert: LowSuccessRate
        expr: |
          rate(agent_task_success_total[5m]) / 
          (rate(agent_task_success_total[5m]) + rate(agent_task_failure_total[5m])) < 0.9
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Low success rate"
          description: "Success rate is {{ $value | humanizePercentage }}"
          
      - alert: OverRelianceOnLLM
        expr: |
          rate(agent_model_selection_total{model_tier="high"}[1h]) /
          rate(agent_model_selection_total[1h]) > 0.3
        for: 1h
        labels:
          severity: info
        annotations:
          summary: "Over-reliance on expensive LLMs"
          description: "{{ $value | humanizePercentage }} of tasks use high-cost models"
```

---

## Decisión 6: Modificaciones al ADR-001

### Cambios en Decisión 6: LiteLLM

**Antes:**
```python
researcher = LlmAgent(
    model="litellm/eo-agent-researcher",  # Un modelo fijo
)
```

**Después:**
```python
researcher = LlmAgent(
    model="litellm/orchestrator",  # Orchestrator SLM que routea
    # El orchestrator decide internamente qué modelo usar
)
```

### Cambios en Decisión 4: Arquitecturas Multi-Agente

**Añadir Patrón F: Hierarchical Hybrid**

```
┌─────────────────────────────────────────────────────────────────┐
│                      HYBRID HIERARCHY                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              ORCHESTRATOR (SLM 8B)                      │  │
│   │              - Complexity analysis                      │  │
│   │              - Cost-aware routing                       │  │
│   └─────────────────────────────────────────────────────────┘  │
│                              │                                 │
│           ┌──────────────────┼──────────────────┐             │
│           ▼                  ▼                  ▼             │
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐    │
│   │   SLM AGENT   │  │   SLM AGENT   │  │   LLM AGENT   │    │
│   │   (Code 7B)   │  │   (Math 7B)   │  │   (Complex)   │    │
│   │               │  │               │  │               │    │
│   │ Low Cost      │  │ Low Cost      │  │ High Cost     │    │
│   │ Fast          │  │ Fast          │  │ Slow          │    │
│   └───────────────┘  └───────────────┘  └───────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Actualización del Mapeo Registry

| Registry `execution_type` | ADK Class | Model Config |
|--------------------------|-----------|--------------|
| `single` | `LlmAgent` | Orchestrator SLM → routea dinámicamente |
| `sequential` | `SequentialAgent` | Cada paso puede usar modelo diferente |
| `parallel` | `ParallelAgent` + `LlmAgent` | SLMs en paralelo, LLM agrega |
| `coordinator` | `LlmAgent` con `AgentTool`s | Orchestrator SLM + experts |
| `hub-spoke` | `LlmAgent` con routing | Hub SLM + spokes mixtos |
| **`hybrid_hierarchical`** | **HybridOrchestrator** | **SLM router + SLM/LLM workers** |

---

## Decisión 7: Actualización del agent_factory.py

```python
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent, BaseAgent
from google.adk.tools import agent_tool
from typing import Optional
import os

class HybridAgentFactory:
    def __init__(self, config: dict):
        self.config = config
        self.orchestrator_model = config.get("orchestrator_model", "phi-3-mini")
        self.slm_experts = config.get("slm_experts", {})
        self.llm_generalists = config.get("llm_generalists", [])
        
    def build(self, runtime_config: dict, resolved_prompts: dict) -> BaseAgent:
        execution_type = runtime_config.get("execution_type", "single")
        roles = runtime_config.get("roles", [])
        cost_preference = runtime_config.get("cost_preference", "balanced")
        
        if execution_type == "single":
            return self._build_hybrid_agent(roles[0], resolved_prompts, cost_preference)
            
        elif execution_type == "sequential":
            return self._build_sequential_hybrid(roles, resolved_prompts, cost_preference)
            
        elif execution_type == "parallel":
            return self._build_parallel_hybrid(roles, resolved_prompts, cost_preference)
            
        elif execution_type == "hybrid_hierarchical":
            return self._build_hybrid_hierarchical(roles, resolved_prompts, cost_preference)
            
        # ... otros casos
            
    def _build_hybrid_agent(
        self, 
        role_cfg: dict, 
        prompts: dict,
        cost_preference: str
    ) -> LlmAgent:
        tools = self._load_tools(role_cfg)
        model = self._select_model(role_cfg, cost_preference)
        
        return LlmAgent(
            name=role_cfg["name"],
            model=f"litellm/{model}",
            instruction=prompts[role_cfg["name"]],
            tools=tools,
        )
    
    def _select_model(self, role_cfg: dict, cost_preference: str) -> str:
        task_type = role_cfg.get("task_type", "general")
        complexity = role_cfg.get("complexity", "moderate")
        
        # Matriz de decisión
        if cost_preference == "cost_optimized":
            if complexity in ["trivial", "simple"]:
                return self.slm_experts.get(task_type, "phi-3-mini")
            elif complexity == "moderate":
                return self.slm_experts.get(task_type, "qwen-2.5-7b")
            else:
                return "gpt-4o-mini"
                
        elif cost_preference == "quality_first":
            if complexity == "complex":
                return "gpt-4o"
            else:
                return self.slm_experts.get(task_type, "gpt-4o-mini")
                
        else:  # balanced
            if complexity == "trivial":
                return "phi-3-mini"
            elif complexity in ["simple", "moderate"]:
                return self.slm_experts.get(task_type, "qwen-2.5-7b")
            else:
                return "gpt-4o"
    
    def _build_hybrid_hierarchical(
        self,
        roles: list,
        prompts: dict,
        cost_preference: str
    ) -> BaseAgent:
        orchestrator_cfg = next((r for r in roles if r.get("is_orchestrator")), None)
        worker_cfgs = [r for r in roles if not r.get("is_orchestrator")]
        
        # Construir workers
        workers = []
        for cfg in worker_cfgs:
            worker = self._build_hybrid_agent(cfg, prompts, cost_preference)
            workers.append(worker)
        
        # Construir orchestrator
        if orchestrator_cfg:
            orchestrator = HybridOrchestrator(
                name=orchestrator_cfg["name"],
                workers=workers,
                cost_preference=cost_preference
            )
            return orchestrator
        
        # Sin orchestrator explícito, usar el primer worker
        return workers[0] if workers else None


class HybridOrchestrator(BaseAgent):
    def __init__(
        self,
        name: str,
        workers: list[BaseAgent],
        cost_preference: str = "balanced"
    ):
        super().__init__(name=name)
        self.workers = workers
        self.cost_preference = cost_preference
        
        # Orchestrator SLM
        self.router = LlmAgent(
            name=f"{name}_router",
            model="litellm/phi-3-mini",
            instruction=self._get_router_instruction(),
            tools=[self._create_worker_tool(w) for w in workers]
        )
        
    def _get_router_instruction(self) -> str:
        return """
You are an intelligent task router. Analyze incoming tasks and route them to the most appropriate worker.

Workers available:
{workers_info}

Decision criteria:
1. Task complexity: trivial/simple → smaller models, complex → larger models
2. Cost preference: {cost_preference}
3. Task type matching: match worker capabilities to task requirements

Always explain your routing decision.
"""
        
    def _create_worker_tool(self, worker: BaseAgent) -> agent_tool.AgentTool:
        return agent_tool.AgentTool(agent=worker)
        
    async def _run_async_impl(self, ctx):
        return await self.router._run_async_impl(ctx)
```

---

## Decisión 8: Configuración de LiteLLM Actualizada

```yaml
# litellm_config.yaml - Configuración híbrida

model_list:
  # === ORCHESTRATOR ===
  - model_name: orchestrator
    litellm_params:
      model: azure/Phi-3-mini-4k-instruct
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "SLM orchestrator for routing decisions"
      max_tokens: 4096
      cost_per_1k_tokens: 0.0001
      
  # === SLM EXPERTS ===
  - model_name: slm-code
    litellm_params:
      model: azure/Qwen2.5-Coder-7B-Instruct
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "Code generation specialist"
      capabilities: ["code", "programming", "debugging"]
      max_tokens: 8192
      cost_per_1k_tokens: 0.0003
      
  - model_name: slm-math
    litellm_params:
      model: azure/DeepSeek-Math-7B-Instruct
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "Math reasoning specialist"
      capabilities: ["math", "calculation", "formula"]
      max_per_1k_tokens: 0.0003
      
  - model_name: slm-general
    litellm_params:
      model: azure/Phi-3-mini-4k-instruct
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "General purpose SLM"
      capabilities: ["general", "summarization", "classification"]
      cost_per_1k_tokens: 0.0001
      
  # === LLM GENERALISTS ===
  - model_name: llm-standard
    litellm_params:
      model: azure/gpt-4o-mini
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "Standard LLM for moderate tasks"
      capabilities: ["reasoning", "analysis", "general"]
      cost_per_1k_tokens: 0.0015
      
  - model_name: llm-premium
    litellm_params:
      model: azure/gpt-4o
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "Premium LLM for complex tasks"
      capabilities: ["complex_reasoning", "creative", "analysis"]
      cost_per_1k_tokens: 0.01
      
  - model_name: llm-reasoning
    litellm_params:
      model: azure/o1-preview
      api_base: os.environ/AZURE_OPENAI_ENDPOINT
      api_key: os.environ/AZURE_OPENAI_KEY
    model_info:
      description: "Advanced reasoning model"
      capabilities: ["deep_reasoning", "multi_step", "planning"]
      cost_per_1k_tokens: 0.03

# === ROUTING RULES ===
routing_strategy: "cost_aware"

routing_rules:
  - name: "trivial_tasks"
    condition:
      estimated_tokens: "< 500"
      task_type: ["formatting", "extraction", "classification"]
    route_to:
      - slm-general
      - slm-code
      
  - name: "code_tasks"
    condition:
      task_type: ["code_generation", "debugging", "code_review"]
    route_to:
      - slm-code
      - llm-standard
      
  - name: "math_tasks"
    condition:
      task_type: ["calculation", "math_reasoning"]
    route_to:
      - slm-math
      
  - name: "complex_reasoning"
    condition:
      task_type: ["analysis", "planning", "multi_step"]
      estimated_tokens: "> 2000"
    route_to:
      - llm-premium
      - llm-reasoning
      
  - name: "fallback"
    condition:
      complexity: "unknown"
    route_to:
      - orchestrator  # Let orchestrator decide

# === FALLBACK CONFIG ===
fallbacks:
  - model: llm-premium
    fallback: [llm-standard, slm-general]
  - model: llm-reasoning
    fallback: [llm-premium, llm-standard]
  - model: slm-code
    fallback: [llm-standard]
    
# === RATE LIMITS ===
rate_limit:
  orchestrator:
    rpm: 1000
    tpm: 100000
  slm-*:
    rpm: 500
    tpm: 50000
  llm-*:
    rpm: 100
    tpm: 20000

# === BUDGET CONFIG ===
budget_limits:
  per_customer_daily_usd: 50.0
  per_agent_daily_usd: 10.0
  per_task_max_usd: 1.0
  
# === COST TRACKING ===
cost_tracking:
  enabled: true
  log_level: "info"
  export_prometheus: true
  alert_threshold_usd: 5.0
```

---

## Plan de Implementación

### Fase 1: Configuración SLM en LiteLLM (1 semana)

- [ ] Registrar modelos SLM en Azure OpenAI (Phi-3-mini, Qwen-Coder-7B)
- [ ] Actualizar `litellm_config.yaml` con modelos SLM
- [ ] Configurar routing rules básicas
- [ ] Validar conectividad y latencia

### Fase 2: Orchestrator SLM (2 semanas)

- [ ] Implementar `HybridOrchestrator`
- [ ] Actualizar `agent_factory.py`
- [ ] Implementar heurísticas de complejidad
- [ ] Tests de routing

### Fase 3: Métricas y Observabilidad (1 semana)

- [ ] Configurar métricas Prometheus
- [ ] Dashboard Grafana de costos por modelo
- [ ] Alertas de costo y latencia
- [ ] Logging estructurado

### Fase 4: Testing y Validación (1 semana)

- [ ] A/B testing: SLM vs LLM en producción
- [ ] Validar accuracy en tareas típicas
- [ ] Medir ahorro de costos real
- [ ] Documentar findings

### Fase 5: Optimización (Continuo - Post MVP)

- [ ] Analizar distribución de tareas
- [ ] Ajustar routing rules basado en datos
- [ ] Considerar fine-tuning si necesario
- [ ] Expandir catálogo de SLMs

---

## Resumen de Costos Esperados

| Escenario | Uso/Mes | Costo LLM Only | Costo Híbrido | Ahorro |
|-----------|---------|----------------|---------------|--------|
| Bajo | 1M tokens | $10 | $2 | 80% |
| Medio | 10M tokens | $100 | $25 | 75% |
| Alto | 50M tokens | $500 | $120 | 76% |

**Inversión inicial:** ~$0 (solo configuración en LiteLLM)
**ROI esperado:** 70-80% ahorro en costos de inferencia

---

## Decisión 9: AG-UI para Interfaz Usuario-Agente

### Contexto

El ADR-001 (Decisión 9) identifica la necesidad de una **UI de usuario** para gestionar credenciales de servicios externos. Además, los usuarios finales necesitan interactuar con los agentes de manera fluida.

### ¿Qué es AG-UI?

**AG-UI** es un protocolo open-source que estandariza la interacción entre agentes de IA y aplicaciones frontend. Es el tercer pilar del stack de protocolos agentic:

```
┌─────────────────────────────────────────────────────────────┐
│                 AGENTIC PROTOCOL STACK                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   MCP        →    Da tools a los agentes                   │
│   A2A        →    Comunica agentes entre sí                │
│   AG-UI      →    Conecta agentes con usuarios (UI)        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Soporte Nativo para Google ADK

AG-UI tiene integración oficial con Google ADK (framework elegido en ADR-001):

| Framework | Status | Documentación |
|-----------|--------|---------------|
| **Google ADK** | ✅ Soportado | [docs.copilotkit.ai/adk](https://docs.copilotkit.ai/adk) |
| LangGraph | ✅ Soportado | - |
| CrewAI | ✅ Soportado | - |
| AWS Strands | ✅ Soportado | - |
| Pydantic AI | ✅ Soportado | - |

### Arquitectura con AG-UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA CON AG-UI                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    FRONTEND (AG-UI Client)                      │  │
│   │                                                                 │  │
│   │   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐     │  │
│   │   │ Chat UI       │  │ Credential    │  │ Tool Approval │     │  │
│   │   │ (streaming)   │  │ Manager       │  │ (human-loop)  │     │  │
│   │   │               │  │               │  │               │     │  │
│   │   │ • Real-time   │  │ • Jira API    │  │ • Approve     │     │  │
│   │   │ • Thinking    │  │ • Slack token │  │ • Reject      │     │  │
│   │   │ • Tool calls  │  │ • GitHub PAT  │  │ • Modify      │     │  │
│   │   └───────────────┘  └───────────────┘  └───────────────┘     │  │
│   │                                                                 │  │
│   │   Tech: React + @ag-ui/react + CopilotKit                     │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│                                    │ AG-UI Protocol                    │
│                                    │ (SSE / WebSocket)                 │
│                                    ▼                                    │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                 CLOUD RUN (cs-agent-service)                    │  │
│   │                                                                 │  │
│   │   ┌─────────────────────────────────────────────────────────┐  │  │
│   │   │ Google ADK + AG-UI Middleware                           │  │  │
│   │   │                                                         │  │  │
│   │   │ Eventos AG-UI (~16 tipos estándar):                    │  │  │
│   │   │ • TEXT_MESSAGE_START/CONTENT/END                       │  │  │
│   │   │ • TOOL_CALL_STARTED/RESULT                              │  │  │
│   │   │ • STATE_DELTA (sync bi-direccional)                    │  │  │
│   │   │ • RUN_STARTED/FINISHED                                  │  │  │
│   │   └─────────────────────────────────────────────────────────┘  │  │
│   │                                                                 │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│                    ┌───────────────┼───────────────┐                   │
│                    ▼               ▼               ▼                   │
│              LiteLLM          MCP Tools       Secret Manager           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Features para Conneskills

#### 1. UI de Gestión de Credenciales

Resuelve la necesidad de la Decisión 9 del ADR-001:

```typescript
// Frontend React con AG-UI
import { CopilotKit, useCoagent } from "@copilotkit/react-core";

function CredentialManager() {
  const { state, setState } = useCoagent({
    name: "credential-manager",
    initialState: {
      jira: { configured: false },
      slack: { configured: false },
      github: { configured: false }
    }
  });

  return (
    <div>
      <h2>Servicios Conectados</h2>
      
      <ServiceConnector
        service="jira"
        onConnect={(creds) => {
          // Guarda en Secret Manager via API
          saveCredentials("jira", creds);
          setState({ jira: { configured: true } });
        }}
      />
      
      {/* Más servicios... */}
    </div>
  );
}
```

#### 2. Human-in-the-Loop para Tools Sensibles

```python
# Backend: cs-agent-service con ADK + AG-UI
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from ag_ui import requires_approval

@FunctionTool
@requires_approval(
    message="El agente quiere eliminar un ticket de Jira. ¿Aprobar?",
    timeout_seconds=300
)
async def delete_jira_ticket(ticket_id: str) -> dict:
    """
    Elimina un ticket de Jira.
    Requiere aprobación del usuario antes de ejecutar.
    """
    # Solo se ejecuta si el usuario aprueba
    result = await jira_client.delete_issue(ticket_id)
    return {"status": "deleted", "ticket_id": ticket_id}

# En el agente
agent = LlmAgent(
    name="jira-agent",
    tools=[delete_jira_ticket, create_jira_ticket, search_issues]
)
```

#### 3. Streaming en Tiempo Real

```typescript
// Frontend: Chat con streaming
import { CopilotChat } from "@copilotkit/react-ui";

function AgentChat() {
  return (
    <CopilotChat
      instructions="Eres un asistente que ayuda con gestión de proyectos."
      labels={{
        title: "Asistente de Proyectos",
        initial: "¿En qué puedo ayudarte?",
        placeholder: "Escribe tu mensaje...",
      }}
      // El agente muestra:
      // - Pensamiento en tiempo real
      // - Tool calls con progreso
      // - Respuestas parciales
    />
  );
}
```

#### 4. Bi-directional State Sync

```typescript
// Frontend y Backend sincronizan estado automáticamente
import { useCoagentState } from "@copilotkit/react-core";

function TaskManager() {
  // Estado sincronizado con el agente
  const [tasks, setTasks] = useCoagentState("tasks", []);
  
  // Cuando el usuario añade una tarea
  const addTask = (task) => {
    setTasks([...tasks, task]);
    // El agente recibe automáticamente el cambio
  };
  
  // Cuando el agente modifica tareas
  // El frontend se actualiza automáticamente
  
  return <TaskList tasks={tasks} onAdd={addTask} />;
}
```

### Integración con ADK

```python
# cs-agent-service/src/__main__.py
from google.adk.agents import Runner
from ag_ui.middleware import AGUIMiddleware
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

# Crear el agente con ADK
agent = AgentFactory().build(runtime_config, resolved_prompts)
runner = Runner(agent=agent)

# Agregar middleware AG-UI
ag_ui = AGUIMiddleware(runner)

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Endpoint compatible con AG-UI.
    Retorna SSE stream con eventos AG-UI.
    """
    async def event_generator():
        async for event in ag_ui.process(request.messages, request.context):
            yield f"data: {event.json()}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### Implementación Frontend

```typescript
// ui-usuario/src/App.tsx
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotPopup } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

function App() {
  return (
    <CopilotKit
      // Conecta con el agente en Cloud Run
      agent={agentConfig}
      publicApiKey={process.env.NEXT_PUBLIC_COPILOT_KEY}
    >
      <main>
        <h1>Conneskills - Tu Agente de Proyectos</h1>
        
        {/* Chat flotante */}
        <CopilotPopup
          instructions="Ayuda al usuario a gestionar sus proyectos y tareas."
          defaultOpen={true}
        />
        
        {/* UI de credenciales */}
        <CredentialManager />
        
        {/* Dashboard */}
        <Dashboard />
      </main>
    </CopilotKit>
  );
}
```

### Comparativa: AG-UI vs Alternativas

| Aspecto | AG-UI | Custom UI | Otras soluciones |
|---------|-------|-----------|------------------|
| Integración ADK | ✅ Nativa | Manual | Limitada |
| Protocolo estándar | ✅ Open source | No | Propietario |
| Human-in-the-loop | ✅ Built-in | Custom | Parcial |
| Streaming | ✅ Built-in | Custom | Básico |
| Bi-directional state | ✅ Built-in | Manual | No |
| Time to market | Semanas | Meses | Variable |
| Costo licencia | Gratuito | - | $$$ |
| Comunidad | 12.1k stars | - | Variable |

### Dependencias

```json
// ui-usuario/package.json
{
  "dependencies": {
    "@copilotkit/react-core": "^1.0.0",
    "@copilotkit/react-ui": "^1.0.0",
    "@ag-ui/core": "^0.0.1",
    "react": "^18.0.0"
  }
}
```

```python
# cs-agent-service/requirements.txt
ag-ui-middleware>=0.1.0
google-adk>=1.0.0
fastapi>=0.100.0
```

### Plan de Implementación AG-UI

**Sprint 1 (1 semana):**
- [ ] Setup proyecto frontend con CopilotKit
- [ ] Configurar AG-UI middleware en cs-agent-service
- [ ] Chat básico con streaming

**Sprint 2 (1 semana):**
- [ ] UI de gestión de credenciales
- [ ] Integración con Secret Manager
- [ ] Tests de flujo completo

**Sprint 3 (1 semana):**
- [ ] Human-in-the-loop para tools sensibles
- [ ] Bi-directional state sync
- [ ] Polishing y UX

### Riesgos y Mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Breaking changes en AG-UI | Media | Pin versiones, monitorear releases |
| Performance con muchos usuarios | Baja | Load testing, escalar Cloud Run |
| Complejidad de UI | Media | Usar componentes pre-built de CopilotKit |

---

## Consecuencias y Trade-offs

| Decisión | Beneficio | Riesgo | Mitigación |
|----------|-----------|--------|------------|
| Azure OpenAI SLMs | 70-80% ahorro, scale-to-zero | Vendor lock-in | LiteLLM abstrae proveedor |
| Orchestrator SLM | Routing inteligente, bajo costo | Punto único de decisión | Fallbacks configurados |
| Routing por complejidad | Usa modelo óptimo por tarea | Overhead de decisión | Heurísticas simples sin LLM |
| Sin fine-tuning inicial | Fast time-to-market, $0 inversión | Models genéricos | Fine-tuning post-MVP si necesario |
| AG-UI para UI | Protocolo estándar, integración ADK nativa | Dependencia externa | Open source, comunidad activa |

### Métricas de Éxito

| Métrica | Target | Medición |
|---------|--------|----------|
| Reducción de costo | >70% | Costo total tokens/mes vs baseline |
| Latencia P95 | <3s | Prometheus histogram |
| Success rate | >95% | Tareas completadas correctamente |
| Distribución SLM | >70% | % de tasks que usan SLM vs LLM |

---

## Referencias

- [arXiv:2506.02153 - Small Language Models are the Future of Agentic AI](https://arxiv.org/abs/2506.02153)
- [arXiv:2511.21689 - ToolOrchestra](https://arxiv.org/abs/2511.21689)
- [Google ADK Docs](https://google.github.io/adk-docs/)
- [LiteLLM Docs](https://litellm.ai/docs/)
- [Azure OpenAI Service - Phi-3](https://azure.microsoft.com/en-us/products/phi-3)
- [Azure OpenAI Service - Models](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Qwen2.5-Coder](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)
- [AG-UI Docs](https://ag-ui.com/)
- [AG-UI + Google ADK Integration](https://docs.copilotkit.ai/adk)
- [CopilotKit](https://github.com/CopilotKit/CopilotKit)
