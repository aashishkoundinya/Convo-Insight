from django.db import models
from django.contrib.auth.models import User
from apps.core.models import TimeStampedModel, Tag, Organization


def call_recording_path(instance, filename):
    """
    Determine the path for call recording uploads
    """
    org_id = instance.organization.id if instance.organization else 'no_org'
    return f'calls/{org_id}/{instance.id}/{filename}'


class CallRecording(TimeStampedModel):
    """
    Represents a recorded sales call uploaded by a user.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to=call_recording_path)
    duration = models.DurationField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='call_recordings')
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='call_recordings',
        null=True, blank=True
    )
    tags = models.ManyToManyField(Tag, related_name='call_recordings', blank=True)
    
    # Metadata
    call_date = models.DateField(null=True, blank=True)
    call_type = models.CharField(max_length=50, null=True, blank=True)  # e.g., 'discovery', 'demo', 'follow-up'
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_company = models.CharField(max_length=255, null=True, blank=True)
    
    def __str__(self):
        return self.title


class Transcription(TimeStampedModel):
    """
    Represents the text transcription of a call recording.
    """
    call_recording = models.OneToOneField(
        CallRecording, 
        on_delete=models.CASCADE, 
        related_name='transcription'
    )
    text = models.TextField()
    
    # For storage optimization, we can segment the transcription
    segments = models.JSONField(default=list)  # List of {start, end, text, speaker} objects
    
    confidence_score = models.FloatField(null=True, blank=True)
    
    def __str__(self):
        return f"Transcription for {self.call_recording.title}"


class CallSummary(TimeStampedModel):
    """
    Represents an AI-generated summary of a sales call.
    """
    call_recording = models.OneToOneField(
        CallRecording, 
        on_delete=models.CASCADE, 
        related_name='summary'
    )
    
    # Summary sections
    overview = models.TextField()
    key_points = models.JSONField(default=list)  # List of important points
    action_items = models.JSONField(default=list)  # List of follow-up tasks
    questions = models.JSONField(default=list)  # Questions asked during the call
    objections = models.JSONField(default=list)  # Objections raised by the customer
    
    def __str__(self):
        return f"Summary for {self.call_recording.title}"


class SentimentAnalysis(TimeStampedModel):
    """
    Represents sentiment analysis results for a call recording.
    """
    call_recording = models.OneToOneField(
        CallRecording, 
        on_delete=models.CASCADE, 
        related_name='sentiment'
    )
    
    # Overall sentiment scores
    overall_sentiment = models.CharField(max_length=20)  # 'positive', 'neutral', 'negative'
    overall_score = models.FloatField()  # -1.0 to 1.0
    
    # Detailed sentiment analysis
    segment_sentiment = models.JSONField(default=list)  # List of {start, end, sentiment, score}
    
    # Emotion detection
    emotions = models.JSONField(default=dict)  # e.g., {'happy': 0.8, 'frustrated': 0.2}
    
    def __str__(self):
        return f"Sentiment Analysis for {self.call_recording.title}"


class SalesPerformance(TimeStampedModel):
    """
    Represents sales performance insights derived from a call.
    """
    call_recording = models.OneToOneField(
        CallRecording, 
        on_delete=models.CASCADE, 
        related_name='performance'
    )
    
    # Analysis metrics
    talk_ratio = models.FloatField(null=True, blank=True)  # Salesperson talk time / total time
    interruption_count = models.IntegerField(default=0)
    avg_response_time = models.DurationField(null=True, blank=True)  # Time to respond to questions
    
    # Performance feedback
    strengths = models.JSONField(default=list)  # List of things done well
    weaknesses = models.JSONField(default=list)  # List of areas for improvement
    suggestions = models.JSONField(default=list)  # List of suggestions for improvement
    
    # Overall score
    overall_score = models.FloatField(null=True, blank=True)  # 0-100
    
    def __str__(self):
        return f"Performance Analysis for {self.call_recording.title}"