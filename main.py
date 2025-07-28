#!/usr/bin/env python3
"""
ClaritaPM MCP Server
A Model Context Protocol server for project management and feature analysis.
All functionality is available only through the MCP interface.

IMPORTANT: This MCP server should NOT perform direct file system access.
Instead, it should instruct the master system (IDE) to perform file operations
and report back the results. The master system has proper access to the workspace
and can provide relevant file information through MCP tools.
"""

import json
import sys
import logging
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime
import uuid
from llm_behavior_tree import LLMBehaviorTree

# Configure logging to stderr so it doesn't interfere with MCP communication
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# Suppress all HTTP and library logging
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)
logging.getLogger("langchain").setLevel(logging.ERROR)
logging.getLogger("langchain_core").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

# Session management
class ConversationSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.feature_info = {}
        self.clarification_questions = []
        self.workspace_path = "."
        self.conversation_history = []
        self.waiting_for_user_input = False
        self.current_prompt = None
        self.behavior_tree_state = None
    
    def add_message(self, role: str, content: str):
        # logger.debug(f"Adding message to session {self.session_id}: role={role}, content_length={len(content)}")
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # logger.debug(f"Session {self.session_id} now has {len(self.conversation_history)} messages")
    
    def is_complete(self) -> bool:
        """Check if we have enough information to generate tickets"""
        required_fields = ["target_page", "feature_type"]
        is_complete = all(field in self.feature_info and self.feature_info[field] for field in required_fields)
        # logger.debug(f"Session {self.session_id} completeness check: {is_complete}")
        # logger.debug(f"Current feature_info: {self.feature_info}")
        return is_complete
    
    def set_waiting_for_input(self, prompt_message: str, behavior_tree_state: dict = None):
        """Set the session to waiting for user input"""
        self.waiting_for_user_input = True
        self.current_prompt = prompt_message
        self.behavior_tree_state = behavior_tree_state
    
    def clear_waiting_state(self):
        """Clear the waiting for input state"""
        self.waiting_for_user_input = False
        self.current_prompt = None
        self.behavior_tree_state = None

class MCPServer:
    def __init__(self):
        try:
            self.bt_manager = LLMBehaviorTree()
            self.sessions = {}
        except Exception as e:
            logger.error(f"Failed to initialize MCP Server: {e}", exc_info=True)
            raise
    
    def get_or_create_session(self, session_id: str) -> ConversationSession:
        """Get existing session or create new one"""
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationSession(session_id)
        return self.sessions[session_id]
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP requests"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
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
                return response
            
            elif method == "notifications/initialized":
                # Acknowledge initialization
                return None
            
            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "analyze_feature_request",
                                "description": "Explore and analyze feature implementation requirements. Use this when you want to investigate how to implement a feature, understand what's needed, or plan development work. The system will analyze the codebase, identify requirements, and generate comprehensive Jira tickets or ask clarifying questions to gather more information.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "description": {
                                            "type": "string",
                                            "description": "Natural language description of the feature you want to explore or implement (e.g., 'Add a save button to the dashboard', 'Create a user profile form', 'Implement real-time notifications')"
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
                            },
                            {
                                "name": "explore_feature_requirements",
                                "description": "Deep dive into feature requirements and technical analysis. Use this to understand what files need to be modified, what new components are needed, and what technical challenges might arise when implementing a feature.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "description": {
                                            "type": "string",
                                            "description": "Detailed description of the feature to explore requirements for"
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
                            },
                            {
                                "name": "plan_feature_implementation",
                                "description": "Create a detailed implementation plan for a feature. This will break down the work into specific tasks, estimate effort, and identify dependencies. Perfect for sprint planning or when you need to understand the scope of work.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "description": {
                                            "type": "string",
                                            "description": "Feature description for implementation planning"
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
                            },
                            {
                                "name": "clarita_pm_health_check",
                                "description": "Perform a simple health check of ClaritaPM system - only checks behavior tree and LLM availability",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {}
                                }
                            },
                            {
                                "name": "get_session_info",
                                "description": "Get information about a conversation session",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "session_id": {
                                            "type": "string",
                                            "description": "Session ID to retrieve information for"
                                        }
                                    },
                                    "required": ["session_id"]
                                }
                            },
                            {
                                "name": "continue_conversation",
                                "description": "Continue a conversation with user response. Use this when the system is waiting for user input and you have received a response.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "session_id": {
                                            "type": "string",
                                            "description": "Session ID for the conversation"
                                        },
                                        "user_response": {
                                            "type": "string",
                                            "description": "User's response to the previous prompt"
                                        }
                                    },
                                    "required": ["session_id", "user_response"]
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
                elif tool_name == "explore_feature_requirements":
                    result = await self.explore_feature_requirements(arguments)
                    
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
                elif tool_name == "plan_feature_implementation":
                    result = await self.plan_feature_implementation(arguments)
                    
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
                elif tool_name == "clarita_pm_health_check":
                    result = await self.clarita_pm_health_check({})
                    
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
                elif tool_name == "get_session_info":
                    result = await self.get_session_info(arguments)
                    
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
                elif tool_name == "continue_conversation":
                    result = await self.continue_conversation(arguments)
                    
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
        
        try:
            # Use behavior tree with LLM decision-making
            result = self.bt_manager.execute(description, workspace_path)
            
            # Check if we're waiting for user input
            if result.get("waiting_for_user_input"):
                # Store the session state and prompt
                session = self.get_or_create_session(session_id)
                session.set_waiting_for_input(result.get("prompt_message", ""), result)
                
                return {
                    "waiting_for_user_input": True,
                    "prompt_message": result.get("prompt_message", ""),
                    "clarification_needed": result.get("clarification_needed", False),
                    "parsed_data": result.get("parsed_data", {}),
                    "message": result.get("prompt_message", ""),
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "waiting_for_user_input")
                }
            
            elif result.get("clarification_needed"):
                # Need more information from user
                questions = result.get("clarification_questions", [])
                codebase_search_queries = result.get("codebase_search_queries", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = "I need some clarification to create comprehensive Jira tickets:\n\n"
                response_text += "**Questions for you:**\n"
                for i, question in enumerate(questions, 1):
                    response_text += f"{i}. {question}\n"
                
                if codebase_search_queries:
                    response_text += f"\n**Codebase searches to perform:**\n"
                    for i, query in enumerate(codebase_search_queries, 1):
                        response_text += f"{i}. {query}\n"
                
                if parsed_data:
                    response_text += f"\n**What I understand so far:**\n"
                    response_text += f"- Target page: {parsed_data.get('target_page', 'Not specified')}\n"
                    response_text += f"- Feature type: {parsed_data.get('feature_type', 'Not specified')}\n"
                    response_text += f"- Action: {parsed_data.get('action', 'Not specified')}\n"
                
                return {
                    "clarification_needed": True,
                    "questions": questions,
                    "codebase_search_queries": codebase_search_queries,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "need_more_info")
                }
            else:
                # We have enough information, tickets were generated
                tickets = result.get("tickets", [])
                parsed_data = result.get("parsed_data", {})
                
                logger.info(f"Generated {len(tickets)} tickets for feature request")
                for i, ticket in enumerate(tickets, 1):
                    logger.info(f"Ticket {i}: {ticket.get('title', 'Untitled')} ({ticket.get('type', 'unknown')})")
                
                response_text = f"✅ Perfect! I have enough information to create comprehensive Jira tickets.\n\n"
                
                if tickets:
                    response_text += f"🎫 **Generated Jira Tickets ({len(tickets)} total):**\n\n"
                    
                    # Group tickets by type
                    parent_stories = [t for t in tickets if t.get('type') == 'parent_story']
                    subtasks = [t for t in tickets if t.get('type') == 'subtask']
                    
                    for i, story in enumerate(parent_stories, 1):
                        response_text += f"**Parent Story {i}:**\n"
                        response_text += f"- Title: {story.get('title', 'Untitled')}\n"
                        response_text += f"- Description: {story.get('description', 'No description')}\n"
                        response_text += f"- System Impact: {story.get('system_impact', 'Not specified')}\n"
                        response_text += f"- Estimate: {story.get('estimate', 'Not specified')}\n"
                        response_text += f"- Priority: {story.get('priority', 'Not specified')}\n\n"
                    
                    if subtasks:
                        response_text += f"**Subtasks:**\n"
                        for i, subtask in enumerate(subtasks, 1):
                            response_text += f"{i}. **{subtask.get('title', 'Untitled')}**\n"
                            response_text += f"   - Parent: {subtask.get('parent', 'No parent')}\n"
                            response_text += f"   - Description: {subtask.get('description', 'No description')}\n"
                            response_text += f"   - Estimate: {subtask.get('estimate', 'Not specified')}\n"
                            response_text += f"   - Priority: {subtask.get('priority', 'Not specified')}\n"
                            
                            if subtask.get('acceptance_criteria'):
                                response_text += f"   - Acceptance Criteria:\n"
                                for criterion in subtask['acceptance_criteria']:
                                    response_text += f"     • {criterion}\n"
                            response_text += "\n"
                
                return {
                    "clarification_needed": False,
                    "tickets": tickets,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "tickets_generated")
                }
        
        except Exception as e:
            logger.error(f"Error in analyze_feature_request: {e}", exc_info=True)
            return {
                "message": f"❌ Error analyzing feature request: {str(e)}",
                "session_id": session_id,
                "execution_path": "error"
            }

    async def explore_feature_requirements(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Deep dive into feature requirements and technical analysis"""
        description = arguments.get("description", "")
        workspace_path = arguments.get("workspace_path", ".")
        session_id = arguments.get("session_id")
        
        try:
            # Use simplified behavior tree for requirements analysis
            result = self.bt_manager.execute(description, workspace_path)
            
            if result.get("clarification_needed"):
                # Need more information from user
                questions = result.get("clarification_questions", [])
                codebase_search_queries = result.get("codebase_search_queries", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = "🔍 **Feature Requirements Analysis**\n\n"
                response_text += "I need some clarification to provide a comprehensive requirements analysis:\n\n"
                response_text += "**Questions for you:**\n"
                for i, question in enumerate(questions, 1):
                    response_text += f"{i}. {question}\n"
                
                if codebase_search_queries:
                    response_text += f"\n**Codebase searches to perform:**\n"
                    for i, query in enumerate(codebase_search_queries, 1):
                        response_text += f"{i}. {query}\n"
                
                if parsed_data:
                    response_text += f"\n**What I understand so far:**\n"
                    response_text += f"- Target page: {parsed_data.get('target_page', 'Not specified')}\n"
                    response_text += f"- Feature type: {parsed_data.get('feature_type', 'Not specified')}\n"
                    response_text += f"- Action: {parsed_data.get('action', 'Not specified')}\n"
                
                return {
                    "clarification_needed": True,
                    "questions": questions,
                    "codebase_search_queries": codebase_search_queries,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "need_more_info")
                }
            else:
                # We have enough information, provide detailed requirements analysis
                tickets = result.get("tickets", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = f"🔍 **Feature Requirements Analysis Complete**\n\n"
                
                if tickets:
                    response_text += f"**📋 Requirements Breakdown:**\n"
                    for i, ticket in enumerate(tickets, 1):
                        if ticket.get('type') == 'parent_story':
                            response_text += f"{i}. {ticket.get('title', 'Main feature implementation')}\n"
                        elif ticket.get('type') == 'subtask':
                            response_text += f"{i}. {ticket.get('title', 'Subtask')}\n"
                    response_text += "\n"
                
                if parsed_data:
                    response_text += f"**🔧 Technical Analysis:**\n"
                    response_text += f"- Target page: {parsed_data.get('target_page', 'Not specified')}\n"
                    response_text += f"- Feature type: {parsed_data.get('feature_type', 'Not specified')}\n"
                    response_text += f"- Action: {parsed_data.get('action', 'Not specified')}\n"
                    response_text += "\n"
                
                response_text += f"**⚡ Implementation Overview:**\n"
                response_text += f"- Total tickets: {len(tickets)}\n"
                response_text += f"- Estimated effort: Medium complexity\n"
                response_text += f"- Recommended approach: Incremental implementation\n"
                response_text += "\n"
                
                return {
                    "clarification_needed": False,
                    "tickets": tickets,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "requirements_analysis")
                }
        
        except Exception as e:
            logger.error(f"Error in explore_feature_requirements: {e}", exc_info=True)
            return {
                "message": f"❌ Error exploring feature requirements: {str(e)}",
                "session_id": session_id,
                "execution_path": "error"
            }

    async def plan_feature_implementation(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detailed implementation plan for a feature"""
        description = arguments.get("description", "")
        workspace_path = arguments.get("workspace_path", ".")
        session_id = arguments.get("session_id")
        
        try:
            # Use simplified behavior tree for implementation planning
            result = self.bt_manager.execute(description, workspace_path)
            
            if result.get("clarification_needed"):
                # Need more information from user
                questions = result.get("clarification_questions", [])
                codebase_search_queries = result.get("codebase_search_queries", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = "📋 **Implementation Planning**\n\n"
                response_text += "I need some clarification to create a detailed implementation plan:\n\n"
                response_text += "**Questions for you:**\n"
                for i, question in enumerate(questions, 1):
                    response_text += f"{i}. {question}\n"
                
                if codebase_search_queries:
                    response_text += f"\n**Codebase searches to perform:**\n"
                    for i, query in enumerate(codebase_search_queries, 1):
                        response_text += f"{i}. {query}\n"
                
                if parsed_data:
                    response_text += f"\n**What I understand so far:**\n"
                    response_text += f"- Target page: {parsed_data.get('target_page', 'Not specified')}\n"
                    response_text += f"- Feature type: {parsed_data.get('feature_type', 'Not specified')}\n"
                    response_text += f"- Action: {parsed_data.get('action', 'Not specified')}\n"
                
                return {
                    "clarification_needed": True,
                    "questions": questions,
                    "codebase_search_queries": codebase_search_queries,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "need_more_info")
                }
            else:
                # We have enough information, provide detailed implementation plan
                tickets = result.get("tickets", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = f"📋 **Implementation Plan Complete**\n\n"
                
                if tickets:
                    response_text += f"**🎯 Project Overview:**\n"
                    response_text += f"Implement {parsed_data.get('feature_type', 'feature')} on {parsed_data.get('target_page', 'page')} page\n\n"
                    
                    response_text += f"**📝 Implementation Tasks:**\n"
                    for i, ticket in enumerate(tickets, 1):
                        response_text += f"{i}. **{ticket.get('title', 'Untitled')}**\n"
                        response_text += f"   - Description: {ticket.get('description', 'No description')}\n"
                        response_text += f"   - Estimate: {ticket.get('estimate', 'Not specified')}\n"
                        response_text += f"   - Priority: {ticket.get('priority', 'Not specified')}\n"
                        if ticket.get('dependencies'):
                            response_text += f"   - Dependencies: {', '.join(ticket['dependencies'])}\n"
                        response_text += "\n"
                
                response_text += f"**⏱️ Timeline Estimate:**\n"
                response_text += f"- Total effort: {len(tickets)} story points\n"
                response_text += f"- Recommended sprint: {'Current Sprint' if len(tickets) <= 3 else 'Next Sprint'}\n"
                response_text += f"- Critical path: Frontend → Backend → Testing\n\n"
                
                response_text += f"**🔗 Key Dependencies:**\n"
                response_text += f"1. Project setup and environment\n"
                response_text += f"2. Design system components\n"
                response_text += f"3. API integration\n"
                response_text += "\n"
                
                return {
                    "clarification_needed": False,
                    "tickets": tickets,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "implementation_planning")
                }
        
        except Exception as e:
            logger.error(f"Error in plan_feature_implementation: {e}", exc_info=True)
            return {
                "message": f"❌ Error planning feature implementation: {str(e)}",
                "session_id": session_id,
                "execution_path": "error"
            }

    async def clarita_pm_health_check(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a simple health check of ClaritaPM system - only checks behavior tree and LLM availability"""
        
        health_status = {
            "overall_status": "healthy",
            "timestamp": None,
            "components": {},
            "errors": []
        }
        
        try:
            import datetime
            health_status["timestamp"] = datetime.datetime.now().isoformat()
            
            # Check 1: Simplified Behavior Tree Manager
            try:
                if hasattr(self, 'bt_manager') and self.bt_manager is not None:
                    # Test if simplified behavior tree can be created
                    test_tree = self.bt_manager.create_tree("Test feature request", ".")
                    if test_tree:
                        health_status["components"]["behavior_tree"] = {
                            "status": "healthy",
                            "details": "Simplified behavior tree manager is working correctly"
                        }
                    else:
                        health_status["components"]["behavior_tree"] = {
                            "status": "error",
                            "details": "Simplified behavior tree manager failed to create tree"
                        }
                        health_status["errors"].append("Simplified behavior tree creation failed")
                else:
                    health_status["components"]["behavior_tree"] = {
                        "status": "error",
                        "details": "Simplified behavior tree manager is not initialized"
                    }
                    health_status["errors"].append("Simplified Behavior Tree manager not initialized")
            except Exception as e:
                health_status["components"]["behavior_tree"] = {
                    "status": "error",
                    "details": f"Error checking simplified behavior tree: {str(e)}"
                }
                health_status["errors"].append(f"Simplified Behavior Tree error: {str(e)}")
            
            # Check 2: LLM Availability
            try:
                from llm_parser import parse_with_llm
                
                # Test LLM with a simple request
                test_result = parse_with_llm("Add a button to the dashboard")
                
                if test_result and isinstance(test_result, dict):
                    health_status["components"]["llm"] = {
                        "status": "healthy",
                        "details": "LLM is available and responding correctly"
                    }
                else:
                    health_status["components"]["llm"] = {
                        "status": "error",
                        "details": "LLM returned invalid response"
                    }
                    health_status["errors"].append("LLM returned invalid response")
            except Exception as e:
                health_status["components"]["llm"] = {
                    "status": "error",
                    "details": f"LLM is not available: {str(e)}"
                }
                health_status["errors"].append(f"LLM is not available: {str(e)}")
            
            # Determine overall status
            if health_status["errors"]:
                health_status["overall_status"] = "unhealthy"
            else:
                health_status["overall_status"] = "healthy"
            
            # Generate response message
            status_emoji = {
                "healthy": "✅",
                "unhealthy": "❌"
            }
            
            response_text = f"{status_emoji[health_status['overall_status']]} **ClaritaPM Health Check**\n\n"
            response_text += f"**Overall Status:** {health_status['overall_status'].upper()}\n"
            response_text += f"**Timestamp:** {health_status['timestamp']}\n\n"
            
            response_text += "**Component Status:**\n"
            for component, info in health_status["components"].items():
                component_emoji = {
                    "healthy": "✅",
                    "error": "❌"
                }
                response_text += f"{component_emoji[info['status']]} **{component.replace('_', ' ').title()}:** {info['details']}\n"
            
            if health_status["errors"]:
                response_text += "\n**Errors:**\n"
                for error in health_status["errors"]:
                    response_text += f"❌ {error}\n"
            
            if health_status["overall_status"] == "healthy":
                response_text += "\n🎉 Simplified behavior tree and LLM are working correctly!"
            else:
                response_text += "\n❌ System has critical errors that need attention."
            
            return {
                "message": response_text,
                "health_status": health_status
            }
            
        except Exception as e:
            logger.error(f"Error in health check: {e}", exc_info=True)
            return {
                "message": f"❌ Error performing health check: {str(e)}",
                "health_status": {
                    "overall_status": "error",
                    "timestamp": None,
                    "components": {},
                    "errors": [f"Health check failed: {str(e)}"]
                }
            }

    async def get_session_info(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get information about a conversation session"""
        session_id = arguments.get("session_id")
        
        if not session_id:
            return {
                "message": "❌ Session ID is required"
            }
        
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            response_text = f"📋 **Session Information**\n\n"
            response_text += f"**Session ID:** {session_id}\n"
            response_text += f"**Created:** {session.created_at.isoformat()}\n"
            response_text += f"**Is Complete:** {'✅ Yes' if session.is_complete() else '❌ No'}\n"
            response_text += f"**Messages:** {len(session.conversation_history)}\n"
            response_text += f"**Waiting for Input:** {'✅ Yes' if session.waiting_for_user_input else '❌ No'}\n\n"
            
            if session.feature_info:
                response_text += "**Feature Information:**\n"
                for key, value in session.feature_info.items():
                    response_text += f"- {key}: {value}\n"
                response_text += "\n"
            
            if session.conversation_history:
                response_text += "**Conversation History:**\n"
                for i, msg in enumerate(session.conversation_history[-5:], 1):  # Show last 5 messages
                    response_text += f"{i}. [{msg['role']}] {msg['content'][:100]}...\n"
            
            return {
                "message": response_text,
                "session_id": session_id,
                "created_at": session.created_at.isoformat(),
                "feature_info": session.feature_info,
                "is_complete": session.is_complete(),
                "conversation_history": session.conversation_history,
                "waiting_for_user_input": session.waiting_for_user_input
            }
        else:
            return {
                "message": f"❌ Session {session_id} not found"
            }

    async def continue_conversation(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Continue a conversation with user response"""
        session_id = arguments.get("session_id")
        user_response = arguments.get("user_response", "")
        
        if not session_id:
            return {
                "message": "❌ Session ID is required"
            }
        
        if not user_response:
            return {
                "message": "❌ User response is required"
            }
        
        if session_id not in self.sessions:
            return {
                "message": f"❌ Session {session_id} not found"
            }
        
        session = self.sessions[session_id]
        
        if not session.waiting_for_user_input:
            return {
                "message": "❌ Session is not waiting for user input"
            }
        
        try:
            # Add user response to conversation history
            session.add_message("user", user_response)
            
            # Get the stored behavior tree state
            behavior_tree_state = session.behavior_tree_state
            if not behavior_tree_state:
                return {
                    "message": "❌ No behavior tree state found for this session"
                }
            
            # Continue the behavior tree execution with user response
            feature_request = behavior_tree_state.get('feature_request', '')
            workspace_path = behavior_tree_state.get('workspace_path', '.')
            
            # Execute behavior tree with user response
            result = self.bt_manager.execute(feature_request, workspace_path, user_response)
            
            # Clear the waiting state
            session.clear_waiting_state()
            
            # Check if we're still waiting for more input
            if result.get("waiting_for_user_input"):
                session.set_waiting_for_input(result.get("prompt_message", ""), result)
                
                return {
                    "waiting_for_user_input": True,
                    "prompt_message": result.get("prompt_message", ""),
                    "clarification_needed": result.get("clarification_needed", False),
                    "parsed_data": result.get("parsed_data", {}),
                    "message": result.get("prompt_message", ""),
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "waiting_for_user_input")
                }
            
            elif result.get("clarification_needed"):
                # Still need more information
                questions = result.get("clarification_questions", [])
                codebase_search_queries = result.get("codebase_search_queries", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = "I still need some clarification:\n\n"
                response_text += "**Questions for you:**\n"
                for i, question in enumerate(questions, 1):
                    response_text += f"{i}. {question}\n"
                
                if codebase_search_queries:
                    response_text += f"\n**Codebase searches to perform:**\n"
                    for i, query in enumerate(codebase_search_queries, 1):
                        response_text += f"{i}. {query}\n"
                
                return {
                    "clarification_needed": True,
                    "questions": questions,
                    "codebase_search_queries": codebase_search_queries,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "need_more_info")
                }
            else:
                # Successfully completed
                tickets = result.get("tickets", [])
                parsed_data = result.get("parsed_data", {})
                
                response_text = f"✅ Thank you for the clarification! I've successfully generated comprehensive Jira tickets.\n\n"
                
                if tickets:
                    response_text += f"🎫 **Generated Jira Tickets ({len(tickets)} total):**\n\n"
                    
                    # Group tickets by type
                    parent_stories = [t for t in tickets if t.get('type') == 'parent_story']
                    subtasks = [t for t in tickets if t.get('type') == 'subtask']
                    
                    for i, story in enumerate(parent_stories, 1):
                        response_text += f"**Parent Story {i}:**\n"
                        response_text += f"- Title: {story.get('title', 'Untitled')}\n"
                        response_text += f"- Description: {story.get('description', 'No description')}\n"
                        response_text += f"- System Impact: {story.get('system_impact', 'Not specified')}\n"
                        response_text += f"- Estimate: {story.get('estimate', 'Not specified')}\n"
                        response_text += f"- Priority: {story.get('priority', 'Not specified')}\n\n"
                    
                    if subtasks:
                        response_text += f"**Subtasks:**\n"
                        for i, subtask in enumerate(subtasks, 1):
                            response_text += f"{i}. **{subtask.get('title', 'Untitled')}**\n"
                            response_text += f"   - Parent: {subtask.get('parent', 'No parent')}\n"
                            response_text += f"   - Description: {subtask.get('description', 'No description')}\n"
                            response_text += f"   - Estimate: {subtask.get('estimate', 'Not specified')}\n"
                            response_text += f"   - Priority: {subtask.get('priority', 'Not specified')}\n"
                            
                            if subtask.get('acceptance_criteria'):
                                response_text += f"   - Acceptance Criteria:\n"
                                for criterion in subtask['acceptance_criteria']:
                                    response_text += f"     • {criterion}\n"
                            response_text += "\n"
                
                return {
                    "clarification_needed": False,
                    "tickets": tickets,
                    "parsed_data": parsed_data,
                    "message": response_text,
                    "session_id": session_id,
                    "execution_path": result.get("execution_path", "tickets_generated")
                }
        
        except Exception as e:
            logger.error(f"Error in continue_conversation: {e}", exc_info=True)
            return {
                "message": f"❌ Error continuing conversation: {str(e)}",
                "session_id": session_id,
                "execution_path": "error"
            }

async def main():
    """Main MCP server loop"""
    try:
        server = MCPServer()
        
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
            
            # logger.debug(f"Received: {line}")
            
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
                # logger.debug(f"Sent response: {response_json}")
        
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