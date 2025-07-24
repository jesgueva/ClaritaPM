from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import os

from pathlib import Path
import logging
from datetime import datetime
import uuid
from llm_behavior_tree import LLMBehaviorTree

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("=== Starting ClaritaPM MCP Server ===")

app = FastAPI(title="ClaritaPM MCP Server", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS middleware configured")

# Pydantic models
class FeatureRequest(BaseModel):
    description: str
    workspace_path: Optional[str] = None
    session_id: Optional[str] = None

class MCPRequest(BaseModel):
    method: str
    params: Dict[str, Any]

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

# Session management
class ConversationSession:
    def __init__(self, session_id: str):
        logger.info(f"Creating new session: {session_id}")
        self.session_id = session_id
        self.created_at = datetime.now()
        self.feature_info = {}
        self.clarification_questions = []
        self.workspace_path = "."
        self.conversation_history = []
        logger.debug(f"Session {session_id} initialized with workspace_path: {self.workspace_path}")
    
    def add_message(self, role: str, content: str):
        logger.debug(f"Adding message to session {self.session_id}: role={role}, content_length={len(content)}")
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"Session {self.session_id} now has {len(self.conversation_history)} messages")
    
    def is_complete(self) -> bool:
        """Check if we have enough information to generate tickets"""
        required_fields = ["target_page", "feature_type"]
        is_complete = all(field in self.feature_info and self.feature_info[field] for field in required_fields)
        logger.debug(f"Session {self.session_id} completeness check: {is_complete}")
        logger.debug(f"Current feature_info: {self.feature_info}")
        return is_complete

# Global session storage
sessions: Dict[str, ConversationSession] = {}

# Global behavior tree manager
logger.info("Initializing LLM Behavior Tree manager")
bt_manager = LLMBehaviorTree()
logger.info("LLM Behavior Tree manager initialized successfully")

def get_or_create_session(session_id: str) -> ConversationSession:
    """Get existing session or create new one"""
    logger.debug(f"Getting or creating session: {session_id}")
    if session_id not in sessions:
        logger.info(f"Creating new session: {session_id}")
        sessions[session_id] = ConversationSession(session_id)
    else:
        logger.debug(f"Using existing session: {session_id}")
    logger.debug(f"Total active sessions: {len(sessions)}")
    return sessions[session_id]

@app.post("/analyze-feature")
async def analyze_feature(request: FeatureRequest):
    """Analyze a feature request and generate tickets or ask for clarification."""
    logger.info("=== Starting feature analysis ===")
    logger.info(f"Request description: '{request.description}'")
    logger.info(f"Workspace path: {request.workspace_path}")
    logger.info(f"Session ID: {request.session_id}")
    
    try:
        # Get or create session
        session_id = request.session_id or str(uuid.uuid4())
        logger.info(f"Using session ID: {session_id}")
        session = get_or_create_session(session_id)
        
        # Update workspace path if provided
        if request.workspace_path:
            logger.info(f"Updating workspace path from '{session.workspace_path}' to '{request.workspace_path}'")
            session.workspace_path = request.workspace_path
        
        # Add user message to conversation history
        session.add_message("user", request.description)
        
        # Use behavior tree with LLM decision-making
        logger.info("Executing behavior tree with LLM decision-making")
        result = bt_manager.execute(request.description, session.workspace_path)
        logger.info(f"Behavior tree result: {result}")
        
        # Update session with parsed data
        if result.get("parsed_data"):
            logger.info(f"Updating session with parsed data: {result['parsed_data']}")
            session.feature_info.update(result["parsed_data"])
        
        if result.get("clarification_needed"):
            # Need more information
            logger.info("Clarification needed, generating questions")
            questions = result.get("clarification_questions", [])
            response_text = "I need some clarification to create the Jira tickets:\n\n"
            for i, question in enumerate(questions, 1):
                response_text += f"{i}. {question}\n"
            
            session.add_message("assistant", response_text)
            
            logger.info(f"Returning clarification response with {len(questions)} questions")
            return {
                "session_id": session_id,
                "clarification_needed": True,
                "questions": questions,
                "message": response_text,
                "current_info": session.feature_info
            }
        else:
            # We have enough information, tickets were generated
            logger.info("Sufficient information gathered, generating tickets")
            tickets = result.get("tickets", [])
            summary = result.get("summary", "")
            
            response_text = f"Perfect! I have enough information to create the Jira tickets.\n\n{summary}"
            session.add_message("assistant", response_text)
            
            logger.info(f"Generated {len(tickets)} tickets")
            logger.info("=== Feature analysis completed successfully ===")
            
            return {
                "session_id": session_id,
                "clarification_needed": False,
                "tickets": tickets,
                "summary": summary,
                "message": response_text,
                "current_info": session.feature_info
            }
    
    except Exception as e:
        logger.error(f"Error analyzing feature: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mcp")
async def mcp_endpoint(request: MCPRequest):
    """MCP protocol endpoint."""
    logger.info("=== MCP endpoint called ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"Params: {request.params}")
    
    try:
        if request.method == "tools/list":
            logger.info("Handling tools/list request")
            return MCPResponse(
                id=request.params.get("id"),
                result={
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
                                        "description": "Path to the workspace to analyze"
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
            )
        elif request.method == "tools/call":
            tool_name = request.params.get("name")
            arguments = request.params.get("arguments", {})
            
            logger.info(f"Handling tools/call request for tool: {tool_name}")
            logger.info(f"Arguments: {arguments}")
            
            if tool_name == "analyze_feature_request":
                feature_request = FeatureRequest(**arguments)
                result = await analyze_feature(feature_request)
                
                logger.info("Feature analysis completed via MCP")
                return MCPResponse(
                    id=request.params.get("id"),
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": result["message"]
                            }
                        ]
                    }
                )
            else:
                logger.warning(f"Unknown tool requested: {tool_name}")
                return MCPResponse(
                    id=request.params.get("id"),
                    error={
                        "code": -32601,
                        "message": f"Method {tool_name} not found"
                    }
                )
        else:
            logger.warning(f"Unknown MCP method: {request.method}")
            return MCPResponse(
                id=request.params.get("id"),
                error={
                    "code": -32601,
                    "message": f"Method {request.method} not found"
                }
            )
    except Exception as e:
        logger.error(f"Error in MCP endpoint: {e}", exc_info=True)
        return MCPResponse(
            id=request.params.get("id"),
            error={
                "code": -32603,
                "message": "Internal error",
                "data": str(e)
            }
        )

@app.get("/")
async def root():
    """Root endpoint with server information."""
    logger.debug("Root endpoint accessed")
    return {
        "name": "ClaritaPM MCP Server",
        "version": "1.0.0",
        "description": "Conversational project management MCP server",
        "endpoints": {
            "/analyze-feature": "POST - Analyze feature requests",
            "/mcp": "POST - MCP protocol endpoint"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check endpoint accessed")
    return {"status": "healthy", "service": "ClaritaPM MCP Server"}

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session information."""
    logger.info(f"Getting session information for: {session_id}")
    
    if session_id in sessions:
        session = sessions[session_id]
        logger.debug(f"Session {session_id} found, returning data")
        return {
            "session_id": session_id,
            "created_at": session.created_at.isoformat(),
            "feature_info": session.feature_info,
            "is_complete": session.is_complete(),
            "conversation_history": session.conversation_history
        }
    else:
        logger.warning(f"Session {session_id} not found")
        raise HTTPException(status_code=404, detail="Session not found")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting uvicorn server on host=0.0.0.0, port=8000")
    uvicorn.run(app, host="0.0.0.0", port=8000) 