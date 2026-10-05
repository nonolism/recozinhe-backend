from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apirecozinhe.views import *

router = DefaultRouter()

router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'recipes', RecipeViewSet, basename='recipe')
router.register(r'photos', PhotoViewSet, basename='photo')
router.register(r'reuses', ReuseViewSet, basename='reuse')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/login/', LoginView.as_view()),
    path('api/register/', RegisterView.as_view()),
    path('api/profile/', ProfileView.as_view()),
    path('api/impact/', ImpactView.as_view()),
    path('api-auth/', include('rest_framework.urls')),  # login do navegador
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
