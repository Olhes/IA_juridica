"""
Debug para verificar valores de settings
"""

from config.settings import settings

print("=== DEBUG DE SETTINGS ===")
print(f"DATABASE_HOST: '{settings.DATABASE_HOST}'")
print(f"DATABASE_PORT: {settings.DATABASE_PORT} (tipo: {type(settings.DATABASE_PORT)})")
print(f"DATABASE_NAME: '{settings.DATABASE_NAME}'")
print(f"DATABASE_USER: '{settings.DATABASE_USER}'")
print(f"DATABASE_PASSWORD: '{settings.DATABASE_PASSWORD}'")
print(f"DATABASE_URL: '{settings.DATABASE_URL}'")
print(f"SQLALCHEMY_DATABASE_URL: '{settings.SQLALCHEMY_DATABASE_URL}'")
print("========================")
