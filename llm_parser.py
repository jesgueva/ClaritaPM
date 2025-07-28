import os
import json
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

# LangChain imports
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langchain_community.llms import Ollama
from langchain_core.runnables import RunnablePassthrough

# Get logger (logging configured centrally in main.py)
logger = logging.getLogger(__name__)

# Configuration for LLM endpoint
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
LLM_MODEL = os.getenv("LLM_MODEL", "devstral-small-2505")

# Fallback to OpenAI if local LLM is not available
USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")



# Pydantic model for structured output
class FeatureRequest(BaseModel):
    target_page: Optional[str] = Field(
        description="Which page the feature should be added to",
        default=None
    )
    feature_type: Optional[str] = Field(
        description="What type of feature (button, form, field, link, component, etc.)",
        default=None
    )
    action: Optional[str] = Field(
        description="What should happen when the feature is used (save, refresh, submit, navigate, etc.)",
        default=None
    )

# Pydantic model for validation responses
class ValidationResponse(BaseModel):
    can_proceed_autonomously: bool = Field(
        description="Whether we have enough information to proceed autonomously"
    )
    missing_info: Optional[list] = Field(
        description="List of missing information items",
        default=None
    )
    suggestions: Optional[list] = Field(
        description="List of suggested questions to ask the user",
        default=None
    )

# System prompt for feature extraction
SYSTEM_PROMPT = """You are a helpful assistant that extracts structured information from feature requests and exploration queries.

Given a user request, identify and extract the following information:
- target_page: Which page the feature should be added to
- feature_type: What type of feature (button, form, field, link, component, etc.)
- action: What should happen when the feature is used (save, refresh, submit, navigate, etc.)

If information is missing, use null.

Examples:
Input: "Add a save button to the dashboard page"
Output: {{"target_page": "dashboard", "feature_type": "button", "action": "save"}}

Input: "Create a contact form on the about page"
Output: {{"target_page": "about", "feature_type": "form", "action": "submit"}}

Input: "Let's add a button to this page"
Output: {{"target_page": null, "feature_type": "button", "action": null}}

Input: "Explore how to implement real-time notifications"
Output: {{"target_page": null, "feature_type": "notifications", "action": "real-time"}}

Input: "How can we add user authentication to the app?"
Output: {{"target_page": null, "feature_type": "authentication", "action": "login"}}

Input: "I want to investigate adding a search feature"
Output: {{"target_page": null, "feature_type": "search", "action": "query"}}"""

# System prompt for validation
VALIDATION_PROMPT = """You are a helpful assistant that validates feature requests to determine if there's enough information to create comprehensive Jira tickets.

Given a feature request and parsed information, determine if we can proceed autonomously or need clarification.

Return a JSON object with:
- can_proceed_autonomously: true/false
- missing_info: list of missing information (if any)
- suggestions: list of questions to ask the user (if any)

Examples:
Input: "Add a save button to the dashboard" with parsed data showing target_page: "dashboard", feature_type: "button", action: "save"
Output: {{"can_proceed_autonomously": true, "missing_info": null, "suggestions": null}}

Input: "Add a button" with parsed data showing target_page: null, feature_type: "button", action: null
Output: {{"can_proceed_autonomously": false, "missing_info": ["target_page", "action"], "suggestions": ["Which page should the button be added to?", "What should the button do when clicked?"]}}

Input: "Implement real-time collaboration" with parsed data showing target_page: null, feature_type: "collaboration", action: "real-time"
Output: {{"can_proceed_autonomously": false, "missing_info": ["target_page", "specific_features"], "suggestions": ["Which page or component should have collaboration?", "What specific collaboration features are needed (chat, document editing, etc.)?"]}}"""

def parse_with_llm(description: str) -> Dict[str, Any]:
    """Parse feature request using LangChain LLM"""
    if USE_OPENAI and OPENAI_API_KEY:
        return _parse_with_langchain_openai(description)
    else:
        return _parse_with_langchain_local(description)

def parse_validation_with_llm(description: str) -> Dict[str, Any]:
    """Parse validation request using LangChain LLM"""
    if USE_OPENAI and OPENAI_API_KEY:
        return _parse_validation_with_langchain_openai(description)
    else:
        return _parse_validation_with_langchain_local(description)

def parse_text_with_llm(description: str) -> str:
    """Parse text request using LangChain LLM (returns plain text, not JSON)"""
    if USE_OPENAI and OPENAI_API_KEY:
        return _parse_text_with_langchain_openai(description)
    else:
        return _parse_text_with_langchain_local(description)

def _parse_with_langchain_local(description: str) -> Dict[str, Any]:
    """Parse using LangChain with local LLM (LM Studio, Ollama, etc.)"""
    try:
        # Create ChatOpenAI with only the necessary parameters to avoid proxy issues
        llm = ChatOpenAI(
            model=LLM_MODEL,
            openai_api_base=LLM_API_BASE,
            openai_api_key=LLM_API_KEY,
            temperature=0.1,
            max_tokens=200,
            # Explicitly set to None to avoid proxy issues
            http_client=None,
            http_async_client=None
        )
        
        return _create_langchain_chain(llm, description, "ChatOpenAI")
        
    except Exception as e:
        logger.error(f"Failed to initialize ChatOpenAI: {e}", exc_info=True)
        raise Exception("LM Studio is not available")

def _parse_with_langchain_openai(description: str) -> Dict[str, Any]:
    """Parse using LangChain with OpenAI API"""
    try:
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            openai_api_key=OPENAI_API_KEY,
            temperature=0.1,
            max_tokens=200,
            # Explicitly set to None to avoid proxy issues
            http_client=None,
            http_async_client=None
        )
        
        return _create_langchain_chain(llm, description, "OpenAI")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI: {e}", exc_info=True)
        raise Exception("OpenAI initialization failed")

def _parse_validation_with_langchain_local(description: str) -> Dict[str, Any]:
    """Parse validation using LangChain with local LLM (LM Studio, Ollama, etc.)"""
    logger.info("Attempting to initialize local LLM with ChatOpenAI for validation")
    logger.info(f"Connecting to local LLM: base={LLM_API_BASE}, model={LLM_MODEL}, key={'set' if LLM_API_KEY else 'not set'}")
    
    try:
        # Create LangChain model
        logger.debug(f"Creating ChatOpenAI with model: {LLM_MODEL}")
        logger.debug(f"API Base: {LLM_API_BASE}")
        logger.debug(f"API Key: {LLM_API_KEY[:8]}..." if LLM_API_KEY else "None")
        
        # Create ChatOpenAI with only the necessary parameters to avoid proxy issues
        llm = ChatOpenAI(
            model=LLM_MODEL,
            openai_api_base=LLM_API_BASE,
            openai_api_key=LLM_API_KEY,
            temperature=0.1,
            max_tokens=200,
            # Explicitly set to None to avoid proxy issues
            http_client=None,
            http_async_client=None
        )
        
        logger.info("ChatOpenAI initialized successfully for validation")
        return _create_validation_langchain_chain(llm, description, "ChatOpenAI")
        
    except Exception as e:
        logger.error(f"Failed to initialize ChatOpenAI for validation: {e}", exc_info=True)
        raise Exception("LM Studio is not available for validation")

def _parse_validation_with_langchain_openai(description: str) -> Dict[str, Any]:
    """Parse validation using LangChain with OpenAI API"""
    logger.info("Attempting to initialize OpenAI for validation")
    
    try:
        logger.debug(f"Creating OpenAI ChatOpenAI with API key: {OPENAI_API_KEY[:8]}...")
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            openai_api_key=OPENAI_API_KEY,
            temperature=0.1,
            max_tokens=200,
            # Explicitly set to None to avoid proxy issues
            http_client=None,
            http_async_client=None
        )
        
        logger.info("OpenAI initialized successfully for validation")
        return _create_validation_langchain_chain(llm, description, "OpenAI")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI for validation: {e}", exc_info=True)
        raise Exception("OpenAI initialization failed for validation")

def _create_langchain_chain(llm, description: str, llm_type: str) -> Dict[str, Any]:
    """Create and run LangChain chain for feature parsing"""
    try:
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user", "{input}")
        ])
        
        # Create output parser
        parser = JsonOutputParser(pydantic_object=FeatureRequest)
        
        # Create chain
        chain = prompt | llm | parser
        
        # Run the chain
        result = chain.invoke({"input": description})
        
        # Validate and format result
        parsed_result = {
            "target_page": result.get("target_page"),
            "feature_type": result.get("feature_type"),
            "action": result.get("action"),
            "original_request": description
        }
        
        return parsed_result
        
    except Exception as e:
        logger.error(f"Chain execution failed: {e}", exc_info=True)
        raise Exception(f"LangChain parsing failed: {e}")

def _parse_text_with_langchain_local(description: str) -> str:
    """Parse text using LangChain with local LLM (LM Studio, Ollama, etc.)"""
    logger.info("Attempting to initialize local LLM with ChatOpenAI for text parsing")
    logger.info(f"Connecting to local LLM: base={LLM_API_BASE}, model={LLM_MODEL}, key={'set' if LLM_API_KEY else 'not set'}")
    
    try:
        # Create LangChain model
        logger.debug(f"Creating ChatOpenAI with model: {LLM_MODEL}")
        logger.debug(f"API Base: {LLM_API_BASE}")
        logger.debug(f"API Key: {LLM_API_KEY[:8]}..." if LLM_API_KEY else "None")
        
        # Create ChatOpenAI with only the necessary parameters to avoid parameter conflicts
        llm = ChatOpenAI(
            model=LLM_MODEL,
            openai_api_base=LLM_API_BASE,
            openai_api_key=LLM_API_KEY,
            max_tokens=1000,
            temperature=0.1
        )
        logger.info("ChatOpenAI initialized successfully for text parsing")
        
        # Create simple text chain (no JSON parsing)
        logger.info("Creating text LangChain chain with ChatOpenAI")
        logger.debug("Creating ChatPromptTemplate for text")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that generates comprehensive text responses. Provide detailed, well-structured responses."),
            ("user", "{input}")
        ])
        logger.debug("ChatPromptTemplate for text created successfully")
        
        # Create simple chain without JSON parser
        logger.debug("Creating text chain: prompt | llm")
        chain = prompt | llm
        logger.debug("Text chain created successfully")
        
        # Invoke the chain
        logger.info(f"Invoking text chain with input: '{description[:100]}...'")
        result = chain.invoke({"input": description})
        logger.info("Text chain execution successful")
        
        # Return the text content
        text_content = result.content if hasattr(result, 'content') else str(result)
        logger.info(f"Text parsing completed successfully with ChatOpenAI")
        return text_content
        
    except Exception as e:
        logger.error(f"Failed to initialize ChatOpenAI: {e}")
        logger.error(f"LLM type: {llm_type}")
        logger.error(f"Input description: {description}")
        raise Exception(f"LangChain text parsing failed: {e}")

def _parse_text_with_langchain_openai(description: str) -> str:
    """Parse text using LangChain with OpenAI"""
    logger.info("Attempting to initialize OpenAI for text parsing")
    
    try:
        # Create OpenAI model
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            openai_api_key=OPENAI_API_KEY,
            max_tokens=1000,
            temperature=0.1
        )
        logger.info("OpenAI initialized successfully for text parsing")
        
        # Create simple text chain (no JSON parsing)
        logger.info("Creating text LangChain chain with OpenAI")
        logger.debug("Creating ChatPromptTemplate for text")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that generates comprehensive text responses. Provide detailed, well-structured responses."),
            ("user", "{input}")
        ])
        logger.debug("ChatPromptTemplate for text created successfully")
        
        # Create simple chain without JSON parser
        logger.debug("Creating text chain: prompt | llm")
        chain = prompt | llm
        logger.debug("Text chain created successfully")
        
        # Invoke the chain
        logger.info(f"Invoking text chain with input: '{description[:100]}...'")
        result = chain.invoke({"input": description})
        logger.info("Text chain execution successful")
        
        # Return the text content
        text_content = result.content if hasattr(result, 'content') else str(result)
        logger.info(f"Text parsing completed successfully with OpenAI")
        return text_content
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI: {e}")
        raise Exception(f"OpenAI text parsing failed: {e}")

def _create_validation_langchain_chain(llm, description: str, llm_type: str) -> Dict[str, Any]:
    """Create and run LangChain chain for validation parsing"""
    logger.info(f"Creating validation LangChain chain with {llm_type}")
    
    try:
        # Create prompt template
        logger.debug("Creating ChatPromptTemplate for validation")
        prompt = ChatPromptTemplate.from_messages([
            ("system", VALIDATION_PROMPT),
            ("user", "{input}")
        ])
        logger.debug("ChatPromptTemplate for validation created successfully")
        
        # Create output parser
        logger.debug("Creating JsonOutputParser with ValidationResponse model")
        parser = JsonOutputParser(pydantic_object=ValidationResponse)
        logger.debug("JsonOutputParser for validation created successfully")
        
        # Create chain
        logger.debug("Creating validation chain: prompt | llm | parser")
        chain = prompt | llm | parser
        logger.debug("Validation chain created successfully")
        
        # Run the chain
        logger.info(f"Invoking validation chain with input: '{description}'")
        result = chain.invoke({"input": description})
        logger.info(f"Validation chain execution successful. Raw result: {result}")
        
        # Validate and format result
        validation_result = {
            "can_proceed_autonomously": result.get("can_proceed_autonomously", False),
            "missing_info": result.get("missing_info"),
            "suggestions": result.get("suggestions"),
            "original_request": description
        }
        
        logger.info(f"Validation result: {validation_result}")
        logger.info(f"=== LLM validation parsing completed successfully with {llm_type} ===")
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Validation chain execution failed: {e}", exc_info=True)
        logger.error(f"LLM type: {llm_type}")
        logger.error(f"Input description: {description}")
        raise Exception(f"LangChain validation parsing failed: {e}")

def _fallback_parsing(description: str) -> Dict[str, Any]:
    """Simple fallback parsing using regex patterns"""
    logger.info("=== Starting fallback regex parsing ===")
    logger.info(f"Input description: '{description}'")
    
    import re
    
    description_lower = description.lower()
    logger.debug(f"Lowercase description: '{description_lower}'")
    
    # Extract target page
    logger.debug("Extracting target page...")
    page_patterns = [
        r"to\s+the\s+(\w+)\s+page",
        r"on\s+the\s+(\w+)\s+page", 
        r"in\s+the\s+(\w+)\s+page",
        r"(\w+)\s+page"
    ]
    
    target_page = None
    for i, pattern in enumerate(page_patterns):
        match = re.search(pattern, description_lower)
        if match:
            target_page = match.group(1)
            logger.debug(f"Found target_page '{target_page}' with pattern {i}: {pattern}")
            break
    
    # Direct page name matching
    if not target_page:
        logger.debug("No target page found with patterns, trying direct matching...")
        common_pages = ["dashboard", "login", "profile", "settings", "admin", "about", "home"]
        for page in common_pages:
            if page in description_lower:
                target_page = page
                logger.debug(f"Found target_page '{target_page}' with direct matching")
                break
    
    # Extract feature type
    logger.debug("Extracting feature type...")
    feature_patterns = [
        r"add\s+(\w+)\s+button",
        r"create\s+(\w+)\s+component",
        r"implement\s+(\w+)",
        r"new\s+(\w+)",
        r"(\w+)\s+button",
        r"(\w+)\s+form",
        r"(\w+)\s+field"
    ]
    
    feature_type = None
    for i, pattern in enumerate(feature_patterns):
        match = re.search(pattern, description_lower)
        if match:
            feature_type = match.group(1)
            if feature_type.lower() in ["a", "the", "this", "that", "some", "any"]:
                feature_type = None
                logger.debug(f"Feature type '{feature_type}' filtered out as common word")
            else:
                logger.debug(f"Found feature_type '{feature_type}' with pattern {i}: {pattern}")
                break
    
    # Direct feature type matching
    if not feature_type:
        logger.debug("No feature type found with patterns, trying direct matching...")
        common_features = ["button", "form", "field", "link", "component"]
        for feature in common_features:
            if feature in description_lower:
                feature_type = feature
                logger.debug(f"Found feature_type '{feature_type}' with direct matching")
                break
    
    # Extract action
    logger.debug("Extracting action...")
    action_patterns = [
        r"(\w+)\s+when\s+clicked",
        r"(\w+)\s+the\s+page",
        r"(\w+)\s+data",
        r"should\s+(\w+)",
        r"will\s+(\w+)"
    ]
    
    action = None
    for i, pattern in enumerate(action_patterns):
        match = re.search(pattern, description_lower)
        if match:
            action = match.group(1)
            if action.lower() in ["a", "the", "this", "that", "some", "any", "be", "do", "have"]:
                action = None
                logger.debug(f"Action '{action}' filtered out as common word")
            else:
                logger.debug(f"Found action '{action}' with pattern {i}: {pattern}")
                break
    
    result = {
        "target_page": target_page,
        "feature_type": feature_type,
        "action": action,
        "original_request": description
    }
    
    logger.info(f"Fallback parsing result: {result}")
    logger.info("=== Fallback regex parsing completed ===")
    
    return result 