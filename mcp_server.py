#!/usr/bin/env python3
"""
ClaritaPM MCP Server
A Model Context Protocol server for project management and feature analysis.
"""

import json
import sys
import logging
from typing import Dict, Any, Optional
import asyncio
from llm_behavior_tree import LLMBehaviorTree

# Configure logging to stderr so it doesn't interfere with MCP communication
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

class MCPServer:
    def __init__(self):
        try:
            self.bt_manager = LLMBehaviorTree()
            self.sessions = {}
            logger.info("ClaritaPM MCP Server initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Server: {e}", exc_info=True)
            raise
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP requests"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        logger.info(f"Handling request: {method} (id: {request_id})")
        
        try:
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {
                                "listChanged": True
                            }
                        },
                        "serverInfo": {
                            "name": "clarita-pm",
                            "version": "1.0.0"
                        }
                    }
                }
                logger.info("Initialization successful")
                return response
            
            elif method == "notifications/initialized":
                # Acknowledge initialization
                logger.info("Received initialized notification")
                return None
            
            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "analyze_feature_request",
                                "description": "Analyze a feature request and generate development tickets or ask for clarification",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "description": {
                                            "type": "string",
                                            "description": "Natural language description of the feature request"
                                        },
                                        "workspace_path": {
                                            "type": "string",
                                            "description": "Path to the workspace to analyze",
                                            "default": "."
                                        },
                                        "session_id": {
                                            "type": "string",
                                            "description": "Session ID for continuing conversation"
                                        }
                                    },
                                    "required": ["description"]
                                }
                            }
                        ]
                    }
                }
            
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                if tool_name == "analyze_feature_request":
                    result = await self.analyze_feature_request(arguments)
                    
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": result["message"]
                                }
                            ]
                        }
                    }
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}"
                        }
                    }
            
            else:
                logger.warning(f"Unknown method received: {method}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown method: {method}"
                    }
                }
        
        except Exception as e:
            logger.error(f"Error handling request {method}: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                }
            }
    
    async def analyze_feature_request(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a feature request using the behavior tree"""
        description = arguments.get("description", "")
        workspace_path = arguments.get("workspace_path", ".")
        session_id = arguments.get("session_id")
        
        logger.info(f"Analyzing feature request: {description}")
        
        try:
            # Use behavior tree with LLM decision-making
            result = self.bt_manager.execute(description, workspace_path)
            
            if result.get("clarification_needed"):
                # Need more information
                questions = result.get("clarification_questions", [])
                response_text = "I need some clarification to create the Jira tickets:\n\n"
                for i, question in enumerate(questions, 1):
                    response_text += f"{i}. {question}\n"
                
                return {
                    "clarification_needed": True,
                    "questions": questions,
                    "message": response_text,
                    "session_id": session_id
                }
            else:
                # We have enough information, tickets were generated
                tickets = result.get("tickets", [])
                summary = result.get("summary", "")
                
                response_text = f"Perfect! I have enough information to create the Jira tickets.\n\n{summary}"
                
                if tickets:
                    response_text += "\n\nGenerated Tickets:\n"
                    for i, ticket in enumerate(tickets, 1):
                        response_text += f"\n{i}. **{ticket.get('title', 'Untitled')}**\n"
                        response_text += f"   Type: {ticket.get('type', 'Story')}\n"
                        response_text += f"   Description: {ticket.get('description', 'No description')}\n"
                
                return {
                    "clarification_needed": False,
                    "tickets": tickets,
                    "summary": summary,
                    "message": response_text,
                    "session_id": session_id
                }
        
        except Exception as e:
            logger.error(f"Error in analyze_feature_request: {e}", exc_info=True)
            return {
                "message": f"Error analyzing feature request: {str(e)}",
                "session_id": session_id
            }

async def main():
    """Main MCP server loop"""
    logger.info("Starting ClaritaPM MCP Server...")
    
    try:
        server = MCPServer()
        logger.info("MCP Server initialized, waiting for requests...")
        
    except Exception as e:
        logger.error(f"Failed to initialize server: {e}", exc_info=True)
        sys.exit(1)
    
    while True:
        try:
            # Read line from stdin
            line = sys.stdin.readline()
            if not line:
                logger.info("EOF received, shutting down")
                break
            
            line = line.strip()
            if not line:
                continue
            
            logger.debug(f"Received: {line}")
            
            # Parse JSON request
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                logger.error(f"Raw input: {repr(line)}")
                continue
            
            # Handle request
            response = await server.handle_request(request)
            
            # Send response to stdout (only if there is a response)
            if response is not None:
                response_json = json.dumps(response)
                print(response_json, flush=True)
                logger.debug(f"Sent response: {response_json}")
        
        except KeyboardInterrupt:
            logger.info("Server shutting down due to interrupt")
            break
        except EOFError:
            logger.info("EOF encountered, shutting down")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1) 