"""Untersucht das ChatGPT-Exportformat und konvertiert es für den MDAL-Trainer."""
import json
import sys
from pathlib import Path

path = Path("f:/MDAL/chatgpt_export/conversations-000.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)

print(f"Anzahl Konversationen in Datei: {len(data)}")
conv = data[0]
print(f"Keys einer Konversation: {list(conv.keys())}")

if "mapping" in conv:
    print("\nFormat: ChatGPT mapping-Struktur")
    mapping = conv["mapping"]
    print(f"Anzahl Nodes: {len(mapping)}")
    # Erstes Node mit Message
    for node_id, node in mapping.items():
        msg = node.get("message")
        if msg and msg.get("content"):
            print(f"\nBeispiel-Node:")
            print(f"  author.role: {msg.get('author', {}).get('role')}")
            content = msg.get("content", {})
            print(f"  content type: {type(content)}")
            if isinstance(content, dict):
                print(f"  content keys: {list(content.keys())}")
                parts = content.get("parts", [])
                print(f"  parts[0] type: {type(parts[0]) if parts else 'none'}")
                if parts and isinstance(parts[0], str):
                    print(f"  parts[0][:100]: {str(parts[0])[:100]}")
            break

elif isinstance(conv, list):
    print("\nFormat: Liste von Messages (OpenAI-kompatibel)")
    print(f"Keys: {list(conv[0].keys())}")
