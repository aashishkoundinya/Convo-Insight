from rest_framework import serializers
from .models import CallRecording, Transcription, CallSummary, SentimentAnalysis, SalesPerformance
from apps.core.models import Tag

class TagSerializer(serializers.ModelSerializer):
    """Serializer for Tag model."""
    
    class Meta:
        model = Tag
        fields = ['id', 'name']


class CallRecordingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new call recording."""
    
    class Meta:
        model = CallRecording
        fields = ['id', 'title', 'description', 'file', 'call_date', 
                  'call_type', 'customer_name', 'customer_company']


class TranscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Transcription model."""
    
    class Meta:
        model = Transcription
        fields = ['id', 'call_recording', 'text', 'segments', 'confidence_score', 
                  'created_at', 'updated_at']


class CallSummarySerializer(serializers.ModelSerializer):
    """Serializer for CallSummary model."""
    
    class Meta:
        model = CallSummary
        fields = ['id', 'call_recording', 'overview', 'key_points', 
                  'action_items', 'questions', 'objections', 
                  'created_at', 'updated_at']


class SentimentAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for SentimentAnalysis model."""
    
    class Meta:
        model = SentimentAnalysis
        fields = ['id', 'call_recording', 'overall_sentiment', 'overall_score', 
                  'segment_sentiment', 'emotions', 'created_at', 'updated_at']


class SalesPerformanceSerializer(serializers.ModelSerializer):
    """Serializer for SalesPerformance model."""
    
    class Meta:
        model = SalesPerformance
        fields = ['id', 'call_recording', 'talk_ratio', 'interruption_count', 
                  'avg_response_time', 'strengths', 'weaknesses', 'suggestions', 
                  'overall_score', 'created_at', 'updated_at']


class CallRecordingDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for CallRecording with nested related data."""
    
    tags = TagSerializer(many=True, read_only=True)
    transcription_available = serializers.SerializerMethodField()
    summary_available = serializers.SerializerMethodField()
    sentiment_available = serializers.SerializerMethodField()
    performance_available = serializers.SerializerMethodField()
    
    class Meta:
        model = CallRecording
        fields = ['id', 'title', 'description', 'file', 'duration', 'status', 
                  'call_date', 'call_type', 'customer_name', 'customer_company', 
                  'tags', 'transcription_available', 'summary_available', 
                  'sentiment_available', 'performance_available', 
                  'created_at', 'updated_at']
    
    def get_transcription_available(self, obj):
        """Check if transcription is available."""
        return hasattr(obj, 'transcription')
    
    def get_summary_available(self, obj):
        """Check if summary is available."""
        return hasattr(obj, 'summary')
    
    def get_sentiment_available(self, obj):
        """Check if sentiment analysis is available."""
        return hasattr(obj, 'sentiment')
    
    def get_performance_available(self, obj):
        """Check if performance analysis is available."""
        return hasattr(obj, 'performance')