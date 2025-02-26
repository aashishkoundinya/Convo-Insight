import logging
from celery import shared_task
from .models import CallRecording
from .services.transcription import TranscriptionService
from .services.sentiment import SentimentAnalysisService
from .services.summarization import SummarizationService

logger = logging.getLogger(__name__)

@shared_task
def process_call_recording_async(call_recording_id):
    """
    Process a call recording asynchronously in the following steps:
    1. Transcribe audio to text
    2. Analyze sentiment in the transcription
    3. Summarize the call content
    
    Args:
        call_recording_id: ID of the CallRecording to process
    """
    logger.info(f"Starting async processing for call recording: {call_recording_id}")
    
    try:
        # Get the call recording
        call_recording = CallRecording.objects.get(id=call_recording_id)
        
        # Update status
        call_recording.status = 'processing'
        call_recording.save()
        
        # Step 1: Transcription
        logger.info(f"Starting transcription for call recording: {call_recording_id}")
        transcription_service = TranscriptionService()
        transcription = transcription_service.transcribe(call_recording)
        
        if not transcription:
            logger.error(f"Transcription failed for call recording: {call_recording_id}")
            call_recording.status = 'failed'
            call_recording.save()
            return
        
        # Optional: Speaker diarization
        transcription_service.perform_speaker_diarization(transcription)
        
        # Step 2: Sentiment Analysis
        logger.info(f"Starting sentiment analysis for call recording: {call_recording_id}")
        sentiment_service = SentimentAnalysisService()
        sentiment = sentiment_service.analyze(call_recording)
        
        if not sentiment:
            logger.warning(f"Sentiment analysis failed for call recording: {call_recording_id}")
            # Continue processing even if sentiment analysis fails
        
        # Step 3: Summarization
        logger.info(f"Starting summarization for call recording: {call_recording_id}")
        summarization_service = SummarizationService()
        summary = summarization_service.summarize(call_recording)
        
        if not summary:
            logger.error(f"Summarization failed for call recording: {call_recording_id}")
            # We can still mark as processed if at least transcription succeeded
        
        # Update status to processed
        call_recording.status = 'processed'
        call_recording.save()
        
        logger.info(f"Completed processing for call recording: {call_recording_id}")
        
    except Exception as e:
        logger.error(f"Error processing call recording {call_recording_id}: {str(e)}")
        try:
            call_recording = CallRecording.objects.get(id=call_recording_id)
            call_recording.status = 'failed'
            call_recording.save()
        except:
            pass