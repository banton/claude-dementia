#!/usr/bin/env python3
"""
MCP Server Wrapper for Claude Intelligence
Implements the MCP protocol for proper integration with Claude
"""

import sys
import json
import asyncio
from typing import Dict, Any, Optional
from mcp_server import ClaudeIntelligence
from claude_session_memory import integrate_with_intelligence
from context_locking import integrate_locking_with_intelligence

# Integrate memory features
integrate_with_intelligence()
# Integrate locking features
integrate_locking_with_intelligence()


class MCPServer:
    """MCP Protocol Server for Claude Intelligence"""
    
    def __init__(self):
        self.server = None
        self.initialized = False
    
    async def initialize(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Initialize the server"""
        try:
            self.server = ClaudeIntelligence()
            self.initialized = True
            
            # Restore session on startup
            session_info = self.server.restore_session() if hasattr(self.server, 'restore_session') else ""
            
            return {
                "name": "claude-intelligence",
                "version": "0.3.0",
                "capabilities": {
                    "tools": [
                        {
                            "name": "understand_project",
                            "description": "Get project overview and tech stack",
                            "parameters": {}
                        },
                        {
                            "name": "find_files",
                            "description": "Search files by content/meaning",
                            "parameters": {
                                "query": {"type": "string", "required": True},
                                "k": {"type": "integer", "default": 10}
                            }
                        },
                        {
                            "name": "recent_changes",
                            "description": "Get changes since last session",
                            "parameters": {}
                        },
                        {
                            "name": "add_update",
                            "description": "Log a status update",
                            "parameters": {
                                "message": {"type": "string", "required": True},
                                "category": {"type": "string"}
                            }
                        },
                        {
                            "name": "add_todo",
                            "description": "Add a TODO item",
                            "parameters": {
                                "content": {"type": "string", "required": True},
                                "priority": {"type": "integer", "default": 0}
                            }
                        },
                        {
                            "name": "get_todos",
                            "description": "Get TODO items",
                            "parameters": {
                                "status": {"type": "string"}
                            }
                        },
                        {
                            "name": "restore_session",
                            "description": "Get session restoration info",
                            "parameters": {}
                        },
                        {
                            "name": "lock_context",
                            "description": "Lock immutable context snapshot",
                            "parameters": {
                                "content": {"type": "string", "required": True},
                                "label": {"type": "string", "required": True},
                                "version": {"type": "string"},
                                "persist": {"type": "boolean", "default": False}
                            }
                        },
                        {
                            "name": "recall_context",
                            "description": "Retrieve locked context",
                            "parameters": {
                                "label": {"type": "string", "required": True},
                                "version": {"type": "string", "default": "latest"}
                            }
                        },
                        {
                            "name": "list_locked_contexts",
                            "description": "List all locked contexts",
                            "parameters": {
                                "session_only": {"type": "boolean", "default": True}
                            }
                        },
                        {
                            "name": "unlock_context",
                            "description": "Remove locked context",
                            "parameters": {
                                "label": {"type": "string", "required": True},
                                "version": {"type": "string"},
                                "confirm": {"type": "boolean", "default": False}
                            }
                        }
                    ]
                },
                "session_restored": session_info
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Handle tool invocations"""
        if not self.initialized:
            return {"error": "Server not initialized"}
        
        try:
            # Map tool names to methods
            if tool_name == "understand_project":
                return await self.server.understand_project()
            
            elif tool_name == "find_files":
                query = params.get("query", "")
                k = params.get("k", 10)
                return await self.server.find_files(query, k)
            
            elif tool_name == "recent_changes":
                return await self.server.recent_changes()
            
            elif tool_name == "add_update":
                message = params.get("message", "")
                category = params.get("category")
                return self.server.add_update(message, category)
            
            elif tool_name == "add_todo":
                content = params.get("content", "")
                priority = params.get("priority", 0)
                return self.server.add_todo(content, priority=priority)
            
            elif tool_name == "get_todos":
                status = params.get("status")
                return self.server.get_todos(status)
            
            elif tool_name == "restore_session":
                return self.server.restore_session()
            
            elif tool_name == "lock_context":
                content = params.get("content", "")
                label = params.get("label", "")
                version = params.get("version")
                persist = params.get("persist", False)
                return await self.server.lock_context(content, label, version, persist)
            
            elif tool_name == "recall_context":
                label = params.get("label", "")
                version = params.get("version", "latest")
                return await self.server.recall_context(label, version)
            
            elif tool_name == "list_locked_contexts":
                session_only = params.get("session_only", True)
                return await self.server.list_locked_contexts(session_only)
            
            elif tool_name == "unlock_context":
                label = params.get("label", "")
                version = params.get("version")
                confirm = params.get("confirm", False)
                return await self.server.unlock_context(label, version, confirm)
            
            else:
                return {"error": f"Unknown tool: {tool_name}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON-RPC request"""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                result = await self.initialize(params)
            elif method == "tools/invoke":
                tool_name = params.get("name")
                tool_params = params.get("parameters", {})
                result = await self.handle_tool(tool_name, tool_params)
            else:
                result = {"error": f"Unknown method: {method}"}
            
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e)
                },
                "id": request_id
            }
    
    async def run(self):
        """Main server loop - read from stdin, write to stdout"""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        while True:
            try:
                # Read line from stdin
                line = await reader.readline()
                if not line:
                    break
                
                # Parse JSON-RPC request
                request = json.loads(line.decode())
                
                # Handle request
                response = await self.handle_request(request)
                
                # Send response
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32700,
                        "message": f"Parse error: {str(e)}"
                    }
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()


async def main():
    """Entry point"""
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    # Run the MCP server
    asyncio.run(main())