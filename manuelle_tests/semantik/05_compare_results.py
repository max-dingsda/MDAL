import json
import os

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    print(f"Warnung: Datei {filepath} nicht gefunden.")
    return []

def main():
    print("Lese Ergebnisdateien ein...")
    llama_data = load_json("llama_chats.json")          # Format: [ [{"role":"user"...}, {"role":"assistant"...}], ... ]
    mistral_base = load_json("mistral_baseline_log.json") # Format: [ {"prompt": ..., "mistral_baseline_response": ...}, ... ]
    mistral_mdal = load_json("mistral_mdal_log.json")     # Format: [ {"prompt": ..., "mistral_mdal_response": ...}, ... ]

    # Baue ein Dictionary auf, indexiert über den Prompt-Text
    results = {}
    
    for chat in llama_data:
        prompt = chat[0]["content"]
        response = chat[1]["content"]
        results[prompt] = {"llama": response}

    for item in mistral_base:
        prompt = item["prompt"]
        if prompt not in results:
            results[prompt] = {}
        results[prompt]["mistral"] = item["mistral_baseline_response"]

    for item in mistral_mdal:
        prompt = item["prompt"]
        if prompt not in results:
            results[prompt] = {}
        results[prompt]["mistral_mdal"] = item["mistral_mdal_response"]

    output_file = "05_comparison_report.md"
    print(f"Erstelle Markdown-Bericht: {output_file} ...")
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# MDAL Vergleichsbericht\n\n")
        for i, (prompt, data) in enumerate(results.items(), 1):
            f.write(f"## Prompt {i}\n**User:** {prompt}\n\n")
            f.write("| Modell / Setup | Antwort |\n")
            f.write("|---|---|\n")
            f.write(f"| **Llama 3.2** *(Golden Standard)* | {data.get('llama', 'N/A').replace(chr(10), '<br>')} |\n")
            f.write(f"| **Mistral** *(ohne MDAL)* | {data.get('mistral', 'N/A').replace(chr(10), '<br>')} |\n")
            f.write(f"| **Mistral** *(mit MDAL)* | {data.get('mistral_mdal', 'N/A').replace(chr(10), '<br>')} |\n\n")
            f.write("---\n\n")

    print(f"Fertig! Der Bericht liegt unter {output_file}")

if __name__ == "__main__":
    main()