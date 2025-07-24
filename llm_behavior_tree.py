import py_trees
from py_trees.behaviour import Behaviour
from py_trees.composites import Selector, Sequence
from py_trees.common import Status
import logging
from typing import Dict, Any, List
from llm_parser import parse_with_llm

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("=== Initializing LLM Behavior Tree Module ===")

class LLMDecisionNode(Behaviour):
    """Base class for LLM-powered decision nodes"""
    
    def __init__(self, name: str, llm_prompt: str):
        super().__init__(name=name)
        self.llm_prompt = llm_prompt
        self.context = {}
        logger.debug(f"Created LLMDecisionNode: {name}")
    
    def setup(self, **kwargs):
        """Setup with context data"""
        self.context = kwargs.get('context', {})
        logger.info(f"Setting up {self.name} with context keys: {list(self.context.keys())}")
        logger.debug(f"Context data: {self.context}")
    
    def initialise(self):
        logger.info(f"Initializing {self.name}")
    
    def _ask_llm(self, question: str) -> Dict[str, Any]:
        """Ask the LLM a question and get structured response"""
        logger.info(f"=== {self.name}: Asking LLM ===")
        logger.debug(f"Question: {question}")
        
        try:
            # Combine the base prompt with the specific question
            full_prompt = f"{self.llm_prompt}\n\nQuestion: {question}\n\nContext: {self.context}"
            logger.debug(f"Full prompt: {full_prompt}")
            
            # Use the LLM parser to get structured response
            response = parse_with_llm(full_prompt)
            logger.info(f"LLM response received: {response}")
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
        logger.info("ParseFeatureRequestNode initialized")
    
    def update(self):
        logger.info("=== ParseFeatureRequestNode: update() called ===")
        try:
            feature_request = self.context.get('feature_request', '')
            logger.debug(f"Feature request: '{feature_request}'")
            
            if not feature_request:
                logger.warning("No feature request found in context")
                return Status.FAILURE
            
            # Use LLM to parse the feature request
            logger.info("Calling LLM parser for feature request")
            self.parsed_data = parse_with_llm(feature_request)
            
            # Store the parsed data in context for other nodes
            self.context['parsed_data'] = self.parsed_data
            
            logger.info(f"LLM parsed data: {self.parsed_data}")
            logger.info("ParseFeatureRequestNode: SUCCESS")
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in ParseFeatureRequest: {e}", exc_info=True)
            return Status.FAILURE

class ValidateRequestNode(LLMDecisionNode):
    """Validate request completeness using LLM"""
    
    def __init__(self):
        super().__init__(
            name="ValidateRequest",
            llm_prompt="Analyze if a feature request has enough information to create tickets. Identify missing information."
        )
        self.missing_info = []
        self.suggestions = []
        logger.info("ValidateRequestNode initialized")
    
    def update(self):
        logger.info("=== ValidateRequestNode: update() called ===")
        try:
            parsed_data = self.context.get('parsed_data', {})
            feature_request = self.context.get('feature_request', '')
            
            logger.debug(f"Parsed data: {parsed_data}")
            logger.debug(f"Feature request: '{feature_request}'")
            
            if not parsed_data:
                logger.warning("No parsed data found in context")
                return Status.FAILURE
            
            # Ask LLM to validate the request
            validation_question = f"""
            Analyze this feature request: "{feature_request}"
            
            Parsed information:
            - Target page: {parsed_data.get('target_page', 'Not specified')}
            - Feature type: {parsed_data.get('feature_type', 'Not specified')}
            - Action: {parsed_data.get('action', 'Not specified')}
            
            Determine if we have enough information to create Jira tickets. 
            If not, identify what's missing and suggest questions to ask.
            """
            
            logger.info("Calling LLM for validation")
            llm_response = self._ask_llm(validation_question)
            
            # Extract missing information from LLM response
            # The LLM should return structured data about what's missing
            if llm_response.get('missing_info'):
                self.missing_info = llm_response['missing_info']
                self.suggestions = llm_response.get('suggestions', [])
                self.context['missing_info'] = self.missing_info
                self.context['suggestions'] = self.suggestions
                logger.info(f"Missing information identified: {self.missing_info}")
                logger.info("ValidateRequestNode: FAILURE (missing info)")
                return Status.FAILURE
            else:
                logger.info("Request validation successful - all required info present")
                logger.info("ValidateRequestNode: SUCCESS")
                return Status.SUCCESS
                
        except Exception as e:
            logger.error(f"Error in ValidateRequest: {e}", exc_info=True)
            return Status.FAILURE

class GenerateClarificationQuestionsNode(LLMDecisionNode):
    """Generate clarification questions using LLM"""
    
    def __init__(self):
        super().__init__(
            name="GenerateClarificationQuestions",
            llm_prompt="Generate specific, helpful clarification questions based on missing information."
        )
        self.questions = []
        logger.info("GenerateClarificationQuestionsNode initialized")
    
    def update(self):
        logger.info("=== GenerateClarificationQuestionsNode: update() called ===")
        try:
            missing_info = self.context.get('missing_info', [])
            feature_request = self.context.get('feature_request', '')
            
            logger.debug(f"Missing info: {missing_info}")
            logger.debug(f"Feature request: '{feature_request}'")
            
            if not missing_info:
                logger.info("No missing info found, skipping question generation")
                return Status.SUCCESS
            
            # Ask LLM to generate specific questions
            question_prompt = f"""
            For this feature request: "{feature_request}"
            
            Missing information: {missing_info}
            
            Generate 2-3 specific, helpful clarification questions that will help gather the missing information.
            Make the questions conversational and provide examples where helpful.
            """
            
            logger.info("Calling LLM to generate clarification questions")
            llm_response = self._ask_llm(question_prompt)
            
            # Extract questions from LLM response
            if llm_response.get('questions'):
                self.questions = llm_response['questions']
                logger.info(f"Generated questions from LLM: {self.questions}")
            else:
                # Fallback to basic questions
                logger.warning("LLM didn't return questions, using fallback")
                self.questions = [
                    "Which page should this feature be added to?",
                    "What type of feature should be added?",
                    "What should happen when this feature is used?"
                ]
                logger.info(f"Using fallback questions: {self.questions}")
            
            self.context['clarification_questions'] = self.questions
            logger.info(f"Generated {len(self.questions)} clarification questions")
            logger.info("GenerateClarificationQuestionsNode: SUCCESS")
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in GenerateClarificationQuestions: {e}", exc_info=True)
            return Status.FAILURE

class AnalyzeCodebaseNode(LLMDecisionNode):
    """Analyze codebase using LLM"""
    
    def __init__(self):
        super().__init__(
            name="AnalyzeCodebase",
            llm_prompt="Analyze codebase structure and identify relevant files for feature implementation."
        )
        self.analysis_result = {}
        logger.info("AnalyzeCodebaseNode initialized")
    
    def update(self):
        logger.info("=== AnalyzeCodebaseNode: update() called ===")
        try:
            workspace_path = self.context.get('workspace_path', '.')
            target_page = self.context.get('parsed_data', {}).get('target_page', '')
            
            logger.debug(f"Workspace path: {workspace_path}")
            logger.debug(f"Target page: {target_page}")
            
            if not target_page:
                logger.warning("No target page found in parsed data")
                return Status.FAILURE
            
            # Ask LLM to analyze the codebase structure
            analysis_question = f"""
            For a feature on the "{target_page}" page, analyze the codebase structure at "{workspace_path}".
            
            Identify:
            1. Frontend component files (React/Vue/Angular)
            2. Stylesheet files (CSS/SCSS)
            3. Test files
            4. Backend files (if needed)
            
            Provide a structured analysis of what files would need to be modified.
            """
            
            logger.info("Calling LLM for codebase analysis")
            llm_response = self._ask_llm(analysis_question)
            
            # Extract analysis from LLM response
            self.analysis_result = {
                'frontend_components': llm_response.get('frontend_files', []),
                'stylesheets': llm_response.get('style_files', []),
                'test_files': llm_response.get('test_files', []),
                'backend_files': llm_response.get('backend_files', [])
            }
            
            self.context['analysis_result'] = self.analysis_result
            logger.info(f"Codebase analysis completed: {self.analysis_result}")
            logger.info("AnalyzeCodebaseNode: SUCCESS")
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in AnalyzeCodebase: {e}", exc_info=True)
            return Status.FAILURE

class GenerateTicketsNode(LLMDecisionNode):
    """Generate Jira tickets using LLM"""
    
    def __init__(self):
        super().__init__(
            name="GenerateTickets",
            llm_prompt="Generate comprehensive Jira tickets with effort estimates and detailed descriptions."
        )
        self.tickets = []
        logger.info("GenerateTicketsNode initialized")
    
    def update(self):
        logger.info("=== GenerateTicketsNode: update() called ===")
        try:
            parsed_data = self.context.get('parsed_data', {})
            analysis_result = self.context.get('analysis_result', {})
            
            logger.debug(f"Parsed data: {parsed_data}")
            logger.debug(f"Analysis result: {analysis_result}")
            
            if not parsed_data or not analysis_result:
                logger.warning("Missing parsed_data or analysis_result")
                return Status.FAILURE
            
            # Ask LLM to generate tickets
            ticket_prompt = f"""
            Generate Jira tickets for this feature:
            
            Feature Info:
            - Target page: {parsed_data.get('target_page')}
            - Feature type: {parsed_data.get('feature_type')}
            - Action: {parsed_data.get('action')}
            
            Codebase Analysis:
            - Frontend files: {analysis_result.get('frontend_components', [])}
            - Style files: {analysis_result.get('stylesheets', [])}
            - Test files: {analysis_result.get('test_files', [])}
            - Backend files: {analysis_result.get('backend_files', [])}
            
            Generate 3-5 detailed Jira tickets covering:
            1. Frontend implementation
            2. Backend implementation (if needed)
            3. Styling
            4. Testing
            5. Documentation
            
            Each ticket should include title, description, effort estimate, priority, and files to modify.
            """
            
            logger.info("Calling LLM to generate tickets")
            llm_response = self._ask_llm(ticket_prompt)
            
            # Extract tickets from LLM response
            if llm_response.get('tickets'):
                self.tickets = llm_response['tickets']
                logger.info(f"Generated tickets from LLM: {len(self.tickets)} tickets")
            else:
                # Fallback to basic ticket generation
                logger.warning("LLM didn't return tickets, using fallback generation")
                self.tickets = self._generate_fallback_tickets(parsed_data, analysis_result)
                logger.info(f"Generated fallback tickets: {len(self.tickets)} tickets")
            
            self.context['tickets'] = self.tickets
            logger.info(f"Generated {len(self.tickets)} tickets total")
            logger.info("GenerateTicketsNode: SUCCESS")
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in GenerateTickets: {e}", exc_info=True)
            return Status.FAILURE
    
    def _generate_fallback_tickets(self, parsed_data: Dict, analysis_result: Dict) -> List[Dict]:
        """Fallback ticket generation if LLM fails"""
        logger.info("Generating fallback tickets")
        tickets = []
        target_page = parsed_data.get('target_page', '')
        feature_type = parsed_data.get('feature_type', '')
        action = parsed_data.get('action', '')
        
        # Frontend ticket
        if analysis_result.get('frontend_components'):
            tickets.append({
                'title': f'Add {feature_type.title()} to {target_page.title()} Component',
                'description': f'Implement {feature_type} on {target_page} page',
                'effort': '2-4 hours',
                'priority': 'Medium',
                'type': 'frontend'
            })
        
        # Backend ticket
        if action in ['save', 'submit', 'update', 'delete']:
            tickets.append({
                'title': f'Implement {action.title()} Handler',
                'description': f'Create backend endpoint for {action} functionality',
                'effort': '4-6 hours',
                'priority': 'Medium',
                'type': 'backend'
            })
        
        logger.info(f"Generated {len(tickets)} fallback tickets")
        return tickets

class CreateSummaryNode(LLMDecisionNode):
    """Create project summary using LLM"""
    
    def __init__(self):
        super().__init__(
            name="CreateSummary",
            llm_prompt="Create comprehensive project summaries with effort estimates and recommendations."
        )
        self.summary = ""
        logger.info("CreateSummaryNode initialized")
    
    def update(self):
        logger.info("=== CreateSummaryNode: update() called ===")
        try:
            parsed_data = self.context.get('parsed_data', {})
            tickets = self.context.get('tickets', [])
            
            logger.debug(f"Parsed data: {parsed_data}")
            logger.debug(f"Tickets count: {len(tickets)}")
            
            if not parsed_data or not tickets:
                logger.warning("Missing parsed_data or tickets")
                return Status.FAILURE
            
            # Ask LLM to create summary
            summary_prompt = f"""
            Create a comprehensive project summary for this feature:
            
            Feature: {parsed_data.get('feature_type')} on {parsed_data.get('target_page')} page
            Action: {parsed_data.get('action')}
            
            Generated tickets: {len(tickets)} tickets
            
            Create a markdown summary including:
            1. Feature overview
            2. Ticket breakdown
            3. Total effort estimate
            4. Sprint recommendations
            5. Risk assessment
            """
            
            logger.info("Calling LLM to create summary")
            llm_response = self._ask_llm(summary_prompt)
            
            # Extract summary from LLM response
            if llm_response.get('summary'):
                self.summary = llm_response['summary']
                logger.info("Generated summary from LLM")
            else:
                # Fallback summary
                logger.warning("LLM didn't return summary, using fallback")
                self.summary = self._generate_fallback_summary(parsed_data, tickets)
                logger.info("Generated fallback summary")
            
            self.context['summary'] = self.summary
            logger.info("Summary created successfully")
            logger.info("CreateSummaryNode: SUCCESS")
            return Status.SUCCESS
            
        except Exception as e:
            logger.error(f"Error in CreateSummary: {e}", exc_info=True)
            return Status.FAILURE
    
    def _generate_fallback_summary(self, parsed_data: Dict, tickets: List[Dict]) -> str:
        """Fallback summary generation"""
        logger.info("Generating fallback summary")
        total_effort = sum(
            int(ticket.get('effort', '2').split('-')[0]) 
            for ticket in tickets 
            if ticket.get('effort')
        )
        
        summary = f"# Feature Analysis Complete\n\n"
        summary += f"**Feature:** {parsed_data.get('feature_type')} on {parsed_data.get('target_page')} page\n"
        summary += f"**Total Tickets:** {len(tickets)}\n"
        summary += f"**Estimated Effort:** {total_effort}+ hours\n"
        summary += f"**Recommended Sprint:** {'Current Sprint' if total_effort <= 8 else 'Next Sprint'}\n"
        
        logger.info(f"Generated fallback summary with {total_effort} hours effort")
        return summary

class LLMBehaviorTree:
    """Behavior tree manager that uses LLM for decision-making"""
    
    def __init__(self):
        self.root = None
        logger.info("LLMBehaviorTree initialized")
    
    def create_tree(self, feature_request: str, workspace_path: str = "."):
        """Create the behavior tree structure"""
        logger.info("=== Creating behavior tree ===")
        logger.debug(f"Feature request: '{feature_request}'")
        logger.debug(f"Workspace path: {workspace_path}")
        
        root = Selector(name="LLMProjectManagerRoot")
        
        # Main analysis sequence
        main_sequence = Sequence(name="LLMAnalysis")
        
        # Parse feature request
        parse_node = ParseFeatureRequestNode()
        main_sequence.add_child(parse_node)
        
        # Validate request
        validate_node = ValidateRequestNode()
        main_sequence.add_child(validate_node)
        
        # Generate clarification questions (if validation fails)
        questions_node = GenerateClarificationQuestionsNode()
        main_sequence.add_child(questions_node)
        
        # Alternative path: complete analysis
        complete_sequence = Sequence(name="CompleteAnalysis")
        
        # Analyze codebase
        analyze_node = AnalyzeCodebaseNode()
        complete_sequence.add_child(analyze_node)
        
        # Generate tickets
        tickets_node = GenerateTicketsNode()
        complete_sequence.add_child(tickets_node)
        
        # Create summary
        summary_node = CreateSummaryNode()
        complete_sequence.add_child(summary_node)
        
        root.add_child(main_sequence)
        root.add_child(complete_sequence)
        
        self.root = root
        logger.info("Behavior tree created successfully")
        return root
    
    def execute(self, feature_request: str, workspace_path: str = "."):
        """Execute the behavior tree with LLM decision-making"""
        logger.info("=== Executing behavior tree ===")
        logger.info(f"Feature request: '{feature_request}'")
        logger.info(f"Workspace path: {workspace_path}")
        
        tree = self.create_tree(feature_request, workspace_path)
        
        # Set up context for all nodes
        context = {
            'feature_request': feature_request,
            'workspace_path': workspace_path
        }
        logger.debug(f"Initial context: {context}")
        
        # Execute the behavior tree
        logger.info("Displaying behavior tree structure:")
        print(py_trees.display.ascii_tree(tree))
        
        # Tick the tree until completion
        tick_count = 0
        while tree.status != Status.SUCCESS and tree.status != Status.FAILURE:
            tick_count += 1
            logger.info(f"=== Tick {tick_count} ===")
            
            # Pass context to each node
            for node in tree.iterate():
                if hasattr(node, 'setup'):
                    node.setup(context=context)
            
            tree.tick_once()
            logger.info(f"Tree status after tick {tick_count}: {tree.status}")
        
        logger.info(f"Behavior tree execution completed after {tick_count} ticks")
        logger.info(f"Final tree status: {tree.status}")
        
        # Extract results by traversing the tree
        def find_node_by_name(node, name):
            if node.name == name:
                return node
            for child in node.children:
                result = find_node_by_name(child, name)
                if result:
                    return result
            return None
        
        logger.info("Extracting results from tree nodes")
        parse_node = find_node_by_name(tree, "ParseFeatureRequest")
        validate_node = find_node_by_name(tree, "ValidateRequest")
        questions_node = find_node_by_name(tree, "GenerateClarificationQuestions")
        analyze_node = find_node_by_name(tree, "AnalyzeCodebase")
        tickets_node = find_node_by_name(tree, "GenerateTickets")
        summary_node = find_node_by_name(tree, "CreateSummary")
        
        if tree.status == Status.SUCCESS:
            result = {
                "tickets": tickets_node.tickets if tickets_node else [],
                "summary": summary_node.summary if summary_node else "",
                "clarification_needed": False,
                "parsed_data": parse_node.parsed_data if parse_node else {},
                "analysis_result": analyze_node.analysis_result if analyze_node else {}
            }
            logger.info("Behavior tree execution: SUCCESS")
            logger.info(f"Generated {len(result['tickets'])} tickets")
            logger.info("=== Behavior tree execution completed successfully ===")
            return result
        else:
            result = {
                "tickets": [],
                "summary": "",
                "clarification_needed": True,
                "clarification_questions": questions_node.questions if questions_node else [],
                "parsed_data": parse_node.parsed_data if parse_node else {}
            }
            logger.info("Behavior tree execution: FAILURE (clarification needed)")
            logger.info(f"Generated {len(result['clarification_questions'])} clarification questions")
            logger.info("=== Behavior tree execution completed with clarification needed ===")
            return result 