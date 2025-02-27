from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.utils import timezone
from django.http import HttpResponse
from datetime import timedelta

from apps.call_analyzer.models import CallRecording, SentimentAnalysis
from apps.email_generator.models import GeneratedEmail, EmailAnalysis, ABTestGroup


def test_login(request):
    from django.contrib.auth import authenticate
    user = authenticate(username='admin', password='password123')
    return HttpResponse(f"Authentication result: {user is not None}")
    
@login_required
def dashboard(request):
    """
    Main dashboard view showing overview statistics and recent data.
    """
    user = request.user
    organization = user.profile.organization if hasattr(user, 'profile') else None
    
    # Filter by organization for non-admin users
    if organization and not user.is_staff:
        calls = CallRecording.objects.filter(organization=organization)
        emails = GeneratedEmail.objects.filter(organization=organization)
        tests = ABTestGroup.objects.filter(organization=organization)
    else:
        # Personal data for regular users
        calls = CallRecording.objects.filter(user=user)
        emails = GeneratedEmail.objects.filter(user=user)
        tests = ABTestGroup.objects.filter(user=user)
    
    # Calculate statistics
    stats = {
        'total_calls': calls.count(),
        'total_emails': emails.count(),
        'active_tests': tests.filter(is_active=True).count(),
        'avg_performance': calls.filter(performance__isnull=False).aggregate(
            avg=Avg('performance__overall_score')
        )['avg'] or 0,
    }
    
    # Get sentiment distribution
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    for sentiment in SentimentAnalysis.objects.filter(call_recording__in=calls):
        sentiment_counts[sentiment.overall_sentiment] = sentiment_counts.get(sentiment.overall_sentiment, 0) + 1
    
    # Calculate email performance averages
    email_performance = {
        'avg_readability': EmailAnalysis.objects.filter(email__in=emails).aggregate(
            avg=Avg('readability_score')
        )['avg'] or 0,
        'avg_spam_score': EmailAnalysis.objects.filter(email__in=emails).aggregate(
            avg=Avg('spam_score')
        )['avg'] or 0,
        'avg_engagement': EmailAnalysis.objects.filter(email__in=emails).aggregate(
            avg=Avg('engagement_score')
        )['avg'] or 0,
    }
    
    # Get recent data
    recent_calls = calls.order_by('-created_at')[:5]
    recent_emails = emails.order_by('-created_at')[:5]
    
    context = {
        'stats': stats,
        'sentiment_data': sentiment_counts,
        'email_performance': email_performance,
        'recent_calls': recent_calls,
        'recent_emails': recent_emails,
    }
    
    return render(request, 'dashboard/dashboard.html', context)


@login_required
def profile(request):
    """
    User profile view.
    """
    user = request.user
    
    if request.method == 'POST':
        # Handle profile update logic here
        pass
    
    context = {
        'user': user
    }
    
    return render(request, 'dashboard/profile.html', context)