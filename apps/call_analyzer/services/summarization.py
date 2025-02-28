import logging
from typing import Dict, List, Any, Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from django.conf import settings
from apps.call_analyzer.models import CallRecording, Transcription, CallSummary, SalesPerformance

logger = logging.getLogger(__name__)

class SummarizationService:
    """
    Service for summarizing call transcriptions using an open-source LLM.
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the summarization service.
        
        Args:
            model_name: Name or path of the open-source LLM to use.
        """
        self.model_name = model_name or settings.OPEN_SOURCE_LLM_MODEL
        self.model = None
        self.tokenizer = None
    
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
    
    def _chunked_summarization(self, text: str, max_length: int = 4000) -> List[Dict[str, Any]]:
        """
        Process long texts by summarizing in chunks.
        
        Args:
            text: Full text to summarize
            max_length: Maximum input length for the model
            
        Returns:
            Combined results from all chunks
        """
        model, tokenizer = self._load_model()
        
        # Split text into chunks if needed
        if len(text) <= max_length:
            chunks = [text]
        else:
            # Split by sentences or paragraphs
            sentences = text.split('. ')
            chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= max_length:
                    current_chunk += sentence + ". "
                else:
                    chunks.append(current_chunk)
                    current_chunk = sentence + ". "
            
            if current_chunk:
                chunks.append(current_chunk)
        
        # Process each chunk
        summarizer = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_length=512
        )
        
        results = []
        for i, chunk in enumerate(chunks):
            prompt = f"Summarize this sales call transcript: {chunk}\n\nSummary:"
            
            # Generate summary
            response = summarizer(prompt, max_length=1024, num_return_sequences=1)[0]['generated_text']
            
            # Extract just the generated part (after the prompt)
            summary_text = response.split("Summary:")[1].strip() if "Summary:" in response else response
            
            results.append({
                "chunk_id": i,
                "summary": summary_text
            })
        
        return results

    def _extract_key_elements(self, text: str) -> Dict[str, Any]:
        """
        Extract key elements from a call transcript using LLM.
        """
        model, tokenizer = self._load_model()
        
        # Create a clearer, more structured prompt
        prompt = f"""
        You are an expert at analyzing sales call transcripts.
        
        Below is a transcript from a sales call. Extract the following information in a clear, structured format:

        TRANSCRIPT:
        {text[:3000]}  # Truncated to avoid token limits
        
        Format your response exactly like this example:
        KEY POINTS:
        - First key point about the conversation
        - Second key point about the conversation
        
        ACTION ITEMS:
        - Action item 1
        - Action item 2
        
        QUESTIONS:
        - Question 1 asked during the call
        - Question 2 asked during the call
        
        OBJECTIONS:
        - Customer objection 1
        - Customer objection 2
        """
        
        # Generate response
        generation = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_length=1024,
            truncation=True
        )
        
        response = generation(prompt, max_length=1024, num_return_sequences=1)[0]['generated_text']
        
        # More robust extraction of sections using regular expressions
        structured_data = {
            "key_points": self._extract_list_items(response, "KEY POINTS"),
            "action_items": self._extract_list_items(response, "ACTION ITEMS"),
            "questions": self._extract_list_items(response, "QUESTIONS"),
            "objections": self._extract_list_items(response, "OBJECTIONS")
        }
        
        return structured_data

    def _extract_list_items(self, text: str, section_name: str) -> List[str]:
        """Extract list items from a section using more robust pattern matching."""
        import re
        
        # Find the section - match everything after section_name: until the next section or end
        pattern = f"{section_name}:(?:\s*\n)?(.*?)(?:\n\s*[A-Z ]+:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        
        if not match:
            return []
        
        section_text = match.group(1).strip()
        
        # Extract list items (bullet points or numbered items)
        items = []
        for line in section_text.split('\n'):
            # Remove bullet points, numbers, etc.
            clean_line = re.sub(r'^\s*[-•*\d]+\.?\s*', '', line).strip()
            if clean_line and len(clean_line) > 3:  # Avoid empty or too short lines
                items.append(clean_line)
        
        return items
    
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
    
    def _analyze_performance(self, text: str, call_recording: CallRecording) -> SalesPerformance:
        """
        Analyze sales performance aspects of the call.
        
        Args:
            text: Call transcript text
            call_recording: The CallRecording model instance
            
        Returns:
            SalesPerformance model instance
        """
        model, tokenizer = self._load_model()
        
        # Create prompt for performance analysis
        prompt = f"""
        Analyze this sales call transcript for sales performance:
        
        Transcript:
        {text[:4000]}  # Truncate to avoid token limits
        
        Provide:
        1. Strengths: What the salesperson did well
        2. Weaknesses: Areas for improvement
        3. Suggestions: Specific advice for improvement
        4. Overall score: Rate the call on a scale of 0-100
        
        Format your response as JSON.
        """
        
        # Generate response
        generation = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_length=1024
        )
        
        response = generation(prompt, max_length=1024, num_return_sequences=1)[0]['generated_text']
        
        # Parse the response (similar to above)
        try:
            import json
            import re
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                analysis_data = json.loads(json_str)
            else:
                # Manual extraction as fallback
                analysis_data = {
                    "strengths": self._extract_section(response, "Strengths"),
                    "weaknesses": self._extract_section(response, "Weaknesses"),
                    "suggestions": self._extract_section(response, "Suggestions"),
                    "overall_score": self._extract_score(response)
                }
        except Exception as e:
            logger.error(f"Error parsing LLM response for performance: {str(e)}")
            analysis_data = {
                "strengths": self._extract_section(response, "Strengths"),
                "weaknesses": self._extract_section(response, "Weaknesses"),
                "suggestions": self._extract_section(response, "Suggestions"),
                "overall_score": self._extract_score(response)
            }
        
        # Create or update performance analysis
        performance, created = SalesPerformance.objects.update_or_create(
            call_recording=call_recording,
            defaults={
                'strengths': analysis_data.get('strengths', []),
                'weaknesses': analysis_data.get('weaknesses', []),
                'suggestions': analysis_data.get('suggestions', []),
                'overall_score': analysis_data.get('overall_score', 50)
            }
        )
        
        return performance
    
    def _extract_score(self, text: str) -> float:
        """Extract numerical score from text."""
        import re
        
        score_pattern = r'Overall score:?\s*(\d+)'
        match = re.search(score_pattern, text, re.IGNORECASE)
        
        if match:
            try:
                score = float(match.group(1))
                # Ensure it's in range 0-100
                return min(max(score, 0), 100)
            except:
                pass
        
        # Default score if we can't extract one
        return 50.0
    
    def summarize(self, call_recording: CallRecording) -> Optional[CallSummary]:
        """
        Generate a summary for the call recording.
        
        Args:
            call_recording: The CallRecording model instance to summarize.
            
        Returns:
            CallSummary model instance if successful, None otherwise.
        """
        try:
            # Get the transcription
            transcription = call_recording.transcription
            if not transcription:
                logger.error(f"No transcription found for call recording: {call_recording.id}")
                return None
            
            # Generate call summary chunks
            summary_chunks = self._chunked_summarization(transcription.text)
            
            # Combine chunk summaries
            full_summary = " ".join([chunk["summary"] for chunk in summary_chunks])
            
            # Extract structured elements
            structured_data = self._extract_key_elements(transcription.text)
            
            # Create or update call summary
            summary, created = CallSummary.objects.update_or_create(
                call_recording=call_recording,
                defaults={
                    'overview': full_summary,
                    'key_points': structured_data.get('key_points', []),
                    'action_items': structured_data.get('action_items', []),
                    'questions': structured_data.get('questions', []),
                    'objections': structured_data.get('objections', [])
                }
            )
            
            # Also analyze performance
            self._analyze_performance(transcription.text, call_recording)
            
            return summary
            
        except Exception as e:
            logger.error(f"Summarization error for {call_recording.title}: {str(e)}")
            return None