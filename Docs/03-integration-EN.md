# Integration into Existing Applications

MDAL is designed as a **drop-in replacement** for the OpenAI API. This means you rarely need to adapt your existing applications, scripts, chatbots, or frameworks. Since MDAL exposes the exact same API surface (`POST /v1/chat/completions`) as OpenAI, simply changing the target URL is usually sufficient.

## 1. Architectural Concept
Instead of your application communicating directly with the LLM (e.g., OpenAI, Ollama, Anthropic), it sends the request to your local MDAL server. MDAL verifies the response and only forwards it to your application once it complies with your defined fingerprint.

## 2. Code Example (Python OpenAI SDK)
You can continue to use the official OpenAI libraries. You only need to point the `base_url` to your MDAL server:

```python
from openai import OpenAI

# Initialize the client, but redirect all requests to MDAL!
client = OpenAI(
    base_url="http://localhost:6969/v1", 
    api_key="mdal-key" # MDAL ignores the key or passes it through transparently
)

response = client.chat.completions.create(
    model="irrelevant", # Ignored by MDAL (Model selection is managed via Control Center)
    messages=[
        {"role": "user", "content": "Write a short rejection letter for a job applicant."}
    ],
    # IMPORTANT: MDAL does not support streaming, as texts must be verified entirely
    stream=False, 
    
    # OPTIONAL: Forces verification against a specific language fingerprint
    extra_headers={"X-MDAL-Language": "en"} 
)

print(response.choices.message.content)
```

## 3. Important Rules for Integration

* **No Streaming:** The parameter `stream=True` is prohibited. Because MDAL must evaluate, parse, and potentially transform the text, it requires the complete output at once. Streaming requests will be blocked by MDAL with an `HTTP 400` error.

* **Model names are irrelevant:** Parameters like `model="gpt-4"` in your code are completely ignored by MDAL. The actual backend model is centrally managed by the administrator in the MDAL Control Center.

* **Language Routing:** If your application handles multiple languages, you can instruct MDAL which fingerprint to load by setting the `X-MDAL-Language` HTTP header (e.g., `en`, `de`) on a per-request basis. If omitted, MDAL falls back to the default language defined in the configuration.