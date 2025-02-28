from django.urls import path
from . import views

urlpatterns = [
    path('', views.call_list, name='call_list'),
    path('<int:pk>/', views.call_detail, name='call_detail'),
    path('upload/', views.call_upload, name='call_upload'),
    path('<int:pk>/generate-email/', views.generate_email, name='generate_email')
]