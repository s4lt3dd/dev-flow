"""
DevFlow AI Prototype Demo
Demonstrates multi-model pipeline with test data
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.sentiment_analyzer import SentimentAnalyzer
from src.story_generator import StoryGenerator
from src.pipeline import MultiModelPipeline
from src.evaluation import StoryEvaluator
from src.advanced_priority_detector import RobustPriorityDetector


def load_test_data():
    """Load test transcripts"""
    data_path = Path(__file__).parent / 'data' / 'test_transcripts.json'
    
    if not data_path.exists():
        print(f"Error: Test data not found at {data_path}")
        return None
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    return data['transcripts']


def demo_sentiment_analysis():
    """Demonstrate basic single-model sentiment analysis (baseline)"""
    print("\n" + "="*80)
    print(" DEMO 1: BASIC SENTIMENT ANALYSIS (single-model baseline)")
    print("="*80 + "\n")
    
    analyzer = SentimentAnalyzer()
    
    test_cases = [
        ("HIGH PRIORITY", "Users are frustrated with checkout. We're losing customers daily!"),
        ("MEDIUM PRIORITY", "We should add export to PDF. A few clients asked about it."),
        ("LOW PRIORITY", "It would be nice to have dark mode eventually.")
    ]
    
    for label, text in test_cases:
        print(f"Expected: {label}")
        print(f"Text: {text}")
        
        result = analyzer.analyze_segment(text)
        
        print(f"→ Detected: {result['priority_label']} (confidence: {result['priority_score']:.2f})")
        print(f"  Sentiment: Negative={result['negative']:.2f}, "
              f"Neutral={result['neutral']:.2f}, Positive={result['positive']:.2f}")
        print()


def demo_advanced_priority():
    """
    Side-by-side comparison: SentimentAnalyzer vs RobustPriorityDetector.

    The three cases expose the core limitation of emotion-only detection:
    medium-priority items are often phrased professionally (no emotional charge),
    so the basic analyzer mislabels them as Low.
    """
    print("\n" + "="*80)
    print(" DEMO 2: ADVANCED PRIORITY DETECTION (MULTI-SIGNAL)")
    print("="*80)
    print("\nProblem: SentimentAnalyzer uses emotion intensity as a proxy for priority.")
    print("         Professionally-worded requests score 'neutral' → mislabelled Low.")
    print("Solution: RobustPriorityDetector fuses 4 signals:")
    print("          sentiment ensemble · keyword database · topic classifier · linguistic patterns\n")

    test_cases = [
        (
            "HIGH",
            "Users are losing data every day. This is a critical security vulnerability "
            "blocking all revenue operations.",
        ),
        (
            "MEDIUM",  # The hard case — neutral tone, but strategically important
            "Enterprise clients have requested PDF export. "
            "It's been on the roadmap and multiple clients depend on it.",
        ),
        (
            "LOW",
            "It would be nice to have dark mode eventually if we have time. "
            "Very minor cosmetic thing.",
        ),
    ]

    basic = SentimentAnalyzer()
    advanced = RobustPriorityDetector()

    for expected, text in test_cases:
        print(f"Expected : {expected}")
        print(f"Text     : {text}")

        basic_result = basic.analyze_segment(text)
        adv_result = advanced.analyze_priority(text)

        basic_match = "✓" if basic_result['priority_label'] == expected else "✗"
        adv_match = "✓" if adv_result['priority_label'] == expected else "✗"

        print(f"  Basic (SentimentAnalyzer)  : {basic_match} {basic_result['priority_label']}"
              f"  (score: {basic_result['priority_score']:.2f})")
        print(f"  Advanced (RobustDetector)  : {adv_match} {adv_result['priority_label']}"
              f"  (score: {adv_result['priority_score']:.2f},"
              f" confidence: {adv_result['confidence']:.2f})")

        bd = adv_result['signal_breakdown']
        dampened_tag = " [DAMPENED -> {:.2f}]".format(bd['effective_sentiment']) if bd.get('sentiment_dampened') else ""
        print(f"    Signal breakdown ->"
              f" sentiment: {bd['sentiment_ensemble']:.2f}{dampened_tag}"
              f" | keywords: {bd['keyword_score']:.2f}"
              f" | topic: {bd['topic_score']:.2f}"
              f" | linguistic: {bd['linguistic_score']:.2f}")
        print(f"    Explanation: {adv_result['explanation']}")
        print()


def demo_context_aware_priority():
    """Show how speaker role and repetition shift the priority score."""
    print("\n" + "="*80)
    print(" DEMO 3: CONTEXT-AWARE PRIORITY SIGNALS")
    print("="*80)
    print("\nThe same requirement can carry different weight depending on")
    print("WHO raised it and HOW MANY TIMES it has been mentioned.\n")

    detector = RobustPriorityDetector()

    requirement = (
        "We should add single sign-on support. "
        "It would help enterprise clients get onboarded faster."
    )

    print(f"Requirement: {requirement}\n")

    contexts = [
        (None,                                           "No context (text only)"),
        ({'speaker_role': 'Developer'},                  "Speaker: Developer"),
        ({'speaker_role': 'Product Manager'},            "Speaker: Product Manager"),
        ({'speaker_role': 'CEO'},                        "Speaker: CEO"),
        ({'speaker_role': 'CEO', 'repetition_count': 3}, "Speaker: CEO  +  mentioned 3× this sprint"),
        ({'speaker_role': 'CEO', 'repetition_count': 3,
          'relates_to_okr': True},                       "Speaker: CEO  +  3×  +  tied to OKR"),
    ]

    base = detector.analyze_priority(requirement, context=None)
    print(f"{'Context':<45} {'Label':<8} {'Score':>6}  {'Δ score':>8}")
    print("-" * 72)
    for ctx, label in contexts:
        result = detector.analyze_priority(requirement, context=ctx)
        delta = result['priority_score'] - base['priority_score']
        delta_str = f"{delta:+.2f}" if ctx else "  base"
        print(f"  {label:<43} {result['priority_label']:<8} {result['priority_score']:>6.2f}  {delta_str:>8}")
    print()


def demo_story_generation():
    """Demonstrate story generation"""
    print("\n" + "="*80)
    print(" DEMO 4: USER STORY GENERATION")
    print("="*80 + "\n")
    
    generator = StoryGenerator()
    
    requirement = "Users are frustrated with the checkout process taking too long. We need to streamline it to 3 clicks maximum."
    sentiment = {
        'negative': 0.75,
        'neutral': 0.15,
        'positive': 0.10,
        'priority_score': 0.85
    }
    
    print("Input Requirement:")
    print(f"  {requirement}")
    print(f"\nSentiment Context:")
    print(f"  Priority Score: {sentiment['priority_score']:.2f} (High)")
    print(f"\nGenerating story...\n")
    
    story = generator.generate_story(
        requirement=requirement,
        priority="High",
        sentiment_context=sentiment,
        project_context="E-commerce Platform"
    )
    
    print("Generated User Story:")
    print(f"  Title: {story['title']}")
    print(f"  Priority: {story['priority']} (confidence: {story['priority_confidence']:.2f})")
    print(f"  Story Points: {story['story_points']}")
    print(f"\n  Story:")
    print(f"    {story['story']}")
    print(f"\n  Acceptance Criteria:")
    for i, ac in enumerate(story['acceptance_criteria'], 1):
        print(f"    {i}. {ac}")
    print()


def demo_full_pipeline():
    """Demonstrate complete multi-model pipeline with advanced priority detection"""
    print("\n" + "="*80)
    print(" DEMO 5: COMPLETE PIPELINE  (use_advanced_detector=True)")
    print("="*80 + "\n")

    transcripts = load_test_data()
    if not transcripts:
        print("Cannot run demo - test data not found")
        return

    # Advanced detector is now the default
    pipeline = MultiModelPipeline(use_advanced_detector=True)

    for i, transcript_data in enumerate(transcripts[:3], 1):
        print(f"\n--- Transcript {i}: {transcript_data['context']} ---")
        print(f"Expected Priority : {transcript_data['expert_priority']}")
        print(f"Transcript        : {transcript_data['text'][:150]}...")
        print()

        stories = pipeline.process_transcript(
            transcript=transcript_data['text'],
            project_context=transcript_data['context']
        )

        if stories:
            story = stories[0]
            match = "✓ MATCH" if story['priority'] == transcript_data['expert_priority'] else "✗ MISMATCH"
            print(f"  Title     : {story['title']}")
            print(f"  Priority  : {story['priority']}  {match}")
            print(f"  Confidence: {story.get('priority_detector_confidence', story['priority_confidence']):.2f}")
            print(f"  Story     : {story['story']}")

            if 'priority_explanation' in story:
                print(f"  Rationale : {story['priority_explanation']}")

            if 'priority_signal_breakdown' in story:
                bd = story['priority_signal_breakdown']
                dampened_tag = " [DAMPENED -> {:.2f}]".format(bd['effective_sentiment']) if bd.get('sentiment_dampened') else ""
                print(f"  Signals   : sentiment={bd['sentiment_ensemble']:.2f}{dampened_tag}"
                      f"  keywords={bd['keyword_score']:.2f}"
                      f"  topic={bd['topic_score']:.2f}"
                      f"  linguistic={bd['linguistic_score']:.2f}")

        print("\n" + "-"*80)


def demo_jira_export():
    """Generate one story and push it to Jira using credentials from .env"""
    print("\n" + "="*80)
    print(" DEMO 7: JIRA EXPORT")
    print("="*80 + "\n")

    print("Creating pipeline with Jira enabled (reads .env for credentials)...")
    try:
        pipeline = MultiModelPipeline.create(enable_jira=True)
    except EnvironmentError as e:
        print(f"  ✗ Could not load Jira config:\n  {e}")
        return

    requirement = (
        "API timing out for a large dataset when doing geocoding. "
        "This is a critical issue affecting hundreds of clients and users daily"
    )
    print(f"Requirement: {requirement}\n")
    print("Generating story...")

    stories = pipeline.process_requirements_list(
        requirements=[requirement],
        project_context="DevFlow AI Demo"
    )

    if not stories:
        print("  ✗ Story generation failed — cannot export.")
        return

    story = stories[0]
    print(f"  Title   : {story['title']}")
    print(f"  Priority: {story['priority']}")
    print(f"  Points  : {story['story_points']}")
    print("\nExporting to Jira...")

    try:
        result = pipeline.jira_exporter.export_story(story)
        print(f"  ✓ Created {result['jira_key']}: {result['jira_url']}")
    except Exception as e:
        print(f"  ✗ Jira export failed: {e}")


def demo_qus_pipeline(runs: int = 2):
    """
    Run the full pipeline on all test transcripts and evaluate with QUS.

    Processes every transcript in data/test_transcripts.json, collects the
    generated stories, and prints a QUS evaluation report.  Repeating the
    same run across multiple executions should yield a consistent story count
    because requirement extraction is deterministic (regex heuristics) — only
    the LLM story text varies.

    Args:
        runs: Number of independent pipeline executions to perform.
    """
    print("\n" + "="*80)
    print(" DEMO 8: FULL PIPELINE + QUS EVALUATION (ALL TRANSCRIPTS)")
    print("="*80 + "\n")

    transcripts = load_test_data()
    if not transcripts:
        print("Cannot run demo - test data not found")
        return

    pipeline = MultiModelPipeline(use_advanced_detector=True)
    evaluator = StoryEvaluator()

    for run in range(1, runs + 1):
        print(f"\n{'─'*80}")
        print(f" Run {run}/{runs}")
        print(f"{'─'*80}")

        all_stories = []

        for t in transcripts:
            stories = pipeline.process_transcript(
                transcript=t['text'],
                project_context=t['context']
            )
            print(f"  {t['id']} ({t['context']}): {len(stories)} story/stories")
            all_stories.extend(stories)

        print(f"\n  Total stories generated: {len(all_stories)}")
        evaluator.print_evaluation_report(all_stories)


def demo_evaluation():
    """Demonstrate quality evaluation"""
    print("\n" + "="*80)
    print(" DEMO 6: QUALITY EVALUATION (QUS FRAMEWORK)")
    print("="*80 + "\n")

    # Create sample stories for evaluation
    stories = [
        {
            'title': 'Streamline checkout process',
            'story': 'As a customer, I want to complete purchases in fewer steps, so that I can checkout quickly without frustration',
            'acceptance_criteria': [
                'Checkout process reduces from 5 steps to 3 steps maximum',
                'Payment information can be saved for future purchases',
                'Order confirmation displayed within 2 seconds of final submission',
                'Error messages appear clearly if payment fails'
            ],
            'story_points': 5
        },
        {
            'title': 'Add dark mode toggle',
            'story': 'As a user, I want to enable dark mode, so that I can reduce eye strain during evening use',
            'acceptance_criteria': [
                'Toggle switch appears in settings menu',
                'Dark mode applies consistently across all screens',
                'User preference persists between sessions'
            ],
            'story_points': 3
        },
        {
            'title': 'Improve system performance',
            'story': 'As a user, I want the system to be faster, so that I have a better experience',
            'acceptance_criteria': [
                'System loads quickly',
                'Pages are responsive'
            ],
            'story_points': 8
        }
    ]
    
    evaluator = StoryEvaluator()
    evaluator.print_evaluation_report(stories)


def main():
    """Run all demos"""
    print()
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "DevFlow AI - Feature Prototype Demo" + " "*23 + "║")
    print("║" + " "*15 + "Multi-Model Requirements Automation" + " "*28 + "║")
    print("╚" + "="*78 + "╝")
    
    print("\nThis demo showcases:")
    print("  1. Basic Sentiment Analysis (single-model baseline)")
    print("  2. Advanced Priority Detection — multi-signal vs basic, side-by-side")
    print("  3. Context-Aware Priority  — speaker role, repetition, OKR signals")
    print("  4. LLM-based User Story Generation (with enriched priority metadata)")
    print("  5. Complete Pipeline  (use_advanced_detector=True, enriched story output)")
    print("  6. Quality Evaluation using QUS Framework")
    print("  7. Jira Export  (generates one story and pushes it to your Jira project)")
    print("  8. Full Pipeline + QUS Evaluation (all transcripts, N runs)")

    input("\nPress Enter to start Demo 1...")
    demo_sentiment_analysis()

    input("\nPress Enter to start Demo 2...")
    demo_advanced_priority()

    input("\nPress Enter to start Demo 3...")
    demo_context_aware_priority()

    input("\nPress Enter to start Demo 4...")
    demo_story_generation()

    input("\nPress Enter to start Demo 5...")
    demo_full_pipeline()

    input("\nPress Enter to start Demo 6...")
    demo_evaluation()

    input("\nPress Enter to start Demo 7 (Jira export)...")
    demo_jira_export()

    input("\nPress Enter to start Demo 8 (Full pipeline + QUS evaluation)...")
    demo_qus_pipeline(runs=2)

    print("\n" + "="*80)
    print(" DEMO COMPLETE")
    print("="*80)
    print("\nTo test with your own data:")
    print("  python -m src.pipeline")
    print("\nTo run tests:")
    print("  pytest tests/test_pipeline.py -v")
    print()


if __name__ == "__main__":
    main()