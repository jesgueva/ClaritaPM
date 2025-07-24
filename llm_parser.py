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

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration for LLM endpoint
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://127.0.0.1:1234/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
LLM_MODEL = os.getenv("LLM_MODEL", "devstral-small-2505")

# Fallback to OpenAI if local LLM is not available
USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Log configuration on startup
logger.info("=== LLM Parser Configuration ===")
logger.info(f"LLM_API_BASE: {LLM_API_BASE}")
logger.info(f"LLM_API_KEY: {LLM_API_KEY[:8]}..." if LLM_API_KEY else "None")
logger.info(f"LLM_MODEL: {LLM_MODEL}")
logger.info(f"USE_OPENAI: {USE_OPENAI}")
logger.info(f"OPENAI_API_KEY: {OPENAI_API_KEY[:8]}..." if OPENAI_API_KEY else "None")
logger.info("================================")

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

# System prompt for feature extraction
SYSTEM_PROMPT = """You are a helpful assistant that extracts structured information from feature requests.

Given a user request, identify and extract the following information:
- target_page: Which page the feature should be added to
- feature_type: What type of feature (button, form, field, link, component, etc.)
- action: What should happen when the feature is used (save, refresh, submit, navigate, etc.)

If information is missing, use null.

Examples:
Input: "Add a save button to the dashboard page"
Output: {"target_page": "dashboard", "feature_type": "button", "action": "save"}

Input: "Create a contact form on the about page"
Output: {"target_page": "about", "feature_type": "form", "action": "submit"}

Input: "Let's add a button to this page"
Output: {"target_page": null, "feature_type": "button", "action": null}"""

def parse_with_llm(description: str) -> Dict[str, Any]:
    """Parse feature request using LangChain LLM"""
    logger.info(f"=== Starting LLM parsing for: '{description}' ===")
    
    try:
        if USE_OPENAI and OPENAI_API_KEY:
            logger.info("Using OpenAI for parsing")
            return _parse_with_langchain_openai(description)
        else:
            logger.info("Using local LLM for parsing")
            return _parse_with_langchain_local(description)
    except Exception as e:
        logger.error(f"LangChain LLM parsing failed: {e}", exc_info=True)
        logger.info("Falling back to simple regex parsing")
        return _fallback_parsing(description)

def _parse_with_langchain_local(description: str) -> Dict[str, Any]:
    """Parse using LangChain with local LLM (LM Studio, Ollama, etc.)"""
    logger.info("Attempting to initialize local LLM with ChatOpenAI")
    
    try:
        # Create LangChain model
        logger.debug(f"Creating ChatOpenAI with model: {LLM_MODEL}")
        logger.debug(f"API Base: {LLM_API_BASE}")
        logger.debug(f"API Key: {LLM_API_KEY[:8]}..." if LLM_API_KEY else "None")
        
        llm = ChatOpenAI(
            model=LLM_MODEL,
            openai_api_base=LLM_API_BASE,
            openai_api_key=LLM_API_KEY,
            temperature=0.1,
            max_tokens=200
        )
        
        logger.info("ChatOpenAI initialized successfully")
        return _create_langchain_chain(llm, description, "ChatOpenAI")
        
    except Exception as e:
        logger.error(f"Failed to initialize ChatOpenAI: {e}", exc_info=True)
        # Try Ollama as fallback
        logger.info("Attempting to initialize Ollama as fallback")
        try:
            logger.debug(f"Creating Ollama with model: {LLM_MODEL}")
            llm = Ollama(
                model=LLM_MODEL,
                temperature=0.1
            )
            logger.info("Ollama initialized successfully")
            return _create_langchain_chain(llm, description, "Ollama")
        except Exception as ollama_error:
            logger.error(f"Failed to initialize Ollama: {ollama_error}", exc_info=True)
            raise Exception("No local LLM available")

def _parse_with_langchain_openai(description: str) -> Dict[str, Any]:
    """Parse using LangChain with OpenAI API"""
    logger.info("Attempting to initialize OpenAI")
    
    try:
        logger.debug(f"Creating OpenAI ChatOpenAI with API key: {OPENAI_API_KEY[:8]}...")
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            openai_api_key=OPENAI_API_KEY,
            temperature=0.1,
            max_tokens=200
        )
        
        logger.info("OpenAI initialized successfully")
        return _create_langchain_chain(llm, description, "OpenAI")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI: {e}", exc_info=True)
        raise Exception("OpenAI initialization failed")

def _create_langchain_chain(llm, description: str, llm_type: str) -> Dict[str, Any]:
    """Create and run LangChain chain for feature parsing"""
    logger.info(f"Creating LangChain chain with {llm_type}")
    
    try:
        # Create prompt template
        logger.debug("Creating ChatPromptTemplate")
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user", "{input}")
        ])
        logger.debug("ChatPromptTemplate created successfully")
        
        # Create output parser
        logger.debug("Creating JsonOutputParser with FeatureRequest model")
        parser = JsonOutputParser(pydantic_object=FeatureRequest)
        logger.debug("JsonOutputParser created successfully")
        
        # Create chain
        logger.debug("Creating chain: prompt | llm | parser")
        chain = prompt | llm | parser
        logger.debug("Chain created successfully")
        
        # Run the chain
        logger.info(f"Invoking chain with input: '{description}'")
        result = chain.invoke({"input": description})
        logger.info(f"Chain execution successful. Raw result: {result}")
        
        # Validate and format result
        parsed_result = {
            "target_page": result.get("target_page"),
            "feature_type": result.get("feature_type"),
            "action": result.get("action"),
            "original_request": description
        }
        
        logger.info(f"Parsed result: {parsed_result}")
        logger.info(f"=== LLM parsing completed successfully with {llm_type} ===")
        
        return parsed_result
        
    except Exception as e:
        logger.error(f"Chain execution failed: {e}", exc_info=True)
        logger.error(f"LLM type: {llm_type}")
        logger.error(f"Input description: {description}")
        raise Exception(f"LangChain parsing failed: {e}")

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