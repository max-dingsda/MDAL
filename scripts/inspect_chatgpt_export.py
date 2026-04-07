"""Inspects the ChatGPT export format and converts it for the MDAL trainer."""
import json
import sys
from pathlib import Path

path = Path("f:/MDAL/chatgpt_export/conversations-000.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)

print(f"Number of conversations in file: {len(data)}")
conv = data[0]
print(f"Keys of a conversation: {list(conv.keys())}")

if "mapping" in conv:
    print("\nFormat: ChatGPT mapping structure")
    mapping = conv["mapping"]
    print(f"Number of nodes: {len(mapping)}")
    # First node with a message
    for node_id, node in mapping.items():
        msg = node.get("message")
        if msg and msg.get("content"):
            print(f"\nExample node:")
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
    print("\nFormat: List of messages (OpenAI-compatible)")
    print(f"Keys: {list(conv[0].keys())}")
