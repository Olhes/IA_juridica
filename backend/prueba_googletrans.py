import asyncio
from googletrans import Translator

async def main():
    print("Prueba aislada de googletrans 4.0.2")
    print("=" * 60)
    
    try:
        async with Translator(service_urls=["translate.googleapis.com"]) as t:
            print("Traduciendo 'Hola, ¿cómo estás?' de español a quechua...")
            r = await t.translate("Hola, ¿cómo estás?", src="es", dest="qu")
            print(f"Resultado: {r.text}")
            print(f"Texto original: {r.origin}")
            print(f"Confianza: {r.confidence}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
