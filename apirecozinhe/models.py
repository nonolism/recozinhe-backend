from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class ReCozinheModel(models.Model):
    timestamp_create = models.DateTimeField(auto_now_add=True)
    timestamp_update = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --------------------------------------------------------------------------
# Usuário  (telas: Login, Criar conta, Perfil)
# --------------------------------------------------------------------------
class User(AbstractUser, ReCozinheModel):
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    # "Meta mensal" do card do perfil, em kg de alimento reaproveitado por mês
    monthly_goal_kg = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))

    @property
    def token(self):
        from rest_framework.authtoken.models import Token

        return Token.objects.get_or_create(user=self)[0].key


# --------------------------------------------------------------------------
# Alimentos e receitas
# --------------------------------------------------------------------------
class Category(ReCozinheModel):
    """Abas das telas de receitas: Sopas, Petiscos, Doces, Bebidas, Pratos."""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Ingredient(ReCozinheModel):
    """Um alimento que a IA pode identificar (ex.: Limão Siciliano)."""
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Recipe(ReCozinheModel):
    SOURCE_CATALOG = 'catalogo'
    SOURCE_AI = 'ia'
    SOURCE_CHOICES = [
        (SOURCE_CATALOG, 'Catálogo'),      # cadastrada pela equipe (admin / popular_dados)
        (SOURCE_AI, 'Gerada por IA'),      # criada pela IA a partir de uma foto
    ]
    DIFFICULTY_CHOICES = [
        ('facil', 'Fácil'),
        ('media', 'Média'),
        ('dificil', 'Difícil'),
    ]

    title = models.CharField(max_length=150)
    description = models.CharField(max_length=300, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='recipes')
    image = models.ImageField(upload_to='recipes/', blank=True, null=True)
    prep_time_minutes = models.PositiveIntegerField()
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='facil')
    # Modo de preparo: um passo por linha
    preparation = models.TextField()
    # Quanto alimento (kg) essa receita costuma reaproveitar
    estimated_saved_kg = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.30'))
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_CATALOG)
    # Alimentos principais: é por aqui que as fotos encontram receitas do catálogo
    key_ingredients = models.ManyToManyField(Ingredient, related_name='recipes', blank=True)
    # Se a receita foi gerada pela IA, de qual foto ela nasceu
    created_from_photo = models.ForeignKey(
        'Photo', on_delete=models.SET_NULL, blank=True, null=True, related_name='generated_recipes'
    )

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class RecipeIngredient(ReCozinheModel):
    """Linha da lista de ingredientes (ex.: '4 limões sicilianos')."""
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='ingredient_lines')
    description = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.description


# --------------------------------------------------------------------------
# Fotos e identificação por IA  (Câmera, Tela inicial, Histórico de Fotos)
# --------------------------------------------------------------------------
class Photo(ReCozinheModel):
    SOURCE_CHOICES = [('camera', 'Câmera'), ('galeria', 'Galeria')]
    STATUS_IDENTIFIED = 'identificado'
    STATUS_NOT_FOOD = 'nao_alimento'
    STATUS_FAILED = 'falhou'
    STATUS_CHOICES = [
        (STATUS_IDENTIFIED, 'Identificado'),
        (STATUS_NOT_FOOD, 'Não é alimento'),
        (STATUS_FAILED, 'Falha na IA'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='photos/')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='camera')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_FAILED)

    # O que a IA respondeu
    identified_ingredient = models.ForeignKey(
        Ingredient, on_delete=models.SET_NULL, blank=True, null=True, related_name='photos'
    )
    food_part = models.CharField(max_length=100, blank=True)      # ex.: "casca", "talos", "fruta inteira"
    condition = models.CharField(max_length=150, blank=True)      # ex.: "madura demais, ainda boa para consumo"
    confidence = models.PositiveSmallIntegerField(blank=True, null=True)  # 0 a 100 (o "94%")
    estimated_weight_g = models.PositiveIntegerField(blank=True, null=True)
    ai_message = models.CharField(max_length=300, blank=True)    # aviso para o usuário (ex.: erro, não é comida)

    # Receitas sugeridas para essa foto (do catálogo + geradas pela IA)
    suggested_recipes = models.ManyToManyField(Recipe, related_name='suggested_in_photos', blank=True)

    class Meta:
        ordering = ['-timestamp_create']


class ReuseTip(ReCozinheModel):
    """Forma de reaproveitamento que não é receita (congelar, caldo, adubo...)."""
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name='reuse_tips')
    title = models.CharField(max_length=120)
    description = models.TextField()

    class Meta:
        ordering = ['id']


# --------------------------------------------------------------------------
# Impacto  (Perfil: kg reaproveitados, receitas feitas, dias seguidos, conquistas)
# --------------------------------------------------------------------------
class Reuse(ReCozinheModel):
    """O usuário registra que reaproveitou um alimento (fazendo uma receita ou seguindo uma dica)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reuses')
    photo = models.ForeignKey(Photo, on_delete=models.SET_NULL, blank=True, null=True, related_name='reuses')
    recipe = models.ForeignKey(Recipe, on_delete=models.SET_NULL, blank=True, null=True, related_name='reuses')
    tip = models.ForeignKey(ReuseTip, on_delete=models.SET_NULL, blank=True, null=True, related_name='reuses')
    saved_kg = models.DecimalField(max_digits=6, decimal_places=2)
    reused_at = models.DateField()

    class Meta:
        ordering = ['-reused_at', '-timestamp_create']
