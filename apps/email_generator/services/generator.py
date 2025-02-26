import logging
from typing import Dict, List, Any, Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from django.conf import settings
from apps.call_analyzer.models import CallRecording
from apps.email_generator.models import GeneratedEmail, EmailTemplate

logger = logging.getLogger(__name__)

class EmailGenerationService:
    """
    Service for generating cold emails based on call insights using an open-source LLM.
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the email generation service.
        
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
    
    def _build_prompt(self, call_recording: CallRecording, tone: str, template: Optional[EmailTemplate] = None) -> str:
        """
        Build the prompt for the email generation based on call insights.
        
        Args:
            call_recording: The call recording to base the email on
            tone: The desired tone for the email
            template: Optional email template to use
            
        Returns:
            Formatted prompt string
        """
        # Check if call has been analyzed
        if not hasattr(call_recording, 'transcription') or not hasattr(call_recording, 'summary'):
            raise ValueError("Call recording must be transcribed and summarized first.")
        
        # Get call data
        customer_name = call_recording.customer_name or "the prospect"
        customer_company = call_recording.customer_company or "their company"
        
        # Extract key insights
        key_points = call_recording.summary.key_points if call_recording.summary.key_points else []
        objections = call_recording.summary.objections if call_recording.summary.objections else []
        
        # Get any sentiment data if available
        sentiment = "neutral"
        if hasattr(call_recording, 'sentiment'):
            sentiment = call_recording.sentiment.overall_sentiment
        
        # Format the prompt
        prompt = f"""
        Generate a personalized cold sales email based on the following call insights:
        
        Call Summary: {call_recording.summary.overview}
        
        Key Points Discussed:
        {', '.join(key_points[:5])}
        
        Objections/Concerns:
        {', '.join(objections[:3])}
        
        Customer Details:
        - Name: {customer_name}
        - Company: {customer_company}
        
        Sentiment from call: {sentiment}
        
        Requirements:
        - Tone should be {tone}
        - Address the key objections tactfully
        - Include a clear call to action
        - Keep it concise and professional
        - Personalize it based on the call insights
        """
        
        # Add template if provided
        if template:
            prompt += f"""
            Use this template structure:
            
            Subject Line: {template.subject_template}
            
            Email Body:
            {template.body_template}
            """
        
        # Add format instructions
        prompt += """
        
        Format your response with:
        SUBJECT: [Email Subject Line]
        
        [Email Body]
        """
        
        return prompt
    
    def _parse_response(self, response: str) -> Dict[str, str]:
        """
        Parse the LLM response to extract subject and body.
        
        Args:
            response: LLM-generated text
            
        Returns:
            Dictionary with 'subject' and 'body' keys
        """
        lines = response.strip().split('\n')
        
        subject = ""
        body_lines = []
        in_body = False
        
        for line in lines:
            line = line.strip()
            
            # Check for subject line
            if line.lower().startswith("subject:"):
                subject = line[8:].strip()
            elif "subject:" in line.lower() and not subject:
                # Handle case where it's not at the start of the line
                parts = line.lower().split("subject:")
                subject = parts[1].strip()
            # Everything after the subject is considered body
            elif subject and not in_body:
                in_body = True
                if line:  # Skip empty line after subject
                    body_lines.append(line)
            elif in_body:
                body_lines.append(line)
        
        # If we didn't find a subject but have body content, use the first line
        if not subject and body_lines:
            subject = body_lines[0]
            body_lines = body_lines[1:]
        
        body = "\n".join(body_lines)
        
        return {
            "subject": subject,
            "body": body
        }
    
    def generate_email(self, 
                     call_recording: CallRecording, 
                     tone: str = 'professional', 
                     user=None, 
                     organization=None, 
                     template: Optional[EmailTemplate] = None) -> Optional[GeneratedEmail]:
        """
        Generate a cold email based on call insights.
        
        Args:
            call_recording: The call recording to base the email on
            tone: The desired tone for the email
            user: The user generating the email
            organization: The organization the user belongs to
            template: Optional email template to use
            
        Returns:
            GeneratedEmail model instance if successful, None otherwise.
        """
        try:
            # Load model
            model, tokenizer = self._load_model()
            
            # Build prompt
            prompt = self._build_prompt(call_recording, tone, template)
            
            # Generate email
            generator = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_length=1024
            )
            
            response = generator(prompt, max_length=1024, num_return_sequences=1)[0]['generated_text']
            
            # Parse response
            parsed_email = self._parse_response(response)
            
            # Determine target length based on body length
            body_length = len(parsed_email['body'])
            if body_length < 400:
                target_length = 'short'
            elif body_length < 800:
                target_length = 'medium'
            else:
                target_length = 'long'
            
            # Create email
            email = GeneratedEmail.objects.create(
                subject=parsed_email['subject'],
                body=parsed_email['body'],
                tone=tone,
                target_length=target_length,
                call_recording=call_recording,
                template=template,
                user=user,
                organization=organization
            )
            
            return email
            
        except Exception as e:
            logger.error(f"Email generation error: {str(e)}")
            return None