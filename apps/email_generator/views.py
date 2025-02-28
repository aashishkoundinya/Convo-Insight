import logging
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.call_analyzer.models import CallRecording
from .models import GeneratedEmail, EmailTemplate, EmailAnalysis, ABTestGroup, ABTestVariant
from .services.generator import EmailGenerationService
from .services.analyzer import EmailAnalyzerService
from .tasks import analyze_email_async, generate_email_variants_async, create_ab_test_variants_async

logger = logging.getLogger(__name__)

class EmailTemplateViewSet(viewsets.ModelViewSet):
    """
    API endpoint for email templates.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        organization = user.profile.organization if hasattr(user, 'profile') else None
        
        # Show the user's templates and public org templates
        if organization:
            return EmailTemplate.objects.filter(
                (models.Q(user=user) | models.Q(organization=organization, is_public=True))
            ).order_by('-created_at')
        return EmailTemplate.objects.filter(user=user).order_by('-created_at')
    
    def get_serializer_class(self):
        from .serializers import EmailTemplateSerializer
        return EmailTemplateSerializer
    
    def perform_create(self, serializer):
        # Save with user and organization
        serializer.save(
            user=self.request.user,
            organization=self.request.user.profile.organization if hasattr(self.request.user, 'profile') else None
        )


class GeneratedEmailViewSet(viewsets.ModelViewSet):
    """
    API endpoint for generated emails.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        organization = user.profile.organization if hasattr(user, 'profile') else None
        
        # Show only the user's emails, or all org emails for admins
        if user.is_staff and organization:
            return GeneratedEmail.objects.filter(organization=organization).order_by('-created_at')
        return GeneratedEmail.objects.filter(user=user).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            from .serializers import EmailGenerationSerializer
            return EmailGenerationSerializer
        else:
            from .serializers import GeneratedEmailSerializer
            return GeneratedEmailSerializer
    
    def create(self, request, *args, **kwargs):
        """
        Generate a new email based on call insights.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get validated data
        call_id = serializer.validated_data.get('call_recording_id')
        tone = serializer.validated_data.get('tone', 'professional')
        template_id = serializer.validated_data.get('template_id')
        
        # Get the call recording
        call_recording = get_object_or_404(CallRecording, id=call_id)
        
        # Check if the call has been processed
        if call_recording.status != 'processed':
            return Response({
                "detail": "Call recording has not been fully processed yet."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get template if provided
        template = None
        if template_id:
            template = get_object_or_404(EmailTemplate, id=template_id)
        
        # Generate the email
        service = EmailGenerationService()
        email = service.generate_email(
            call_recording=call_recording,
            tone=tone,
            user=request.user,
            organization=request.user.profile.organization if hasattr(request.user, 'profile') else None,
            template=template
        )
        
        if not email:
            return Response({
                "detail": "Failed to generate email."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Start async analysis
        analyze_email_async.delay(email.id)
        
        # Return the created email
        from .serializers import GeneratedEmailSerializer
        return Response(
            GeneratedEmailSerializer(email).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        """
        Manually trigger analysis for a generated email.
        """
        email = self.get_object()
        
        # Start analysis
        service = EmailAnalyzerService()
        analysis = service.analyze_email(email)
        
        if not analysis:
            return Response({
                "detail": "Failed to analyze email."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Return the analysis
        from .serializers import EmailAnalysisSerializer
        return Response(EmailAnalysisSerializer(analysis).data)
    
    @action(detail=True, methods=['get'])
    def analysis(self, request, pk=None):
        """
        Get the analysis for a generated email.
        """
        email = self.get_object()
        
        try:
            analysis = email.analysis
            from .serializers import EmailAnalysisSerializer
            serializer = EmailAnalysisSerializer(analysis)
            return Response(serializer.data)
        except EmailAnalysis.DoesNotExist:
            return Response({
                "detail": "Analysis not available."
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def variant(self, request, pk=None):
        """
        Create a variant of an existing email with different tone.
        """
        original_email = self.get_object()
        
        # Get the tone from request
        tone = request.data.get('tone', 'professional')
        
        # We need the call recording
        call_recording = original_email.call_recording
        if not call_recording:
            return Response({
                "detail": "Cannot create variant because the original email is not linked to a call recording."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate the variant
        service = EmailGenerationService()
        variant_email = service.generate_email(
            call_recording=call_recording,
            tone=tone,
            user=request.user,
            organization=request.user.profile.organization if hasattr(request.user, 'profile') else None,
            template=original_email.template
        )
        
        if not variant_email:
            return Response({
                "detail": "Failed to generate variant email."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Update parent reference
        variant_email.parent = original_email
        variant_email.version = original_email.version + 1
        variant_email.save()
        
        # Start async analysis
        analyze_email_async.delay(variant_email.id)
        
        # Return the created variant
        from .serializers import GeneratedEmailSerializer
        return Response(
            GeneratedEmailSerializer(variant_email).data,
            status=status.HTTP_201_CREATED
        )


class ABTestViewSet(viewsets.ModelViewSet):
    """
    API endpoint for A/B testing email variants.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        organization = user.profile.organization if hasattr(user, 'profile') else None
        
        # Show only the user's test groups, or all org test groups for admins
        if user.is_staff and organization:
            return ABTestGroup.objects.filter(organization=organization).order_by('-created_at')
        return ABTestGroup.objects.filter(user=user).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'retrieve' or self.action == 'list':
            from .serializers import ABTestGroupDetailSerializer
            return ABTestGroupDetailSerializer
        else:
            from .serializers import ABTestGroupSerializer
            return ABTestGroupSerializer
    
    def perform_create(self, serializer):
        # Save with user and organization
        serializer.save(
            user=self.request.user,
            organization=self.request.user.profile.organization if hasattr(self.request.user, 'profile') else None
        )
    
    @action(detail=True, methods=['post'])
    def add_variant(self, request, pk=None):
        """
        Add an email variant to the test group.
        """
        test_group = self.get_object()
        
        # Get the email ID from request
        email_id = request.data.get('email_id')
        if not email_id:
            return Response({
                "detail": "Email ID is required."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the label from request
        label = request.data.get('label', f"Variant {test_group.variants.count() + 1}")
        
        # Get the email
        email = get_object_or_404(GeneratedEmail, id=email_id)
        
        # Create the variant
        variant = ABTestVariant.objects.create(
            group=test_group,
            email=email,
            label=label,
            description=request.data.get('description', '')
        )
        
        # Return the created variant
        from .serializers import ABTestVariantSerializer
        return Response(
            ABTestVariantSerializer(variant).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def update_metrics(self, request, pk=None):
        """
        Update metrics for a test variant.
        """
        test_group = self.get_object()
        
        # Get the variant ID and metrics from request
        variant_id = request.data.get('variant_id')
        if not variant_id:
            return Response({
                "detail": "Variant ID is required."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the variant
        variant = get_object_or_404(ABTestVariant, id=variant_id, group=test_group)
        
        # Update metrics if provided
        if 'sent_count' in request.data:
            variant.sent_count = request.data['sent_count']
        if 'open_count' in request.data:
            variant.open_count = request.data['open_count']
        if 'click_count' in request.data:
            variant.click_count = request.data['click_count']
        if 'reply_count' in request.data:
            variant.reply_count = request.data['reply_count']
        
        variant.save()
        
        # Return the updated variant
        from .serializers import ABTestVariantSerializer
        return Response(ABTestVariantSerializer(variant).data)
    
    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        """
        Get comparative results for all variants in the test group.
        """
        test_group = self.get_object()
        variants = test_group.variants.all()
        
        if not variants:
            return Response({
                "detail": "No variants in this test group."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate comparative metrics
        results = []
        for variant in variants:
            results.append({
                "id": variant.id,
                "label": variant.label,
                "email_subject": variant.email.subject,
                "email_tone": variant.email.tone,
                "metrics": {
                    "sent_count": variant.sent_count,
                    "open_count": variant.open_count,
                    "click_count": variant.click_count,
                    "reply_count": variant.reply_count,
                    "open_rate": variant.open_rate,
                    "click_rate": variant.click_rate,
                    "reply_rate": variant.reply_rate
                }
            })
        
        return Response(results)


# Template Views for web interface

@login_required
def email_list(request):
    """
    View to display the list of generated emails.
    """
    user = request.user
    
    # Get emails based on user role
    if user.is_staff and hasattr(user, 'profile') and user.profile.organization:
        emails = GeneratedEmail.objects.filter(organization=user.profile.organization).order_by('-created_at')
    else:
        emails = GeneratedEmail.objects.filter(user=user).order_by('-created_at')
    
    context = {
        'emails': emails
    }
    
    return render(request, 'email_generator/email_list.html', context)


@login_required
def email_detail(request, pk):
    """
    View to display the details of a generated email.
    """
    email = get_object_or_404(GeneratedEmail, pk=pk)
    
    # Check permission
    if not request.user.is_staff and email.user != request.user:
        messages.error(request, "You do not have permission to view this email.")
        return redirect('email_list')
    
    # Get analysis if available
    try:
        analysis = email.analysis
    except:
        analysis = None
    
    # Get variants if available
    variants = email.variations.all()
    
    context = {
        'email': email,
        'analysis': analysis,
        'variants': variants
    }
    
    return render(request, 'email_generator/email_detail.html', context)


@login_required
def analyze_email_view(request, pk):
    """
    View to manually trigger analysis for an email.
    """
    email = get_object_or_404(GeneratedEmail, pk=pk)
    
    # Check permission
    if not request.user.is_staff and email.user != request.user:
        messages.error(request, "You do not have permission to analyze this email.")
        return redirect('email_list')
    
    # Analyze the email
    service = EmailAnalyzerService()
    analysis = service.analyze_email(email)
    
    if analysis:
        messages.success(request, "Email analysis completed successfully.")
    else:
        messages.error(request, "Failed to analyze email. Please try again.")
    
    return redirect('email_detail', pk=pk)


@login_required
def template_list(request):
    """
    View to display the list of email templates.
    """
    user = request.user
    
    # Get templates based on user role
    if user.is_staff and hasattr(user, 'profile') and user.profile.organization:
        templates = EmailTemplate.objects.filter(
            models.Q(user=user) | 
            models.Q(organization=user.profile.organization, is_public=True)
        ).order_by('-created_at')
    else:
        templates = EmailTemplate.objects.filter(user=user).order_by('-created_at')
    
    context = {
        'templates': templates
    }
    
    return render(request, 'email_generator/template_list.html', context)


@login_required
def template_detail(request, pk):
    """
    View to display the details of an email template.
    """
    template = get_object_or_404(EmailTemplate, pk=pk)
    
    # Check permission
    is_org_public = (template.organization and template.is_public and 
                     hasattr(request.user, 'profile') and 
                     request.user.profile.organization == template.organization)
    
    if not request.user.is_staff and template.user != request.user and not is_org_public:
        messages.error(request, "You do not have permission to view this template.")
        return redirect('template_list')
    
    context = {
        'template': template
    }
    
    return render(request, 'email_generator/template_detail.html', context)


@login_required
def abtest_list(request):
    """
    View to display the list of A/B test groups.
    """
    user = request.user
    
    # Get test groups based on user role
    if user.is_staff and hasattr(user, 'profile') and user.profile.organization:
        tests = ABTestGroup.objects.filter(organization=user.profile.organization).order_by('-created_at')
    else:
        tests = ABTestGroup.objects.filter(user=user).order_by('-created_at')
    
    context = {
        'tests': tests
    }
    
    return render(request, 'email_generator/abtest_list.html', context)


@login_required
def abtest_detail(request, pk):
    """
    View to display the details of an A/B test group.
    """
    test = get_object_or_404(ABTestGroup, pk=pk)
    
    # Check permission
    if not request.user.is_staff and test.user != request.user:
        messages.error(request, "You do not have permission to view this test.")
        return redirect('abtest_list')
    
    # Get variants
    variants = test.variants.all()
    
    context = {
        'test': test,
        'variants': variants
    }
    
    return render(request, 'email_generator/abtest_detail.html', context)