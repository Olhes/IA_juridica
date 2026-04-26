import asyncio
import asyncpg

async def test_direct():
    """Test direct asyncpg connection"""
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='juridica_user',
            database='juridica_db',
            password='',
            timeout=10
        )
        result = await conn.fetchval('SELECT version()')
        print(f"[OK] Direct asyncpg: {result[:50]}...")
        await conn.close()
        return True
    except Exception as e:
        print(f"[FAIL] Direct asyncpg: {type(e).__name__}: {e}")
        return False

async def test_sqlalchemy():
    """Test SQLAlchemy asyncpg connection"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    
    try:
        engine = create_async_engine(
            'postgresql+asyncpg://juridica_user@localhost:5432/juridica_db',
            echo=False,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=False
        )
        async with engine.begin() as conn:
            result = await conn.execute(text('SELECT version()'))
            version = result.scalar()
            print(f"[OK] SQLAlchemy asyncpg: {version[:50]}...")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"[FAIL] SQLAlchemy asyncpg: {type(e).__name__}: {e}")
        return False

async def test_url_with_password():
    """Test with explicit empty password"""
    try:
        conn = await asyncpg.connect(
            'postgresql://juridica_user:@localhost:5432/juridica_db'
        )
        result = await conn.fetchval('SELECT 1')
        print(f"[OK] URL with empty password: {result}")
        await conn.close()
        return True
    except Exception as e:
        print(f"[FAIL] URL with empty password: {type(e).__name__}: {e}")
        return False

async def main():
    print("=" * 50)
    print("PostgreSQL Connection Diagnostics")
    print("=" * 50)
    
    results = []
    results.append(("Direct asyncpg", await test_direct()))
    results.append(("SQLAlchemy asyncpg", await test_sqlalchemy()))
    results.append(("URL empty password", await test_url_with_password()))
    
    print("=" * 50)
    print("Summary:")
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {name}: {status}")
    print("=" * 50)

if __name__ == '__main__':
    asyncio.run(main())
