"""
Stage 3: User Story Generation using Ollama LLMs
Generates properly formatted Agile user stories with sentiment-aware prompting
"""

import json
import re
import requests
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StoryGenerator:
    """Generate structured user stories using local LLMs via Ollama"""
    
    def __init__(self, 
                 model_name: str = "llama3.2:3b",
                 ollama_url: str = "http://localhost:11434"):
        """
        Initialize story generator
        
        Args:
            model_name: Ollama model identifier
            ollama_url: Ollama server URL
        """
        self.model_name = model_name
        self.ollama_url = ollama_url
        self.api_endpoint = f"{ollama_url}/api/generate"
        
        # Verify Ollama is running
        try:
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                logger.info(f"Connected to Ollama at {ollama_url}")
                models = response.json().get('models', [])
                available = [m['name'] for m in models]
                if model_name not in available:
                    logger.warning(f"Model {model_name} not found. Available: {available}")
                    logger.warning(f"Run: ollama pull {model_name}")
            else:
                logger.error("Ollama server not responding correctly")
        except requests.exceptions.RequestException as e:
            logger.error(f"Cannot connect to Ollama: {e}")
            logger.error("Make sure Ollama is running: brew services start ollama")
    
    def generate_story(self,
                      requirement: str,
                      priority: str,
                      sentiment_context: Dict[str, float],
                      project_context: str = "General software project") -> Dict[str, Any]:
        """
        Generate structured user story with sentiment-informed prompting
        
        Args:
            requirement: Extracted requirement text
            priority: "High", "Medium", or "Low"
            sentiment_context: Sentiment analysis results
            project_context: Project/sprint information
            
        Returns:
            Structured user story dictionary
        """
        logger.info(f"Generating story for: {requirement[:50]}... (Priority: {priority})")
        
        # Build prompt with sentiment context
        prompt = self._build_prompt(requirement, priority, sentiment_context, project_context)
        
        try:
            # Call Ollama API
            response = requests.post(
                self.api_endpoint,
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                },
                timeout=60
            )
            
            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code}")
            
            generated_text = response.json()['response']
            story = self._extract_json(generated_text)
            
            # Validate and enrich
            validated_story = self._validate_and_enrich(
                story, priority, sentiment_context, requirement
            )
            
            logger.info(f"✓ Generated story: '{validated_story['title']}'")
            return validated_story
            
        except Exception as e:
            logger.error(f"Story generation failed: {e}")
            # Return fallback story
            return self._create_fallback_story(requirement, priority, sentiment_context)
    
    def _build_prompt(self, 
                     requirement: str,
                     priority: str, 
                     sentiment_context: Dict[str, float],
                     project_context: str) -> str:
        """Build sentiment-aware prompt for LLM"""
        
        # Add sentiment-specific guidance
        sentiment_guidance = ""
        explanation = sentiment_context.get('explanation', '')
        if priority == "High":
            sentiment_guidance = (
                f"\n\nIMPORTANT: This requirement was expressed with high urgency "
                f"(priority score: {sentiment_context['priority_score']:.2f}). "
                f"Ensure the 'so that' clause clearly emphasizes business impact, "
                f"user frustration, or revenue/retention concerns."
            )
        if explanation:
            sentiment_guidance += f"\nPriority rationale: {explanation}"
        
        prompt = f"""You are an experienced Agile product manager writing user stories for a development team.

Project Context: {project_context}

Requirement from stakeholder discussion:
"{requirement}"

Priority Level: {priority}{sentiment_guidance}

Generate a properly formatted Agile work item following best practices.

OUTPUT FORMAT (must be valid JSON):
{{
    "title": "Brief descriptive title (max 60 characters)",
    "issue_type": "Story" | "Bug" | "Task" | "Epic",
    "story": "As a [specific user type], I want [clear goal], so that [concrete benefit]",
    "acceptance_criteria": [
        "Given [context], When [action], Then [expected outcome with measurable result]",
        "Given [context], When [action], Then [expected outcome with measurable result]",
        "Given [edge case context], When [action], Then [expected outcome or error handling]"
    ],
    "story_points": 1 | 2 | 3 | 5 | 8 | 13,
    "notes": "Technical considerations, dependencies, or implementation hints"
}}

ISSUE TYPE SELECTION RULES (pick exactly one):
- "Bug": The requirement describes something broken, incorrect behaviour, a defect, or a regression. Keywords: "broken", "not working", "error", "crash", "wrong", "fix", "doesn't work".
- "Epic": The requirement is very large or high-level, spanning multiple features or sprints. Keywords: "platform", "overhaul", "redesign", "entire", "all", "system-wide".
- "Task": A purely technical or non-user-facing piece of work (infrastructure, refactor, migration, CI/CD, documentation). No direct user value statement.
- "Story": Default for any user-facing feature, improvement, or enhancement that has a clear user benefit. Use this when none of the above apply.

REQUIREMENTS:
- Story/acceptance_criteria still required for all issue types (adapt the "As a..." format to make sense for bugs/tasks if needed)
- Story must be ATOMIC (single feature only, not multiple)
- User type must be specific (not just "user" - e.g., "customer", "admin", "developer")
- Acceptance criteria MUST be written in BDD format: "Given [context], When [action], Then [outcome]"
- Each criterion must be testable with measurable outcomes
- Include specific metrics where applicable (e.g., "< 3 seconds", "with 95% accuracy")
- Story points should reflect complexity: 1-2 (trivial), 3-5 (moderate), 8+ (complex)

Generate ONLY the JSON object. No additional text or explanation."""

        return prompt
    
    def _extract_json(self, response_text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response, handling various formats"""
        try:
            # Try direct parsing first
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks or surrounding text
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # Try finding JSON between ```json and ```
            markdown_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if markdown_match:
                try:
                    return json.loads(markdown_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            raise ValueError(f"Could not extract valid JSON from response: {response_text[:200]}")
    
    def _validate_and_enrich(self,
                            story: Dict[str, Any],
                            priority: str,
                            sentiment_context: Dict[str, float],
                            original_requirement: str) -> Dict[str, Any]:
        """Validate story structure and add metadata"""
        
        # Check required fields
        required_fields = ['title', 'story', 'acceptance_criteria', 'story_points']
        for field in required_fields:
            if field not in story:
                raise ValueError(f"Generated story missing required field: {field}")

        # Validate and normalise issue_type
        valid_issue_types = {"Story", "Bug", "Task", "Epic"}
        raw_type = story.get("issue_type", "Story")
        if raw_type not in valid_issue_types:
            logger.warning(f"Unknown issue_type '{raw_type}', defaulting to 'Story'")
            raw_type = "Story"
        story["issue_type"] = raw_type

        # Validate story format
        if not story['story'].startswith("As a"):
            logger.warning(f"Story doesn't follow 'As a...' format: {story['story'][:50]}")

        # Validate acceptance criteria
        if len(story['acceptance_criteria']) < 3:
            logger.warning(f"Story has only {len(story['acceptance_criteria'])} acceptance criteria (recommended: 3+)")

        # Validate story points
        valid_points = [1, 2, 3, 5, 8, 13]
        if story['story_points'] not in valid_points:
            logger.warning(f"Invalid story points: {story['story_points']}. Using 5 as default.")
            story['story_points'] = 5
        
        # Add metadata
        story['priority'] = priority
        story['priority_confidence'] = sentiment_context['priority_score']
        story['sentiment_scores'] = {
            'negative': sentiment_context.get('negative', 0.0),
            'neutral': sentiment_context.get('neutral', 0.0),
            'positive': sentiment_context.get('positive', 0.0),
        }
        if 'confidence' in sentiment_context:
            story['priority_detector_confidence'] = sentiment_context['confidence']
        if 'signal_breakdown' in sentiment_context:
            story['priority_signal_breakdown'] = sentiment_context['signal_breakdown']
        if 'explanation' in sentiment_context:
            story['priority_explanation'] = sentiment_context['explanation']
        story['generation_timestamp'] = datetime.now().isoformat()
        story['source_requirement'] = original_requirement
        story['model_used'] = self.model_name
        
        return story
    
    def _create_fallback_story(self,
                               requirement: str,
                               priority: str,
                               sentiment_context: Dict[str, float]) -> Dict[str, Any]:
        """Create a basic story when generation fails"""
        logger.warning("Using fallback story generation")
        
        return {
            'title': f"Implement: {requirement[:40]}",
            'issue_type': 'Story',
            'story': f"As a user, I want {requirement}, so that my needs are met",
            'acceptance_criteria': [
                "Feature is implemented according to requirements",
                "Feature is tested and working",
                "Documentation is updated"
            ],
            'story_points': 5,
            'priority': priority,
            'priority_confidence': sentiment_context['priority_score'],
            'sentiment_scores': {
                'negative': sentiment_context.get('negative', 0.0),
                'neutral': sentiment_context.get('neutral', 0.0),
                'positive': sentiment_context.get('positive', 0.0),
            },
            'generation_timestamp': datetime.now().isoformat(),
            'source_requirement': requirement,
            'model_used': self.model_name,
            'notes': 'Generated using fallback method due to LLM error'
        }


if __name__ == "__main__":
    # Quick test
    generator = StoryGenerator()
    
    test_requirement = "Users are frustrated with the checkout process taking too long. We need to streamline it to 3 clicks maximum."
    test_sentiment = {
        'negative': 0.75,
        'neutral': 0.15,
        'positive': 0.10,
        'priority_score': 0.85
    }
    
    print("\n=== Story Generation Test ===\n")
    story = generator.generate_story(
        requirement=test_requirement,
        priority="High",
        sentiment_context=test_sentiment,
        project_context="E-commerce platform"
    )
    
    print(json.dumps(story, indent=2))