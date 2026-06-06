## Deploying a Cyberpunk AI Coding Agent on OpenShift: Eve Agent V2 Unleashed

What happens when you take an autonomous coding agent built for local GPU execution and deploy it to a managed Kubernetes cluster? We ran that experiment with Eve Agent V2 Unleashed, and the results tell a useful story about containerizing LLM-powered applications for Red Hat OpenShift AI.

## What is Eve Agent V2 Unleashed?

Eve is an open-source autonomous coding agent that plans, executes, and verifies multi-step programming tasks through a 40-round agentic tool loop. Built by developer Jeff Green, it runs on Ollama for local inference and optionally escalates to cloud models (MiniMax M3) when tasks exceed local model capacity.

The feature list reads like an RPG character sheet: 112 sub-agents, 111 slash commands, 273 composable skills, a quest system, XP progression, and a cyberpunk-themed web UI. Under the hood, it's a FastAPI server with a comprehensive tool suite: bash execution, file operations, grep, glob, web search, URL fetch, and git integration.

The question we wanted to answer: can all of this run on OpenShift without a local GPU?

## Why this matters for OpenShift AI

Agentic AI workloads are a growing category on Red Hat OpenShift AI. These aren't simple model-serving deployments. They combine LLM inference with tool-calling loops, persistent memory (Eve uses ChromaDB), and stateful multi-turn interactions. Understanding how these applications behave in containerized environments helps platform engineers plan for the next wave of AI workloads.

Eve's architecture maps directly to patterns we see in production agentic systems: a FastAPI gateway, pluggable model backends, a tool registry, and session state management. Getting it running on OpenShift validates the deployment model for this entire class of applications.

## The containerization challenge: cutting 200MB of dead weight

Eve's original dependency tree was built for a developer's local machine. It included `playwright` (headless browser automation, 200MB+), `solders` and `solana` (blockchain SDK with platform-specific Rust binaries), and `tweepy` (Twitter API integration). None of these are needed for the core agent loop, and several won't compile on UBI9.

We created a stripped `requirements-poc.txt` that preserved the essential stack:

- **FastAPI + Uvicorn** for the web server
- **Ollama client** for model routing
- **ChromaDB** for vector memory
- **aiohttp + httpx** for async HTTP operations
- **Rich** for terminal formatting
- **psutil** for system monitoring (this one was missing from the original requirements and caused a runtime import failure on the first build)

The `Dockerfile.ubi` uses `registry.access.redhat.com/ubi9/python-312` as the base image, installs `gcc` and `python3-devel` for native extensions, and sets `USER 1001` with proper group permissions for OpenShift's security model.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#EE0000', 'primaryTextColor': '#fff', 'primaryBorderColor': '#A30000', 'lineColor': '#6A6E73', 'secondaryColor': '#F0F0F0', 'tertiaryColor': '#0066CC'}}}%%
graph LR
    A["Original Deps<br/>(30+ packages)"] -->|Strip| B["PoC Deps<br/>(20 packages)"]
    B -->|Build| C["UBI9 Container"]
    C -->|Push| D["Quay.io Registry"]
    D -->|Deploy| E["OpenShift Cluster"]

    style A fill:#6A6E73,color:#fff
    style B fill:#0066CC,color:#fff
    style C fill:#EE0000,color:#fff
    style D fill:#F0F0F0,color:#151515
    style E fill:#EE0000,color:#fff
```

It took three build iterations to get a clean image. The first build succeeded but crashed at runtime because `psutil` wasn't in the requirements file even though `eve_server.py` imports it at startup. A common pattern: the dependency works on the developer's machine because it was installed globally, but the container has no such safety net.

## Deploying to the cluster

The Kubernetes manifests are minimal. One Deployment (single replica, 1Gi-2Gi memory range), one ClusterIP Service on port 7777, and an image pull secret for Quay.io. We added a readiness probe on `/status` so the platform knows when Eve is ready to accept requests.

The security context drops all Linux capabilities and prevents privilege escalation. Eve runs as UID 1001, matching the UBI9 convention for non-root containers on OpenShift.

```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

Deployment to namespace `poc-eve-agent-v2-unleashed` completed without issues. The pod reached ready state within 15 seconds.

## Test results: 4/4 passing

We validated four scenarios covering the core surface area:

| Test | Result | What we verified |
|------|--------|-----------------|
| Web UI | Pass | Full cyberpunk HTML interface served with embedded CSS/JS |
| Status endpoint | Pass | Provider config, 14 tools, 5 models, RPG mood state |
| Models endpoint | Pass | 5 model definitions (4B, 8B local; 397B, MiniMax M3 cloud) |
| Tools endpoint | Pass | 12 registered tools (bash, file ops, web, search, git) |

All responses returned in under 30ms. The server starts up fast and serves the complete web UI from a single HTML response with no external asset dependencies, which makes it resilient in cluster environments where CDN access might be restricted.

The status endpoint confirmed that Eve's model routing configuration survives containerization intact. All five model definitions (spanning local 4B/8B parameter models and cloud-scale 397B models) are properly loaded, even though no Ollama backend is connected. The agent gracefully degrades: it initializes the routing table and tool registry, and waits for a model backend to become available.

## What we learned

**Strip aggressively, but test runtime imports.** Static dependency analysis isn't enough. Eve's `psutil` import only surfaces at server startup, not during `pip install`. Always test the container's actual entry point after building.

**Agentic apps degrade gracefully when designed for multi-model routing.** Eve's architecture separates the agent runtime from the inference backend. The FastAPI server, tool registry, and web UI all function without a connected LLM. This is the right pattern for containerized deployment: the platform manages the lifecycle, and the model backend is a separate concern.

**UBI9 handles Python AI stacks well, with caveats.** The standard `ubi9/python-312` image covers most Python AI dependencies. The gaps appear with packages that ship pre-compiled Rust or C++ binaries targeting specific OS/architecture combinations (like `solders`). Stripping those for the PoC is the right call; replacing them with platform-appropriate alternatives is the production path.

## Next steps

To move from PoC to production, the deployment needs an Ollama sidecar (or a connection to a Red Hat OpenShift AI model serving endpoint via KServe). Eve's model router already supports OpenAI-compatible endpoints, so pointing it at a KServe InferenceService is a configuration change, not a code change.

ChromaDB persistence requires a PVC for production use, and multi-replica scaling needs sticky sessions for WebSocket connections or an externalized vector database like Qdrant.

The full deployment artifacts, including the UBI Dockerfile, Kubernetes manifests, and test scripts, are available in the [forked repository](https://github.com/aicatalyst-team/eve-agent-v2-unleashed).
