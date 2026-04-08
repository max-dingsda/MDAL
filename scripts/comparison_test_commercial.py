import json
import os
import time
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from anthropic import Anthropic

def main():
    # API Keys prüfen
    oai_key = os.environ.get("OPENAI_API_KEY")
    ant_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if not oai_key or not ant_key:
        print("FEHLER: OPENAI_API_KEY und ANTHROPIC_API_KEY müssen gesetzt sein!")
        return

    # Clients initialisieren (GPT-Client entfällt, da wir den Cache nutzen)
    client_claude = Anthropic(api_key=ant_key)
    mdal_port = os.environ.get("MDAL_PORT", "6969")
    client_mdal = OpenAI(base_url=f"http://localhost:{mdal_port}/v1", api_key="dummy-key")

    input_file = Path("manuelle_tests/semantik/gpt4o_chats.json")
    output_dir = Path("manuelle_tests/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_file = output_dir / f"commercial_comparison_{timestamp}.md"

    if not input_file.exists():
        print(f"FEHLER: Baseline-Datei fehlt: {input_file}. Bitte erst Schritt 1 ausführen!")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        chats = json.load(f)

    print(f"Starte Commercial Comparison Test mit vollen {len(chats)} Prompts (GPT-4o aus Cache)...\n")

    with open(md_file, "w", encoding="utf-8") as md:
        md.write(f"# MDAL Commercial Model-Shift Test\n")
        md.write(f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        md.write("| # | Prompt (Auszug) | GPT-4o (Soll) | Claude (Roh) | Claude + MDAL (Ist) |\n")
        md.write("|---|---|---|---|---|\n")

        for i, item in enumerate(chats, 1):
            prompt_text = item[0]["content"]
            res_gpt     = item[1]["content"]  # A: GPT-4o (Baseline direkt aus JSON)
            
            print(f"[{i}/{len(chats)}] {prompt_text[:50]}...")
            
            res_claude = "FEHLER"
            res_mdal = "FEHLER"

            # B: Claude Sonnet direkt
            try:
                resp = client_claude.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt_text}]
                )
                res_claude = resp.content[0].text
            except Exception as e:
                print(f"  [!] Claude Fehler: {e}")

            # C: Claude Sonnet via MDAL (welcher via LiteLLM zu Claude spricht)
            try:
                resp = client_mdal.chat.completions.create(
                    model="claude-sonnet-4-6",
                    messages=[{"role": "user", "content": prompt_text}],
                    extra_headers={"X-MDAL-Language": "de"}
                )
                res_mdal = resp.choices[0].message.content
            except Exception as e:
                print(f"  [!] MDAL Fehler: {e}")
                
            # Ins Markdown schreiben (Zeilenumbrüche entfernen für die Tabelle)
            safe_prompt = prompt_text[:40].replace('\n', ' ') + "..."
            safe_gpt = res_gpt.replace('\n', '<br>')
            safe_claude = res_claude.replace('\n', '<br>')
            safe_mdal = res_mdal.replace('\n', '<br>')
            
            md.write(f"| {i} | {safe_prompt} | {safe_gpt} | {safe_claude} | {safe_mdal} |\n")
            
            time.sleep(1) # Kurze Pause für Rate Limits

        md.write("\n## Beobachtungen & Ergebnisse\n")
        md.write("*Hier manuell Eintragen: Hat MDAL die Claude-Antworten in Richtung des GPT-4o-Stils korrigiert?*\n")

    print(f"\nTest abgeschlossen! Ergebnisse gespeichert in: {md_file}")

if __name__ == "__main__":
    main()