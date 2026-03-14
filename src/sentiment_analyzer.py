"""
Stage 2: Sentiment Analysis for Priority Detection
Uses HuggingFace transformers to analyze emotional signals in requirements
"""

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Analyze transcript sentiment to detect priority signals"""
    
    def __init__(self, model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"):
        """
        Initialize sentiment analyzer
        
        Args:
            model_name: HuggingFace model identifier
        """
        logger.info(f"Loading sentiment model: {model_name}")
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        
        # Domain-specific priority indicators
        self.high_priority_phrases = [
            "losing customers", "revenue impact", "critical", "urgent",
            "blocking", "can't", "broken", "frustrated", "angry",
            "complaining", "immediately", "asap"
        ]
        
        self.low_priority_phrases = [
            "nice to have", "eventually", "when we have time",
            "known issue", "minor", "cosmetic", "optional"
        ]
        
        logger.info("Sentiment analyzer ready")
    
    def analyze_segment(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of a text segment
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary with sentiment scores and priority
        """
        # Tokenize and get model predictions
        inputs = self.tokenizer(
            text, 
            return_tensors="pt", 
            truncation=True, 
            max_length=512,
            padding=True
        )
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            scores = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # Extract scores (negative, neutral, positive)
        negative_score = scores[0][0].item()
        neutral_score = scores[0][1].item()
        positive_score = scores[0][2].item()
        
        # Calculate base priority score
        # High negative OR high positive = more urgent (emotional intensity)
        # Neutral = less urgent (informational discussion)
        base_priority = max(negative_score, positive_score)
        
        # Apply domain-specific adjustments
        adjusted_priority = self._adjust_priority_with_phrases(text, base_priority)
        
        return {
            'negative': negative_score,
            'neutral': neutral_score,
            'positive': positive_score,
            'priority_score': adjusted_priority,
            'priority_label': self.classify_priority(adjusted_priority)
        }
    
    def _adjust_priority_with_phrases(self, text: str, base_score: float) -> float:
        """Apply domain-specific phrase adjustments to priority score"""
        text_lower = text.lower()
        
        # Check for high-priority indicators
        for phrase in self.high_priority_phrases:
            if phrase in text_lower:
                base_score = min(1.0, base_score * 1.3)
                logger.debug(f"High-priority phrase detected: '{phrase}' -> boosting score")
        
        # Check for low-priority indicators
        for phrase in self.low_priority_phrases:
            if phrase in text_lower:
                base_score = base_score * 0.7
                logger.debug(f"Low-priority phrase detected: '{phrase}' -> reducing score")
        
        return base_score
    
    def classify_priority(self, priority_score: float) -> str:
        """
        Convert numerical priority score to categorical label
        
        Args:
            priority_score: Float between 0-1
            
        Returns:
            "High", "Medium", or "Low"
        """
        if priority_score > 0.7:
            return "High"
        elif priority_score > 0.4:
            return "Medium"
        else:
            return "Low"
    
    def batch_analyze(self, segments: List[str]) -> List[Dict[str, float]]:
        """Analyze multiple segments efficiently"""
        return [self.analyze_segment(segment) for segment in segments]


if __name__ == "__main__":
    # Quick test
    analyzer = SentimentAnalyzer()
    
    test_cases = [
        "Users are really frustrated with the checkout process. We're losing customers daily.",
        "It would be nice to have dark mode eventually.",
        "The login button color could be slightly better, not urgent though."
    ]
    
    print("\n=== Sentiment Analysis Test ===\n")
    for text in test_cases:
        result = analyzer.analyze_segment(text)
        print(f"Text: {text[:60]}...")
        print(f"Priority: {result['priority_label']} (score: {result['priority_score']:.2f})")
        print(f"Sentiment: Neg={result['negative']:.2f}, Neu={result['neutral']:.2f}, Pos={result['positive']:.2f}\n")