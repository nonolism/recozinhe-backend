"""
Regras de negócio do ReCozinhe. As views só chamam estas funções.
"""
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apirecozinhe import ai
from apirecozinhe.models import Category, Ingredient, Photo, Recipe, RecipeIngredient, ReuseTip


class DailyLimitReached(Exception):
    pass


# --------------------------------------------------------------------------
# 1. Identificação por imagem + sugestões
# --------------------------------------------------------------------------
def check_daily_limit(user):
    """Protege a cota gratuita da IA: cada usuário tem um número de análises por dia."""
    today = timezone.localdate()
    used = user.photos.filter(timestamp_create__date=today).count()
    if used >= settings.AI_DAILY_LIMIT_PER_USER:
        raise DailyLimitReached(
            f'Você já analisou {used} fotos hoje. O limite diário é {settings.AI_DAILY_LIMIT_PER_USER}.'
        )


def process_photo(photo, hint=None):
    """
    Manda a foto para a IA e salva tudo o que voltou:
    alimento identificado, receitas geradas, receitas do catálogo e dicas de reaproveitamento.
    """
    try:
        result = ai.analyze_food_photo(photo.image, hint=hint)
    except ai.AIError as exc:
        photo.status = Photo.STATUS_FAILED
        photo.ai_message = str(exc)[:300]
        photo.save()
        return photo

    food = result.get('food') or {}
    if not result.get('is_food') or not food.get('name'):
        photo.status = Photo.STATUS_NOT_FOOD
        photo.ai_message = (result.get('message') or 'Não encontramos um alimento nessa foto.')[:300]
        photo.save()
        return photo

    with transaction.atomic():
        ingredient = get_or_create_ingredient(food['name'])
        photo.status = Photo.STATUS_IDENTIFIED
        photo.identified_ingredient = ingredient
        photo.food_part = (food.get('part') or '')[:100]
        photo.condition = (food.get('condition') or '')[:150]
        photo.confidence = _clamp(food.get('confidence'), 0, 100)
        photo.estimated_weight_g = _clamp(food.get('estimated_weight_g'), 0, 50000) or None
        photo.ai_message = (result.get('message') or '')[:300]
        photo.save()

        # Receitas geradas pela IA (só se o alimento estiver bom para consumo)
        if food.get('safe_to_eat', True):
            for data in result.get('recipes') or []:
                recipe = save_ai_recipe(data, ingredient, photo)
                if recipe:
                    photo.suggested_recipes.add(recipe)

            # Receitas do catálogo que usam o mesmo alimento
            catalog = Recipe.objects.filter(source=Recipe.SOURCE_CATALOG, key_ingredients=ingredient)
            photo.suggested_recipes.add(*catalog)

        for tip in result.get('reuse_tips') or []:
            if tip.get('title') and tip.get('description'):
                ReuseTip.objects.create(photo=photo, title=tip['title'][:120], description=tip['description'])

    return photo


def regenerate_recipes(photo):
    """Pede à IA receitas novas para um alimento que já foi identificado."""
    if photo.identified_ingredient is None:
        raise ai.AIError('Essa foto não tem um alimento identificado.')

    old_titles = list(photo.suggested_recipes.values_list('title', flat=True))
    result = ai.generate_recipes(photo.identified_ingredient.name, photo.food_part, avoid_titles=old_titles)

    new = []
    with transaction.atomic():
        for data in result.get('recipes') or []:
            recipe = save_ai_recipe(data, photo.identified_ingredient, photo)
            if recipe:
                photo.suggested_recipes.add(recipe)
                new.append(recipe)
    return new


def save_ai_recipe(data, ingredient, photo):
    """Transforma uma receita em JSON (vinda da IA) em Recipe + linhas de ingredientes."""
    title = (data.get('title') or '').strip()[:150]
    steps = [s.strip() for s in data.get('steps') or [] if s and s.strip()]
    lines = [i.strip() for i in data.get('ingredients') or [] if i and i.strip()]
    if not title or not steps or not lines:
        return None  # resposta incompleta: ignoramos essa receita

    category = Category.objects.filter(slug=data.get('category')).first() or _default_category()
    difficulty = data.get('difficulty') if data.get('difficulty') in {'facil', 'media', 'dificil'} else 'facil'
    weight_kg = Decimal(photo.estimated_weight_g or 300) / 1000

    recipe = Recipe.objects.create(
        title=title,
        description=(data.get('description') or '')[:300],
        category=category,
        prep_time_minutes=_clamp(data.get('prep_time_minutes'), 1, 600) or 30,
        difficulty=difficulty,
        preparation='\n'.join(steps),
        estimated_saved_kg=weight_kg.quantize(Decimal('0.01')),
        source=Recipe.SOURCE_AI,
        created_from_photo=photo,
    )
    recipe.key_ingredients.add(ingredient)
    RecipeIngredient.objects.bulk_create(
        RecipeIngredient(recipe=recipe, description=line[:200], order=i) for i, line in enumerate(lines)
    )
    return recipe


def get_or_create_ingredient(name):
    """Evita duplicados como 'limão siciliano' e 'Limao Siciliano'."""
    name = ' '.join(name.strip().split()).title()[:100]
    for ingredient in Ingredient.objects.all():
        if _normalize(ingredient.name) == _normalize(name):
            return ingredient
    return Ingredient.objects.create(name=name)


def suggested_recipes(user, photo=None, limit_photos=5):
    """Receitas sugeridas: as de uma foto, ou as das últimas fotos do usuário."""
    photos = [photo] if photo else list(user.photos.filter(status=Photo.STATUS_IDENTIFIED)[:limit_photos])
    return Recipe.objects.filter(suggested_in_photos__in=photos).distinct().order_by('-timestamp_create')


# --------------------------------------------------------------------------
# 2. Acompanhamento do impacto
# --------------------------------------------------------------------------
ACHIEVEMENTS = [
    {'code': 'primeira_receita', 'title': 'Primeira receita feita!', 'icon': 'star'},
    {'code': 'tres_dias', 'title': '3 dias seguidos!', 'icon': 'heart'},
    {'code': 'dois_kg', 'title': '2kg salvos!', 'icon': 'check'},
]


def current_streak(user):
    """Quantos dias seguidos (até hoje ou ontem) o usuário reaproveitou algo."""
    days = set(user.reuses.values_list('reused_at', flat=True))
    today = timezone.localdate()
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def profile_stats(user):
    """Números do card escuro do Perfil + conquistas."""
    today = timezone.localdate()
    reuses = user.reuses.all()

    total_kg = _kg(reuses.aggregate(t=Sum('saved_kg'))['t'])
    month_kg = _kg(reuses.filter(reused_at__year=today.year, reused_at__month=today.month)
                   .aggregate(t=Sum('saved_kg'))['t'])
    goal = user.monthly_goal_kg or Decimal('0')
    recipes_count = reuses.exclude(recipe=None).count()
    streak = current_streak(user)

    unlocked = {
        'primeira_receita': recipes_count >= 1,
        'tres_dias': streak >= 3,
        'dois_kg': total_kg >= 2,
    }
    return {
        'saved_kg_total': total_kg,
        'saved_kg_month': month_kg,
        'monthly_goal_kg': goal,
        'monthly_goal_percent': int(min(month_kg / goal * 100, 100)) if goal else 0,
        'recipes_cooked': recipes_count,
        'reuses_total': reuses.count(),
        'streak_days': streak,
        'achievements': [{**a, 'unlocked': unlocked[a['code']]} for a in ACHIEVEMENTS],
    }


def impact_history(user, months=6):
    """Evolução mês a mês e os alimentos mais reaproveitados (para um gráfico no app)."""
    today = timezone.localdate()
    index = today.year * 12 + today.month - 1 - (months - 1)   # volta (months - 1) meses
    start = today.replace(year=index // 12, month=index % 12 + 1, day=1)

    per_month = {
        row['month'].strftime('%Y-%m'): row
        for row in user.reuses.filter(reused_at__gte=start)
        .annotate(month=TruncMonth('reused_at')).values('month')
        .annotate(kg=Sum('saved_kg'), count=Count('id'))
    }

    series, cursor = [], start
    while cursor <= today:
        key = cursor.strftime('%Y-%m')
        row = per_month.get(key, {})
        series.append({'month': key, 'saved_kg': _kg(row.get('kg')), 'reuses': row.get('count', 0)})
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    top_foods = [
        {'food': row['photo__identified_ingredient__name'], 'saved_kg': _kg(row['kg']), 'reuses': row['count']}
        for row in user.reuses.exclude(photo__identified_ingredient=None)
        .values('photo__identified_ingredient__name')
        .annotate(kg=Sum('saved_kg'), count=Count('id')).order_by('-kg')[:5]
    ]

    return {'months': series, 'top_foods': top_foods, 'totals': profile_stats(user)}


# --------------------------------------------------------------------------
# Auxiliares
# --------------------------------------------------------------------------
def _normalize(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return ' '.join(text.lower().replace('_', ' ').replace('-', ' ').split())


def _clamp(value, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return None


def _kg(value):
    return Decimal(value or 0).quantize(Decimal('0.01'))


def _default_category():
    return Category.objects.get_or_create(slug='pratos', defaults={'name': 'Pratos'})[0]
