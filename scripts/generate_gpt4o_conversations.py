import json
import os
import time
from pathlib import Path
from openai import OpenAI

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("FEHLER: OPENAI_API_KEY Umgebungsvariable nicht gesetzt!")
        return

    client = OpenAI(api_key=api_key)
    prompts_file = Path("manuelle_tests/semantik/prosa_prompts.json")
    output_file = Path("manuelle_tests/semantik/gpt4o_chats.json")
    
    if not prompts_file.exists():
        print(f"FEHLER: Prompts-Datei nicht gefunden: {prompts_file}")
        return

    with open(prompts_file, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    results = []
    print(f"Starte Generierung von {len(prompts)} Baseline-Chats mit GPT-4o...")

    for i, item in enumerate(prompts, 1):
        # Unterstützt sowohl reine Strings als auch Dictionaries
        prompt_text = item.get("prompt", "") if isinstance(item, dict) else str(item)
        print(f"[{i}/{len(prompts)}] Verarbeite: {prompt_text[:50]}...")
        
        messages = [{"role": "user", "content": prompt_text}]
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.7
            )
            answer = response.choices[0].message.content
            
            results.append([
                {"role": "user", "content": prompt_text},
                {"role": "assistant", "content": answer}
            ])
        except Exception as e:
            print(f"  -> Fehler bei Prompt {i}: {e}")
        
        time.sleep(0.5) # Kurze Pause für Rate Limits

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nFertig! {len(results)} Konversationen gespeichert in {output_file}")

if __name__ == "__main__":
    main()