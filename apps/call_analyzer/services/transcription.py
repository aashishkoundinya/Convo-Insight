import os
import tempfile
import logging
from typing import Dict, List, Tuple, Optional
from datetime import timedelta

import whisper
from pydub import AudioSegment
from django.conf import settings

from apps.call_analyzer.models import CallRecording, Transcription

logger = logging.getLogger(__name__)

class TranscriptionService:
    """
    Service for transcribing audio recordings using Whisper AI.
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the transcription service with the specified Whisper model.
        
        Args:
            model_name: Name of the Whisper model to use.
                        Options: 'tiny', 'base', 'small', 'medium', 'large'
        """
        self.model_name = model_name or settings.WHISPER_MODEL
        self.model = None
    
    def _load_model(self):
        """
        Load the Whisper model if it's not already loaded.
        """
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self.model = whisper.load_model(self.model_name)
        return self.model
    
    def _prepare_audio_file(self, file_path: str) -> str:
        """
        Prepare the audio file for transcription by converting to WAV if needed.
        
        Args:
            file_path: Path to the audio file.
            
        Returns:
            Path to the prepared audio file.
        """
        # Check file extension
        _, ext = os.path.splitext(file_path)
        if ext.lower() in ['.wav']:
            return file_path
        
        # Convert to WAV for better compatibility
        try:
            audio = AudioSegment.from_file(file_path)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                audio.export(tmp_path, format='wav')
                return tmp_path
        except Exception as e:
            logger.error(f"Error converting audio file: {e}")
            return file_path
    
    def transcribe(self, call_recording: CallRecording) -> Optional[Transcription]:
        """
        Transcribe the given call recording and save the results.
        
        Args:
            call_recording: The CallRecording model instance to transcribe.
            
        Returns:
            Transcription model instance if successful, None otherwise.
        """
        try:
            # Update status to processing
            call_recording.status = 'processing'
            call_recording.save()
            
            # Load model
            model = self._load_model()
            
            # Prepare audio file
            file_path = call_recording.file.path
            prepared_path = self._prepare_audio_file(file_path)
            
            # Run transcription
            logger.info(f"Starting transcription for: {call_recording.title}")
            result = model.transcribe(prepared_path, fp16=False)
            
            # Extract transcription text and segments
            text = result.get('text', '')
            segments = [
                {
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'text': segment.get('text', ''),
                    'speaker': 'unknown'  # Whisper doesn't do speaker diarization by default
                }
                for segment in result.get('segments', [])
            ]
            
            # Calculate total duration
            if segments:
                duration_seconds = segments[-1].get('end', 0)
                call_recording.duration = timedelta(seconds=duration_seconds)
            
            # Create or update transcription
            transcription, created = Transcription.objects.update_or_create(
                call_recording=call_recording,
                defaults={
                    'text': text,
                    'segments': segments,
                    'confidence_score': result.get('confidence', None)
                }
            )
            
            # Update call recording status
            call_recording.status = 'processed'
            call_recording.save()
            
            # Clean up temporary file if created
            if prepared_path != file_path and os.path.exists(prepared_path):
                os.remove(prepared_path)
                
            return transcription
            
        except Exception as e:
            logger.error(f"Transcription error for {call_recording.title}: {str(e)}")
            call_recording.status = 'failed'
            call_recording.save()
            return None
            
    def perform_speaker_diarization(self, transcription: Transcription) -> None:
        """
        Separate speakers in the transcription using a diarization model.
        This is a placeholder - a full implementation would use a dedicated
        speaker diarization model like pyannote.audio.
        
        Args:
            transcription: The Transcription model instance.
        """
        # This is a simplistic approach - in a real implementation,
        # you would use a dedicated speaker diarization model
        segments = transcription.segments
        
        # Simple heuristic: alternate speakers based on pauses
        current_speaker = "speaker_A"
        last_end_time = 0
        
        for i, segment in enumerate(segments):
            # Switch speaker if there's a significant pause (e.g., > 1 second)
            if i > 0 and segment['start'] - last_end_time > 1.0:
                current_speaker = "speaker_B" if current_speaker == "speaker_A" else "speaker_A"
            
            segment['speaker'] = current_speaker
            last_end_time = segment['end']
        
        # Update the transcription
        transcription.segments = segments
        transcription.save()