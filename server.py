#!/usr/bin/env python3
"""
Claude Dementia MCP Server - Lean Local Version
"""

import os
import json
import sqlite3
import asyncio
import hashlib
import time
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
import uuid
from contextlib import contextmanager

from mcp.server import FastMCP
import httpx

# Initialize MCP server
mcp = FastMCP("claude-dementia-local")

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    def __init__(self):
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.db_path = os.getenv("CLAUDE_MEMORY_DB", ".claude-memory.db")

config = Config()

# ============================================================================
# DATABASE SETUP (SQLite)
# ============================================================================

def get_db_connection():
    """Get SQLite database connection"""
    conn = sqlite3.connect(config.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Initialize database tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            started_at REAL NOT NULL,
            ended_at REAL,
            last_active REAL,
            summary TEXT,
            project_path TEXT,
            project_name TEXT
        )
    ''')

    # Context locks (memories)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS context_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_persistent BOOLEAN DEFAULT 0,
            metadata TEXT,
            embedding BLOB,
            embedding_model TEXT,
            UNIQUE(session_id, label)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize on startup
initialize_database()

# ============================================================================
# EMBEDDING SERVICE (Ollama)
# ============================================================================

async def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding using Ollama"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.ollama_base_url}/api/embeddings",
                json={
                    "model": config.embedding_model,
                    "prompt": text
                },
                timeout=10.0
            )
            if response.status_code == 200:
                return response.json().get("embedding")
            else:
                print(f"Error getting embedding: {response.status_code} {response.text}", file=sys.stderr)
                return None
    except Exception as e:
        print(f"Embedding error: {e}", file=sys.stderr)
        return None

# ============================================================================
# CORE TOOLS
# ============================================================================

@mcp.tool()
def get_status() -> str:
    """Get the current status of the memory server"""
    return f"Claude Dementia Local Server Active\nDatabase: {config.db_path}\nEmbedding Model: {config.embedding_model}"

@mcp.tool()
async def store_memory(content: str, label: str, is_persistent: bool = False, project_path: str = None) -> str:
    """
    Store a memory in the database.
    
    Args:
        content: The text content to store
        label: A unique label/key for this memory
        is_persistent: Whether this memory should persist across sessions (default: False)
        project_path: Optional project path to associate with
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get or create session
    # For local mode, we can use a simpler session management or just one session per project
    # For now, let's just use a "default" session if not specified, or derive from project path
    
    project_path = project_path or os.getcwd()
    project_name = os.path.basename(project_path)
    session_id = f"local_{hashlib.md5(project_path.encode()).hexdigest()[:8]}"
    
    # Ensure session exists
    cursor.execute("INSERT OR IGNORE INTO sessions (id, started_at, last_active, project_path, project_name) VALUES (?, ?, ?, ?, ?)",
                  (session_id, time.time(), time.time(), project_path, project_name))
    
    # Generate embedding
    embedding = await get_embedding(content)
    embedding_blob = json.dumps(embedding) if embedding else None
    
    content_hash = hashlib.md5(content.encode()).hexdigest()
    
    try:
        # Use version 1.0 for lean mode
        version = "1.0"
        cursor.execute("""
            INSERT INTO context_locks (session_id, label, version, content, content_hash, is_persistent, embedding, embedding_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, label, version) DO UPDATE SET
            content = excluded.content,
            content_hash = excluded.content_hash,
            is_persistent = excluded.is_persistent,
            embedding = excluded.embedding,
            embedding_model = excluded.embedding_model,
            locked_at = CURRENT_TIMESTAMP
        """, (session_id, label, version, content, content_hash, is_persistent, embedding_blob, config.embedding_model))
        conn.commit()
        return f"Memory '{label}' stored successfully."
    except Exception as e:
        return f"Error storing memory: {str(e)}"
    finally:
        conn.close()

@mcp.tool()
def retrieve_memory(label: str, project_path: str = None) -> str:
    """Retrieve a specific memory by label"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    project_path = project_path or os.getcwd()
    session_id = f"local_{hashlib.md5(project_path.encode()).hexdigest()[:8]}"
    
    cursor.execute("SELECT content FROM context_locks WHERE session_id = ? AND label = ?", (session_id, label))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row['content']
    return f"No memory found with label '{label}'"

@mcp.tool()
async def search_memories(query: str, limit: int = 5, project_path: str = None) -> str:
    """
    Search memories using vector similarity (if embeddings available) or text search.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    project_path = project_path or os.getcwd()
    session_id = f"local_{hashlib.md5(project_path.encode()).hexdigest()[:8]}"
    
    # Try vector search first
    query_embedding = await get_embedding(query)
    
    results = []
    
    if query_embedding:
        # Naive vector search in Python (for "lean" implementation without vector extension)
        # Fetch all memories for session with embeddings
        cursor.execute("SELECT label, content, embedding FROM context_locks WHERE session_id = ? AND embedding IS NOT NULL", (session_id,))
        rows = cursor.fetchall()
        
        import numpy as np
        
        def cosine_similarity(v1, v2):
            return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        
        scored_results = []
        for row in rows:
            try:
                emb = json.loads(row['embedding'])
                score = cosine_similarity(query_embedding, emb)
                scored_results.append((score, row['label'], row['content']))
            except:
                continue
        
        scored_results.sort(key=lambda x: x[0], reverse=True)
        results = [f"[{label}] (Score: {score:.2f})\n{content[:200]}..." for score, label, content in scored_results[:limit]]
    
    # Fallback to text search if no results or no embedding
    if not results:
        cursor.execute("SELECT label, content FROM context_locks WHERE session_id = ? AND content LIKE ? LIMIT ?", (session_id, f"%{query}%", limit))
        rows = cursor.fetchall()
        results = [f"[{row['label']}]\n{row['content'][:200]}..." for row in rows]
        
    conn.close()
    
    if not results:
        return "No matching memories found."
    
    return "\n\n".join(results)

if __name__ == "__main__":
    mcp.run()
