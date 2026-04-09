import json
import urllib.request
import urllib.error
from langdetect import detect
import sys

print("Script loaded successfully!")
sys.stdout.flush()

PROMPTS_FILE = "prosa_prompts.json"
OUTPUT_FILE = "gemma4_mdal_log.json"
URL = "http://localhost:6969/v1/chat/completions" # MDAL Proxy Port
MODEL = "gemma4:e4b"

def detect_language(text: str) -> str:
    """Detects language of the text, returns 'de' as fallback."""
    try:
        return detect(text).split('-')[0].lower()
    except Exception as e:
        print(f"Language detection failed: {e}, using 'de'")
        return 'de'

def main():
    print("Starting script...")
    print(f"Reading prompts from {PROMPTS_FILE}...")
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        print(f"Loaded {len(prompts)} prompts.")
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return

    log_entries = []

    for i, prompt in enumerate(prompts, 1):
        detected_lang = detect_language(prompt)
        print(f"[{i}/{len(prompts)}] Sending prompt (detected lang: {detected_lang})...")
        
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        
        req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers={
            "Content-Type": "application/json",
            "X-MDAL-Language": detected_lang  # Set detected language in header
        })
        
        try:
            print("Sending request...")
            # Der Timeout ist höher gesetzt (120s), da MDAL Retries im Hintergrund ausführen könnte
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                assistant_message = result["choices"][0]["message"]["content"]
                
                log_entries.append({
                    "prompt": prompt,
                    "detected_lang": detected_lang,
                    "gemma4_mdal_response": assistant_message
                })
                print(f"  Success: received {len(assistant_message)} chars.")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  HTTP Error {e.code}: {error_body}")
            log_entries.append({
                "prompt": prompt,
                "detected_lang": detected_lang,
                "error": f"{e.code}: {error_body}"
            })
        except Exception as e:
            print(f"  Network/System Error: {e}")
            log_entries.append({
                "prompt": prompt,
                "detected_lang": detected_lang,
                "error": str(e)
            })

    # Log speichern
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(log_entries, f, indent=2, ensure_ascii=False)
        print(f"Done! Saved {len(log_entries)} entries to {OUTPUT_FILE}.")
    except Exception as e:
        print(f"Error saving log: {e}")

if __name__ == "__main__":
    main()