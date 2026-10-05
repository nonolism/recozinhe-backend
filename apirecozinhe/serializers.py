from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from apirecozinhe.models import *


# --------------------------------------------------------------------------
# Usuário
# --------------------------------------------------------------------------
class LoginSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['token', 'username', 'email', 'first_name', 'last_name']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class ProfileSerializer(serializers.ModelSerializer):
    member_since = serializers.DateTimeField(source='date_joined', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'monthly_goal_kg', 'member_since']
        read_only_fields = ['id', 'username']


# --------------------------------------------------------------------------
# Receitas
# --------------------------------------------------------------------------
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ['id', 'name']


class RecipeListSerializer(serializers.ModelSerializer):
    """Cards das listas: imagem, categoria, título, tempo e dificuldade."""
    category = CategorySerializer(read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ['id', 'title', 'description', 'image', 'category', 'prep_time_minutes',
                  'difficulty', 'difficulty_display', 'source']

    def get_image(self, obj):
        # Receita da IA não tem foto própria: usamos a foto do alimento que o usuário tirou
        image = obj.image or (obj.created_from_photo.image if obj.created_from_photo_id else None)
        if not image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(image.url) if request else image.url


class RecipeDetailSerializer(RecipeListSerializer):
    """Tela 'Receita aberta': inclui ingredientes e modo de preparo."""
    ingredients = serializers.SerializerMethodField()
    preparation_steps = serializers.SerializerMethodField()

    class Meta(RecipeListSerializer.Meta):
        fields = RecipeListSerializer.Meta.fields + ['ingredients', 'preparation_steps', 'estimated_saved_kg']

    def get_ingredients(self, obj):
        return [line.description for line in obj.ingredient_lines.all()]

    def get_preparation_steps(self, obj):
        return [line.strip() for line in obj.preparation.splitlines() if line.strip()]


# --------------------------------------------------------------------------
# Fotos
# --------------------------------------------------------------------------
class ReuseTipSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReuseTip
        fields = ['id', 'title', 'description']


class PhotoSerializer(serializers.ModelSerializer):
    """Lista do Histórico de Fotos e envio de foto nova."""
    identified_ingredient = IngredientSerializer(read_only=True)
    # Dica opcional do usuário (ex.: corrige "não é limão, é laranja")
    ingredient_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Photo
        fields = ['id', 'image', 'source', 'status', 'identified_ingredient', 'food_part', 'condition',
                  'confidence', 'estimated_weight_g', 'ai_message', 'ingredient_name', 'timestamp_create']
        read_only_fields = ['status', 'food_part', 'condition', 'confidence', 'estimated_weight_g',
                            'ai_message', 'timestamp_create']


class PhotoDetailSerializer(PhotoSerializer):
    """Resultado completo de uma análise: alimento + receitas + formas de reaproveitamento."""
    suggested_recipes = RecipeListSerializer(many=True, read_only=True)
    reuse_tips = ReuseTipSerializer(many=True, read_only=True)

    class Meta(PhotoSerializer.Meta):
        fields = PhotoSerializer.Meta.fields + ['suggested_recipes', 'reuse_tips']


# --------------------------------------------------------------------------
# Impacto
# --------------------------------------------------------------------------
class ReuseSerializer(serializers.ModelSerializer):
    recipe_detail = RecipeListSerializer(source='recipe', read_only=True)

    class Meta:
        model = Reuse
        fields = ['id', 'photo', 'recipe', 'recipe_detail', 'tip', 'saved_kg', 'reused_at']
        extra_kwargs = {'saved_kg': {'required': False}, 'reused_at': {'required': False}}

    def validate(self, attrs):
        user = self.context['request'].user
        photo, recipe, tip = attrs.get('photo'), attrs.get('recipe'), attrs.get('tip')

        if not (photo or recipe or tip):
            raise serializers.ValidationError('Informe a foto, a receita ou a dica que foi reaproveitada.')
        if photo and photo.user != user:
            raise serializers.ValidationError({'photo': 'Foto não encontrada.'})
        if recipe and recipe.source == Recipe.SOURCE_AI and recipe.created_from_photo.user != user:
            raise serializers.ValidationError({'recipe': 'Receita não encontrada.'})
        if tip and tip.photo.user != user:
            raise serializers.ValidationError({'tip': 'Dica não encontrada.'})
        if tip and not photo:
            attrs['photo'] = tip.photo
        return attrs

    def create(self, validated_data):
        if 'saved_kg' not in validated_data:
            validated_data['saved_kg'] = self._estimate_kg(validated_data)
        validated_data.setdefault('reused_at', timezone.localdate())
        return super().create(validated_data)

    @staticmethod
    def _estimate_kg(data):
        """Sem peso informado: usa o peso estimado pela IA na foto, ou o da receita."""
        photo, recipe = data.get('photo'), data.get('recipe')
        if photo and photo.estimated_weight_g:
            return (Decimal(photo.estimated_weight_g) / 1000).quantize(Decimal('0.01'))
        if recipe:
            return recipe.estimated_saved_kg
        return Decimal('0.30')
