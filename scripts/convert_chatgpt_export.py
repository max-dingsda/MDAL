"""
Konvertiert ChatGPT-Export (mapping-Struktur) in MDAL-Trainer-Format.

ChatGPT-Export: Liste von Konversationen, jede mit 'mapping'-Dict (Baum-Struktur).
MDAL-Format: [[{"role": "user"|"assistant", "content": "..."}], ...]

Führt folgende Filterung durch:
- Nur Textnachrichten (parts[0] muss str sein)
- Leere Inhalte werden übersprungen
- Konversationen mit weniger als 2 Turns werden verworfen
- Nur Konversationen mit erkennbar deutschem Inhalt (sofern --language=de)

Ausgabe: training_de.json im Projektordner
"""

import json
import sys
from pathlib import Path


def extract_turns(conv: dict) -> list[dict]:
    """
    Extrahiert die lineare Abfolge von User/Assistant-Turns aus der
    ChatGPT-Mapping-Struktur (Tiefensuche vom current_node rückwärts).
    """
    mapping = conv.get("mapping", {})
    current_node_id = conv.get("current_node")

    if not current_node_id or current_node_id not in mapping:
        return []

    # Pfad vom current_node zur Wurzel rekonstruieren
    path = []
    node_id = current_node_id
    visited = set()
    while node_id and node_id not in visited:
        visited.add(node_id)
        node = mapping.get(node_id)
        if not node:
            break
        path.append(node)
        node_id = node.get("parent")

    path.reverse()

    turns = []
    for node in path:
        msg = node.get("message")
        if not msg:
            continue
        role = msg.get("author", {}).get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", {})
        if not isinstance(content, dict):
            continue
        parts = content.get("parts", [])
        if not parts or not isinstance(parts[0], str) or not parts[0].strip():
            continue
        turns.append({"role": role, "content": parts[0].strip()})

    return turns


def is_mostly_german(turns: list[dict], sample_size: int = 3) -> bool:
    """Grobe Heuristik: prüft auf typisch deutsche Wörter in den ersten Turns."""
    german_markers = {
        "ich", "ist", "das", "die", "der", "und", "nicht", "du", "wir",
        "sie", "es", "mit", "auf", "für", "von", "zu", "an", "ein", "eine",
        "auch", "wie", "aber", "wenn", "dann", "kann", "haben", "sein",
        "werden", "gibt", "nach", "über", "aus", "noch", "oder", "dass",
    }
    text = " ".join(t["content"] for t in turns[:sample_size]).lower()
    words = set(text.split())
    overlap = words & german_markers
    return len(overlap) >= 4


def convert_files(
    input_paths: list[Path],
    output_path: Path,
    language: str = "de",
    min_turns: int = 2,
    max_conversations: int | None = None,
) -> None:
    all_conversations: list[list[dict]] = []

    for path in input_paths:
        print(f"Lese {path.name} ...", flush=True)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for conv in data:
            turns = extract_turns(conv)
            if len(turns) < min_turns:
                continue
            if language == "de" and not is_mostly_german(turns):
                continue
            all_conversations.append(turns)
            if max_conversations and len(all_conversations) >= max_conversations:
                break

        if max_conversations and len(all_conversations) >= max_conversations:
            break

    print(f"\nGefilterte Konversationen: {len(all_conversations)}")
    print(f"Gesamte Turns: {sum(len(c) for c in all_conversations)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_conversations, f, ensure_ascii=False, indent=2)
    print(f"Gespeichert: {output_path}")


if __name__ == "__main__":
    base = Path("f:/MDAL")
    export_dir = base / "chatgpt_export"
    output = base / "training_data" / "training_de.json"

    input_files = sorted(export_dir.glob("conversations-*.json"))
    print(f"Gefundene Dateien: {[f.name for f in input_files]}")

    convert_files(
        input_paths=input_files,
        output_path=output,
        language="de",
    )
