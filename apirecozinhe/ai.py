"""
Integração com a Inteligência Artificial.

- Provedor "gemini": usa a API do Google Gemini (tem cota gratuita no Google AI Studio).
  Uma única chamada recebe a foto e devolve: o alimento identificado, receitas e
  formas de reaproveitamento, tudo em JSON.
- Provedor "demo": não chama nenhuma IA. Devolve respostas prontas, usado nos testes
  automáticos e para apresentar sem internet. Liga sozinho quando não há GEMINI_API_KEY.

O resto do sistema só conhece as funções `analyze_food_photo` e `generate_recipes`,
então trocar de IA no futuro mexe apenas neste arquivo.
"""
import io
import json
import logging

from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

CATEGORY_SLUGS = ['sopas', 'petiscos', 'doces', 'bebidas', 'pratos']


class AIError(Exception):
    """Algo deu errado ao falar com a IA (sem chave, sem cota, resposta inválida...)."""


# --------------------------------------------------------------------------
# Formato da resposta que pedimos para a IA (JSON Schema)
# --------------------------------------------------------------------------
RECIPE_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'description': {'type': 'string', 'description': 'Uma frase curta sobre a receita'},
        'category': {'type': 'string', 'enum': CATEGORY_SLUGS},
        'prep_time_minutes': {'type': 'integer'},
        'difficulty': {'type': 'string', 'enum': ['facil', 'media', 'dificil']},
        'ingredients': {'type': 'array', 'items': {'type': 'string'}},
        'steps': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['title', 'description', 'category', 'prep_time_minutes', 'difficulty', 'ingredients', 'steps'],
}

TIP_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'description': {'type': 'string'},
    },
    'required': ['title', 'description'],
}

ANALYSIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'is_food': {'type': 'boolean'},
        'food': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Nome do alimento em português, ex.: Limão Siciliano'},
                'part': {'type': 'string', 'description': 'Parte do alimento na foto, ex.: casca, talo, fruta inteira'},
                'condition': {'type': 'string', 'description': 'Estado do alimento, ex.: maduro demais, murcho'},
                'confidence': {'type': 'integer', 'description': 'Certeza da identificação, de 0 a 100'},
                'estimated_weight_g': {'type': 'integer', 'description': 'Peso aproximado do que aparece na foto, em gramas'},
                'safe_to_eat': {'type': 'boolean'},
            },
            'required': ['name', 'part', 'condition', 'confidence', 'estimated_weight_g', 'safe_to_eat'],
        },
        'message': {'type': 'string', 'description': 'Aviso curto para o usuário, se necessário'},
        'recipes': {'type': 'array', 'items': RECIPE_SCHEMA},
        'reuse_tips': {'type': 'array', 'items': TIP_SCHEMA},
    },
    'required': ['is_food', 'food', 'message', 'recipes', 'reuse_tips'],
}

RECIPES_ONLY_SCHEMA = {
    'type': 'object',
    'properties': {'recipes': {'type': 'array', 'items': RECIPE_SCHEMA}},
    'required': ['recipes'],
}

SYSTEM_PROMPT = (
    'Você é a assistente do ReCozinhe, um app brasileiro contra o desperdício de alimentos. '
    'O usuário fotografa um alimento, ou parte dele (casca, talo, semente, sobra), que iria para o lixo. '
    'Responda sempre em português do Brasil, com receitas caseiras, simples e seguras, '
    'usando ingredientes comuns em casas brasileiras. '
    'Se o alimento parecer estragado (mofo, cheiro ou aspecto de podre), marque safe_to_eat como false, '
    'não sugira receitas para comer e sugira apenas descarte correto ou compostagem.'
)


def _analysis_prompt(hint, n_recipes):
    prompt = (
        'Analise a foto. '
        '1) Diga se é um alimento (is_food). Se não for, devolva listas vazias e explique em "message". '
        '2) Identifique o alimento, a parte que aparece, o estado, sua certeza (0-100) e o peso aproximado em gramas. '
        f'3) Sugira {n_recipes} receitas que REAPROVEITEM esse alimento ou essa parte dele, '
        f'com categoria entre {", ".join(CATEGORY_SLUGS)}. '
        'Cada ingrediente é uma linha com quantidade (ex.: "2 xícaras de açúcar"); cada passo é uma frase. '
        '4) Sugira 2 formas de reaproveitamento que não são receitas (ex.: congelar, fazer caldo, compostagem).'
    )
    if hint:
        prompt += f' O usuário informou que o alimento é: "{hint}". Considere essa informação.'
    return prompt


# --------------------------------------------------------------------------
# Funções usadas pelo resto do sistema
# --------------------------------------------------------------------------
def analyze_food_photo(image_file, hint=None):
    """Recebe o arquivo de imagem enviado e devolve o dicionário no formato ANALYSIS_SCHEMA."""
    if _provider() == 'demo':
        return _demo_analysis(getattr(image_file, 'name', ''), hint)

    image_bytes = _prepare_image(image_file)
    return _call_gemini(
        contents=[_image_part(image_bytes), _analysis_prompt(hint, settings.AI_RECIPES_PER_PHOTO)],
        schema=ANALYSIS_SCHEMA,
    )


def generate_recipes(food_name, food_part='', avoid_titles=()):
    """Gera receitas novas para um alimento já identificado (botão 'gerar outras receitas')."""
    if _provider() == 'demo':
        return {'recipes': _demo_recipes(food_name, variant=len(avoid_titles))}

    prompt = (
        f'Sugira {settings.AI_RECIPES_PER_PHOTO} receitas que reaproveitem "{food_name}"'
        + (f' (parte: {food_part})' if food_part else '')
        + f', com categoria entre {", ".join(CATEGORY_SLUGS)}.'
    )
    if avoid_titles:
        prompt += ' Não repita estas receitas: ' + '; '.join(avoid_titles) + '.'
    return _call_gemini(contents=[prompt], schema=RECIPES_ONLY_SCHEMA)


# --------------------------------------------------------------------------
# Google Gemini
# --------------------------------------------------------------------------
def _provider():
    provider = settings.AI_PROVIDER
    if provider == 'auto':
        provider = 'gemini' if settings.GEMINI_API_KEY else 'demo'
    return provider


def _call_gemini(contents, schema):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AIError('Biblioteca google-genai não instalada (pip install -r requirements.txt).') from exc

    if not settings.GEMINI_API_KEY:
        raise AIError('GEMINI_API_KEY não configurada no arquivo .env.')

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type='application/json',
                response_json_schema=schema,
                temperature=0.7,
            ),
        )
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise AIError('A IA respondeu num formato inesperado. Tente novamente.') from exc
    except Exception as exc:  # erros de rede, cota (429), chave inválida...
        logger.exception('Erro ao chamar o Gemini')
        if '429' in str(exc) or 'RESOURCE_EXHAUSTED' in str(exc):
            raise AIError('Limite gratuito da IA atingido. Aguarde um minuto e tente de novo.') from exc
        raise AIError(f'Não foi possível falar com a IA: {exc}') from exc


def _image_part(image_bytes):
    from google.genai import types

    return types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')


def _prepare_image(image_file, max_side=1024):
    """Reduz a foto para no máximo 1024px e converte para JPEG: gasta menos cota e é mais rápido."""
    image_file.seek(0)
    image = Image.open(image_file)
    image = image.convert('RGB')
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=85)
    image_file.seek(0)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Modo demonstração (sem IA de verdade)
# --------------------------------------------------------------------------
DEMO_FOODS = {
    'banana': ('Banana', 'casca', 'madura, com pintas escuras', 250),
    'limao': ('Limão Siciliano', 'fruta inteira', 'casca firme, um pouco murcho', 300),
    'cenoura': ('Cenoura', 'cascas e ramas', 'boas para consumo', 150),
    'pao': ('Pão Francês', 'pão inteiro', 'amanhecido e duro', 100),
}


def _demo_analysis(filename, hint):
    import unicodedata

    text = unicodedata.normalize('NFKD', f'{hint or ""} {filename}').encode('ascii', 'ignore').decode().lower()
    key = next((k for k in DEMO_FOODS if k in text), None)
    if key is None:
        return {
            'is_food': False,
            'food': {'name': '', 'part': '', 'condition': '', 'confidence': 0,
                     'estimated_weight_g': 0, 'safe_to_eat': False},
            'message': 'Modo demonstração: não reconheci um alimento. Configure a GEMINI_API_KEY para usar a IA.',
            'recipes': [],
            'reuse_tips': [],
        }

    name, part, condition, weight = DEMO_FOODS[key]
    return {
        'is_food': True,
        'food': {'name': name, 'part': part, 'condition': condition, 'confidence': 90,
                 'estimated_weight_g': weight, 'safe_to_eat': True},
        'message': '',
        'recipes': _demo_recipes(name),
        'reuse_tips': [
            {'title': 'Congele para depois', 'description': f'Pique {name.lower()} e congele em porções para usar em até 3 meses.'},
            {'title': 'Compostagem', 'description': 'O que não for aproveitado pode virar adubo numa composteira doméstica.'},
        ],
    }


def _demo_recipes(name, variant=0):
    suffix = f' {variant + 1}' if variant else ''
    return [
        {
            'title': f'Bolo de {name.lower()}{suffix}',
            'description': f'Bolo simples que aproveita {name.lower()} que iria para o lixo.',
            'category': 'doces',
            'prep_time_minutes': 45,
            'difficulty': 'facil',
            'ingredients': [f'200 g de {name.lower()}', '2 ovos', '1 xícara de açúcar', '2 xícaras de farinha de trigo'],
            'steps': ['Bata tudo no liquidificador, menos a farinha.', 'Misture a farinha.', 'Asse a 180 °C por 35 minutos.'],
        },
        {
            'title': f'Chips de {name.lower()}{suffix}',
            'description': 'Petisco crocante de forno.',
            'category': 'petiscos',
            'prep_time_minutes': 25,
            'difficulty': 'facil',
            'ingredients': [f'{name} em fatias finas', 'Azeite', 'Sal'],
            'steps': ['Tempere as fatias com azeite e sal.', 'Asse a 200 °C até dourar.'],
        },
    ]
