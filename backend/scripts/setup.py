#!/usr/bin/env python3.12
"""
Script de configuración inicial para IA Jurídica
"""

import os
import sys
import subprocess
import asyncio
from pathlib import Path
from loguru import logger

# Agregar directorio raíz al path
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import settings
from utils.file_utils import FileUtils


class SetupManager:
    """Gestor de configuración inicial"""

    def __init__(self):
        self.file_utils = FileUtils()
        self.setup_steps = [
            ("Validando configuración", self.validate_config),
            ("Creando directorios", self.create_directories),
            ("Instalando dependencias", self.install_dependencies),
            ("Verificando componentes", self.verify_components),
            ("Inicializando base de datos", self.init_database),
            ("Configurando variables de entorno", self.setup_env_file),
        ]

    async def run_setup(self):
        """Ejecuta configuración completa"""

        print("🚀 Iniciando configuración de IA Jurídica v2.0")
        print("=" * 50)

        for step_name, step_func in self.setup_steps:
            print(f"\n📋 {step_name}...")
            try:
                await step_func()
                print(f"✅ {step_name} completado")
            except Exception as e:
                print(f"❌ Error en {step_name}: {str(e)}")
                logger.error(f"Setup step failed: {step_name} - {str(e)}")
                return False

        print("\n🎉 Configuración completada exitosamente!")
        await self.show_next_steps()
        return True

    async def validate_config(self):
        """Valida configuración del sistema"""

        validation = settings.validate_configuration()

        if not validation["valid"]:
            print("⚠️  Problemas críticos encontrados:")
            for issue in validation["issues"]:
                print(f"  - {issue}")
            raise Exception("Configuración inválida")

        if validation["warnings"]:
            print("⚠️  Advertencias:")
            for warning in validation["warnings"]:
                print(f"  - {warning}")

        print(
            f"✅ Configuración válida - {validation['configuration_summary']['app_name']} v{validation['configuration_summary']['version']}"
        )

    async def create_directories(self):
        """Crea estructura de directorios"""

        directories = [
            settings.DOCS_ROOT_DIR,
            settings.RAW_PDF_DIR,
            settings.PROCESSED_DIR,
            settings.KNOWLEDGE_GRAPH_DIR,
            settings.FAILED_DIR,
            settings.DATABASE_PATH.rsplit("/", 1)[0],
            settings.LOG_FILE.rsplit("/", 1)[0],
            settings.PDF_OUTPUT_DIR,
            settings.PDF_TEMPLATE_DIR,
            "./temp",
            "./evaluation",
            "./evaluation/test_cases",
            "./evaluation/results",
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            print(f"  📁 {directory}")

        print(f"✅ {len(directories)} directorios creados")

    async def install_dependencies(self):
        """Instala dependencias de Python"""
        project_root = Path(__file__).resolve().parents[2]
        pyproject_file = project_root / "pyproject.toml"

        if not pyproject_file.exists():
            raise Exception("pyproject.toml no encontrado en la raiz del proyecto")

        print("  📦 Sincronizando dependencias con uv...")

        try:
            result = subprocess.run(
                ["uv", "sync"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutos
            )

            if result.returncode != 0:
                print(f"⚠️  Advertencia durante instalación: {result.stderr}")
            else:
                print("  ✅ Dependencias sincronizadas")

        except subprocess.TimeoutExpired:
            print("⚠️  Instalación tomó mucho tiempo, continuando...")
        except Exception as e:
            raise Exception(f"Error instalando dependencias: {str(e)}")

    async def verify_components(self):
        """Verifica componentes principales"""

        components = {
            "FastAPI": self._check_fastapi,
            "Docling": self._check_docling,
            "LightRAG": self._check_lightrag,
            "Pydantic AI": self._check_pydantic_ai,
            "DeepEval": self._check_deepeval,
        }

        for component_name, check_func in components.items():
            try:
                available = await check_func()
                status = "✅" if available else "❌"
                print(f"  {status} {component_name}")
            except Exception as e:
                print(f"  ❌ {component_name} - Error: {str(e)}")

    async def _check_fastapi(self) -> bool:
        """Verifica FastAPI"""
        try:
            import fastapi

            return True
        except ImportError:
            return False

    async def _check_docling(self) -> bool:
        """Verifica Docling"""
        try:
            import docling

            return True
        except ImportError:
            return False

    async def _check_lightrag(self) -> bool:
        """Verifica LightRAG"""
        try:
            import lightrag

            return True
        except ImportError:
            return False

    async def _check_pydantic_ai(self) -> bool:
        """Verifica Pydantic AI"""
        try:
            import pydantic_ai

            return True
        except ImportError:
            return False

    async def _check_deepeval(self) -> bool:
        """Verifica DeepEval"""
        try:
            import deepeval

            return True
        except ImportError:
            return False

    async def init_database(self):
        """Inicializa base de datos"""

        try:
            # Importar y ejecutar inicialización
            from database.init import initializeDatabase

            await initializeDatabase()
            print("  ✅ Base de datos inicializada")
        except Exception as e:
            print(f"  ⚠️  Error inicializando BD: {str(e)}")
            # No es crítico, continuar

    async def setup_env_file(self):
        """Configura archivo .env"""

        env_file = Path(__file__).parent.parent / ".env"
        env_example = Path(__file__).parent.parent / ".env.example"

        if not env_file.exists() and env_example.exists():
            # Copiar ejemplo
            import shutil

            shutil.copy(env_example, env_file)
            print("  📝 .env creado desde .env.example")

            print("  ⚠️  IMPORTANTE: Edita .env y configura:")
            print("    - COHERE_API_KEY")
            print("    - SECRET_KEY")
            print("    - Otras variables según necesites")
        elif env_file.exists():
            print("  ✅ .env ya existe")
        else:
            print("  ⚠️  No se encontró .env.example")

    async def show_next_steps(self):
        """Muestra próximos pasos"""

        print("\n🎯 Próximos pasos:")
        print("1. Configura tus API Keys en .env:")
        print("   - COHERE_API_KEY=tu_api_key_aqui")
        print("   - SECRET_KEY=tu_secreto_aqui")
        print()
        print("2. Coloca tus PDFs legales en:")
        print(f"   {settings.RAW_PDF_DIR}")
        print()
        print("3. Inicia el servidor:")
        print("   pnpm run backend:dev:safe")
        print()
        print("4. Accede a la API:")
        print(f"   http://{settings.HOST}:{settings.PORT}")
        print()
        print("5. Sube y procesa PDFs:")
        print("   POST /upload-pdf")
        print("   POST /batch-process")
        print()
        print("📚 Para más información, consulta DOCUMENTATION.md")


async def main():
    """Función principal"""

    # Configurar logging
    logger.remove()
    logger.add(sys.stdout, level="INFO")

    # Ejecutar setup
    setup_manager = SetupManager()
    success = await setup_manager.run_setup()

    if success:
        print("\n🎉 Sistema listo para usar!")
        sys.exit(0)
    else:
        print("\n❌ Configuración fallida")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
