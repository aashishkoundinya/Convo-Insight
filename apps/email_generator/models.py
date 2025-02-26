from django.db import models
from django.contrib.auth.models import User
from apps.core.models import TimeStampedModel, Tag, Organization
from apps.call_analyzer.models import CallRecording


class EmailTemplate(TimeStampedModel):
    """
    Represents an email template that can be used for generating emails.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    subject_template = models.CharField(max_length=255)
    body_template = models.TextField()
    
    # Template categorization
    purpose = models.CharField(max_length=50)  # e.g., 'cold outreach', 'follow-up', 'meeting request'
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_templates')
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='email_templates',
        null=True, blank=True
    )
    tags = models.ManyToManyField(Tag, related_name='email_templates', blank=True)
    
    is_public = models.BooleanField(default=False)  # If True, available to all org members
    
    def __str__(self):
        return self.name


class GeneratedEmail(TimeStampedModel):
    """
    Represents an AI-generated email based on call insights.
    """
    TONE_CHOICES = (
        ('professional', 'Professional'),
        ('friendly', 'Friendly'),
        ('persuasive', 'Persuasive'),
        ('urgent', 'Urgent'),
        ('formal', 'Formal'),
        ('casual', 'Casual'),
    )
    
    subject = models.CharField(max_length=255)
    body = models.TextField()
    
    # Generation parameters
    tone = models.CharField(max_length=20, choices=TONE_CHOICES, default='professional')
    target_length = models.CharField(max_length=20, default='medium')  # 'short', 'medium', 'long'
    
    # Source data
    call_recording = models.ForeignKey(
        CallRecording, 
        on_delete=models.SET_NULL, 
        related_name='generated_emails',
        null=True, blank=True
    )
    template = models.ForeignKey(
        EmailTemplate, 
        on_delete=models.SET_NULL, 
        related_name='generated_emails',
        null=True, blank=True
    )
    
    # Creation metadata
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_emails')
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='generated_emails',
        null=True, blank=True
    )
    
    # Version tracking
    version = models.IntegerField(default=1)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        related_name='variations',
        null=True, blank=True
    )
    
    def __str__(self):
        return self.subject


class EmailAnalysis(TimeStampedModel):
    """
    Represents analytics and quality assessment for a generated email.
    """
    email = models.OneToOneField(
        GeneratedEmail, 
        on_delete=models.CASCADE, 
        related_name='analysis'
    )
    
    # Quality metrics (0-100 scores)
    readability_score = models.FloatField()
    spam_score = models.FloatField()  # Higher means more likely to be spam
    engagement_score = models.FloatField()
    overall_score = models.FloatField()
    
    # Detailed analysis
    strengths = models.JSONField(default=list)
    weaknesses = models.JSONField(default=list)
    suggestions = models.JSONField(default=list)
    
    # Readability metrics
    word_count = models.IntegerField()
    avg_sentence_length = models.FloatField()
    complexity_score = models.FloatField()  # Based on vocabulary and sentence structure
    
    def __str__(self):
        return f"Analysis for email: {self.email.subject}"


class ABTestGroup(TimeStampedModel):
    """
    Represents a group of email variations for A/B testing.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ab_test_groups')
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='ab_test_groups',
        null=True, blank=True
    )
    
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.name


class ABTestVariant(TimeStampedModel):
    """
    Represents a specific variant in an A/B test.
    """
    group = models.ForeignKey(
        ABTestGroup, 
        on_delete=models.CASCADE, 
        related_name='variants'
    )
    email = models.ForeignKey(
        GeneratedEmail, 
        on_delete=models.CASCADE, 
        related_name='ab_test_variants'
    )
    
    # Variant metadata
    label = models.CharField(max_length=50)  # e.g., 'A', 'B', 'Professional', 'Friendly'
    description = models.TextField(blank=True, null=True)
    
    # Performance metrics
    sent_count = models.IntegerField(default=0)
    open_count = models.IntegerField(default=0)
    click_count = models.IntegerField(default=0)
    reply_count = models.IntegerField(default=0)
    
    @property
    def open_rate(self):
        """Calculate the open rate for this variant."""
        return (self.open_count / self.sent_count) if self.sent_count > 0 else 0
    
    @property
    def click_rate(self):
        """Calculate the click rate for this variant."""
        return (self.click_count / self.open_count) if self.open_count > 0 else 0
    
    @property
    def reply_rate(self):
        """Calculate the reply rate for this variant."""
        return (self.reply_count / self.sent_count) if self.sent_count > 0 else 0
    
    def __str__(self):
        return f"{self.group.name} - Variant {self.label}"