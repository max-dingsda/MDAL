"""
Converts ChatGPT export (mapping structure) to MDAL trainer format.

ChatGPT export: list of conversations, each with a 'mapping' dict (tree structure).
MDAL format: [[{"role": "user"|"assistant", "content": "..."}], ...]

Applies the following filters:
- Text messages only (parts[0] must be a str)
- Empty content is skipped
- Conversations with fewer than 2 turns are discarded
- Only conversations with recognizably German content (if --language=de)

Output: training_de.json in the project folder
"""

import json
import sys
from pathlib import Path


def extract_turns(conv: dict) -> list[dict]:
    """
    Extracts the linear sequence of user/assistant turns from the
    ChatGPT mapping structure (depth-first traversal backwards from current_node).
    """
    mapping = conv.get("mapping", {})
    current_node_id = conv.get("current_node")

    if not current_node_id or current_node_id not in mapping:
        return []

    # Reconstruct path from current_node to root
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
    """Rough heuristic: checks for typical German words in the first turns."""
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
        print(f"Reading {path.name} ...", flush=True)
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

    print(f"\nFiltered conversations: {len(all_conversations)}")
    print(f"Total turns: {sum(len(c) for c in all_conversations)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_conversations, f, ensure_ascii=False, indent=2)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    base = Path("f:/MDAL")
    export_dir = base / "chatgpt_export"
    output = base / "training_data" / "training_de.json"

    input_files = sorted(export_dir.glob("conversations-*.json"))
    print(f"Files found: {[f.name for f in input_files]}")

    convert_files(
        input_paths=input_files,
        output_path=output,
        language="de",
    )
