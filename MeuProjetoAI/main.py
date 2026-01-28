import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def check_ollama():
    try:
        response = requests.get(f"{os.getenv('OLLAMA_BASE_URL')}/api/tags")
        return response.status_code == 200
    except:
        return False

def run_task():
    print("--- Iniciando Tarefa ---")
    
    if not check_ollama():
        print("ERRO: Ollama não está rodando! Certifique-se de que o Docker ou o App Ollama está ativo.")
        return

    payload = {
        "provider": "openai",
        "task": "text_to_image",
        "prompt": "Gragas Oktoberfest holding an iPhone 17 Pro Max, realistic, 9:16, cinematic",
        "mode": "social_meme",
        "include_thinking": True
    }
    
    # Aqui entraria sua lógica de chamada para a OpenAI ou DeepSeek
    print(f"Enviando solicitação: {payload['prompt']}")
    print("Status: Processando com melhorias de estabilidade...")

if __name__ == "__main__":
    run_task()