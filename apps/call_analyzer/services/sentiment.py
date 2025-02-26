import logging
from typing import Dict, List, Tuple, Optional
import nltk
from textblob import TextBlob
from nltk.sentiment.vader import SentimentIntensityAnalyzer

from apps.call_analyzer.models import CallRecording, Transcription, SentimentAnalysis

# Download required NLTK resources on first import
try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')
    
logger = logging.getLogger(__name__)

class SentimentAnalysisService:
    """
    Service for analyzing sentiment in call transcriptions.
    """
    
    def __init__(self):
        """Initialize the sentiment analysis service with required models."""
        self.vader = SentimentIntensityAnalyzer()
    
    def _get_sentiment_label(self, score: float) -> str:
        """
        Convert a sentiment score to a label.
        
        Args:
            score: Sentiment score from -1 (negative) to 1 (positive)
            
        Returns:
            Sentiment label: 'positive', 'neutral', or 'negative'
        """
        if score > 0.05:
            return 'positive'
        elif score < -0.05:
            return 'negative'
        else:
            return 'neutral'
    
    def _analyze_text_sentiment(self, text: str) -> Tuple[str, float]:
        """
        Analyze the sentiment of a text segment.
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (sentiment_label, sentiment_score)
        """
        # VADER sentiment analysis
        sentiment_scores = self.vader.polarity_scores(text)
        compound_score = sentiment_scores['compound']
        
        # TextBlob analysis for comparison
        blob = TextBlob(text)
        blob_score = blob.sentiment.polarity
        
        # Average the scores (could use more sophisticated ensemble approach)
        combined_score = (compound_score + blob_score) / 2
        sentiment_label = self._get_sentiment_label(combined_score)
        
        return sentiment_label, combined_score
    
    def _detect_emotions(self, text: str) -> Dict[str, float]:
        """
        Detect emotions in text.
        
        This is a simplified placeholder - a full implementation would use
        a dedicated emotion detection model.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping emotion labels to confidence scores
        """
        # Placeholder for emotion detection
        # In a real implementation, you would use a dedicated model
        # like the HuggingFace emotion detection models
        
        emotions = {
            'joy': 0.0,
            'sadness': 0.0,
            'anger': 0.0,
            'fear': 0.0,
            'surprise': 0.0,
            'neutral': 0.0
        }
        
        # Simple keyword-based approach
        joy_keywords = ['happy', 'excellent', 'great', 'excited', 'thrilled']
        sadness_keywords = ['sad', 'disappointed', 'unhappy', 'regret']
        anger_keywords = ['angry', 'upset', 'frustrated', 'annoyed']
        fear_keywords = ['worried', 'concerned', 'nervous', 'anxious']
        surprise_keywords = ['surprised', 'shocked', 'unexpected', 'amazed']
        
        text_lower = text.lower()
        
        # Count keyword occurrences
        for keyword in joy_keywords:
            if keyword in text_lower:
                emotions['joy'] += 0.2
        
        for keyword in sadness_keywords:
            if keyword in text_lower:
                emotions['sadness'] += 0.2
        
        for keyword in anger_keywords:
            if keyword in text_lower:
                emotions['anger'] += 0.2
        
        for keyword in fear_keywords:
            if keyword in text_lower:
                emotions['fear'] += 0.2
        
        for keyword in surprise_keywords:
            if keyword in text_lower:
                emotions['surprise'] += 0.2
        
        # Cap at 1.0
        for emotion in emotions:
            emotions[emotion] = min(emotions[emotion], 1.0)
        
        # If no emotion detected, mark as neutral
        if sum(emotions.values()) == 0:
            emotions['neutral'] = 1.0
        
        return emotions
    
    def analyze(self, call_recording: CallRecording) -> Optional[SentimentAnalysis]:
        """
        Analyze sentiment in a call recording's transcription.
        
        Args:
            call_recording: The CallRecording model instance to analyze.
            
        Returns:
            SentimentAnalysis model instance if successful, None otherwise.
        """
        try:
            # Get the transcription
            transcription = call_recording.transcription
            if not transcription:
                logger.error(f"No transcription found for call recording: {call_recording.id}")
                return None
            
            # Analyze overall sentiment
            overall_label, overall_score = self._analyze_text_sentiment(transcription.text)
            
            # Analyze segment sentiment
            segment_sentiment = []
            for segment in transcription.segments:
                label, score = self._analyze_text_sentiment(segment['text'])
                sentiment_info = {
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'],
                    'speaker': segment.get('speaker', 'unknown'),
                    'sentiment': label,
                    'score': score
                }
                segment_sentiment.append(sentiment_info)
            
            # Detect emotions in the entire transcript
            emotions = self._detect_emotions(transcription.text)
            
            # Create or update sentiment analysis
            sentiment_analysis, created = SentimentAnalysis.objects.update_or_create(
                call_recording=call_recording,
                defaults={
                    'overall_sentiment': overall_label,
                    'overall_score': overall_score,
                    'segment_sentiment': segment_sentiment,
                    'emotions': emotions
                }
            )
            
            return sentiment_analysis
            
        except Exception as e:
            logger.error(f"Sentiment analysis error for {call_recording.title}: {str(e)}")
            return None