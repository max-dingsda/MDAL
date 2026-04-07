"""
Trainer run for Phase 6.

Arguments:
  --pilot   Only the first 30 conversations (quick functional test)
  --full    All filtered conversations (production fingerprint)
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

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mdal.config import load_config
from mdal.fingerprint.store import FingerprintStore
from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config
from mdal.trainer.trainer import Trainer, load_conversations_from_file

parser = argparse.ArgumentParser()
parser.add_argument("--pilot", action="store_true", help="30 conversations only (functional test)")
parser.add_argument("--full",  action="store_true", help="All conversations")
args = parser.parse_args()

base = Path("f:/MDAL")
config = load_config(base / "config" / "train.yaml")

# Load training data
print("Loading training data ...", flush=True)
conversations = load_conversations_from_file(
    base / "training_data" / "training_de.json",
    language="de",
)
print(f"Total: {len(conversations)} conversations", flush=True)

if args.pilot:
    conversations = conversations[:30]
    print(f"Pilot mode: {len(conversations)} conversations", flush=True)
elif not args.full:
    print("Please specify --pilot or --full.", flush=True)
    sys.exit(1)

# Adapter + Store
llm   = llm_adapter_from_config(config.llm)
embed = embedding_adapter_from_config(config.embedding)
store = FingerprintStore(config.fingerprint_path)

print(f"\nLLM:       {config.llm.model} @ {config.llm.url}", flush=True)
print(f"Embedding: {config.embedding.model} @ {config.embedding.url}", flush=True)
print(f"Fingerprint target: {config.fingerprint_path}", flush=True)

# Embedding test
print("\nTesting embedding endpoint ...", flush=True)
try:
    vec = embed.embed("Das ist ein Test.")
    print(f"OK — Dimensions: {len(vec)}", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    sys.exit(1)

# LLM test
print("Testing LLM endpoint ...", flush=True)
try:
    resp = llm.complete([{"role": "user", "content": "Antworte mit 'OK'."}])
    print(f"OK — Response: {resp[:50]}", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    sys.exit(1)

# Trainer run
print(f"\nStarting trainer run with {len(conversations)} conversations ...\n", flush=True)
trainer = Trainer(
    llm_adapter=llm,
    embedding_adapter=embed,
    store=store,
    golden_sample_count=5,
    embedding_model_name=config.embedding.model,
)

version = trainer.run(conversations=conversations, language="de")
print(f"\nFingerprint v{version} for 'de' saved.", flush=True)
print(f"Path: {config.fingerprint_path}", flush=True)
