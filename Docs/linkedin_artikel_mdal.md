# LinkedIn Article: Drafts

---

## Variant 1: Original Draft

**Title Ideas:**
1. Strictness Over Silent Compromise: How We Tame LLMs with a "Character Fingerprint".
2. The Model-Shift Effect: Why Your LLM Speaks Differently Tomorrow Than Today — and How We Fix That.
3. The Danger of "Semantic Corruption" in LLMs: Lessons from Our MDAL Project.

---

## Introduction: The Pain in Production
Good Friday 2026. I was sitting on the balcony with my morning coffee, my thoughts circling a topic that had been on my mind for a while. Since the migration from GPT-4o to GPT-5, to be precise. That's when I first noticed it — clearly and unmistakably: models (particularly LLMs) behave differently and communicate in noticeably distinct ways — even when the provider is the same and the system prompts are identical.

A second, seemingly unrelated but extremely annoying issue: LLMs occasionally have massive problems adhering to correct versions of standards. More than once, for example, I've asked an LLM to help with ArchiMate modeling. Even though the currently valid standard no longer includes a "Use" relationship (older versions did), it stubbornly kept appearing in the responses.

From this came the idea to build a tool that solves both problems: dampening model shift through stylistic verification (and correction if needed) of output, and enforcing structural fidelity through hard validation against standards (XML schemas, element lists).

This is exactly where our current architecture project comes in: **MDAL (Model-Driven Architecture Layer)**.

## The Idea: The "Character Fingerprint"
MDAL is a middleware — an OpenAI-compatible proxy that sits invisibly between application and LLM. The core idea: instead of blindly trusting the model, MDAL checks every generated response against a pre-calibrated, versioned "character fingerprint". I define a target state — tonality, phrasing style, structure — and the system forces the model to comply through a multi-stage scoring cascade (embeddings and LLM-as-a-Judge).

## The Approach: Strictness Over Silent Compromise
Traditional systems often accept "graceful degradation" — passing through a half-baked response rather than making the user wait. With MDAL we deliberately chose the opposite: **quality over silent passthrough.**

The system delivers either correct output or it escalates. Along the way we had to absorb some architectural setbacks: our initial rule-based regex transformer for automatic style correction was too error-prone and failed badly in practice. Our current pipeline therefore looks like this:
1. When text deviates stylistically, a dedicated **LLM-based transformer** (`LLMToneTransformer`) now smooths the output.
2. When the structure is broken (e.g. malformed JSON/XML), the primary model is forced into a retry with the exact error message.
3. If the model fails after 3 attempts, the system blocks mercilessly (`HTTP 503`).

🔒 **Privacy by Design: No Silent Data Collection**
Another central architectural principle that matters to us: MDAL stores *no* data beyond the moment strictly required for operation. Conversation contents and verification decisions are fully ephemeral and discarded immediately after the session.

## The Results: Our Lessons from Phase 6 (Python PoC)
We just completed the sixth phase of our proof-of-concept (with Mistral & Llama 3). From this we gained fundamental insights for production use:

**1. The Danger of "Semantic Corruption" (The LLM as a Pleaser)**
This was our most important — and most amusing — finding. LLMs will do anything to satisfy the instructions in the system prompt. When we set extremely hard style constraints (e.g. forcing formal vocabulary around "service provider" and "contracts"), the model started bending facts completely absurdly just to match the style.

*A real example from our logs (task: write an invitation to the IT summer party):*
🎯 **1. The Llama Standard (Our Target State):**
> *"Warm invitation to the IT department's summer party! Dear colleagues, the time has come..."* (Casual, collegial)
🤖 **2. The Model Shift (Mistral without MDAL):**
> *"Title: 🌞 Wedding of the Codes! 💻 Dear colleagues..."* (Noticeably different, highly exaggerated style)
💥 **3. Semantic Corruption (Mistral with our old, overly strict MDAL Transformer):**
> *"We are very pleased to send you the formal invitation to the annual IT department summer party in the form of a contract negotiation. We look forward to a successful application of the service provider agreement..."* (The model invented a contract negotiation just to satisfy our style requirement!)

*Our solution:* Semantic integrity takes mandatory precedence over stylistic perfection! We built in hard "confidence scoring". If the transformer changes more than 30% of the original text (so-called over-optimization), the adjustment is immediately and humbly discarded. MDAL therefore intervenes at step 3 and prevents the corruption before it reaches the user.

**2. Hard Language Lock Prevents Language Drift**
When small models cannot cleanly transform a German style specification, they tend to "escape" into English. An upstream validator now mandatorily compares input and output locale and blocks this language drift rigorously.

**3. Context Leaks & Domain Profiles**
When static reference phrases are used (e.g. "Mr./Ms. Service Provider"), the LLM sometimes inserts them out of context everywhere. The solution was to introduce dynamic domain profiles (`TECHNICAL`, `BUSINESS`, `CREATIVE`) into which prompts are classified upfront.

## What's Next?
Thanks to this defensive normalization architecture we successfully reduced the abort rate to under 5% and massively dampened the model-shift effect.

Our next milestones for the project:
* **Hardening structured outputs:** We are continuing to expand the plugin architecture for hard XML/JSON validations.
* **The commercial stress test:** Can we get Claude to sound exactly like ChatGPT? (As a training basis for our offline trainer, 90 MB of historical ChatGPT conversations are potentially available).
* **Admin UI:** Development of an interface for administrators to comfortably manage the system.
* **External audit logs:** Support for exporting audit logs to external, operator-controlled systems (e.g. databases).

---

Has anyone in production experienced similar "semantic corruption" with LLMs? Or how do you handle format failures after a model update? Let's discuss in the comments!

#SoftwareArchitecture #ArtificialIntelligence #LLM #MDAL #Python #MachineLearning #EnterpriseArchitecture

----

## Variant 2: Revised Version (Focus on Storytelling & Authenticity)
*This draft goes out tomorrow morning.*

Good Friday 2026. I was sitting on the balcony, coffee in hand, annoyed for the umpteenth time about the same problem.

Since the migration from GPT-4o to GPT-5 it had finally hit me clearly: the same system prompt, the same provider — and yet the model suddenly speaks differently. Different tonality. Different style. As if someone had secretly replaced the intern.

Then a second, annoying detail from my work with ArchiMate: even though the current standard no longer includes a specific relationship type, it keeps showing up stubbornly in LLM responses. Hallucinated domain knowledge from older training data.

Two problems, one idea: **MDAL — Model Drift Avoidance Layer.** (Yes, I initially confused "Model Drift" with "Model Shift". The name stuck anyway.)

---

## Think First, Then Code

I didn't just start building this project. I started the way I start every proper software project: requirements. Then an architecture sketch. Then code. Then iterations across all three levels.

That sounds obvious — but in hobby projects it usually isn't. And it paid off, more on that shortly.

---

## What MDAL Is

MDAL is a middleware — an OpenAI-compatible proxy that sits invisibly between application and LLM.

The core idea: instead of blindly trusting the model, MDAL checks every response against a pre-calibrated "character fingerprint". I define a target state — tonality, phrasing style, structure — and the system forces the model to comply.

Quality over silent passthrough. If the output doesn't fit, the system escalates. After three failed attempts: HTTP 503. Mercilessly.

---

## The Most Important Insight: Semantic Corruption

This was my most fascinating — and most amusing — finding from phase 6 of the proof of concept.

LLMs will do anything to satisfy the instructions in the system prompt. When I set extremely hard style constraints, the model eventually starts bending facts to meet the style requirements.

A real example from my logs. Task: write an invitation to the IT summer party.

**Llama (my target state):**
"Warm invitation to the IT department's summer party! Dear colleagues..."
Casual. Collegial. Fits.

**Mistral without MDAL:**
"Title: 🌞 Wedding of the Codes! 💻 Dear colleagues..."
Over the top — but at least still an invitation.

**Mistral with my old, overly strict Transformer:**
"We are very pleased to send you the formal invitation to the annual IT department summer party in the form of a contract negotiation. We look forward to a successful application of the service provider agreement..."

The model invented a contract negotiation. Just to satisfy my style requirement.

This was also the moment my first solution approach failed spectacularly. My rule-based regex transformer for automatic style correction was simply too error-prone. So back to the architecture: I replaced it with a dedicated `LLMToneTransformer` — one LLM corrects the style of another. And since LLMs tend to overdo it, confidence scoring was added: if the transformer changes more than 30% of the original text, the adjustment is discarded.

This was a requirement I hadn't formulated. Gap identified, architecture updated: semantic integrity takes precedence over stylistic perfection.

---

## Further Learnings

**Language Drift:** Small models tend to "escape" into English when faced with difficult style requirements. An upstream locale validator now blocks this hard.

**Context Leaks:** The LLM sometimes inserts static reference phrases out of context everywhere. Solution: dynamic domain profiles (`TECHNICAL`, `BUSINESS`, `CREATIVE`) into which prompts are classified upfront.

**Privacy by Design:** MDAL stores nothing beyond the strictly necessary processing moment. No logging of conversation contents.

---

## Current Status

The abort rate is below 5%. The model-shift effect is significantly dampened.

Next up: harder XML/JSON validation, an admin UI, and — the most exciting test — can I get Claude to sound exactly like ChatGPT?

I have 90 MB of historical ChatGPT conversations as a training base. The attempt is coming.

---

Has anyone in production experienced similar semantic corruption? Or how do you handle unexpected model behavior after an update?

#LLM #SoftwareArchitecture #AI #Python #EnterpriseArchitecture
