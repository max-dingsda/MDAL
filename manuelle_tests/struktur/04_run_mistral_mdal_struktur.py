import json
import urllib.request
import urllib.error

PROMPTS_FILE = "struktur_prompts.json"
OUTPUT_FILE = "mistral_mdal_struktur_log.json"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions" # Raw Mistral
MDAL_URL = "http://localhost:8081/v1/chat/completions"    # MDAL Proxy
MODEL = "mistral:latest"

def main():
    print(f"Lese Struktur-Prompts aus {PROMPTS_FILE}...")
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    log_entries = []

    for i, prompt in enumerate(prompts, 1):
        print(f"\n[{i}/{len(prompts)}] Verarbeite Prompt...")
        
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2  # Niedrige Temperatur für strukturierte Outputs
        }
        data = json.dumps(payload).encode("utf-8")
        
        # 1. RAW Aufruf (ohne MDAL)
        print(f"  -> Sende an RAW Mistral (Port 11434)...")
        raw_req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
        raw_response_text = "N/A"
        try:
            with urllib.request.urlopen(raw_req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                raw_response_text = result["choices"][0]["message"]["content"]
                print(f"     Raw-Antwort erhalten ({len(raw_response_text)} Zeichen).")
        except Exception as e:
            print(f"     Fehler bei RAW: {e}")

        # 2. MDAL Aufruf
        print(f"  -> Sende an MDAL (Port 8081)...")
        mdal_req = urllib.request.Request(MDAL_URL, data=data, headers={"Content-Type": "application/json"})
        mdal_response_text = "N/A"
        try:
            with urllib.request.urlopen(mdal_req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                mdal_response_text = result["choices"][0]["message"]["content"]
                print(f"     MDAL-Antwort erhalten ({len(mdal_response_text)} Zeichen).")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"     MDAL HTTP Fehler: {e.code} - {error_body}")
        except Exception as e:
            print(f"     System/Netzwerk Fehler bei MDAL: {e}")

        # Loggen von BEIDEN Antworten
        log_entries.append({
            "prompt": prompt,
            "mistral_raw_response": raw_response_text,
            "mistral_mdal_response": mdal_response_text
        })

        # Inkrementelles Speichern
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(log_entries, f, indent=2, ensure_ascii=False)

    print(f"\nFertig! Struktur-Ergebnisse in {OUTPUT_FILE} gespeichert.")

if __name__ == "__main__":
    main()