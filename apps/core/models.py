from django.db import models
from django.contrib.auth.models import User

class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    `created_at` and `updated_at` fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    """
    Represents a company or organization that is using the system.
    """
    name = models.CharField(max_length=100)
    industry = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return self.name


class Profile(TimeStampedModel):
    """
    Extends the built-in User model with additional fields.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='members',
        null=True, blank=True
    )
    position = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.organization.name if self.organization else 'No Organization'}"


class Tag(TimeStampedModel):
    """
    Tags can be applied to various entities for better organization.
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name