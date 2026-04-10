import json
import os
from pathlib import Path

import httpx

# ---------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PLUGIN_DIR = BASE_DIR / "plugins" / "archimate3"
LOG_FILE = Path(__file__).resolve().parent / "archimate_test_log.json"

PROXY_URL = "http://localhost:6969/v1/chat/completions"
MODEL = "gpt-oss:20b"


def read_xsds() -> str:
    """Liest die Inhalte der drei ArchiMate-XSD-Dateien aus dem Plugin-Ordner."""
    xsds = ""
    xsd_files = ["archimate3_Model.xsd", "archimate3_View.xsd", "archimate3_Diagram.xsd"]
    
    for xsd_file in xsd_files:
        path = PLUGIN_DIR / xsd_file
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                xsds += f"\n--- XSD: {xsd_file} ---\n"
                xsds += f.read()
        else:
            print(f"Warnung: {xsd_file} nicht gefunden unter {path}")
            
    return xsds


def run_test(test_name: str, system_prompt: str, user_prompt: str) -> dict:
    """Sendet den Prompt an den MDAL-Proxy und gibt das Ergebnis zurück."""
    print(f"\nStarte Testlauf: {test_name}")
    print("Warte auf Antwort vom Proxy (dies kann bei großen Prompts lokal dauern)...")
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1
    }

    try:
        # Sehr hoher Timeout (900s), da lokales 20B Modell extrem lange rechnet
        with httpx.Client(timeout=900.0) as client:
            response = client.post(PROXY_URL, json=payload)
            
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print(f"✓ {test_name}: Erfolgreich (Status 200)")
            return {"test": test_name, "status": "success", "response": content}
        else:
            print(f"✗ {test_name}: Fehler (Status {response.status_code})")
            return {"test": test_name, "status": "error", "error": f"{response.status_code}: {response.text}"}
    except Exception as e:
        print(f"⚠ {test_name}: Exception aufgetreten ({str(e)})")
        return {"test": test_name, "status": "exception", "error": str(e)}


def main():
    os.makedirs(LOG_FILE.parent, exist_ok=True)
    
    user_prompt = (
        "Erstelle ein simples ArchiMate 3.1 Modell im XML Exchange Format. "
        "Es soll nur einen 'Business Actor' (Kunde) und einen 'Business Process' "
        "(Kundenbetreuung) enthalten, die miteinander verbunden sind.\n\n"
        "WICHTIGE REGELN FÜR DAS XML:\n"
        "1. Das Wurzelelement muss zwingend klein geschrieben sein und eine ID haben: "
        "<model identifier=\"id-1234\" xmlns=\"http://www.opengroup.org/xsd/archimate/3.0/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">\n"
        "2. Das <model>-Element muss als erstes Kind-Element zwingend ein <name>-Element enthalten (z.B. <name>Test</name>).\n"
        "3. Erst danach dürfen die Tags <elements> und <relationships> folgen."
    )

    results = []

    # Test 1: Ohne XSD
    sys_no_xsd = "Du bist ein Experte für Unternehmensarchitektur. Antworte ausschließlich mit validem XML-Code."
    results.append(run_test("Ohne_XSD", sys_no_xsd, user_prompt))

    # Test 2: Mit XSD
    sys_with_xsd = f"Du bist ein Experte für Unternehmensarchitektur. Antworte ausschließlich mit validem XML-Code. Die folgenden XSD-Definitionen sind bindend:\n{read_xsds()}"
    results.append(run_test("Mit_XSD", sys_with_xsd, user_prompt))

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nBeendet! Ergebnisse in {LOG_FILE} gespeichert.")

if __name__ == "__main__":
    main()