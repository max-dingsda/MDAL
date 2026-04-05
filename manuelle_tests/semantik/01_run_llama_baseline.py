import json
import urllib.request
import urllib.error
import os

PROMPTS_FILE = "prosa_prompts.json"
OUTPUT_FILE = "llama_chats.json"
URL = "http://localhost:11434/v1/chat/completions"
MODEL = "llama3.2:latest"

def main():
    print(f"Lese Prompts aus {PROMPTS_FILE}...")
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    golden_samples = []

    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] Sende Prompt an {MODEL}...")
        
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        
        req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                assistant_message = result["choices"][0]["message"]["content"]
                
                # Format für den MDAL-Trainer: [ [{"role": "user", ...}, {"role": "assistant", ...}], ... ]
                chat_history = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": assistant_message}
                ]
                golden_samples.append(chat_history)
                print(f"  Erfolgreich empfangen ({len(assistant_message)} Zeichen).")
        except Exception as e:
            print(f"  Fehler bei Prompt {i}: {e}")

    # Speichern im Format für den Trainer
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(golden_samples, f, indent=2, ensure_ascii=False)
    print(f"\nFertig! {len(golden_samples)} Golden Samples in {OUTPUT_FILE} gespeichert.")

if __name__ == "__main__":
    main()