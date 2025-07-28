import py_trees
from py_trees.behaviour import Behaviour
from py_trees.composites import Selector, Sequence
from py_trees.common import Status
import logging
from typing import Dict, Any, List
from llm_parser import parse_with_llm

# Get logger (logging configured centrally in main.py)
logger = logging.getLogger(__name__)



class LLMDecisionNode(Behaviour):
    """Base class for LLM-powered decision nodes"""
    
    def __init__(self, name: str, llm_prompt: str):
        super().__init__(name=name)
        self.llm_prompt = llm_prompt
        self.context = {}
        # logger.debug(f"Created LLMDecisionNode: {name}")
    
    def setup(self, **kwargs):
        """Setup with context data"""
        self.context = kwargs.get('context', {})
    
    def initialise(self):
        pass
    
    def _ask_llm(self, question: str) -> Dict[str, Any]:
        """Ask the LLM a question and get structured response"""
        try:
            # Combine the base prompt with the specific question
            full_prompt = f"{self.llm_prompt}\n\nQuestion: {question}\n\nContext: {self.context}"
            
            # Use the LLM parser to get structured response
            response = parse_with_llm(full_prompt)
            return response
        except Exception as e:
            logger.error(f"LLM decision failed in {self.name}: {e}", exc_info=True)
            return {}

class ParseFeatureRequestNode(LLMDecisionNode):
    """Parse feature request using LLM"""
    
    def __init__(self):
        super().__init__(
            name="ParseFeatureRequest",
            llm_prompt="Extract structured information from feature requests. Identify target_page, feature_type, and action."
        )
        self.parsed_data = {}
    
    def update(self):
        try:
            feature_request = self.context.get('feature_request', '')
            
            if not feature_request:
                logger.warning("No feature request found in context")
                return Status.FAILURE
            
            # Use LLM to parse the feature request
            self.parsed_data = parse_with_llm(feature_request)
            
            # Store the parsed data in context for other nodes
            self.context['parsed_data'] = self.parsed_data
            
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in ParseFeatureRequest: {e}", exc_info=True)
            return Status.FAILURE

class CheckIfEnoughInfoNode(LLMDecisionNode):
    """Check if we have enough information to generate Jira tickets"""
    
    def __init__(self):
        super().__init__(
            name="CheckIfEnoughInfo",
            llm_prompt="Determine if we have enough information to generate comprehensive Jira tickets."
        )
        self.has_enough_info = False
        self.missing_info = []
    
    def update(self):
        try:
            parsed_data = self.context.get('parsed_data', {})
            feature_request = self.context.get('feature_request', '')
            
            if not parsed_data:
                logger.warning("No parsed data found in context")
                return Status.FAILURE
            
            # Ask LLM to check if we have enough information
            check_question = f"""
            Analyze this feature request: "{feature_request}"
            
            Parsed information:
            - Target page: {parsed_data.get('target_page', 'Not specified')}
            - Feature type: {parsed_data.get('feature_type', 'Not specified')}
            - Action: {parsed_data.get('action', 'Not specified')}
            
            Determine if we have enough information to generate comprehensive Jira tickets.
            
            Consider:
            1. Is the target page clearly identified?
            2. Is the feature type specific enough?
            3. Is the action/behavior well-defined?
            4. Can we infer technical requirements from the context?
            
            Return 'has_enough_info: true' if we have enough info, false otherwise.
            If false, provide 'missing_info' list.
            """
            
            from llm_parser import parse_validation_with_llm
            llm_response = parse_validation_with_llm(check_question)
            
            # Check if LLM thinks we have enough info
            self.has_enough_info = llm_response.get('can_proceed_autonomously', False)
            
            if self.has_enough_info:
                self.context['has_enough_info'] = True
                self.context['missing_info'] = []
                return Status.SUCCESS
            else:
                # Extract missing information
                self.missing_info = llm_response.get('missing_info', [])
                self.context['has_enough_info'] = False
                self.context['missing_info'] = self.missing_info
                return Status.FAILURE
                
        except Exception as e:
            logger.error(f"Error in CheckIfEnoughInfo: {e}", exc_info=True)
            return Status.FAILURE

class GetMoreInfoNode(LLMDecisionNode):
    """Get more information by asking user or searching codebase"""
    
    def __init__(self):
        super().__init__(
            name="GetMoreInfo",
            llm_prompt="Generate questions to ask user or search codebase for missing information."
        )
        self.questions = []
        self.codebase_search_queries = []
    
    def update(self):
        try:
            missing_info = self.context.get('missing_info', [])
            feature_request = self.context.get('feature_request', '')
            parsed_data = self.context.get('parsed_data', {})
            
            if not missing_info:
                return Status.SUCCESS
            
            # Ask LLM to generate questions and search queries
            info_prompt = f"""
            For this feature request: "{feature_request}"
            
            Missing information: {missing_info}
            Current parsed data: {parsed_data}
            
            Generate:
            1. 2-3 specific questions to ask the user
            2. 2-3 codebase search queries to find relevant information
            
            Make questions conversational and search queries specific.
            """
            
            llm_response = self._ask_llm(info_prompt)
            
            # Extract questions and search queries
            self.questions = llm_response.get('questions', [
                "Which page should this feature be added to?",
                "What type of feature should be added?",
                "What should happen when this feature is used?"
            ])
            
            self.codebase_search_queries = llm_response.get('search_queries', [
                f"search for {parsed_data.get('target_page', 'dashboard')} components",
                f"search for {parsed_data.get('feature_type', 'button')} implementations"
            ])
            
            self.context['clarification_questions'] = self.questions
            self.context['codebase_search_queries'] = self.codebase_search_queries
            
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in GetMoreInfo: {e}", exc_info=True)
            return Status.FAILURE

class GenerateTicketsNode(LLMDecisionNode):
    """Generate Jira tickets using LLM"""
    
    def __init__(self):
        super().__init__(
            name="GenerateTickets",
            llm_prompt="Generate comprehensive Jira tickets with effort estimates and detailed descriptions."
        )
        self.tickets = []
    
    def update(self):
        try:
            parsed_data = self.context.get('parsed_data', {})
            feature_request = self.context.get('feature_request', '')
            
            if not parsed_data:
                logger.warning("No parsed data found")
                return Status.FAILURE
            
            # Ask LLM to generate comprehensive Jira tickets
            ticket_prompt = f"""
            Generate comprehensive Jira tickets for this feature request.
            
            Feature Request: "{feature_request}"
            
            Parsed Information:
            - Target page: {parsed_data.get('target_page')}
            - Feature type: {parsed_data.get('feature_type')}
            - Action: {parsed_data.get('action')}
            
            Generate a comprehensive set of Jira tickets following this structure:
            
            1. **Parent Story** - High-level feature story with:
               - Story description (As a... I want... so that...)
               - System impact
               - Technical changes overview
               - Dependencies
               - Estimate (Story points)
            
            2. **Subtasks** - Detailed implementation tasks:
               - Backend/API tasks
               - Frontend component tasks
               - Styling tasks
               - Testing tasks
               - Documentation tasks
            
            Each ticket should include:
            - Clear title and description
            - Technical changes needed
            - Files to modify/create
            - Dependencies
            - Acceptance criteria
            - Effort estimate (story points)
            - Priority level
            
            Structure the response with a parent story and 2-4 subtasks that cover all aspects of the implementation.
            """
            
            from llm_parser import parse_text_with_llm
            try:
                llm_response_text = parse_text_with_llm(ticket_prompt)
                # For now, use fallback since we need structured tickets
                self.tickets = self._generate_fallback_tickets(parsed_data)
            except Exception as e:
                logger.warning(f"LLM ticket generation failed: {e}, using fallback")
                self.tickets = self._generate_fallback_tickets(parsed_data)
            
            # Log the generated tickets
            logger.info(f"Generated {len(self.tickets)} tickets for feature request: {feature_request}")
            for i, ticket in enumerate(self.tickets, 1):
                logger.info(f"Ticket {i}: {ticket.get('title', 'Untitled')} - {ticket.get('type', 'unknown')}")
                logger.info(f"  Description: {ticket.get('description', 'No description')}")
                logger.info(f"  Estimate: {ticket.get('estimate', 'Not specified')}")
                logger.info(f"  Priority: {ticket.get('priority', 'Not specified')}")
                if ticket.get('acceptance_criteria'):
                    logger.info(f"  Acceptance Criteria: {len(ticket['acceptance_criteria'])} items")
                logger.info("---")
            
            self.context['tickets'] = self.tickets
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in GenerateTickets: {e}", exc_info=True)
            return Status.FAILURE
    
    def _generate_fallback_tickets(self, parsed_data: Dict) -> List[Dict]:
        """Fallback ticket generation if LLM fails"""
        logger.info("Generating fallback tickets")
        tickets = []
        target_page = parsed_data.get('target_page', '')
        feature_type = parsed_data.get('feature_type', '')
        action = parsed_data.get('action', '')
        
        logger.info(f"Creating tickets for: {feature_type} on {target_page} page with action: {action}")
        
        # Parent Story
        parent_story = {
            'type': 'parent_story',
            'title': f'Implement {feature_type.title()} on {target_page.title()} Page',
            'description': f'As a user, I want to {action} {feature_type} on the {target_page} page so that I can interact with the system effectively.',
            'system_impact': f'{target_page.title()} page, {feature_type} functionality',
            'technical_changes': f'Add {feature_type} component to {target_page} page',
            'dependencies': [],
            'estimate': 'Medium (5 story points)',
            'priority': 'Medium'
        }
        tickets.append(parent_story)
        logger.info(f"Created parent story: {parent_story['title']}")
        
        # Frontend subtask
        frontend_subtask = {
            'type': 'subtask',
            'parent': parent_story['title'],
            'title': f'Create {feature_type.title()} Component for {target_page.title()}',
            'description': f'Implement the {feature_type} component on the {target_page} page with proper styling and functionality.',
            'technical_changes': [
                f'Create new {feature_type} component',
                f'Integrate component into {target_page} page',
                f'Add event handlers for {action} functionality'
            ],
            'files_to_modify': [f'src/components/{target_page.title()}.js'],
            'dependencies': [],
            'acceptance_criteria': [
                f'{feature_type.title()} component renders correctly',
                f'Component responds to user interactions',
                f'Proper error handling implemented'
            ],
            'estimate': 'Small (3 story points)',
            'priority': 'Medium'
        }
        tickets.append(frontend_subtask)
        logger.info(f"Created frontend subtask: {frontend_subtask['title']}")
        
        # Backend subtask (if action involves data persistence)
        if action in ['save', 'submit', 'update', 'delete', 'create']:
            backend_subtask = {
                'type': 'subtask',
                'title': f'Implement {action.title()} API Endpoint',
                'description': f'Create backend API endpoint to handle {action} operations for {feature_type}.',
                'technical_changes': [
                    f'Create {action} API endpoint',
                    f'Add data validation',
                    f'Implement error handling'
                ],
                'files_to_modify': [f'src/api/{target_page.lower()}.js'],
                'dependencies': [frontend_subtask['title']],
                'acceptance_criteria': [
                    f'API endpoint accepts {action} requests',
                    f'Proper validation and error responses',
                    f'Data persistence working correctly'
                ],
                'estimate': 'Medium (5 story points)',
                'priority': 'Medium'
            }
            tickets.append(backend_subtask)
            logger.info(f"Created backend subtask: {backend_subtask['title']} (action: {action})")
        else:
            logger.info(f"Skipping backend subtask - action '{action}' doesn't require data persistence")
        
        # Testing subtask
        testing_subtask = {
            'type': 'subtask',
            'parent': parent_story['title'],
            'title': f'Test {feature_type.title()} Implementation',
            'description': f'Create comprehensive tests for the {feature_type} feature on {target_page} page.',
            'technical_changes': [
                'Write unit tests for components',
                'Create integration tests',
                'Add end-to-end tests'
            ],
            'files_to_modify': [f'tests/{target_page.title()}{feature_type.title()}.test.js'],
            'dependencies': [frontend_subtask['title']],
            'acceptance_criteria': [
                'All unit tests pass',
                'Integration tests cover main flows',
                'E2E tests validate user journey'
            ],
            'estimate': 'Small (2 story points)',
            'priority': 'Medium'
        }
        tickets.append(testing_subtask)
        logger.info(f"Created testing subtask: {testing_subtask['title']}")
        
        logger.info(f"Generated {len(tickets)} fallback tickets")
        return tickets

class InteractivePromptNode(LLMDecisionNode):
    """Node that prompts results to user and waits for response before continuing"""
    
    def __init__(self):
        super().__init__(
            name="InteractivePrompt",
            llm_prompt="Generate prompts to present results to user and wait for responses."
        )
        self.prompt_message = ""
        self.waiting_for_response = False
        self.user_response = None
    
    def update(self):
        try:
            # Check if we have a user response
            user_response = self.context.get('user_response')
            
            if user_response:
                # Handle the user response
                return self.handle_user_response(user_response)
            
            clarification_needed = self.context.get('clarification_needed', False)
            questions = self.context.get('clarification_questions', [])
            codebase_search_queries = self.context.get('codebase_search_queries', [])
            parsed_data = self.context.get('parsed_data', {})
            tickets = self.context.get('tickets', [])
            
            if clarification_needed:
                # Generate prompt for clarification questions
                prompt_text = "I need some clarification to create comprehensive Jira tickets:\n\n"
                prompt_text += "**Questions for you:**\n"
                for i, question in enumerate(questions, 1):
                    prompt_text += f"{i}. {question}\n"
                
                if codebase_search_queries:
                    prompt_text += f"\n**Codebase searches to perform:**\n"
                    for i, query in enumerate(codebase_search_queries, 1):
                        prompt_text += f"{i}. {query}\n"
                
                if parsed_data:
                    prompt_text += f"\n**What I understand so far:**\n"
                    prompt_text += f"- Target page: {parsed_data.get('target_page', 'Not specified')}\n"
                    prompt_text += f"- Feature type: {parsed_data.get('feature_type', 'Not specified')}\n"
                    prompt_text += f"- Action: {parsed_data.get('action', 'Not specified')}\n"
                
                prompt_text += "\n**Please provide the missing information so I can continue.**"
                
                self.prompt_message = prompt_text
                self.context['interactive_prompt'] = prompt_text
                self.context['waiting_for_user_response'] = True
                
                return Status.RUNNING  # Keep running until user responds
                
            else:
                # Generate prompt for successful ticket generation
                prompt_text = f"✅ Perfect! I have enough information to create comprehensive Jira tickets.\n\n"
                
                if tickets:
                    prompt_text += f"🎫 **Generated Jira Tickets ({len(tickets)} total):**\n\n"
                    
                    # Group tickets by type
                    parent_stories = [t for t in tickets if t.get('type') == 'parent_story']
                    subtasks = [t for t in tickets if t.get('type') == 'subtask']
                    
                    for i, story in enumerate(parent_stories, 1):
                        prompt_text += f"**Parent Story {i}:**\n"
                        prompt_text += f"- Title: {story.get('title', 'Untitled')}\n"
                        prompt_text += f"- Description: {story.get('description', 'No description')}\n"
                        prompt_text += f"- System Impact: {story.get('system_impact', 'Not specified')}\n"
                        prompt_text += f"- Estimate: {story.get('estimate', 'Not specified')}\n"
                        prompt_text += f"- Priority: {story.get('priority', 'Not specified')}\n\n"
                    
                    if subtasks:
                        prompt_text += f"**Subtasks:**\n"
                        for i, subtask in enumerate(subtasks, 1):
                            prompt_text += f"{i}. **{subtask.get('title', 'Untitled')}**\n"
                            prompt_text += f"   - Parent: {subtask.get('parent', 'No parent')}\n"
                            prompt_text += f"   - Description: {subtask.get('description', 'No description')}\n"
                            prompt_text += f"   - Estimate: {subtask.get('estimate', 'Not specified')}\n"
                            prompt_text += f"   - Priority: {subtask.get('priority', 'Not specified')}\n"
                            
                            if subtask.get('acceptance_criteria'):
                                prompt_text += f"   - Acceptance Criteria:\n"
                                for criterion in subtask['acceptance_criteria']:
                                    prompt_text += f"     • {criterion}\n"
                            prompt_text += "\n"
                
                prompt_text += "\n**Would you like me to continue with implementation planning or explore other aspects?**"
                
                self.prompt_message = prompt_text
                self.context['interactive_prompt'] = prompt_text
                self.context['waiting_for_user_response'] = True
                
                return Status.RUNNING  # Keep running until user responds
            
        except Exception as e:
            logger.error(f"Error in InteractivePromptNode: {e}", exc_info=True)
            return Status.FAILURE
    
    def handle_user_response(self, response: str):
        """Handle user response and update context"""
        self.user_response = response
        self.context['user_response'] = response
        self.context['waiting_for_user_response'] = False
        
        # Parse the response to determine next steps
        response_lower = response.lower()
        
        if any(word in response_lower for word in ['yes', 'continue', 'proceed', 'ok', 'sure']):
            self.context['should_continue'] = True
        elif any(word in response_lower for word in ['no', 'stop', 'cancel', 'end']):
            self.context['should_continue'] = False
        else:
            # Default to continue if response is unclear
            self.context['should_continue'] = True
        
        return Status.SUCCESS

class SimpleSelector(Behaviour):
    """Simple selector that chooses between two paths based on context"""
    
    def __init__(self, name: str = "SimpleSelector"):
        super().__init__(name)
        self.context = {}
        self.children = []
    
    def add_child(self, child):
        """Add a child to the selector"""
        self.children.append(child)
    
    def setup(self, **kwargs):
        self.context = kwargs.get('context', {})
        # Setup all children
        for child in self.children:
            if hasattr(child, 'setup'):
                child.setup(**kwargs)
    
    def update(self):
        # Check if we have enough information
        has_enough_info = self.context.get('has_enough_info', False)
        
        if has_enough_info:
            # Execute ticket generation path (second child)
            if len(self.children) >= 2:
                # Execute the ticket generation sequence and return its status
                for status in self.children[1].tick():
                    pass  # Consume the generator
                return self.children[1].status
            else:
                logger.error("SimpleSelector: not enough children")
                return Status.FAILURE
        else:
            # Execute get more info path (first child)
            if len(self.children) >= 1:
                # Execute the get more info sequence and return its status
                for status in self.children[0].tick():
                    pass  # Consume the generator
                return self.children[0].status
            else:
                logger.error("SimpleSelector: no children")
                return Status.FAILURE

class LLMBehaviorTree:
    """Simplified behavior tree manager that uses LLM for decision-making"""
    
    def __init__(self):
        self.root = None
    
    def create_tree(self, feature_request: str, workspace_path: str = "."):
        """Create the simplified behavior tree structure"""
        
        # Main sequence that handles the complete flow
        root = Sequence(name="SimpleProjectManagerRoot", memory=True)
        
        # Step 1: Parse the initial feature request
        parse_node = ParseFeatureRequestNode()
        root.add_child(parse_node)
        
        # Step 2: Check if we have enough information
        check_node = CheckIfEnoughInfoNode()
        root.add_child(check_node)
        
        # Step 3: Decision point - do we have enough info?
        decision_selector = SimpleSelector(name="InfoDecision")
        
        # Option A: Get more information
        get_info_sequence = Sequence(name="GetMoreInformation", memory=True)
        get_info_node = GetMoreInfoNode()
        get_info_sequence.add_child(get_info_node)
        
        # Add interactive prompt for clarification
        interactive_prompt_node = InteractivePromptNode()
        get_info_sequence.add_child(interactive_prompt_node)
        
        # Option B: Generate tickets
        generate_tickets_sequence = Sequence(name="GenerateTickets", memory=True)
        tickets_node = GenerateTicketsNode()
        generate_tickets_sequence.add_child(tickets_node)
        
        # Add interactive prompt for ticket results
        interactive_prompt_node_tickets = InteractivePromptNode()
        generate_tickets_sequence.add_child(interactive_prompt_node_tickets)
        
        # Add both options to the decision selector
        decision_selector.add_child(get_info_sequence)
        decision_selector.add_child(generate_tickets_sequence)
        
        # Add the decision point to the main sequence
        root.add_child(decision_selector)
        
        self.root = root
        return root
    
    def execute(self, feature_request: str, workspace_path: str = ".", user_response: str = None):
        """Execute the simplified behavior tree with LLM decision-making"""
        tree = self.create_tree(feature_request, workspace_path)
        
        # Set up context for all nodes
        context = {
            'feature_request': feature_request,
            'workspace_path': workspace_path
        }
        
        # If we have a user response, add it to context
        if user_response:
            context['user_response'] = user_response
            # Clear any previous waiting state
            context['waiting_for_user_response'] = False
        
        # Execute the behavior tree
        print(py_trees.display.ascii_tree(tree))
        
        # Tick the tree until completion or until we need user input
        tick_count = 0
        max_ticks = 100  # Prevent infinite loops
        
        while tree.status != Status.SUCCESS and tree.status != Status.FAILURE and tick_count < max_ticks:
            tick_count += 1
            
            # Pass context to each node
            for node in tree.iterate():
                if hasattr(node, 'setup'):
                    node.setup(context=context)
            
            tree.tick_once()
            
            # Check if we have an interactive prompt waiting for user input
            interactive_prompt_node = self._find_interactive_prompt_node(tree)
            if interactive_prompt_node and interactive_prompt_node.status == Status.RUNNING:
                # We need user input, return the prompt
                return {
                    "waiting_for_user_input": True,
                    "prompt_message": interactive_prompt_node.prompt_message,
                    "clarification_needed": context.get('clarification_needed', False),
                    "parsed_data": context.get('parsed_data', {}),
                    "execution_path": "waiting_for_user_input"
                }
        
        # Extract results by traversing the tree
        def find_node_by_name(node, name):
            if node.name == name:
                return node
            for child in node.children:
                result = find_node_by_name(child, name)
                if result:
                    return result
            return None
        
        parse_node = find_node_by_name(tree, "ParseFeatureRequest")
        check_node = find_node_by_name(tree, "CheckIfEnoughInfo")
        get_info_node = find_node_by_name(tree, "GetMoreInfo")
        tickets_node = find_node_by_name(tree, "GenerateTickets")
        interactive_prompt_node = find_node_by_name(tree, "InteractivePrompt")
        
        # Determine the execution path taken
        get_info_sequence = find_node_by_name(tree, "GetMoreInformation")
        generate_tickets_sequence = find_node_by_name(tree, "GenerateTickets")
        
        if generate_tickets_sequence and generate_tickets_sequence.status == Status.SUCCESS:
            # Tickets generated successfully
            result = {
                "tickets": tickets_node.tickets if tickets_node else [],
                "clarification_needed": False,
                "parsed_data": parse_node.parsed_data if parse_node else {},
                "execution_path": "tickets_generated",
                "waiting_for_user_input": False
            }
        elif get_info_sequence and get_info_sequence.status == Status.SUCCESS:
            # Need more information
            result = {
                "tickets": [],
                "clarification_needed": True,
                "clarification_questions": get_info_node.questions if get_info_node else [],
                "codebase_search_queries": get_info_node.codebase_search_queries if get_info_node else [],
                "parsed_data": parse_node.parsed_data if parse_node else {},
                "execution_path": "need_more_info",
                "waiting_for_user_input": False
            }
        else:
            # Something went wrong
            result = {
                "tickets": [],
                "clarification_needed": True,
                "clarification_questions": ["Could you please provide more details about your feature request?"],
                "parsed_data": parse_node.parsed_data if parse_node else {},
                "execution_path": "error",
                "waiting_for_user_input": False
            }
            logger.error("Behavior tree execution: FAILURE")
        
        return result
    
    def _find_interactive_prompt_node(self, tree):
        """Find the interactive prompt node in the tree"""
        def find_node_by_name(node, name):
            if node.name == name:
                return node
            for child in node.children:
                result = find_node_by_name(child, name)
                if result:
                    return result
            return None
        
        return find_node_by_name(tree, "InteractivePrompt")