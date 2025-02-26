import logging
import re
from typing import Dict, List, Any, Optional
import nltk
from textblob import TextBlob
import spacy
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from django.conf import settings
from apps.email_generator.models import GeneratedEmail, EmailAnalysis

# Download required NLTK resources
try:
    nltk.data.find('punkt')
    nltk.data.find('stopwords')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')

logger = logging.getLogger(__name__)

class EmailAnalyzerService:
    """
    Service for analyzing and scoring generated emails.
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the email analyzer service.
        
        Args:
            model_name: Name of the LLM model to use for advanced analysis.
        """
        self.model_name = model_name or settings.OPEN_SOURCE_LLM_MODEL
        self.model = None
        self.tokenizer = None
        self.nlp = None
    
    def _load_model(self):
        """
        Load the LLM model if it's not already loaded.
        """
        if self.model is None or self.tokenizer is None:
            logger.info(f"Loading LLM model: {self.model_name}")
            try:
                # Try to load with reduced precision for memory efficiency
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16,
                    device_map="auto",
                    load_in_8bit=True  # Quantize for memory efficiency
                )
            except:
                # Fall back to standard loading
                logger.info("Falling back to standard model loading")
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
        
        return self.model, self.tokenizer
    
    def _load_spacy(self):
        """
        Load the spaCy model if it's not already loaded.
        """
        if self.nlp is None:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except:
                # Download if not available
                spacy.cli.download("en_core_web_sm")
                self.nlp = spacy.load("en_core_web_sm")
        
        return self.nlp
    
    def _analyze_readability(self, text: str) -> Dict[str, Any]:
        """
        Analyze the readability of a text.
        
        Args:
            text: The text to analyze
            
        Returns:
            Dictionary with readability metrics
        """
        # Get sentences and words
        sentences = nltk.sent_tokenize(text)
        words = nltk.word_tokenize(text)
        
        # Calculate basic metrics
        sentence_count = len(sentences)
        word_count = len(words)
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        
        # Calculate average word length
        total_chars = sum(len(word) for word in words)
        avg_word_length = total_chars / word_count if word_count > 0 else 0
        
        # Calculate Flesch Reading Ease
        # Formula: 206.835 - 1.015(total words / total sentences) - 84.6(total syllables / total words)
        # Simplified version
        flesch_score = 206.835 - (1.015 * avg_sentence_length) - (84.6 * (avg_word_length / 4.5))
        # Normalize to 0-100
        normalized_flesch = max(0, min(100, flesch_score))
        
        # Convert to our readability score (higher is better)
        readability_score = normalized_flesch if normalized_flesch > 60 else (60 - normalized_flesch) / 2
        
        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_sentence_length,
            "avg_word_length": avg_word_length,
            "readability_score": readability_score,
            "complexity_score": avg_sentence_length * 0.05 + avg_word_length * 10  # Custom complexity metric
        }
    
    def _analyze_spam_likelihood(self, subject: str, body: str) -> Dict[str, Any]:
        """
        Analyze how likely an email is to be flagged as spam.
        
        Args:
            subject: Email subject line
            body: Email body
            
        Returns:
            Dictionary with spam metrics
        """
        # Red flags that could trigger spam filters
        spam_indicators = [
            r'\b(?:free|limited time|act now|congratulations|exclusive|urgent)\b',
            r'\b(?:buy|cash|earn|money|dollars|€|\$|£)\b',
            r'\b(?:guarantee|guaranteed|warranty|promised)\b',
            r'!\s*!',  # Multiple exclamation marks
            r'\b(?:click here|click below|click this)\b',
            r'\b(?:special offer|special promotion|special deal)\b',
            r'ALL\s+CAPS',
            r'\b(?:winner|prize|offer|promotion|discount|sale)\b',
        ]
        
        combined_text = f"{subject} {body}"
        
        # Count spam indicators
        spam_count = 0
        for pattern in spam_indicators:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            spam_count += len(matches)
        
        # Check for ALL CAPS usage
        words = combined_text.split()
        all_caps_words = [word for word in words if word.isupper() and len(word) > 2]
        all_caps_ratio = len(all_caps_words) / len(words) if words else 0
        
        # Check for excessive punctuation
        exclamation_count = combined_text.count('!')
        exclamation_ratio = exclamation_count / len(words) if words else 0
        
        # Check for HTML in plain text
        html_indicators = ['<a href', '<img', '<table', '<div', '<span', '<br']
        html_count = sum(1 for indicator in html_indicators if indicator in body.lower())
        
        # Calculate spam score (0-100, lower is better)
        base_score = min(100, spam_count * 10 + all_caps_ratio * 50 + exclamation_ratio * 30 + html_count * 15)
        
        # Invert so higher is better
        spam_score = 100 - base_score
        
        return {
            "spam_score": spam_score,
            "spam_indicators": spam_count,
            "all_caps_ratio": all_caps_ratio,
            "exclamation_ratio": exclamation_ratio,
            "html_count": html_count
        }
    
    def _analyze_engagement_potential(self, subject: str, body: str) -> Dict[str, Any]:
        """
        Analyze how engaging the email is likely to be.
        
        Args:
            subject: Email subject line
            body: Email body
            
        Returns:
            Dictionary with engagement metrics
        """
        nlp = self._load_spacy()
        
        # Analyze subject line engagement
        subject_doc = nlp(subject)
        
        # Check for question in subject (can increase open rates)
        has_question_subject = any(token.pos_ == "VERB" and token.dep_ == "aux" for token in subject_doc) or "?" in subject
        
        # Check personalization indicators
        personalization_terms = ["you", "your", "we", "our", "together"]
        personalization_count = sum(1 for term in personalization_terms if term.lower() in body.lower().split())
        
        # Check for call to action
        cta_patterns = [
            r'\b(?:call|contact|email|respond|reply|schedule|book)\b',
            r'\b(?:join|sign up|register|download|get started|learn more)\b',
            r'\b(?:visit|check out|see|watch|find out)\b',
            r'(?:looking forward|talk soon)',
            r'(?:\?|let me know)'
        ]
        
        has_cta = False
        for pattern in cta_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                has_cta = True
                break
        
        # Sentiment analysis for positivity (people respond better to positive messaging)
        blob = TextBlob(body)
        sentiment_score = blob.sentiment.polarity
        
        # Normalize sentiment from -1,1 to 0,100
        normalized_sentiment = (sentiment_score + 1) * 50
        
        # Calculate engagement score
        engagement_factors = [
            normalized_sentiment * 0.3,  # 30% weight for sentiment
            personalization_count * 5,   # 5 points per personalization term
            15 if has_cta else 0,        # 15 points for having a CTA
            10 if has_question_subject else 0  # 10 points for question in subject
        ]
        
        engagement_score = min(100, sum(engagement_factors))
        
        return {
            "engagement_score": engagement_score,
            "has_question_subject": has_question_subject,
            "personalization_count": personalization_count,
            "has_cta": has_cta,
            "sentiment_score": sentiment_score
        }
    
    def _get_quality_feedback(self, email: GeneratedEmail) -> Dict[str, List[str]]:
        """
        Get detailed quality feedback using the LLM.
        
        Args:
            email: The email to analyze
            
        Returns:
            Dictionary with strengths, weaknesses, and suggestions
        """
        model, tokenizer = self._load_model()
        
        # Create prompt for email quality analysis
        prompt = f"""
        Analyze this cold sales email for quality and provide feedback:
        
        Subject: {email.subject}
        
        Body:
        {email.body}
        
        Provide:
        1. Strengths: What's good about this email
        2. Weaknesses: Problems or issues with the email
        3. Suggestions: Specific improvements to make
        
        Format your response as JSON.
        """
        
        # Generate response
        generator = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_length=1024
        )
        
        response = generator(prompt, max_length=1024, num_return_sequences=1)[0]['generated_text']
        
        # Parse the response
        try:
            import json
            import re
            
            # Look for content between curly braces
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                feedback_data = json.loads(json_str)
            else:
                # Manual extraction as fallback
                feedback_data = {
                    "strengths": self._extract_section(response, "Strengths"),
                    "weaknesses": self._extract_section(response, "Weaknesses"),
                    "suggestions": self._extract_section(response, "Suggestions")
                }
        except Exception as e:
            logger.error(f"Error parsing LLM response for email feedback: {str(e)}")
            feedback_data = {
                "strengths": self._extract_section(response, "Strengths"),
                "weaknesses": self._extract_section(response, "Weaknesses"),
                "suggestions": self._extract_section(response, "Suggestions")
            }
        
        return feedback_data
    
    def _extract_section(self, text: str, section_name: str) -> List[str]:
        """Helper to extract list items from a section in the response."""
        import re
        
        # Find the section
        pattern = f"{section_name}:(.*?)(?:\n\d+\.|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        
        if not match:
            return []
        
        section_text = match.group(1).strip()
        
        # Extract list items
        items = []
        for line in section_text.split('\n'):
            # Remove list markers and clean
            clean_line = re.sub(r'^\s*[-•*\d]+\.?\s*', '', line).strip()
            if clean_line:
                items.append(clean_line)
        
        return items
    
    def analyze_email(self, email: GeneratedEmail) -> Optional[EmailAnalysis]:
        """
        Analyze a generated email for quality, spam likelihood, and engagement potential.
        
        Args:
            email: The email to analyze
            
        Returns:
            EmailAnalysis model instance if successful, None otherwise.
        """
        try:
            # Run the analyses
            readability = self._analyze_readability(email.body)
            spam = self._analyze_spam_likelihood(email.subject, email.body)
            engagement = self._analyze_engagement_potential(email.subject, email.body)
            
            # Get quality feedback
            feedback = self._get_quality_feedback(email)
            
            # Calculate overall score (weighted average)
            overall_score = (
                readability["readability_score"] * 0.3 +  # 30% weight for readability
                spam["spam_score"] * 0.3 +               # 30% weight for spam score
                engagement["engagement_score"] * 0.4      # 40% weight for engagement
            )
            
            # Create or update email analysis
            analysis, created = EmailAnalysis.objects.update_or_create(
                email=email,
                defaults={
                    'readability_score': readability["readability_score"],
                    'spam_score': spam["spam_score"],
                    'engagement_score': engagement["engagement_score"],
                    'overall_score': overall_score,
                    'strengths': feedback.get("strengths", []),
                    'weaknesses': feedback.get("weaknesses", []),
                    'suggestions': feedback.get("suggestions", []),
                    'word_count': readability["word_count"],
                    'avg_sentence_length': readability["avg_sentence_length"],
                    'complexity_score': readability["complexity_score"]
                }
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Email analysis error: {str(e)}")
            return None