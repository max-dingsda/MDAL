import json
import urllib.request
import urllib.error

PROMPTS_FILE = "prosa_prompts.json"
OUTPUT_FILE = "mistral_baseline_log.json"
URL = "http://localhost:11434/v1/chat/completions" # Direkter Ollama Port
MODEL = "mistral:latest"

def main():
    print(f"Lese Prompts aus {PROMPTS_FILE}...")
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    log_entries = []

    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] Sende Prompt an {MODEL} (OHNE MDAL)...")
        
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
                
                log_entries.append({
                    "prompt": prompt,
                    "mistral_baseline_response": assistant_message
                })
                print(f"  Erfolgreich empfangen ({len(assistant_message)} Zeichen).")
        except Exception as e:
            print(f"  Fehler bei Prompt {i}: {e}")

    # Log speichern
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(log_entries, f, indent=2, ensure_ascii=False)
    print(f"\nFertig! {len(log_entries)} Baseline-Antworten in {OUTPUT_FILE} gespeichert.")

if __name__ == "__main__":
    main()