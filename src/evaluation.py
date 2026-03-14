"""
Story Quality Evaluation using QUS Framework
Based on Lucassen et al. (2016) Quality User Story criteria
"""

import re
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StoryEvaluator:
    """Evaluate user story quality using QUS framework"""
    
    def __init__(self):
        """Initialize evaluator with QUS criteria"""
        self.qus_criteria = {
            'well_formed': 'Story follows "As a... I want... So that..." format',
            'atomic': 'Story addresses only one feature/capability',
            'minimal': 'Story is concise and not verbose',
            'complete': 'Story has all required elements (role, goal, benefit)',
            'testable': 'Acceptance criteria are verifiable',
            'estimable': 'Story points assigned appropriately'
        }
    
    def evaluate_story(self, story: Dict) -> Dict[str, float]:
        """
        Evaluate single story against QUS criteria
        
        Args:
            story: Generated user story dictionary
            
        Returns:
            Dictionary of criterion scores (0-1)
        """
        scores = {}
        
        scores['well_formed'] = self._check_well_formed(story['story'])
        scores['atomic'] = self._check_atomic(story)
        scores['minimal'] = self._check_minimal(story)
        scores['complete'] = self._check_complete(story)
        scores['testable'] = self._check_testable(story['acceptance_criteria'])
        scores['estimable'] = self._check_estimable(story)
        
        # Calculate overall QUS score
        scores['overall_qus'] = sum(scores.values()) / len(scores)
        
        return scores
    
    def _check_well_formed(self, story_text: str) -> float:
        """Check if story follows proper format"""
        pattern = r"As a .+, I want .+, so that .+"
        
        if re.search(pattern, story_text, re.IGNORECASE):
            return 1.0
        elif story_text.lower().startswith("as a"):
            return 0.5  # Partial credit for starting correctly
        else:
            return 0.0
    
    def _check_atomic(self, story: Dict) -> float:
        """
        Check if story addresses single feature
        Heuristic: Look for conjunction words that might indicate multiple features
        """
        conjunctions = ['and', 'also', 'plus', 'additionally', 'as well as']
        story_lower = story['story'].lower()
        
        conjunction_count = sum(1 for conj in conjunctions if conj in story_lower)
        
        # Check acceptance criteria count (>5 might indicate multiple features)
        ac_count = len(story.get('acceptance_criteria', []))
        
        if conjunction_count == 0 and ac_count <= 5:
            return 1.0
        elif conjunction_count == 1 or ac_count == 6:
            return 0.7
        elif conjunction_count <= 2 or ac_count <= 7:
            return 0.4
        else:
            return 0.0
    
    def _check_minimal(self, story: Dict) -> float:
        """Check if story is concise (not verbose)"""
        story_word_count = len(story['story'].split())
        
        # Ideal user story: 15-30 words
        if 15 <= story_word_count <= 30:
            return 1.0
        elif 10 <= story_word_count <= 40:
            return 0.7
        elif story_word_count < 10:
            return 0.4  # Too brief, might be missing information
        else:
            return 0.3  # Too verbose
    
    def _check_complete(self, story: Dict) -> float:
        """Check if story has all required elements"""
        story_text = story['story'].lower()
        
        has_role = 'as a' in story_text
        has_goal = 'i want' in story_text
        has_benefit = 'so that' in story_text
        has_ac = len(story.get('acceptance_criteria', [])) >= 3
        
        completeness = sum([has_role, has_goal, has_benefit, has_ac]) / 4
        return completeness
    
    def _check_testable(self, acceptance_criteria: List[str]) -> float:
        """
        Check if acceptance criteria are testable
        Testable criteria have measurable outcomes or specific conditions
        """
        if not acceptance_criteria:
            return 0.0
        
        # Keywords indicating testability
        testable_indicators = [
            # Measurable quantities
            'second', 'minute', 'hour', 'day',
            'click', 'step', 'page',
            '%', 'percent',
            # Specific conditions
            'less than', 'greater than', 'equal to', 'within',
            'display', 'show', 'hide', 'appear',
            'success', 'fail', 'error',
            'must', 'should',
            # Verification actions
            'verify', 'confirm', 'check', 'validate'
        ]
        
        vague_indicators = [
            'good', 'better', 'nice', 'clean', 'intuitive',
            'user-friendly', 'easy', 'simple', 'fast', 'slow',
            'appropriate', 'reasonable', 'acceptable'
        ]
        
        testable_count = 0
        for criterion in acceptance_criteria:
            criterion_lower = criterion.lower()
            
            # Check for vague language (penalty)
            has_vague = any(ind in criterion_lower for ind in vague_indicators)
            
            # Check for testable indicators
            has_testable = any(ind in criterion_lower for ind in testable_indicators)
            
            # Has specific numbers
            has_numbers = bool(re.search(r'\d+', criterion))
            
            if (has_testable or has_numbers) and not has_vague:
                testable_count += 1
            elif not has_vague:
                testable_count += 0.5  # Partial credit
        
        return min(1.0, testable_count / len(acceptance_criteria))
    
    def _check_estimable(self, story: Dict) -> float:
        """Check if story points are reasonable"""
        valid_points = [1, 2, 3, 5, 8, 13]
        points = story.get('story_points', 0)
        
        if points in valid_points:
            # Additional check: Points should align with complexity
            ac_count = len(story.get('acceptance_criteria', []))
            
            # Heuristic: More ACs suggests more complexity
            if points <= 3 and ac_count <= 3:
                return 1.0
            elif points in [5, 8] and 3 <= ac_count <= 5:
                return 1.0
            elif points == 13 and ac_count >= 5:
                return 1.0
            else:
                return 0.7  # Points assigned but may not match complexity
        else:
            return 0.0
    
    def evaluate_batch(self, stories: List[Dict]) -> Tuple[Dict[str, float], List[Dict]]:
        """
        Evaluate multiple stories and return aggregate statistics
        
        Returns:
            Tuple of (aggregate_scores, individual_scores)
        """
        individual_scores = []
        
        for story in stories:
            scores = self.evaluate_story(story)
            scores['story_title'] = story['title']
            individual_scores.append(scores)
        
        # Calculate averages
        if not individual_scores:
            return {}, []
        
        aggregate = {}
        for criterion in self.qus_criteria.keys():
            if criterion in individual_scores[0]:
                aggregate[f'{criterion}_avg'] = sum(s.get(criterion, 0) for s in individual_scores) / len(individual_scores)
        
        aggregate['overall_qus_avg'] = sum(s['overall_qus'] for s in individual_scores) / len(individual_scores)
        
        return aggregate, individual_scores
    
    def print_evaluation_report(self, stories: List[Dict]):
        """Print formatted evaluation report"""
        aggregate, individual = self.evaluate_batch(stories)
        
        print("\n" + "="*70)
        print(" QUS EVALUATION REPORT")
        print("="*70 + "\n")
        
        print(f"Total Stories Evaluated: {len(stories)}\n")
        
        print("AGGREGATE SCORES:")
        print("-" * 70)
        for criterion, description in self.qus_criteria.items():
            avg_score = aggregate.get(f'{criterion}_avg', 0)
            status = '✓' if avg_score >= 0.7 else '✗'
            print(f"{criterion.replace('_', ' ').title():20} {avg_score:.2f}  {status}")
        
        print("-" * 70)
        overall_status = 'PASS ✓' if aggregate['overall_qus_avg'] >= 0.75 else 'NEEDS IMPROVEMENT ✗'
        print(f"{'OVERALL QUS SCORE':20} {aggregate['overall_qus_avg']:.2f}  {overall_status}\n")
        
        print("\nINDIVIDUAL STORY SCORES:")
        print("-" * 70)
        for i, score_dict in enumerate(individual, 1):
            print(f"\n{i}. {score_dict['story_title']}")
            print(f"   Overall: {score_dict['overall_qus']:.2f}")
            
            # Show weakest criterion
            criteria_scores = {k: v for k, v in score_dict.items() 
                             if k in self.qus_criteria.keys()}
            weakest = min(criteria_scores.items(), key=lambda x: x[1])
            if weakest[1] < 0.7:
                print(f"   ⚠️  Weakest: {weakest[0]} ({weakest[1]:.2f})")
        
        print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    # Test evaluator
    evaluator = StoryEvaluator()
    
    test_stories = [
        {
            'title': 'Streamline checkout process',
            'story': 'As a customer, I want to complete purchases in fewer steps, so that I can checkout quickly',
            'acceptance_criteria': [
                'Checkout reduces from 5 to 3 steps',
                'Payment info can be saved',
                'Confirmation displays within 2 seconds'
            ],
            'story_points': 5
        },
        {
            'title': 'Improve performance',
            'story': 'As a user, I want the system to be faster, so that I have a better experience',
            'acceptance_criteria': [
                'System loads quickly',
                'Pages are responsive'
            ],
            'story_points': 8
        }
    ]
    
    print("\n=== QUS Evaluation Demo ===")
    evaluator.print_evaluation_report(test_stories)