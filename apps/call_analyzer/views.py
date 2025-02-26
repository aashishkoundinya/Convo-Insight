# import logging
# from django.shortcuts import get_object_or_404, render, redirect
# from django.contrib.auth.decorators import login_required
# from django.conf import settings
# from django.contrib import messages
# from django.core.exceptions import ValidationError
# from rest_framework import viewsets, status, permissions
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.parsers import MultiPartParser, FormParser

import logging
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError

from .models import CallRecording, Transcription, CallSummary, SentimentAnalysis, SalesPerformance
from .services.transcription import TranscriptionService
from .services.sentiment import SentimentAnalysisService
from .services.summarization import SummarizationService
from .tasks import process_call_recording_async

logger = logging.getLogger(__name__)

class CallRecordingViewSet(viewsets.ModelViewSet):
    """
    API endpoint for call recordings.
    """
    parser_classes = (MultiPartParser, FormParser)
    
    def get_queryset(self):
        user = self.request.user
        # Show only the user's recordings, or all recordings for admins
        if user.is_staff:
            return CallRecording.objects.all().order_by('-created_at')
        return CallRecording.objects.filter(user=user).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create' or self.action == 'update':
            from .serializers import CallRecordingCreateSerializer
            return CallRecordingCreateSerializer
        else:
            from .serializers import CallRecordingDetailSerializer
            return CallRecordingDetailSerializer
    
    def perform_create(self, serializer):
        """
        When a new call recording is uploaded, save it and start processing.
        """
        # Validate file size
        file = self.request.FILES.get('file')
        if file and file.size > settings.MAX_CALL_FILE_SIZE:
            raise ValidationError(f"File size exceeds the limit of {settings.MAX_CALL_FILE_SIZE / 1024 / 1024}MB.")
        
        # Validate file type
        if file.content_type not in settings.ALLOWED_CALL_FILE_TYPES:
            raise ValidationError(f"File type {file.content_type} is not supported.")
        
        # Save with user and organization
        call_recording = serializer.save(
            user=self.request.user,
            organization=self.request.user.profile.organization if hasattr(self.request.user, 'profile') else None,
            status='pending'
        )
        
        # Start async processing
        process_call_recording_async.delay(call_recording.id)
        
        return call_recording
    
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """
        Manually trigger processing for a call recording.
        """
        call_recording = self.get_object()
        
        # Check if the call is already being processed
        if call_recording.status == 'processing':
            return Response(
                {"detail": "This call is already being processed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Start processing
        call_recording.status = 'processing'
        call_recording.save()
        
        # Start async task
        process_call_recording_async.delay(call_recording.id)
        
        return Response({"detail": "Processing started."})
    
    @action(detail=True, methods=['get'])
    def transcription(self, request, pk=None):
        """
        Get the transcription for a call recording.
        """
        call_recording = self.get_object()
        
        try:
            transcription = call_recording.transcription
            from .serializers import TranscriptionSerializer
            serializer = TranscriptionSerializer(transcription)
            return Response(serializer.data)
        except Transcription.DoesNotExist:
            return Response(
                {"detail": "Transcription not available."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """
        Get the summary for a call recording.
        """
        call_recording = self.get_object()
        
        try:
            summary = call_recording.summary
            from .serializers import CallSummarySerializer
            serializer = CallSummarySerializer(summary)
            return Response(serializer.data)
        except CallSummary.DoesNotExist:
            return Response(
                {"detail": "Summary not available."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def sentiment(self, request, pk=None):
        """
        Get the sentiment analysis for a call recording.
        """
        call_recording = self.get_object()
        
        try:
            sentiment = call_recording.sentiment
            from .serializers import SentimentAnalysisSerializer
            serializer = SentimentAnalysisSerializer(sentiment)
            return Response(serializer.data)
        except SentimentAnalysis.DoesNotExist:
            return Response(
                {"detail": "Sentiment analysis not available."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """
        Get the sales performance analysis for a call recording.
        """
        call_recording = self.get_object()
        
        try:
            performance = call_recording.performance
            from .serializers import SalesPerformanceSerializer
            serializer = SalesPerformanceSerializer(performance)
            return Response(serializer.data)
        except SalesPerformance.DoesNotExist:
            return Response(
                {"detail": "Performance analysis not available."},
                status=status.HTTP_404_NOT_FOUND
            )


class CallAnalyticsView(viewsets.ViewSet):
    """
    API endpoint for aggregated call analytics.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """
        Get an overview of call analytics.
        """
        user = request.user
        organization = user.profile.organization if hasattr(user, 'profile') else None
        
        # Filter by organization if applicable
        if organization and not user.is_staff:
            calls = CallRecording.objects.filter(organization=organization)
        else:
            calls = CallRecording.objects.filter(user=user)
        
        # Get counts
        total_calls = calls.count()
        processed_calls = calls.filter(status='processed').count()
        
        # Get average sentiment
        positive_sentiment = 0
        neutral_sentiment = 0
        negative_sentiment = 0
        
        for call in calls:
            try:
                sentiment = call.sentiment.overall_sentiment
                if sentiment == 'positive':
                    positive_sentiment += 1
                elif sentiment == 'neutral':
                    neutral_sentiment += 1
                elif sentiment == 'negative':
                    negative_sentiment += 1
            except:
                # No sentiment analysis available
                pass
        
        # Get average performance
        total_score = 0
        scored_calls = 0
        
        for call in calls:
            try:
                score = call.performance.overall_score
                if score is not None:
                    total_score += score
                    scored_calls += 1
            except:
                # No performance analysis available
                pass
        
        avg_performance = total_score / scored_calls if scored_calls > 0 else None
        
        return Response({
            "total_calls": total_calls,
            "processed_calls": processed_calls,
            "sentiment_breakdown": {
                "positive": positive_sentiment,
                "neutral": neutral_sentiment,
                "negative": negative_sentiment
            },
            "avg_performance_score": avg_performance
        })


# Template Views for web interface

@login_required
def call_list(request):
    """
    View to display the list of call recordings.
    """
    user = request.user
    
    # Get calls based on user role
    if user.is_staff and hasattr(user, 'profile') and user.profile.organization:
        calls = CallRecording.objects.filter(organization=user.profile.organization).order_by('-created_at')
    else:
        calls = CallRecording.objects.filter(user=user).order_by('-created_at')
    
    context = {
        'calls': calls
    }
    
    return render(request, 'call_analyzer/call_list.html', context)


@login_required
def call_detail(request, pk):
    """
    View to display the details of a call recording.
    """
    call = get_object_or_404(CallRecording, pk=pk)
    
    # Check permission
    if not request.user.is_staff and call.user != request.user:
        messages.error(request, "You do not have permission to view this call.")
        return redirect('call_list')
    
    context = {
        'call': call
    }
    
    return render(request, 'call_analyzer/call_detail.html', context)


@login_required
def call_upload(request):
    """
    View to upload a new call recording.
    """
    if request.method == 'POST':
        # Handle file upload
        file = request.FILES.get('file')
        title = request.POST.get('title')
        description = request.POST.get('description')
        
        if not file:
            messages.error(request, "Please select a file to upload.")
            return render(request, 'call_analyzer/call_upload.html')
        
        # Validate file size
        if file.size > settings.MAX_CALL_FILE_SIZE:
            messages.error(request, f"File size exceeds the limit of {settings.MAX_CALL_FILE_SIZE / 1024 / 1024}MB.")
            return render(request, 'call_analyzer/call_upload.html')
        
        # Validate file type
        if file.content_type not in settings.ALLOWED_CALL_FILE_TYPES:
            messages.error(request, f"File type {file.content_type} is not supported.")
            return render(request, 'call_analyzer/call_upload.html')
        
        # Create call recording
        call = CallRecording.objects.create(
            title=title or file.name,
            description=description or "",
            file=file,
            user=request.user,
            organization=request.user.profile.organization if hasattr(request.user, 'profile') else None,
            status='pending'
        )
        
        # Start async processing
        process_call_recording_async.delay(call.id)
        
        messages.success(request, "Call recording uploaded successfully and is being processed.")
        return redirect('call_detail', pk=call.id)
    
    return render(request, 'call_analyzer/call_upload.html')