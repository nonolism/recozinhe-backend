from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from rest_framework import filters, permissions, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apirecozinhe import ai, services
from apirecozinhe.models import *
from apirecozinhe.serializers import *


class ApiReCozinheViewSet(ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]


# --------------------------------------------------------------------------
# Autenticação  (Login / Criar conta)
# --------------------------------------------------------------------------
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(username=username, password=password)

        if user is None:
            return Response({"detail": "Usuário ou senha inválidos."}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(LoginSerializer(user, many=False).data)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(LoginSerializer(user).data, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------
# Perfil e impacto
# --------------------------------------------------------------------------
class ProfileView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        data = ProfileSerializer(request.user, context={'request': request}).data
        data['stats'] = services.profile_stats(request.user)
        return Response(data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ImpactView(APIView):
    """Acompanhamento do impacto: totais, evolução mês a mês e alimentos mais salvos."""

    def get(self, request):
        months = min(int(request.query_params.get('months', 6) or 6), 24)
        return Response(services.impact_history(request.user, months=months))


# --------------------------------------------------------------------------
# Receitas
# --------------------------------------------------------------------------
class CategoryViewSet(ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class RecipeViewSet(ReadOnlyModelViewSet):
    """
    GET /api/recipes/?search=limão&category=doces&source=ia
    GET /api/recipes/{id}/
    GET /api/recipes/suggested/?photo=<id>&category=&search=
    """
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'key_ingredients__name', 'ingredient_lines__description']

    def get_queryset(self):
        # Receitas do catálogo são de todos; as geradas pela IA só aparecem para quem tirou a foto
        qs = (Recipe.objects.filter(source=Recipe.SOURCE_CATALOG)
              | Recipe.objects.filter(source=Recipe.SOURCE_AI, created_from_photo__user=self.request.user))
        qs = qs.select_related('category', 'created_from_photo').prefetch_related('ingredient_lines')

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)

        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)

        return qs.distinct()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return RecipeDetailSerializer
        return RecipeListSerializer

    @action(detail=False, methods=['get'])
    def suggested(self, request):
        photo = None
        photo_id = request.query_params.get('photo')
        if photo_id:
            photo = get_object_or_404(Photo, pk=photo_id, user=request.user)

        qs = services.suggested_recipes(request.user, photo=photo)
        qs = qs.filter(pk__in=self.get_queryset().values('pk'))  # aplica category/source da URL
        qs = self.filter_queryset(qs)

        return Response(RecipeListSerializer(qs, many=True, context={'request': request}).data)


# --------------------------------------------------------------------------
# Fotos  (Câmera / Galeria  +  Histórico de Fotos)
# --------------------------------------------------------------------------
class PhotoViewSet(ApiReCozinheViewSet):
    """
    POST /api/photos/            envia a foto (campo image, source=camera|galeria) e já recebe a análise
    GET  /api/photos/            histórico
    GET  /api/photos/{id}/       análise completa (alimento, receitas, dicas)
    GET  /api/photos/latest/     card "Identificado agora"
    POST /api/photos/{id}/regenerate/   pede outras receitas para a IA
    """
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        qs = Photo.objects.filter(user=self.request.user).select_related('identified_ingredient')

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return PhotoSerializer
        return PhotoDetailSerializer

    def create(self, request, *args, **kwargs):
        try:
            services.check_daily_limit(request.user)
        except services.DailyLimitReached as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        serializer = PhotoSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        hint = serializer.validated_data.pop('ingredient_name', None)
        photo = serializer.save(user=request.user)

        services.process_photo(photo, hint=hint)

        data = PhotoDetailSerializer(photo, context={'request': request}).data
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        photo = self.get_queryset().filter(status=Photo.STATUS_IDENTIFIED).first()
        if photo is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(PhotoSerializer(photo, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        photo = self.get_object()
        try:
            services.check_daily_limit(request.user)
            recipes = services.regenerate_recipes(photo)
        except services.DailyLimitReached as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ai.AIError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(RecipeListSerializer(recipes, many=True, context={'request': request}).data)


# --------------------------------------------------------------------------
# Reaproveitamentos  ("Fiz essa receita" / "Segui essa dica")
# --------------------------------------------------------------------------
class ReuseViewSet(ApiReCozinheViewSet):
    serializer_class = ReuseSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        qs = Reuse.objects.filter(user=self.request.user).select_related('recipe__category', 'recipe__created_from_photo')

        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
