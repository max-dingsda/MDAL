(MDAL) F:\MDAL>python -m mdal.proxy.server
2026-04-05 19:47:29,171 INFO mdal.server: Lade Konfiguration: config/mdal.yaml
2026-04-05 19:47:29,174 INFO mdal.server: Initialisiere MDAL-Pipeline …
2026-04-05 19:47:29,175 INFO mdal.server: Prüfe Konnektivität zu externen Endpunkten …
2026-04-05 19:47:29,278 INFO httpx: HTTP Request: GET http://localhost:11434/v1/models "HTTP/1.1 200 OK"
2026-04-05 19:47:29,311 INFO httpx: HTTP Request: GET http://localhost:11434/v1/models "HTTP/1.1 200 OK"
2026-04-05 19:47:29,312 INFO mdal.server: MDAL-Proxy bereit auf 0.0.0.0:8081
INFO:     Started server process [9468]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8081 (Press CTRL+C to quit)
2026-04-05 19:47:39,905 INFO mdal.status: [STATUS] Anfrage wird verarbeitet
2026-04-05 19:47:40,152 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:40,154 INFO mdal.pipeline: Säule B: Erkannte Text-Domäne für Request: TECHNICAL
2026-04-05 19:47:40,804 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:40,805 INFO mdal.status: [STATUS] Ergebnis wird geprüft
2026-04-05 19:47:40,806 INFO mdal.status: [STATUS] Antwort ist bereit
INFO:     127.0.0.1:64173 - "POST /v1/chat/completions HTTP/1.1" 200 OK
2026-04-05 19:47:44,114 INFO mdal.status: [STATUS] Anfrage wird verarbeitet
2026-04-05 19:47:44,396 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:44,397 INFO mdal.pipeline: Säule B: Erkannte Text-Domäne für Request: SHORT_COPY
2026-04-05 19:47:46,520 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:46,521 INFO mdal.status: [STATUS] Ergebnis wird geprüft
2026-04-05 19:47:48,321 INFO httpx: HTTP Request: POST http://localhost:11434/v1/embeddings "HTTP/1.1 200 OK"
2026-04-05 19:47:49,789 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:49,790 INFO mdal.status: [STATUS] Ergebnis wird angepasst
2026-04-05 19:47:52,756 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:52,758 WARNING mdal.transformer: Transformer Confidence Score zu niedrig (Ratio: 0.34). Transformation verworfen (Demut).
2026-04-05 19:47:52,759 INFO mdal.status: [STATUS] Antwort ist bereit
INFO:     127.0.0.1:64180 - "POST /v1/chat/completions HTTP/1.1" 200 OK
2026-04-05 19:47:55,413 INFO mdal.status: [STATUS] Anfrage wird verarbeitet
2026-04-05 19:47:55,740 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:55,741 INFO mdal.pipeline: Säule B: Erkannte Text-Domäne für Request: TECHNICAL
2026-04-05 19:47:56,353 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:56,354 INFO mdal.status: [STATUS] Ergebnis wird geprüft
2026-04-05 19:47:56,477 INFO httpx: HTTP Request: POST http://localhost:11434/v1/embeddings "HTTP/1.1 200 OK"
2026-04-05 19:47:56,479 INFO mdal.status: [STATUS] Antwort wird überarbeitet
2026-04-05 19:47:57,396 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:47:57,398 INFO mdal.status: [STATUS] Ergebnis wird geprüft
2026-04-05 19:47:57,549 INFO httpx: HTTP Request: POST http://localhost:11434/v1/embeddings "HTTP/1.1 200 OK"
2026-04-05 19:47:57,552 ERROR mdal.notifier: 🛑 Fachliche Eskalation (503) - Abbruch nach 2 Versuchen: Stilregel-Verletzung: Kein bevorzugtes Vokabular gefunden.; Formalität stark abweichend: erwartet=4, geschätzt≈2 (Δ=2).; Stil-Abweichung (Embedding): Cosine-Similarity: 0.6039 (high≥0.8, low<0.65)
INFO:     127.0.0.1:64251 - "POST /v1/chat/completions HTTP/1.1" 503 Service Unavailable
2026-04-05 19:48:04,653 INFO mdal.status: [STATUS] Anfrage wird verarbeitet
2026-04-05 19:48:04,905 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:48:04,906 INFO mdal.pipeline: Säule B: Erkannte Text-Domäne für Request: SHORT_COPY
2026-04-05 19:48:11,153 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:48:11,153 INFO mdal.status: [STATUS] Ergebnis wird geprüft
2026-04-05 19:48:11,239 INFO httpx: HTTP Request: POST http://localhost:11434/v1/embeddings "HTTP/1.1 200 OK"
2026-04-05 19:48:11,242 INFO mdal.status: [STATUS] Antwort wird überarbeitet
2026-04-05 19:48:17,290 INFO httpx: HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
2026-04-05 19:48:17,291 INFO mdal.status: [STATUS] Ergebnis wird geprüft
2026-04-05 19:48:17,442 INFO httpx: HTTP Request: POST http://localhost:11434/v1/embeddings "HTTP/1.1 200 OK"
2026-04-05 19:48:17,445 ERROR mdal.notifier: 🛑 Fachliche Eskalation (503) - Abbruch nach 2 Versuchen: Stilregel-Verletzung: Kein bevorzugtes Vokabular gefunden.; Formalität stark abweichend: erwartet=4, geschätzt≈2 (Δ=2).