import asyncio
import os
import sys
import sqlite3
from server import get_embedding, store_memory, retrieve_memory, search_memories, config

async def verify():
    print("Verifying Local MCP Server...")
    
    # 1. Check Database
    print(f"\n1. Checking Database: {config.db_path}")
    if not os.path.exists(config.db_path):
        print("❌ Database file not found!")
        return
    
    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"   Tables found: {tables}")
    if 'sessions' in tables and 'context_locks' in tables:
        print("✅ Database initialized correctly")
    else:
        print("❌ Missing tables")
    conn.close()
    
    # 2. Check Embeddings (Ollama)
    print("\n2. Checking Ollama Embeddings...")
    try:
        embedding = await get_embedding("Hello world")
        if embedding and len(embedding) > 0:
            print(f"✅ Embedding generated (length: {len(embedding)})")
        else:
            print("❌ Failed to generate embedding (is Ollama running?)")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 3. Check Memory Storage
    print("\n3. Checking Memory Storage...")
    try:
        result = await store_memory(
            content="This is a test memory for verification.",
            label="test_memory_1",
            project_path=os.getcwd()
        )
        print(f"   Store result: {result}")
        
        retrieved = retrieve_memory("test_memory_1", project_path=os.getcwd())
        print(f"   Retrieved: {retrieved}")
        
        if "test memory" in retrieved:
            print("✅ Memory stored and retrieved")
        else:
            print("❌ Memory retrieval failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")

    # 4. Check Vector Search
    print("\n4. Checking Vector Search...")
    try:
        # Give it a moment for any async/background stuff (though sqlite is sync here)
        results = await search_memories("verification", limit=1, project_path=os.getcwd())
        print(f"   Search results:\n{results}")
        if "test_memory_1" in results:
            print("✅ Vector/Text search working")
        else:
            print("⚠️ Search didn't find the memory (might be expected if embedding failed)")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
