"""
Multi-Model Pipeline Orchestrator
Coordinates sentiment analysis and story generation
"""

import json
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

from sentiment_analyzer import SentimentAnalyzer
from story_generator import StoryGenerator
from advanced_priority_detector import RobustPriorityDetector
from jira_exporter import JiraExporter
from config import get_jira_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MultiModelPipeline:
    """Orchestrator for multi-model requirements automation"""

    def __init__(self,
                 sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest",
                 story_model: str = "llama3.2:3b",
                 use_advanced_detector: bool = True,
                 jira_exporter: Optional[JiraExporter] = None,
                 transcriber=None):
        """
        Initialize pipeline with model specifications

        Args:
            sentiment_model: HuggingFace model for sentiment analysis
            story_model: Ollama model for story generation
            use_advanced_detector: Use multi-signal RobustPriorityDetector instead of
                                   the single-model SentimentAnalyzer
            jira_exporter: Optional JiraExporter instance
            transcriber: Optional AudioTranscriber instance for audio input
        """
        logger.info("Initializing Multi-Model Pipeline...")
        logger.info(f"Story Generation Model: {story_model}")

        if use_advanced_detector:
            logger.info("Priority detection: RobustPriorityDetector (ensemble + keywords + topic)")
            self.priority_detector = RobustPriorityDetector()
            self.sentiment_analyzer = None
        else:
            logger.info(f"Priority detection: SentimentAnalyzer ({sentiment_model})")
            self.sentiment_analyzer = SentimentAnalyzer(model_name=sentiment_model)
            self.priority_detector = None

        self.story_generator = StoryGenerator(model_name=story_model)
        self.jira_exporter = jira_exporter
        self.transcriber = transcriber

        if jira_exporter:
            logger.info("Jira export enabled")
        if transcriber:
            logger.info("Audio transcriber ready")
        logger.info("Pipeline ready")

    @classmethod
    def create(cls,
               use_advanced_detector: bool = True,
               enable_jira: bool = False,
               load_transcriber: bool = True) -> "MultiModelPipeline":
        """
        Preferred entry point. Wires credentials and optional integrations
        so callers don't need to import config or JiraExporter directly.
        """
        exporter = None
        if enable_jira:
            config = get_jira_config()
            exporter = JiraExporter(**config)

        transcriber = None
        if load_transcriber:
            from transcriber import AudioTranscriber
            transcriber = AudioTranscriber()

        return cls(
            use_advanced_detector=use_advanced_detector,
            jira_exporter=exporter,
            transcriber=transcriber,
        )

    def _analyze_priority(self, text: str, context: Dict = None) -> Dict[str, Any]:
        """
        Route priority analysis to the active detector and normalize output.
        """
        if self.priority_detector:
            result = self.priority_detector.analyze_priority(text, context)
            result.setdefault('negative', 0.0)
            result.setdefault('neutral', 0.0)
            result.setdefault('positive', 0.0)
            return result
        return self.sentiment_analyzer.analyze_segment(text)

    def _process_requirement(self, req_text: str, project_context: str) -> Dict[str, Any]:
        """
        Run the full pipeline for a single requirement text:
        priority analysis → story generation → Jira export.

        Jira errors (requests.HTTPError) are not swallowed — they propagate
        so callers can surface them to the user.
        """
        sentiment = self._analyze_priority(req_text)
        logger.info(
            f"Priority: {sentiment['priority_label']} "
            f"(score: {sentiment['priority_score']:.2f}"
            + (f", confidence: {sentiment['confidence']:.2f}" if 'confidence' in sentiment else "")
            + ")"
        )

        story = self.story_generator.generate_story(
            requirement=req_text,
            priority=sentiment['priority_label'],
            sentiment_context=sentiment,
            project_context=project_context,
        )
        logger.info(f"Story generated: '{story['title']}'")

        if self.jira_exporter:
            jira = self.jira_exporter.export_story(story)  # raises HTTPError on failure
            story['jira_key'] = jira['jira_key']
            story['jira_url'] = jira['jira_url']

        return story

    def process_transcript(self,
                           transcript: str,
                           project_context: str = "Software development project") -> List[Dict[str, Any]]:
        """
        Process meeting transcript into user stories.

        Args:
            transcript: Raw transcript text
            project_context: Project information for context

        Returns:
            List of generated user stories with metadata
        """
        logger.info(f"Processing transcript ({len(transcript)} chars)...")

        requirements = self._extract_requirements(transcript)
        logger.info(f"Extracted {len(requirements)} requirements")

        stories = []
        for i, req in enumerate(requirements, 1):
            logger.info(f"\n--- Processing requirement {i}/{len(requirements)} ---")
            logger.info(f"Text: {req['text'][:80]}...")
            try:
                story = self._process_requirement(req['text'], project_context)
                stories.append(story)
            except requests.HTTPError:
                raise  # Jira failures propagate to the caller
            except Exception as e:
                logger.error(f"Failed to process requirement: {e}")
                continue

        logger.info(f"\n=== Pipeline Complete: {len(stories)}/{len(requirements)} stories generated ===")
        return stories

    def process_requirements_list(self,
                                  requirements: List[str],
                                  project_context: str = "Software development project") -> List[Dict[str, Any]]:
        """
        Process a list of pre-extracted requirement strings.
        """
        logger.info(f"Processing {len(requirements)} requirements...")

        stories = []
        for i, req_text in enumerate(requirements, 1):
            logger.info(f"\n--- Requirement {i}/{len(requirements)} ---")
            logger.info(f"Text: {req_text[:80]}...")
            try:
                story = self._process_requirement(req_text, project_context)
                stories.append(story)
            except requests.HTTPError:
                raise
            except Exception as e:
                logger.error(f"Failed: {e}")
                continue

        return stories

    def process_audio_file(self,
                           audio_path: str,
                           project_context: str = "Software development project") -> List[Dict[str, Any]]:
        """
        Transcribe an audio file then run the full pipeline on the transcript.

        Args:
            audio_path: Path to audio file (wav, mp3, webm, etc.)
            project_context: Project information for context

        Returns:
            List of generated user stories with metadata
        """
        if self.transcriber is None:
            raise RuntimeError("No transcriber configured. Use MultiModelPipeline.create(load_transcriber=True).")

        logger.info(f"Transcribing {audio_path}...")
        result = self.transcriber.transcribe_audio(audio_path)
        transcript = result['text']
        logger.info(f"Transcript ({len(transcript)} chars): {transcript[:120]}...")

        return self.process_transcript(transcript, project_context)

    def _extract_requirements(self, transcript: str) -> List[Dict[str, str]]:
        """
        Extract requirements from transcript using heuristics.
        """
        indicators = [
            "we need to",
            "we need",
            "need this",
            "we should",
            "it would be good to",
            "it would be nice to",
            "customers are asking for",
            "users want",
            "users need",
            "the issue is",
            "the problem is",
            "is broken",
            "is not working",
            "isn't working",
            "doesn't work",
            "not working",
            "broken in",
            "users complain about",
            "customers mention",
            "we have to",
            "let's add",
            "can we",
            "frustrated with",
            "annoying that",
            "need to fix",
            "needs to be fixed",
            "fixed immediately",
            "as soon as possible",
            "asap"
        ]

        requirements = []
        sentences = transcript.replace('!', '.').replace('?', '.').split('.')
        current_requirement = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            is_requirement = any(indicator in sentence.lower() for indicator in indicators)

            if is_requirement:
                if current_requirement:
                    req_text = ' '.join(current_requirement)
                    if len(req_text.split()) > 5:
                        requirements.append({'text': req_text, 'type': 'requirement'})
                current_requirement = [sentence]
            elif current_requirement:
                current_requirement.append(sentence)

        if current_requirement:
            req_text = ' '.join(current_requirement)
            if len(req_text.split()) > 5:
                requirements.append({'text': req_text, 'type': 'requirement'})

        return requirements

    def save_results(self, stories: List[Dict[str, Any]], output_path: str):
        """Save generated stories to JSON file"""
        output_data = {
            'generation_date': datetime.now().isoformat(),
            'total_stories': len(stories),
            'priority_model': (
                'RobustPriorityDetector' if self.priority_detector
                else self.sentiment_analyzer.model_name
            ),
            'story_model': self.story_generator.model_name,
            'stories': stories
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        logger.info(f"Results saved to {output_path}")


if __name__ == "__main__":
    pipeline = MultiModelPipeline.create(enable_jira=False, load_transcriber=False)

    test_transcript = """
    Product Manager: We need to address the checkout flow. Users are really frustrated with how long it takes.
    Developer: How many steps are we talking about?
    Product Manager: Currently it's 5 clicks from cart to confirmation. Customers are complaining that it's causing them to abandon purchases. This is critical for revenue.
    Scrum Master: Anything else high priority?
    Product Manager: Yes, we should also add dark mode eventually. It's been requested a few times, but it's not urgent. Nice to have.
    Developer: What about the login button color?
    Product Manager: Oh that's just cosmetic. We can look at it when we have time. Known issue but very minor.
    """

    print("\n=== Multi-Model Pipeline Demo ===\n")
    stories = pipeline.process_transcript(
        transcript=test_transcript,
        project_context="E-commerce Platform - Sprint 23"
    )

    print("\n\n=== Generated Stories ===\n")
    for i, story in enumerate(stories, 1):
        print(f"\n--- Story {i} ---")
        print(f"Title: {story['title']}")
        print(f"Priority: {story['priority']} (confidence: {story['priority_confidence']:.2f})")
        print(f"Story: {story['story']}")
        print(f"Acceptance Criteria:")
        for ac in story['acceptance_criteria']:
            print(f"  - {ac}")
        print(f"Story Points: {story['story_points']}")