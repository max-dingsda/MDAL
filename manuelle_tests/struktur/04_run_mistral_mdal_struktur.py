import json
import urllib.request
import urllib.error

PROMPTS_FILE = "struktur_prompts.json"
OUTPUT_FILE = "mistral_mdal_struktur_log.json"
URL = "http://localhost:8081/v1/chat/completions" # MDAL Proxy Port
MODEL = "mistral:latest"

def main():
    print(f"Lese Struktur-Prompts aus {PROMPTS_FILE}...")
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    log_entries = []

    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] Sende Struktur-Prompt an {MODEL} (MIT MDAL)...")
        
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2  # Niedrige Temperatur für strukturierte Outputs
        }
        
        req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                assistant_message = result["choices"][0]["message"]["content"]
                
                log_entries.append({
                    "prompt": prompt,
                    "mistral_mdal_response": assistant_message
                })
                print(f"  Erfolgreich empfangen ({len(assistant_message)} Zeichen).")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  HTTP Fehler bei Prompt {i}: {e.code} - {error_body}")
        except Exception as e:
            print(f"  System/Netzwerk Fehler bei Prompt {i}: {e}")

        # Inkrementelles Speichern
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(log_entries, f, indent=2, ensure_ascii=False)

    print(f"\nFertig! Struktur-Ergebnisse in {OUTPUT_FILE} gespeichert.")

if __name__ == "__main__":
    main()