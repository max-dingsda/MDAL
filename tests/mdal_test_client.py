from openai import OpenAI

# 1. Wir initialisieren den offiziellen OpenAI-Client,
# leiten ihn aber auf unseren lokalen MDAL-Proxy um!
client = OpenAI(
    base_url="http://localhost:6969/v1", 
    api_key="mdal-key" # Wird von MDAL ignoriert oder durchgereicht
)

def main():
    print("Sende Test-Anfrage an MDAL...\n")
    
    try:
        response = client.chat.completions.create(
            model="irrelevant", # Das tatsächliche Modell wird in der config.html festgelegt
            messages=[
                {"role": "user", "content": "Schreibe eine kurze Absage auf eine Bewerbung."}
            ],
            stream=False, # WICHTIG: MDAL benötigt den vollständigen Text zur Überprüfung
            extra_headers={"X-MDAL-Language": "de"} # Erzwingt die Prüfung gegen den deutschen Fingerprint
        )
        
        print("✅ Antwort von MDAL erfolgreich verifiziert und empfangen:\n")
        print(response.choices[0].message.content)
        
    except Exception as e:
        print(f"❌ Fehler bei der Anfrage: {e}")

if __name__ == "__main__":
    main()