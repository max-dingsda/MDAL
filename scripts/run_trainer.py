"""
Trainer-Lauf für Phase 6.

Argumente:
  --pilot   Nur die ersten 30 Konversationen (schneller Funktionstest)
  --full    Alle gefilterten Konversationen (produktiver Fingerprint)
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Projekt-Root zum Pfad
sys.path.insert(0, str(Path(__file__).parent.parent))

from mdal.config import load_config
from mdal.fingerprint.store import FingerprintStore
from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config
from mdal.trainer.trainer import Trainer, load_conversations_from_file

parser = argparse.ArgumentParser()
parser.add_argument("--pilot", action="store_true", help="Nur 30 Konversationen (Funktionstest)")
parser.add_argument("--full",  action="store_true", help="Alle Konversationen")
args = parser.parse_args()

base = Path("f:/MDAL")
config = load_config(base / "config" / "train.yaml")

# Trainingsdaten laden
print("Lade Trainingsdaten ...", flush=True)
conversations = load_conversations_from_file(
    base / "training_data" / "training_de.json",
    language="de",
)
print(f"Gesamt: {len(conversations)} Konversationen", flush=True)

if args.pilot:
    conversations = conversations[:30]
    print(f"Pilot-Modus: {len(conversations)} Konversationen", flush=True)
elif not args.full:
    print("Bitte --pilot oder --full angeben.", flush=True)
    sys.exit(1)

# Adapter + Store
llm   = llm_adapter_from_config(config.llm)
embed = embedding_adapter_from_config(config.embedding)
store = FingerprintStore(config.fingerprint_path)

print(f"\nLLM:       {config.llm.model} @ {config.llm.url}", flush=True)
print(f"Embedding: {config.embedding.model} @ {config.embedding.url}", flush=True)
print(f"Fingerprint-Ziel: {config.fingerprint_path}", flush=True)

# Embedding-Test
print("\nTeste Embedding-Endpunkt ...", flush=True)
try:
    vec = embed.embed("Das ist ein Test.")
    print(f"OK — Dimension: {len(vec)}", flush=True)
except Exception as e:
    print(f"FEHLER: {e}", flush=True)
    sys.exit(1)

# LLM-Test
print("Teste LLM-Endpunkt ...", flush=True)
try:
    resp = llm.complete([{"role": "user", "content": "Antworte mit 'OK'."}])
    print(f"OK — Antwort: {resp[:50]}", flush=True)
except Exception as e:
    print(f"FEHLER: {e}", flush=True)
    sys.exit(1)

# Trainer-Lauf
print(f"\nStarte Trainer-Lauf mit {len(conversations)} Konversationen ...\n", flush=True)
trainer = Trainer(
    llm_adapter=llm,
    embedding_adapter=embed,
    store=store,
    golden_sample_count=5,
    embedding_model_name=config.embedding.model,
)

version = trainer.run(conversations=conversations, language="de")
print(f"\nFingerprint v{version} für 'de' gespeichert.", flush=True)
print(f"Pfad: {config.fingerprint_path}", flush=True)
