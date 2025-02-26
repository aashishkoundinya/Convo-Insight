from django.urls import path
from . import views

urlpatterns = [
    path('', views.email_list, name='email_list'),
    path('<int:pk>/', views.email_detail, name='email_detail'),
    path('templates/', views.template_list, name='template_list'),
    path('templates/<int:pk>/', views.template_detail, name='template_detail'),
    path('abtests/', views.abtest_list, name='abtest_list'),
    path('abtests/<int:pk>/', views.abtest_detail, name='abtest_detail'),
]