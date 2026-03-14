import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import torch
import re
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import pickle
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

class RobustPriorityDetector:
    """
    Multi-signal priority detection combining:
    - Ensemble sentiment (3 models)
    - Keyword/phrase detection
    - Topic classification
    - Linguistic features
    - Weighted fusion for final prediction
    """
    
    def __init__(self):
        logger.info("Initializing Robust Priority Detector...")
        
        # Signal 1: Ensemble Sentiment Models
        self._init_sentiment_ensemble()
        
        # Signal 2: Domain-specific keywords
        self._init_keyword_database()
        
        # Signal 3: Topic classifier
        self._init_topic_classifier()
        
        # Signal 4: Linguistic feature extractors
        self._init_linguistic_extractors()
        
        # Fusion layer (start with simple weighted average, can train logistic regression later)
        self.fusion_weights = {
            'sentiment_ensemble': 0.35,
            'keyword_score': 0.25,
            'topic_score': 0.20,
            'linguistic_score': 0.20
        }
        
        logger.info("✓ Robust Priority Detector ready")
    
    def _init_sentiment_ensemble(self):
        """Initialize 3 diverse sentiment models for ensemble voting"""
        logger.info("Loading sentiment ensemble (3 models)...")
        
        # Model 1: Twitter-trained (good for informal, emotional language)
        self.sentiment_models = []
        
        model1_name = "cardiffnlp/twitter-roberta-base-sentiment-latest"
        tokenizer1 = AutoTokenizer.from_pretrained(model1_name)
        model1 = AutoModelForSequenceClassification.from_pretrained(model1_name)
        self.sentiment_models.append({
            'name': 'twitter-roberta',
            'tokenizer': tokenizer1,
            'model': model1,
            'weight': 0.4  # Higher weight - currently best performer
        })
        
        # Model 2: DistilBERT (good for formal business language)
        model2_name = "distilbert-base-uncased-finetuned-sst-2-english"
        tokenizer2 = AutoTokenizer.from_pretrained(model2_name)
        model2 = AutoModelForSequenceClassification.from_pretrained(model2_name)
        self.sentiment_models.append({
            'name': 'distilbert-sst2',
            'tokenizer': tokenizer2,
            'model': model2,
            'weight': 0.35
        })
        
        # Model 3: Multilingual BERT (handles technical jargon better)
        model3_name = "nlptown/bert-base-multilingual-uncased-sentiment"
        tokenizer3 = AutoTokenizer.from_pretrained(model3_name)
        model3 = AutoModelForSequenceClassification.from_pretrained(model3_name)
        self.sentiment_models.append({
            'name': 'multilingual-bert',
            'tokenizer': tokenizer3,
            'model': model3,
            'weight': 0.25
        })
        
        # Set all to eval mode
        for m in self.sentiment_models:
            m['model'].eval()
        
        logger.info("✓ Sentiment ensemble loaded (3 models)")
    
    def _init_keyword_database(self):
        """Comprehensive keyword database with fine-grained priority signals"""
        
        # HIGH PRIORITY SIGNALS
        self.high_priority_keywords = {
            # Business impact
            'revenue': 1.0,
            'losing customers': 1.0,
            'customer churn': 1.0,
            'competitive advantage': 0.9,
            'market share': 0.9,
            
            # Urgency
            'urgent': 1.0,
            'critical': 1.0,
            'asap': 1.0,
            'immediately': 1.0,
            'blocking': 1.0,
            'broken': 0.95,
            'not working': 0.95,
            'failing': 0.9,
            
            # User pain
            'frustrated': 0.9,
            'complaining': 0.9,
            'angry': 0.9,
            'lawsuit': 1.0,
            'regulatory': 0.95,
            'compliance': 0.9,
            'security vulnerability': 1.0,
            'data breach': 1.0,
        }
        
        # MEDIUM PRIORITY SIGNALS
        self.medium_priority_keywords = {
            # Strategic
            'roadmap': 0.6,
            'strategic': 0.65,
            'enterprise': 0.6,
            'enterprise customers': 0.7,
            'key clients': 0.7,
            'requested by': 0.6,
            'multiple clients': 0.7,
            
            # Workflow improvement
            'efficiency': 0.55,
            'productivity': 0.55,
            'workflow': 0.6,
            'improve': 0.5,
            'optimize': 0.55,
            'enhance': 0.5,
            
            # Moderate urgency
            'should': 0.5,
            'need to': 0.6,
            'important': 0.6,
            'significant': 0.6,
        }
        
        # LOW PRIORITY SIGNALS
        self.low_priority_keywords = {
            'nice to have': -0.8,
            'eventually': -0.7,
            'someday': -0.8,
            'if we have time': -0.9,
            'not urgent': -1.0,
            'cosmetic': -0.8,
            'minor': -0.7,
            'polish': -0.6,
            'could': -0.5,
            'might': -0.5,
            'maybe': -0.6,
            'consider': -0.4,
        }
    
    def _init_topic_classifier(self):
        """Zero-shot topic classification for domain importance"""
        logger.info("Loading topic classifier...")
        
        self.topic_classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli"
        )
        
        # Topics ranked by typical priority
        self.topic_labels = [
            "revenue generation",      # Usually high priority
            "security and compliance", # Usually high priority
            "core functionality",      # Usually high priority
            "customer satisfaction",   # Usually medium-high
            "performance optimization",# Usually medium
            "workflow efficiency",     # Usually medium
            "user interface polish",   # Usually low-medium
            "aesthetic improvements",  # Usually low
        ]
        
        logger.info("✓ Topic classifier ready")
    
    def _init_linguistic_extractors(self):
        """Linguistic pattern extractors"""
        
        # Patterns indicating urgency/importance
        self.urgency_patterns = [
            r'\b(must|need to|have to|required to)\b',  # Obligation
            r'\b(now|immediately|asap|urgent|critical)\b',  # Time pressure
            r'\b(every|all|everyone|daily|constantly)\b',  # Frequency/scope
            r'!{1,}',  # Exclamation marks
            r'\b(breaking|broken|failing|crashed)\b',  # Failure states
        ]
        
        # Patterns indicating lower priority
        self.low_priority_patterns = [
            r'\b(could|might|maybe|perhaps|possibly)\b',  # Uncertainty
            r'\b(nice|good|great) to have\b',  # Wish list
            r'\b(eventually|someday|future|long.term)\b',  # Distant timeframe
            r'\b(consider|think about|look into)\b',  # Exploratory
        ]
    
    def analyze_priority(self, text: str, context: Dict = None) -> Dict:
        """
        Comprehensive priority analysis using all signals
        
        Args:
            text: Requirement text
            context: Optional context (speaker_role, repetition_count, etc.)
        
        Returns:
            {
                'priority_label': 'High' | 'Medium' | 'Low',
                'priority_score': float (0-1),
                'confidence': float (0-1),
                'signal_breakdown': {...},
                'explanation': str
            }
        """
        
        # Extract all signals
        sentiment_score = self._ensemble_sentiment(text)
        keyword_score = self._keyword_analysis(text)
        topic_score = self._topic_analysis(text)
        linguistic_score = self._linguistic_analysis(text)
        
        # Apply context adjustments if available
        if context:
            sentiment_score = self._apply_context(sentiment_score, context)

        # --- Sentinel damping -----------------------------------------------
        # Social-media sentiment models can fire on friendly/enthusiastic phrasing
        # that has nothing to do with urgency (e.g. "It would be nice to have dark
        # mode"). When both domain-aware signals (keyword + linguistic) independently
        # agree the item is low-priority, the sentiment score is likely a false signal
        # and should not be allowed to single-handedly escalate the result.
        _LOW_SIGNAL = 0.40
        sentiment_dampened = (
            keyword_score < _LOW_SIGNAL and linguistic_score < _LOW_SIGNAL
        )
        effective_sentiment = min(sentiment_score, 0.45) if sentiment_dampened else sentiment_score
        if sentiment_dampened and effective_sentiment < sentiment_score:
            logger.debug(
                f"Sentiment dampened {sentiment_score:.2f} -> {effective_sentiment:.2f} "
                f"(keyword={keyword_score:.2f}, linguistic={linguistic_score:.2f} "
                f"both below {_LOW_SIGNAL})"
            )
        # --------------------------------------------------------------------

        # Weighted fusion
        final_score = (
            effective_sentiment * self.fusion_weights['sentiment_ensemble'] +
            keyword_score * self.fusion_weights['keyword_score'] +
            topic_score * self.fusion_weights['topic_score'] +
            linguistic_score * self.fusion_weights['linguistic_score']
        )

        # Threshold: High > 0.60 (was 0.65 — previous value caused false-negatives
        # on items with strong keyword/linguistic signals but moderate sentiment)
        if final_score > 0.60:
            priority = "High"
            confidence = min(1.0, (final_score - 0.60) / 0.40 + 0.5)
        elif final_score > 0.35:
            priority = "Medium"
            confidence = 0.5 + (0.5 - abs(final_score - 0.5)) * 0.6
        else:
            priority = "Low"
            confidence = min(1.0, (0.35 - final_score) / 0.35 + 0.5)

        return {
            'priority_label': priority,
            'priority_score': final_score,
            'confidence': confidence,
            'signal_breakdown': {
                'sentiment_ensemble': sentiment_score,     # raw, for transparency
                'effective_sentiment': effective_sentiment, # what fusion actually used
                'sentiment_dampened': sentiment_dampened,
                'keyword_score': keyword_score,
                'topic_score': topic_score,
                'linguistic_score': linguistic_score,
            },
            'explanation': self._generate_explanation(
                effective_sentiment, keyword_score, topic_score, linguistic_score,
                priority, sentiment_dampened
            )
        }
    
    def _ensemble_sentiment(self, text: str) -> float:
        """Run all 3 sentiment models and combine with weighted voting"""
        
        ensemble_scores = []
        
        for model_info in self.sentiment_models:
            tokenizer = model_info['tokenizer']
            model = model_info['model']
            weight = model_info['weight']
            
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            
            with torch.no_grad():
                outputs = model(**inputs)
                scores = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # Extract negative and positive scores (model-specific indexing)
            if model_info['name'] == 'multilingual-bert':
                # This model has 5 classes (1-5 stars)
                negative = scores[0][0].item() + scores[0][1].item()  # 1-2 stars
                positive = scores[0][3].item() + scores[0][4].item()  # 4-5 stars
            else:
                # Binary or 3-class sentiment
                negative = scores[0][0].item()
                positive = scores[0][-1].item()
            
            # Priority heuristic: high emotion (either direction) = potential importance
            emotion_intensity = max(negative, positive)
            ensemble_scores.append(emotion_intensity * weight)
        
        # Weighted average
        weighted_sentiment = sum(ensemble_scores)
        
        return weighted_sentiment
    
    def _keyword_analysis(self, text: str) -> float:
        """Analyze keywords and phrases for priority signals"""
        
        text_lower = text.lower()
        score = 0.5  # Start neutral
        matches = []
        
        # Check high-priority keywords
        for keyword, weight in self.high_priority_keywords.items():
            if keyword in text_lower:
                score += weight * 0.15  # Each match boosts score
                matches.append(('HIGH', keyword, weight))
        
        # Check medium-priority keywords
        for keyword, weight in self.medium_priority_keywords.items():
            if keyword in text_lower:
                score += weight * 0.08  # Smaller boost
                matches.append(('MEDIUM', keyword, weight))
        
        # Check low-priority keywords (these reduce score)
        for keyword, weight in self.low_priority_keywords.items():
            if keyword in text_lower:
                score += weight * 0.12  # Negative weights reduce score
                matches.append(('LOW', keyword, weight))
        
        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))
        
        logger.debug(f"Keyword matches: {matches}, score: {score:.2f}")
        
        return score
    
    def _topic_analysis(self, text: str) -> float:
        """Classify topic and map to priority score"""
        
        result = self.topic_classifier(text, self.topic_labels, multi_label=False)
        
        # Map top topic to priority score
        top_topic = result['labels'][0]
        top_score = result['scores'][0]
        
        # Topic-to-priority mapping
        topic_priority_map = {
            "revenue generation": 0.95,
            "security and compliance": 0.90,
            "core functionality": 0.85,
            "customer satisfaction": 0.70,
            "performance optimization": 0.60,
            "workflow efficiency": 0.55,
            "user interface polish": 0.40,
            "aesthetic improvements": 0.30,
        }
        
        base_score = topic_priority_map.get(top_topic, 0.5)
        
        # Weight by classification confidence
        weighted_score = base_score * top_score + 0.5 * (1 - top_score)
        
        logger.debug(f"Top topic: {top_topic} ({top_score:.2f}), priority score: {weighted_score:.2f}")
        
        return weighted_score
    
    def _linguistic_analysis(self, text: str) -> float:
        """Extract linguistic features indicating priority"""
        
        score = 0.5
        
        # Count urgency patterns
        urgency_count = sum(len(re.findall(pattern, text, re.IGNORECASE)) 
                           for pattern in self.urgency_patterns)
        
        # Count low-priority patterns
        low_priority_count = sum(len(re.findall(pattern, text, re.IGNORECASE))
                                for pattern in self.low_priority_patterns)
        
        # Adjust score
        score += urgency_count * 0.1
        score -= low_priority_count * 0.1
        
        # Text length (very short = might be vague/unimportant)
        if len(text.split()) < 5:
            score -= 0.1
        
        # Multiple exclamation marks = emphasis
        if '!!' in text or '!!!' in text:
            score += 0.15
        
        # Clamp
        score = max(0.0, min(1.0, score))
        
        return score
    
    def _apply_context(self, base_score: float, context: Dict) -> float:
        """Apply contextual adjustments (speaker role, repetition, etc.)"""
        
        adjusted_score = base_score
        
        # Speaker role weighting
        if 'speaker_role' in context:
            role_weights = {
                'CEO': 1.25,
                'CTO': 1.20,
                'Product Owner': 1.15,
                'Product Manager': 1.10,
                'Tech Lead': 1.05,
                'Developer': 1.0,
                'Designer': 0.95,
                'QA': 0.95
            }
            multiplier = role_weights.get(context['speaker_role'], 1.0)
            adjusted_score *= multiplier
        
        # Repetition count (mentioned multiple times = higher priority)
        if 'repetition_count' in context and context['repetition_count'] > 1:
            boost = min(0.2, context['repetition_count'] * 0.05)
            adjusted_score += boost
        
        # Historical context (related to known high-priority initiatives)
        if context.get('relates_to_okr', False):
            adjusted_score += 0.15
        
        return min(1.0, adjusted_score)
    
    def _generate_explanation(self, effective_sentiment, keyword, topic, linguistic,
                              priority, sentiment_dampened=False):
        """Generate human-readable explanation for priority decision"""

        explanations = []

        if sentiment_dampened:
            explanations.append(
                "Sentiment signal dampened — keyword and linguistic patterns both indicate "
                "low priority, overriding emotional intensity"
            )
        elif effective_sentiment > 0.7:
            explanations.append(f"High emotional intensity ({effective_sentiment:.2f})")
        elif effective_sentiment < 0.3:
            explanations.append(f"Low emotional intensity ({effective_sentiment:.2f})")

        if keyword > 0.7:
            explanations.append("Strong priority keywords present")
        elif keyword < 0.3:
            explanations.append("Low-priority phrasing detected")

        if topic > 0.8:
            explanations.append("High-impact topic identified")

        if linguistic > 0.7:
            explanations.append("Urgency patterns in language")
        elif linguistic < 0.3:
            explanations.append("Low-priority linguistic patterns detected")

        if not explanations:
            explanations.append("Balanced signals across all dimensions")

        return f"{priority} priority — " + "; ".join(explanations)
    
    def batch_analyze(self, texts: List[str]) -> List[Dict]:
        """Analyze multiple requirements"""
        return [self.analyze_priority(text) for text in texts]