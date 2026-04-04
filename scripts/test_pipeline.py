"""
Phase 6 Pipeline-Test — direkte Validierung ohne HTTP-Proxy.

Testet die vier PoC-Kernfragen:
  K1: Fingerprint-Tragfähigkeit — wie stabil ist der Centroid?
  K2: Scoring-Kaskade — welche Entscheidungen trifft das System?
  K3: Transformer-Verlässlichkeit — bleiben Semantik und Struktur erhalten?
  K4: Schwellwert-Defaults — passen die Defaults 0.85/0.65 zur Realität?

Ausgabe: console + phase6_findings.md
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mdal.config import load_config
from mdal.fingerprint.store import FingerprintStore
from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config
from mdal.pipeline import PipelineOrchestrator
from mdal.proxy.startup import build_pipeline
from mdal.session import SessionContext
from mdal.verification.semantic.layer2 import Layer2EmbeddingChecker, cosine_similarity

BASE = Path("f:/MDAL")


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# K1: Fingerprint-Tragfähigkeit
# ---------------------------------------------------------------------------

def test_fingerprint(config, store) -> dict:
    section("K1: Fingerprint-Tragfähigkeit")

    fp = store.load_current("de")
    print(f"Fingerprint v{fp.version}, Sprache={fp.language}")
    print(f"Layer 1: Formalität={fp.layer1.formality_level}, "
          f"preferred={fp.layer1.preferred_vocabulary[:3]}")
    print(f"Layer 2: Dimensionen={fp.layer2.dimensions}, "
          f"Samples={fp.layer2.sample_count}")
    print(f"Layer 3: {len(fp.layer3.samples)} Golden Samples")

    # Centroid-Norm prüfen (sollte > 0 sein)
    import math
    centroid = fp.layer2.centroid
    norm = math.sqrt(sum(x*x for x in centroid))
    print(f"Centroid-Norm: {norm:.4f} ({'OK' if norm > 0.1 else 'SCHWACH'})")

    return {
        "version": fp.version,
        "layer1_formality": fp.layer1.formality_level,
        "layer2_dimensions": fp.layer2.dimensions,
        "layer2_samples": fp.layer2.sample_count,
        "layer3_samples": len(fp.layer3.samples),
        "centroid_norm": norm,
    }


# ---------------------------------------------------------------------------
# K2 + K4: Scoring-Kaskade und Schwellwerte
# ---------------------------------------------------------------------------

def test_scoring(config, store) -> list[dict]:
    section("K2/K4: Scoring-Kaskade und Schwellwert-Kalibrierung")

    embed = embedding_adapter_from_config(config.embedding)
    fp = store.load_current("de")
    checker = Layer2EmbeddingChecker(embedding_adapter=embed)

    test_cases = [
        {
            "label": "Stilähnlicher Text (deutsch, sachlich)",
            "text": (
                "Die Architektur des Systems basiert auf einer dreischichtigen "
                "Verifikationskaskade. Jede Schicht prüft einen anderen Aspekt des "
                "generierten Outputs. Die Entscheidung erfolgt binär ohne Kompromisse."
            ),
        },
        {
            "label": "Sehr ähnlicher ChatGPT-Stil",
            "text": (
                "Hier ist eine übersichtliche Erklärung der ArchiMate-Notation:\n\n"
                "**1. Business Layer:** Enthält Akteure, Rollen und Prozesse.\n"
                "**2. Application Layer:** Beschreibt Softwarekomponenten und deren Interaktionen.\n"
                "**3. Technology Layer:** Zeigt physische Infrastruktur und Plattformen.\n\n"
                "Die Pfeile zwischen den Layern zeigen Abhängigkeiten und Realisierungen."
            ),
        },
        {
            "label": "Informeller Casual-Stil",
            "text": (
                "hey, also ich hab das mal kurz angeschaut und ich glaub du musst "
                "einfach nochmal drüberschauen, is eigentlich nicht so kompliziert lol. "
                "mach einfach was ich dir gesagt hab und dann sollte das klappen :)"
            ),
        },
        {
            "label": "Englischer Text",
            "text": (
                "The system architecture follows a microservices pattern with three "
                "independent services communicating via REST APIs. Each service "
                "maintains its own database to ensure loose coupling."
            ),
        },
        {
            "label": "Kurze Antwort",
            "text": "Ja, das ist korrekt.",
        },
        {
            "label": "Technisch-formaler Stil",
            "text": (
                "Gemäß §4 Abs. 2 des Vertrages vom 15. März 2024 sind alle Parteien "
                "verpflichtet, die vereinbarten Leistungen innerhalb der festgelegten "
                "Fristen zu erbringen. Bei Nichteinhaltung gelten die in §7 definierten "
                "Vertragsstrafen."
            ),
        },
    ]

    results = []
    print(f"{'Label':<40} {'Similarity':>10} {'Level':<8}")
    print("-" * 60)

    for tc in test_cases:
        t0 = time.time()
        result = checker.check(
            output=tc["text"],
            fingerprint=fp,
            context=SessionContext(language="de", fingerprint_version=fp.version),
        )
        elapsed = time.time() - t0
        print(f"{tc['label']:<40} {result.raw_score:>10.4f} {result.level.value:<8}  ({elapsed:.1f}s)")
        results.append({
            "label": tc["label"],
            "similarity": result.raw_score,
            "level": result.level.value,
            "details": result.details,
        })

    # Schwellwert-Analyse
    similarities = [r["similarity"] for r in results]
    print(f"\nMin:    {min(similarities):.4f}")
    print(f"Max:    {max(similarities):.4f}")
    print(f"Median: {sorted(similarities)[len(similarities)//2]:.4f}")
    from mdal.verification.semantic.layer2 import THRESHOLD_HIGH, THRESHOLD_LOW
    print(f"\nThresholds: HIGH≥{THRESHOLD_HIGH} / MEDIUM≥{THRESHOLD_LOW} / LOW<{THRESHOLD_LOW}")

    return results


# ---------------------------------------------------------------------------
# K3: Transformer-Verlässlichkeit
# ---------------------------------------------------------------------------

def test_transformer() -> dict:
    section("K3: Transformer-Verlässlichkeit")

    from mdal.transformer import RuleBasedToneTransformer

    transformer = RuleBasedToneTransformer()

    test_cases = [
        {
            "label": "Senkung Formalitätslevel (5→3)",
            "text": "Sehr geehrte Damen und Herren, ich erlaube mir hiermit, Sie "
                    "darauf hinzuweisen, dass das System derzeit nicht verfügbar ist.",
            "target_formality": 3,
        },
        {
            "label": "Erhöhung Formalitätslevel (1→4)",
            "text": "hey, das system ist grad down, kannst du kurz warten?",
            "target_formality": 4,
        },
        {
            "label": "Strukturerhalt bei Transformation",
            "text": "Das sind die wichtigsten Punkte:\n1. Erster Punkt\n2. Zweiter Punkt\n"
                    "3. Dritter Punkt\n\nBitte beachten: Die Reihenfolge ist wichtig!",
            "target_formality": 4,
        },
    ]

    results = []
    for tc in test_cases:
        from mdal.fingerprint.models import Fingerprint, StyleRules, EmbeddingProfile, GoldenSamples
        mock_fp = Fingerprint(
            version=1,
            language="de",
            layer1=StyleRules(formality_level=tc["target_formality"]),
            layer2=EmbeddingProfile(centroid=[0.1], model_name="test", sample_count=1, dimensions=1),
            layer3=GoldenSamples(samples=[]),
        )
        try:
            transformed = transformer.transform(tc["text"], mock_fp)
            # Struktur-Check: Nummerierte Listen müssen erhalten bleiben
            has_list = "1." in tc["text"]
            list_preserved = ("1." in transformed) if has_list else True
            print(f"\n{tc['label']}")
            print(f"  Original:     {tc['text'][:80]}")
            print(f"  Transformiert:{transformed[:80]}")
            print(f"  Struktur OK:  {list_preserved}")
            results.append({
                "label": tc["label"],
                "preserved_structure": list_preserved,
                "changed": transformed != tc["text"],
            })
        except Exception as e:
            print(f"  FEHLER: {e}")
            results.append({"label": tc["label"], "error": str(e)})

    return {"cases": results}


# ---------------------------------------------------------------------------
# Haupt-Aufruf
# ---------------------------------------------------------------------------

def main() -> None:
    config = load_config(BASE / "config" / "proxy.yaml")
    store = FingerprintStore(config.fingerprint_path)

    if not store.has_fingerprint("de"):
        print("FEHLER: Kein Fingerprint für 'de' vorhanden. Trainer zuerst ausführen.")
        sys.exit(1)

    findings = {}
    findings["fingerprint"] = test_fingerprint(config, store)
    findings["scoring"]     = test_scoring(config, store)
    findings["transformer"] = test_transformer()

    # Zusammenfassung
    section("ZUSAMMENFASSUNG — Phase 6 PoC-Kernfragen")
    fp = findings["fingerprint"]
    sc = findings["scoring"]

    print(f"K1 Fingerprint-Tragfähigkeit:")
    print(f"  v{fp['version']} mit {fp['layer2_samples']} Embedding-Samples, "
          f"Norm={fp['centroid_norm']:.4f} → {'OK' if fp['centroid_norm'] > 0.1 else 'Schwach'}")

    highs  = sum(1 for r in sc if r["level"] == "high")
    meds   = sum(1 for r in sc if r["level"] == "medium")
    lows   = sum(1 for r in sc if r["level"] == "low")
    print(f"\nK2/K4 Scoring ({len(sc)} Tests): HIGH={highs}, MEDIUM={meds}, LOW={lows}")
    for r in sc:
        print(f"  [{r['level']:<6}] {r['similarity']:.4f}  {r['label']}")

    sims = sorted(r["similarity"] for r in sc)
    print(f"\n  → Similarity-Range: {sims[0]:.4f} – {sims[-1]:.4f}")
    from mdal.verification.semantic.layer2 import THRESHOLD_HIGH, THRESHOLD_LOW
    if sims[-1] < THRESHOLD_HIGH:
        print(f"  ⚠ Kein Test erreicht HIGH (≥{THRESHOLD_HIGH}) → Threshold_HIGH zu hoch?")
    if sims[0] > THRESHOLD_LOW:
        print(f"  ⚠ Kein Test fällt in LOW (<{THRESHOLD_LOW}) → Threshold_LOW zu niedrig?")

    # Ergebnis speichern
    findings_path = BASE / "phase6_findings.json"
    findings_path.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull findings: {findings_path}")


if __name__ == "__main__":
    main()
