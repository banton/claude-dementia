
import logging

logger = logging.getLogger(__name__)

def clean_schema(schema):
    """
    Recursively clean JSON schema to be more compatible with Custom Connector.
    
    Changes:
    1. Remove 'title' fields (reduce noise)
    2. Simplify 'anyOf' for optional fields to 'type': ['string', 'null']
    3. Remove 'default': null
    """
    if isinstance(schema, dict):
        # Remove title
        if 'title' in schema:
            del schema['title']
            
        # Simplify anyOf for Optional[T]
        if 'anyOf' in schema:
            options = schema['anyOf']
            if len(options) == 2:
                # Check for Optional pattern: [{'type': 'T'}, {'type': 'null'}]
                types = [opt.get('type') for opt in options]
                if 'null' in types and len(types) == 2:
                    other_type = next(t for t in types if t != 'null')
                    if other_type:
                        # Replace anyOf with type: [T, 'null']
                        del schema['anyOf']
                        schema['type'] = [other_type, 'null']
        
        # Remove default: null
        if 'default' in schema and schema['default'] is None:
            del schema['default']

        # Recurse
        for key, value in schema.items():
            clean_schema(value)
            
    elif isinstance(schema, list):
        for item in schema:
            clean_schema(item)

def patch_mcp_tools(mcp_instance):
    """
    Patch all tools in the FastMCP instance to have cleaner schemas.
    """
    if not hasattr(mcp_instance, '_tool_manager'):
        logger.warning("MCP instance has no _tool_manager, skipping patch")
        return
        
    tool_manager = mcp_instance._tool_manager
    if not hasattr(tool_manager, '_tools'):
        logger.warning("ToolManager has no _tools, skipping patch")
        return
        
    tools = tool_manager._tools
    count = 0
    
    for name, tool in tools.items():
        # FastMCP tools have inputSchema, not parameters
        if hasattr(tool, 'inputSchema'):
            try:
                clean_schema(tool.inputSchema)
                count += 1
            except Exception as e:
                logger.error(f"Failed to clean schema for tool {name}: {e}")
        elif hasattr(tool, 'parameters'):
            try:
                clean_schema(tool.parameters)
                count += 1
            except Exception as e:
                logger.error(f"Failed to clean schema for tool {name}: {e}")

    logger.info(f"Patched schemas for {count} tools")
