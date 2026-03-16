#!/usr/bin/env python3
"""
Script para configurar el modo híbrido de IA Jurídica
Combina servicios locales con Docker y servicios en la nube
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def print_status(message: str, status: str = "INFO"):
    """Imprimir mensajes con formato"""
    icons = {
        "INFO": "ℹ️",
        "SUCCESS": "✅", 
        "ERROR": "❌",
        "WARNING": "⚠️"
    }
    print(f"{icons.get(status, 'ℹ️')} {message}")

def check_requirements():
    """Verificar requisitos del sistema"""
    print_status("Verificando requisitos del sistema...")
    
    # Verificar Docker
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        print_status("Docker encontrado", "SUCCESS")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_status("Docker no encontrado. Por favor instala Docker Desktop", "ERROR")
        return False
    
    # Verificar Python
    if sys.version_info < (3, 8):
        print_status("Python 3.8+ requerido", "ERROR")
        return False
    
    print_status("Requisitos verificados", "SUCCESS")
    return True

def setup_environment():
    """Configurar variables de entorno"""
    print_status("Configurando variables de entorno...")
    
    # Copiar env.hybrid a .env si no existe
    if not Path(".env").exists():
        if Path("env.hybrid").exists():
            shutil.copy("env.hybrid", ".env")
            print_status("env.hybrid copiado a .env", "SUCCESS")
        else:
            print_status("env.hybrid no encontrado", "ERROR")
            return False
    else:
        print_status(".env ya existe, omitiendo copia", "WARNING")
    
    return True

def start_docker_services():
    """Iniciar servicios Docker"""
    print_status("Iniciando servicios Docker...")
    
    services = {
        "weaviate": {
            "image": "semitechnologies/weaviate:1.19.0",
            "ports": ["8082:8080", "8083:8081"],
            "env": {
                "QUERY_DEFAULTS_LIMIT": "25",
                "AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED": "true",
                "PERSISTENCE_DATA_PATH": "/var/lib/weaviate"
            },
            "volumes": ["./data:/var/lib/weaviate"]
        }
    }
    
    for service_name, config in services.items():
        print_status(f"Iniciando {service_name}...")
        
        cmd = [
            "docker", "run", "-d", 
            "--name", service_name,
            "-p", config["ports"][0],
            "-p", config["ports"][1]
        ]
        
        # Agregar variables de entorno
        for key, value in config["env"].items():
            cmd.extend(["-e", f"{key}={value}"])
        
        # Agregar volúmenes
        for volume in config["volumes"]:
            cmd.extend(["-v", volume])
        
        cmd.append(config["image"])
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print_status(f"{service_name} iniciado", "SUCCESS")
        except subprocess.CalledProcessError as e:
            print_status(f"Error iniciando {service_name}: {e}", "ERROR")
            return False
    
    return True

def wait_for_services():
    """Esperar a que los servicios estén listos"""
    import time
    import requests
    
    print_status("Esperando a que Weaviate esté listo...")
    
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:8082/v1/.well-known/ready", timeout=5)
            if response.status_code == 200:
                print_status("Weaviate está listo", "SUCCESS")
                return True
        except requests.exceptions.RequestException:
            pass
        
        print_status(f"Intento {i+1}/{max_retries}...")
        time.sleep(2)
    
    print_status("Timeout esperando a Weaviate", "ERROR")
    return False

def setup_python_environment():
    """Configurar entorno Python"""
    print_status("Configurando entorno Python...")
    
    os.chdir("backend")
    
    # Crear virtual environment si no existe
    if not Path("venv").exists():
        print_status("Creando virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
    
    # Activar virtual environment
    if os.name == "nt":  # Windows
        activate_cmd = ["venv\\Scripts\\activate.bat"]
    else:  # Unix
        activate_cmd = ["source", "venv/bin/activate"]
    
    # Instalar dependencias
    print_status("Instalando dependencias...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    
    os.chdir("..")
    print_status("Entorno Python configurado", "SUCCESS")
    return True

def main():
    """Función principal"""
    print_status("🚀 Configurando modo híbrido de IA Jurídica", "INFO")
    print("=" * 50)
    
    # Verificar requisitos
    if not check_requirements():
        sys.exit(1)
    
    # Configurar entorno
    if not setup_environment():
        sys.exit(1)
    
    # Iniciar servicios Docker
    if not start_docker_services():
        sys.exit(1)
    
    # Esperar a servicios
    if not wait_for_services():
        sys.exit(1)
    
    # Configurar Python
    if not setup_python_environment():
        sys.exit(1)
    
    print("=" * 50)
    print_status("🎉 Modo híbrido configurado exitosamente!", "SUCCESS")
    print_status("Para iniciar la aplicación:", "INFO")
    print_status("  cd backend && python main.py", "INFO")
    print_status("O usa: python start-dev.py", "INFO")

if __name__ == "__main__":
    main()
