# MDAL (Model-Driven Architecture Layer)

## What is it?
MDAL is a specialized normalization layer (proxy) that acts as middleware between applications/users and Large Language Models (LLMs).

The goal of MDAL is to dampen the so-called **"Model-Shift Effect"**: the user experience, tone, and structure of responses stay absolutely consistent, regardless of which AI model (or which model version) is doing the actual generation work in the background.

## What does MDAL do? (High-Level)
MDAL intercepts LLM responses and checks them against a pre-defined "character fingerprint" (the target state). MDAL only forwards responses to the user once they meet the quality criteria:

- **Style Normalization:** MDAL checks formality level, sentence structure, and vocabulary (e.g. consistent formal register).
- **Structure Validation:** Hard verification of structured outputs (e.g. JSON or XML) against defined schemas.
- **Semantic Integrity:** An LLM-based transformer smooths the text style when needed, but strictly blocks hallucinations or factual drift (entity check).
- **Merciless Escalation Logic:** When the model fails to meet requirements, MDAL forces retries. If the model fails repeatedly, MDAL blocks the response with `HTTP 503 Service Unavailable` rather than passing through bad output ("strictness over silent compromise").

---

## How do I start?

The system is lightweight, API-first by design, and ideal for use with e.g. Ollama or OpenAI-compatible endpoints.

### 1. Install dependencies
All that's needed is a recent Python environment:
```bash
pip install -r requirements.txt
```

### 2. Start the MDAL Server 
MDAL features a built-in configuration web interface (similar to a smart home router setup). You don't need to manually edit YAML files to get started.

```bash
# Starts on port 6969 by default
python -m mdal.proxy.server
```

### 3. Configure and Run

Open the built-in Control Center in your browser at `http://localhost:6969/config`.

From the Control Center UI, you can:
- set up your LLM and embedding endpoints with presets for Ollama, OpenAI, Anthropic, and Google
- configure audit logging, validation checks, notifier settings, fingerprint path, and plugin registry path
- start or stop the MDAL proxy and launch the trainer from the UI

Some advanced runtime options such as `fallback_llm`, `max_retries`, and `language` are still configured manually in `config/mdal.yaml`.

```bash
python -m mdal.trainer.trainer --config config/mdal.yaml --input your_chats.json --language de
```

---

## Further Documentation
For in-depth information on the architecture, detailed layer concepts, configuration, and plugin development, see the full user documentation:
👉 **Open User Documentation**
