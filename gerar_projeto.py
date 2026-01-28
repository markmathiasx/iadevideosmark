import os

# Estrutura do projeto
files = {
    "docker-compose.yml": """
version: '3.8'
services:
  ollama:
    image: ollama/ollama
    container_name: ollama_server
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  app:
    build: .
    depends_on:
      - ollama
    environment:
      - OPENAI_API_KEY=SUA_CHAVE_AQUI
      - OLLAMA_HOST=http://ollama:11434

volumes:
  ollama_data:
""",

    "requirements.txt": """
requests
python-dotenv
openai
""",

    ".env": """
OPENAI_API_KEY=sk-xxxxxxx # Substitua pela sua chave
OLLAMA_BASE_URL=http://localhost:11434
""",

    "main.py": """
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
""",
    "Dockerfile": """
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
"""
}

def create_project():
    project_dir = "MeuProjetoAI"
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)
    
    for filename, content in files.items():
        with open(os.path.join(project_dir, filename), 'w', encoding='utf-8') as f:
            f.write(content.strip())
    
    print(f"✅ Projeto criado com sucesso na pasta: {os.path.abspath(project_dir)}")
    print("Próximos passos:")
    print(f"1. cd {project_dir}")
    print("2. pip install -r requirements.txt")
    print("3. docker compose up --build -d")

if __name__ == "__main__":
    create_project()