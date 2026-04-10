import pytest
from unittest.mock import patch, mock_open
from fastapi.testclient import TestClient

from mdal.proxy.app import app

client = TestClient(app)

@patch("mdal.proxy.app.subprocess.Popen")
@patch("mdal.proxy.app.Path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data="env_start_cmd: 'conda activate mdal'")
def test_start_trainer_api_with_payload(mock_file, mock_exists, mock_popen):
    """Testet, ob der Trainer mit den korrekten Custom-Parametern und aktivem VENV gestartet wird."""
    payload = {
        "input_path": "varPrivateDocs/my_custom_chats.json",
        "language": "en"
    }
    
    response = client.post("/api/trainer/start", json=payload)
    
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    
    # Prüfen, ob Popen aufgerufen wurde und der Befehl korrekt formatiert ist
    mock_popen.assert_called_once()
    call_args = mock_popen.call_args[0][0]
    
    assert "conda activate mdal" in call_args
    assert "timeout /t 3 /nobreak" in call_args
    assert "python -m mdal.trainer.trainer" in call_args
    assert "--input \"varPrivateDocs/my_custom_chats.json\"" in call_args
    assert "--language en" in call_args
    assert call_args.startswith("cmd.exe /k")

@patch("mdal.proxy.app.subprocess.Popen")
@patch("mdal.proxy.app.Path.exists", return_value=False)
def test_start_trainer_api_default_values(mock_exists, mock_popen):
    """Testet, ob die Default-Werte verwendet werden, wenn nur ein leeres JSON gesendet wird."""
    response = client.post("/api/trainer/start", json={})
    
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    
    mock_popen.assert_called_once()
    call_args = mock_popen.call_args[0][0]
    
    # Da config/mdal.yaml in diesem Mock "nicht existiert", darf kein env_start_cmd/timeout dabei sein
    assert "timeout" not in call_args
    assert "--input \"manuelle_tests/semantik/gpt4o_chats.json\"" in call_args
    assert "--language de" in call_args