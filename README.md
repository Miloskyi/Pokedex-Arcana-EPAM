# 🔴 Pokédex Arcana

> Sistema multiagente de IA que funciona como una Pokédex potenciada, capaz de responder consultas complejas en lenguaje natural sobre el universo Pokémon — en inglés y español.

---

## ¿Qué hace?

- **Stats**: tipos, estadísticas base, habilidades, cadenas evolutivas con datos reales de PokéAPI
- **Daño**: cálculos con la fórmula Gen IX (STAB, naturaleza, EVs/IVs, clima, items)
- **Lore**: información narrativa, entradas de Pokédex, anime — búsqueda RAG sobre Bulbapedia
- **Equipos**: recomendaciones competitivas con sets completos (naturaleza, EVs, item, moveset)
- **Observabilidad**: dashboard en tiempo real con latencia, tokens y trazas por query

---

## Arquitectura

```
Usuario → React Frontend (WebSocket) → FastAPI Backend
                                              ↓
                                    Orchestrator (LangGraph)
                                    ↙    ↓    ↘    ↓    ↘
                              Stats  Damage  Lore  Team  Verification
                              Agent  Agent  Agent  Agent    Agent
                                ↓      ↓      ↓     ↓
                            PokéAPI  Gen IX  RAG  Smogon
                                     Formula Pipeline
                                              ↓
                                    ChromaDB (Bulbapedia + PokéDex entries)
                                    PostgreSQL (historial, trazas)
                                    Redis (sesión, caché)
```

---

## Requisitos previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 24+
- [Ollama](https://ollama.com/) instalado y corriendo localmente
- Modelo `llama3.1:8b` descargado en Ollama

### Instalar el modelo LLM

```bash
ollama pull llama3.1:8b
```

Verifica que Ollama esté corriendo:
```bash
ollama list
# Debe mostrar: llama3.1:8b
```

> **No se necesita API key de OpenAI.** El sistema usa Ollama localmente (gratis).

---

## Instalación y ejecución

### 1. Clonar el repositorio

```bash
git clone https://github.com/Miloskyi/Pokedex-Arcana-EPAM.git
cd Pokedex-Arcana-EPAM
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

El `.env` ya viene preconfigurado para usar Ollama local. **No necesitas cambiar nada** si tienes `llama3.1:8b` instalado.

Si tienes otro modelo, edita `.env`:
```dotenv
OLLAMA_MODEL=llama3.1:8b   # cambia por tu modelo disponible
```

### 3. Arrancar todos los servicios

```bash
docker-compose up
```

Esto inicia: PostgreSQL, Redis, ChromaDB, el backend FastAPI (con Celery worker) y el frontend React.

**Primera ejecución:** el backend descarga e indexa automáticamente datos de PokéAPI y Bulbapedia (~2-3 minutos). El sistema es usable mientras tanto.

### 4. Abrir la aplicación

| Servicio | URL |
|---|---|
| 🎮 **Pokédex UI** | http://localhost:3000 |
| ⚙️ **Backend API** | http://localhost:8080 |


---

## Variables de entorno

Todas están en `.env.example`. Las más importantes:

| Variable | Descripción | Default |
|---|---|---|
| `OLLAMA_BASE_URL` | URL del servidor Ollama | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | Modelo LLM a usar | `llama3.1:8b` |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL | `pokedex_secret` |
| `DATABASE_URL` | URL de conexión a PostgreSQL | auto-configurada |
| `REDIS_URL` | URL de Redis | `redis://redis:6379/0` |
| `CHROMADB_HOST` | Host de ChromaDB | `chromadb` |

---

## Ejemplos de consultas

```
# Stats básicas (inglés y español)
What are Jigglypuff's types and base stats?
¿Cuáles son los tipos y estadísticas de Charizard?
datos de pidgeotto

# Cálculo de daño
Bold natured Abomasnow uses Blizzard against Jigglypuff with 0 SpD EVs
Abomasnow de naturaleza Audaz usa Ventisca contra Jigglypuff con 0 EVs en Defensa Especial

# Team building
I need 5 teammates for Dragapult in OU
Necesito compañeros para Garchomp en competitivo

# Lore
Tell me about Pikachu: friends, rivals, abilities
Háblame de Mewtwo: su origen y poderes

# Comparaciones
best water pokemon
mejor pokemon de fuego
Pikachu vs Charizard
```

---

## Stack técnico

### Backend
- **Python 3.11** + **FastAPI** + **WebSockets**
- **LangGraph** — orquestación multiagente
- **Ollama** (`llama3.1:8b`) — LLM local sin costo de API
- **sentence-transformers** (`all-MiniLM-L6-v2`) — embeddings locales
- **ChromaDB** — vector store (Bulbapedia + PokéDex entries + PDF guides)
- **BM25 + dense retrieval + cross-encoder reranking** — pipeline RAG híbrido
- **PostgreSQL** — historial conversacional, trazas de observabilidad
- **Redis** — buffer de sesión (últimos 10 turnos, TTL 2h)
- **Celery** — tareas asíncronas

### Frontend
- **React 18 + Vite + TypeScript**
- **Tailwind CSS** — paleta Pokédex (rojo #CC0000, amarillo #FFCB05, azul #1E3A5F)
- **Recharts** — radar chart de stats, gráficos BST
- **Framer Motion** — animaciones
- **Zustand** — estado global de sesión

### Datos
- **PokéAPI** — 1025 Pokémon (Gen I–IX)
- **Bulbapedia** — scraping de lore (45 Pokémon representativos)
- **14,496 entradas de Pokédex** embebidas en ChromaDB

---

## Agentes del sistema

| Agente | Responsabilidad |
|---|---|
| **Orchestrator** | Clasifica intención, delega a agentes en paralelo, agrega respuestas |
| **Stats Agent** | Stats base, tipos, habilidades, evoluciones — datos reales de PokéAPI |
| **Damage Calc Agent** | Fórmula Gen IX con todos los modificadores |
| **Lore Agent** | Lore, anime, Pokédex entries — búsqueda RAG |
| **Team Builder Agent** | Equipos competitivos con sets completos |
| **Verification Agent** | Revalida cálculos numéricos de forma independiente |
| **Report Agent** | Reportes en Markdown y PDF |
| **DataViz Agent** | Radar charts, grillas de tipos, diagramas evolutivos |

---

## Observabilidad

El dashboard en `/admin/observability` muestra:
- Latencia promedio por agente
- Tokens consumidos por consulta
- Agentes más invocados
- Queries lentas (>10s)
- Tabla de trazas con query, latencia, tokens y agente más lento

---

## Decisiones de diseño

**LLM local con Ollama** — Elimina costos de API. `llama3.1:8b` tiene suficiente capacidad para clasificar intenciones, parsear queries complejas y generar respuestas de lore.

**Embeddings locales** — `all-MiniLM-L6-v2` (22 MB) corre en CPU sin GPU, sin costo, con buena calidad para búsqueda semántica en Pokémon.

**Hybrid RAG (BM25 + dense)** — Los nombres de Pokémon y movimientos son identificadores exactos que el retrieval denso solo puede perder. BM25 los captura con precisión; el cross-encoder reordena los candidatos.

**Stats sin LLM** — Las consultas de estadísticas van directamente a PokéAPI y se formatean sin pasar por el LLM, lo que las hace instantáneas (~400ms vs ~30s con LLM).

**WebSocket con replay** — El gateway almacena eventos en Redis. Si el cliente se desconecta, al reconectar recibe los tokens perdidos desde el último índice.
