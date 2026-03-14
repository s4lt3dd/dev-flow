"""
Integration tests for multi-model pipeline
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from sentiment_analyzer import SentimentAnalyzer
from story_generator import StoryGenerator
from pipeline import MultiModelPipeline
from evaluation import StoryEvaluator
from advanced_priority_detector import RobustPriorityDetector


class TestSentimentAnalyzer:
    """Test sentiment analysis functionality"""
    
    @pytest.fixture
    def analyzer(self):
        return SentimentAnalyzer()
    
    def test_high_priority_detection(self, analyzer):
        """Test detection of high-priority requirements"""
        text = "Users are frustrated and we're losing customers daily. This is critical!"
        result = analyzer.analyze_segment(text)
        
        assert result['priority_label'] == 'High'
        assert result['priority_score'] > 0.7
    
    def test_low_priority_detection(self, analyzer):
        """Test detection of low-priority requirements"""
        text = "It would be nice to have this eventually when we have time."
        result = analyzer.analyze_segment(text)
        
        assert result['priority_label'] == 'Low'
        assert result['priority_score'] < 0.4
    
    def test_phrase_adjustment(self, analyzer):
        """Test domain-specific phrase adjustments"""
        text_with_boost = "We're losing customers and this is blocking revenue"
        text_without = "This feature would be good to add"
        
        result_boosted = analyzer.analyze_segment(text_with_boost)
        result_normal = analyzer.analyze_segment(text_without)
        
        assert result_boosted['priority_score'] > result_normal['priority_score']


class TestStoryGenerator:
    """Test story generation functionality"""
    
    @pytest.fixture
    def generator(self):
        return StoryGenerator()
    
    def test_story_generation_structure(self, generator):
        """Test that generated stories have required fields"""
        requirement = "Users need faster checkout to reduce cart abandonment"
        sentiment = {
            'negative': 0.7,
            'neutral': 0.2,
            'positive': 0.1,
            'priority_score': 0.8
        }
        
        story = generator.generate_story(
            requirement=requirement,
            priority="High",
            sentiment_context=sentiment,
            project_context="E-commerce platform"
        )
        
        # Check required fields
        assert 'title' in story
        assert 'story' in story
        assert 'acceptance_criteria' in story
        assert 'story_points' in story
        assert 'priority' in story
        
        # Check field types
        assert isinstance(story['title'], str)
        assert isinstance(story['story'], str)
        assert isinstance(story['acceptance_criteria'], list)
        assert isinstance(story['story_points'], int)
    
    def test_story_format(self, generator):
        """Test that stories follow proper format"""
        requirement = "Add dark mode for better user experience"
        sentiment = {
            'negative': 0.2,
            'neutral': 0.3,
            'positive': 0.5,
            'priority_score': 0.4
        }
        
        story = generator.generate_story(
            requirement=requirement,
            priority="Medium",
            sentiment_context=sentiment,
            project_context="Mobile app"
        )
        
        # Check story format
        assert story['story'].lower().startswith('as a')
        assert 'i want' in story['story'].lower()
        assert len(story['acceptance_criteria']) >= 3


class TestMultiModelPipeline:
    """Test full pipeline integration"""

    @pytest.fixture
    def pipeline(self):
        # use_advanced_detector=False keeps this fixture fast (1 model, not 4)
        return MultiModelPipeline(use_advanced_detector=False)
    
    def test_requirements_extraction(self, pipeline):
        """Test extraction of requirements from transcript"""
        transcript = """
        We need to improve the search function. Users can't find products.
        Also, it would be nice to add filters eventually.
        """
        
        requirements = pipeline._extract_requirements(transcript)
        
        assert len(requirements) > 0
        assert all('text' in req for req in requirements)
    
    def test_end_to_end_processing(self, pipeline):
        """Test complete pipeline from transcript to stories"""
        transcript = "We need to fix the broken checkout. Users are frustrated and leaving."
        
        stories = pipeline.process_transcript(
            transcript=transcript,
            project_context="E-commerce"
        )
        
        assert len(stories) > 0
        
        # Check first story structure
        story = stories[0]
        assert 'title' in story
        assert 'priority' in story
        assert 'story' in story
        assert 'acceptance_criteria' in story


class TestStoryEvaluator:
    """Test story quality evaluation"""
    
    @pytest.fixture
    def evaluator(self):
        return StoryEvaluator()
    
    def test_well_formed_detection(self, evaluator):
        """Test detection of well-formed stories"""
        good_story = "As a user, I want to login quickly, so that I can access my account"
        bad_story = "Make the login faster"
        
        score_good = evaluator._check_well_formed(good_story)
        score_bad = evaluator._check_well_formed(bad_story)
        
        assert score_good == 1.0
        assert score_bad < 1.0
    
    def test_testability_check(self, evaluator):
        """Test detection of testable acceptance criteria"""
        testable_ac = [
            "Login completes in under 2 seconds",
            "Success rate is 99.5% or higher",
            "Error messages display within 1 second"
        ]
        
        vague_ac = [
            "System should be fast",
            "Users should have a good experience"
        ]
        
        score_testable = evaluator._check_testable(testable_ac)
        score_vague = evaluator._check_testable(vague_ac)
        
        assert score_testable > score_vague
    
    def test_full_evaluation(self, evaluator):
        """Test complete story evaluation"""
        story = {
            'title': 'Streamline checkout',
            'story': 'As a customer, I want to checkout in 3 clicks, so that I can complete purchases quickly',
            'acceptance_criteria': [
                'Checkout reduces from 5 to 3 steps',
                'Payment info can be saved for future purchases',
                'Order confirmation displays within 2 seconds'
            ],
            'story_points': 5
        }
        
        scores = evaluator.evaluate_story(story)
        
        assert 'overall_qus' in scores
        assert 0 <= scores['overall_qus'] <= 1
        assert scores['well_formed'] >= 0.9
        assert scores['testable'] >= 0.5


class TestRobustPriorityDetector:
    """
    Tests for the multi-signal priority detector.

    Fast tests (no marker): exercise pure-Python signal methods by patching
    the expensive model-loading helpers so the fixture is instant.

    Slow tests (@pytest.mark.slow): load real models and run end-to-end.
    Run with:  pytest -m slow
    Skip with: pytest -m "not slow"   (default CI behaviour)
    """

    @pytest.fixture
    def detector(self):
        """Lightweight detector with model loaders stubbed out."""
        with patch.object(RobustPriorityDetector, '_init_sentiment_ensemble', return_value=None), \
             patch.object(RobustPriorityDetector, '_init_topic_classifier', return_value=None):
            d = RobustPriorityDetector()
            # Provide a stub topic_classifier so _topic_analysis doesn't blow up
            # in any test that accidentally calls it.
            d.topic_classifier = MagicMock(return_value={
                'labels': ['core functionality'], 'scores': [0.9]
            })
            return d

    # ------------------------------------------------------------------
    # Keyword signal (pure Python, instant)
    # ------------------------------------------------------------------

    def test_keyword_high_priority_terms(self, detector):
        score = detector._keyword_analysis("This is a critical security vulnerability blocking revenue")
        assert score > 0.7, "Strong high-priority keywords should push score above 0.7"

    def test_keyword_low_priority_terms(self, detector):
        score = detector._keyword_analysis("It would be nice to have this someday if we have time")
        assert score < 0.4, "Low-priority phrasing should push score below 0.4"

    def test_keyword_medium_priority_terms(self, detector):
        score = detector._keyword_analysis("Clients have requested PDF export to improve workflow efficiency")
        assert 0.4 <= score <= 0.8, "Medium signals should land in the middle band"

    def test_keyword_score_clamped(self, detector):
        # Many high-priority keywords in one sentence — score must not exceed 1.0
        text = "critical urgent revenue blocking asap immediately data breach lawsuit"
        score = detector._keyword_analysis(text)
        assert 0.0 <= score <= 1.0

    # ------------------------------------------------------------------
    # Linguistic signal (pure Python, instant)
    # ------------------------------------------------------------------

    def test_linguistic_urgency_patterns(self, detector):
        score = detector._linguistic_analysis("We must fix this immediately, it is breaking every day!")
        assert score > 0.5, "Obligation + time-pressure patterns should raise score"

    def test_linguistic_low_priority_patterns(self, detector):
        score = detector._linguistic_analysis("We could perhaps consider this eventually in the long-term")
        assert score < 0.5, "Hedging/distant-timeframe patterns should lower score"

    def test_linguistic_short_text_penalty(self, detector):
        short_score = detector._linguistic_analysis("Fix it")
        normal_score = detector._linguistic_analysis("We need to fix the checkout flow for all users")
        assert short_score <= normal_score, "Very short text should not outscore normal text"

    # ------------------------------------------------------------------
    # Context adjustment (pure Python, instant)
    # ------------------------------------------------------------------

    def test_context_ceo_weight(self, detector):
        base = 0.6
        adjusted = detector._apply_context(base, {'speaker_role': 'CEO'})
        assert adjusted > base, "CEO speaker should increase priority score"

    def test_context_repetition_boost(self, detector):
        base = 0.5
        adjusted = detector._apply_context(base, {'repetition_count': 3})
        assert adjusted > base, "Repeated mentions should boost priority"

    def test_context_okr_boost(self, detector):
        base = 0.5
        adjusted = detector._apply_context(base, {'relates_to_okr': True})
        assert adjusted > base, "OKR-linked items should boost priority"

    def test_context_score_clamped_at_one(self, detector):
        score = detector._apply_context(0.95, {'speaker_role': 'CEO', 'relates_to_okr': True, 'repetition_count': 5})
        assert score <= 1.0

    # ------------------------------------------------------------------
    # Pipeline routing (_analyze_priority dispatch)
    # ------------------------------------------------------------------

    def test_pipeline_routes_to_advanced_detector(self):
        """_analyze_priority should call RobustPriorityDetector when enabled."""
        with patch.object(RobustPriorityDetector, '_init_sentiment_ensemble', return_value=None), \
             patch.object(RobustPriorityDetector, '_init_topic_classifier', return_value=None):
            pipeline = MultiModelPipeline(use_advanced_detector=True)
            pipeline.priority_detector.analyze_priority = MagicMock(return_value={
                'priority_label': 'High',
                'priority_score': 0.85,
                'confidence': 0.9,
                'signal_breakdown': {},
                'explanation': 'Test explanation',
            })

            result = pipeline._analyze_priority("We are losing customers due to broken checkout")

            pipeline.priority_detector.analyze_priority.assert_called_once()
            assert result['priority_label'] == 'High'
            # Defaults injected for story_generator compatibility
            assert 'negative' in result
            assert 'neutral' in result
            assert 'positive' in result

    def test_pipeline_routes_to_basic_analyzer(self):
        """_analyze_priority should call SentimentAnalyzer when advanced is off."""
        pipeline = MultiModelPipeline(use_advanced_detector=False)
        pipeline.sentiment_analyzer.analyze_segment = MagicMock(return_value={
            'priority_label': 'Low',
            'priority_score': 0.2,
            'negative': 0.1,
            'neutral': 0.8,
            'positive': 0.1,
        })

        result = pipeline._analyze_priority("Nice to have eventually")

        pipeline.sentiment_analyzer.analyze_segment.assert_called_once()
        assert result['priority_label'] == 'Low'

    # ------------------------------------------------------------------
    # Slow / full-model tests (skipped by default)
    # ------------------------------------------------------------------

    @pytest.mark.slow
    def test_full_analyze_priority_high(self):
        detector = RobustPriorityDetector()
        result = detector.analyze_priority(
            "Users are losing data daily. This is a critical security vulnerability blocking all operations."
        )
        assert result['priority_label'] == 'High'
        assert 'signal_breakdown' in result
        assert 'explanation' in result
        # Sentinel should NOT fire — keyword and linguistic are both high here
        assert not result['signal_breakdown']['sentiment_dampened']

    @pytest.mark.slow
    def test_full_analyze_priority_low(self):
        detector = RobustPriorityDetector()
        result = detector.analyze_priority(
            "It would be nice to have dark mode someday if we have time."
        )
        assert result['priority_label'] == 'Low'

    @pytest.mark.slow
    def test_full_analyze_priority_medium(self):
        """The hardest case: professionally-worded strategic request."""
        detector = RobustPriorityDetector()
        result = detector.analyze_priority(
            "Enterprise clients have requested PDF export. It's on the roadmap for next quarter."
        )
        assert result['priority_label'] == 'Medium'


if __name__ == "__main__":
    pytest.main([__file__, '-v'])