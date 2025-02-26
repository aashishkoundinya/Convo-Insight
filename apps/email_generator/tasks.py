import logging
from celery import shared_task
from .models import GeneratedEmail
from .services.analyzer import EmailAnalyzerService

logger = logging.getLogger(__name__)

@shared_task
def analyze_email_async(email_id):
    """
    Analyze a generated email asynchronously.
    
    Args:
        email_id: ID of the GeneratedEmail to analyze
    """
    logger.info(f"Starting async analysis for email: {email_id}")
    
    try:
        # Get the email
        email = GeneratedEmail.objects.get(id=email_id)
        
        # Analyze email
        analyzer_service = EmailAnalyzerService()
        analysis = analyzer_service.analyze_email(email)
        
        if not analysis:
            logger.error(f"Analysis failed for email: {email_id}")
            return
        
        logger.info(f"Completed analysis for email: {email_id}")
        
    except Exception as e:
        logger.error(f"Error analyzing email {email_id}: {str(e)}")


@shared_task
def generate_email_variants_async(email_id, tones=None):
    """
    Generate variants of an email with different tones.
    
    Args:
        email_id: ID of the original GeneratedEmail
        tones: List of tones to generate variants for. If None, generates all possible tones.
    """
    from .services.generator import EmailGenerationService
    
    logger.info(f"Starting async variant generation for email: {email_id}")
    
    try:
        # Get the original email
        original_email = GeneratedEmail.objects.get(id=email_id)
        
        # Check if we have a call recording
        if not original_email.call_recording:
            logger.error(f"Cannot generate variants - no call recording associated with email: {email_id}")
            return
        
        # Get all possible tones if not specified
        if not tones:
            tones = [tone[0] for tone in GeneratedEmail.TONE_CHOICES]
            # Remove the original tone to avoid duplicates
            if original_email.tone in tones:
                tones.remove(original_email.tone)
        
        # Generate a variant for each tone
        generator_service = EmailGenerationService()
        for tone in tones:
            logger.info(f"Generating {tone} variant for email: {email_id}")
            
            variant = generator_service.generate_email(
                call_recording=original_email.call_recording,
                tone=tone,
                user=original_email.user,
                organization=original_email.organization,
                template=original_email.template
            )
            
            if variant:
                # Update parent reference
                variant.parent = original_email
                variant.version = original_email.version + 1
                variant.save()
                
                # Analyze the variant
                analyze_email_async.delay(variant.id)
            else:
                logger.warning(f"Failed to generate {tone} variant for email: {email_id}")
        
        logger.info(f"Completed variant generation for email: {email_id}")
        
    except Exception as e:
        logger.error(f"Error generating variants for email {email_id}: {str(e)}")


@shared_task
def create_ab_test_variants_async(email_id, test_group_id):
    """
    Create A/B test variants from an email and its variations.
    
    Args:
        email_id: ID of the original GeneratedEmail
        test_group_id: ID of the ABTestGroup to add variants to
    """
    from .models import ABTestGroup, ABTestVariant
    
    logger.info(f"Creating A/B test variants for email: {email_id}")
    
    try:
        # Get the original email
        original_email = GeneratedEmail.objects.get(id=email_id)
        
        # Get the test group
        test_group = ABTestGroup.objects.get(id=test_group_id)
        
        # Add the original email as a variant
        variant = ABTestVariant.objects.create(
            group=test_group,
            email=original_email,
            label=f"Original ({original_email.tone})",
            description=f"Original email with {original_email.tone} tone"
        )
        
        # Add all variations as variants
        for i, variation in enumerate(original_email.variations.all()):
            ABTestVariant.objects.create(
                group=test_group,
                email=variation,
                label=f"Variant {i+1} ({variation.tone})",
                description=f"Variant email with {variation.tone} tone"
            )
        
        logger.info(f"Completed creating A/B test variants for email: {email_id}")
        
    except Exception as e:
        logger.error(f"Error creating A/B test variants for email {email_id}: {str(e)}")