# ClaritaPM MCP Server

A conversational project management MCP (Model Context Protocol) server that uses LLM-powered behavior trees to generate Jira tickets through natural language conversations.

## Overview

ClaritaPM is designed to work with Cursor and other MCP-compatible environments. It combines the intelligence of local LLMs with structured behavior trees to provide a sophisticated conversational interface. You can describe feature requests in natural language, and the server will use LLM decision-making to ask clarifying questions and generate comprehensive Jira tickets.

## How It Works

1. **User Request**: "Let's add a button to this page"
2. **Server Analysis**: Parses the request and identifies missing information
3. **Clarification Questions**: Asks specific questions to gather more details
4. **Conversation**: Continues until enough information is collected
5. **Ticket Generation**: Creates detailed Jira tickets with effort estimates

## Features

- **LLM-Powered Decision Making**: Uses local LLMs for intelligent parsing and analysis
- **Behavior Tree Architecture**: Structured workflow with py_trees for reliable execution
- **Conversational Interface**: Natural language feature requests with context awareness
- **Session Management**: Maintains conversation state across multiple interactions
- **Smart Codebase Analysis**: LLM-driven identification of relevant files
- **Intelligent Ticket Generation**: Creates comprehensive Jira tickets with effort estimates
- **MCP Protocol**: Compatible with Cursor and other MCP clients

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd ClaritaPM
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your local LLM (optional):
```bash
# Set environment variables for your LLM
export LLM_API_BASE="http://127.0.0.1:1234/v1"  # LM Studio default
export LLM_MODEL="devstral-small-2505"          # Your model name
export LLM_API_KEY="lm-studio"                  # Dummy key for local LLMs

# Or use OpenAI (requires API key)
export USE_OPENAI="true"
export OPENAI_API_KEY="your-openai-api-key"
```

4. Start the server:
```bash
python main.py
```

The server will start on `http://localhost:8000`

## Usage

### Direct API Usage

```bash
# Initial request
curl -X POST http://localhost:8000/analyze-feature \
  -H "Content-Type: application/json" \
  -d '{"description": "Let\'s add a button to this page"}'

# Continue conversation with session ID
curl -X POST http://localhost:8000/analyze-feature \
  -H "Content-Type: application/json" \
  -d '{"description": "It should be a save button on the dashboard page", "session_id": "your-session-id"}'
```

### MCP Protocol (Cursor Integration)

1. Configure Cursor to use the MCP server by adding to your MCP configuration:

```json
{
  "mcpServers": {
    "clarita-pm": {
      "command": "python",
      "args": ["main.py"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

2. In Cursor, you can now use the `analyze_feature_request` tool to start conversations about feature requests.

## API Endpoints

### POST /analyze-feature
Analyze a feature request and either ask for clarification or generate tickets.

**Request Body:**
```json
{
  "description": "string",
  "workspace_path": "string (optional)",
  "session_id": "string (optional)"
}
```

**Response:**
```json
{
  "session_id": "string",
  "clarification_needed": "boolean",
  "questions": ["string"],
  "message": "string",
  "tickets": [{"title": "string", "description": "string", ...}],
  "summary": "string",
  "current_info": {"target_page": "string", "feature_type": "string", ...}
}
```

### GET /sessions/{session_id}
Get information about a conversation session.

### POST /mcp
MCP protocol endpoint for tool discovery and execution.

## Testing

Run the test script to see the conversational workflow in action:

```bash
python test_conversation.py
```

This will demonstrate:
- Initial incomplete request
- Clarification questions
- Progressive information gathering
- Final ticket generation

## Architecture

The server uses LLM-powered behavior trees for sophisticated decision-making:

### Behavior Tree Structure
```
LLMProjectManagerRoot (Selector)
├── LLMAnalysis (Sequence)
│   ├── ParseFeatureRequestNode (LLM parsing)
│   ├── ValidateRequestNode (LLM validation)
│   └── GenerateClarificationQuestionsNode (LLM question generation)
└── CompleteAnalysis (Sequence)
    ├── AnalyzeCodebaseNode (LLM codebase analysis)
    ├── GenerateTicketsNode (LLM ticket generation)
    └── CreateSummaryNode (LLM summary creation)
```

### LLM Decision Nodes
1. **ParseFeatureRequestNode**: Uses LLM to extract structured information
2. **ValidateRequestNode**: LLM determines if enough information is available
3. **GenerateClarificationQuestionsNode**: LLM creates specific, helpful questions
4. **AnalyzeCodebaseNode**: LLM identifies relevant files and structure
5. **GenerateTicketsNode**: LLM creates comprehensive Jira tickets
6. **CreateSummaryNode**: LLM generates project summaries and recommendations

### Key Benefits
- **Intelligent Parsing**: LLM understands context and nuance
- **Adaptive Questions**: Dynamic question generation based on missing information
- **Smart Analysis**: LLM-driven codebase understanding
- **Comprehensive Output**: Detailed tickets with effort estimates and dependencies

## Example Conversation

```
User: "Let's add a button to this page"
Server: "I need some clarification to create the Jira tickets:
1. Which page should this feature be added to? (e.g., dashboard, login, profile, settings)
2. What type of feature should be added? (e.g., button, form, field, link, component)"

User: "It should be a save button on the dashboard page"
Server: "I need some clarification to create the Jira tickets:
1. What should happen when this feature is used? (e.g., refresh, save, submit, navigate)"

User: "When clicked, it should save the form data"
Server: "Perfect! I have enough information to create the Jira tickets.
[Generated tickets with effort estimates and file modifications]"
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License 