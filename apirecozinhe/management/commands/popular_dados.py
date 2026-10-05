from decimal import Decimal

from django.core.management.base import BaseCommand

from apirecozinhe.models import Category, Ingredient, Recipe, RecipeIngredient

CATEGORIES = [('Sopas', 'sopas'), ('Petiscos', 'petiscos'), ('Doces', 'doces'),
              ('Bebidas', 'bebidas'), ('Pratos', 'pratos')]

# (título, categoria, minutos, dificuldade, kg salvos, [(ingrediente, linha)], preparo)
RECIPES = [
    (
        'Geleia rápida de limão siciliano', 'doces', 20, 'facil', '0.50',
        [
            ('Limão Siciliano', '4 limões sicilianos'),
            ('Água', '1 litro de água para o miolo'),
            ('Água', '1/2 litro de água para a casca'),
            ('Açúcar', '2 xícaras (chá) de açúcar refinado'),
        ],
        'Lave os limões.\n'
        'Com um zester ou uma faca ou ralador pequeno, rale as cascas amarelas do limão '
        '(não rale nada da branca, por favor, senão amarga).\n'
        'Agora parta o limão em quatro pedaços e tire o miolo da casca branca como se fosse '
        'uma mexerica. Retire também as sementes.\n'
        'Pique os pedaços do limão e coloque para ferver em 1 litro de água até o líquido '
        'reduzir pela metade.\n'
        'Junte as raspas e o açúcar e cozinhe em fogo baixo até dar ponto de geleia.',
    ),
    (
        'Sal aromatizado de casca de limão siciliano', 'petiscos', 15, 'facil', '0.10',
        [
            ('Limão Siciliano', 'Cascas de 3 limões sicilianos'),
            ('Sal grosso', '1 xícara de sal grosso'),
        ],
        'Rale apenas a parte amarela das cascas.\n'
        'Misture as raspas com o sal grosso.\n'
        'Espalhe numa assadeira e leve ao forno baixo por 10 minutos para secar.\n'
        'Guarde em pote bem fechado.',
    ),
    (
        'Limonada suíça com raspas', 'bebidas', 25, 'facil', '0.30',
        [
            ('Limão Siciliano', '2 limões sicilianos com casca'),
            ('Açúcar', '4 colheres (sopa) de açúcar'),
            ('Água', '1 litro de água gelada'),
        ],
        'Corte os limões em quatro e retire o miolo branco central.\n'
        'Bata no liquidificador com a água e o açúcar por poucos segundos.\n'
        'Coe e sirva com gelo.',
    ),
    (
        'Mousse de limão com raspas de laranja', 'doces', 20, 'facil', '0.25',
        [
            ('Limão', 'Suco de 3 limões'),
            ('Laranja', 'Raspas de 1 laranja'),
            ('Leite condensado', '1 lata de leite condensado'),
            ('Creme de leite', '1 caixa de creme de leite'),
        ],
        'Bata o leite condensado, o creme de leite e o suco de limão.\n'
        'Coloque em taças e finalize com as raspas de laranja.\n'
        'Leve à geladeira por 2 horas.',
    ),
    (
        'Mousse de maracujá com cobertura', 'doces', 15, 'facil', '0.25',
        [
            ('Maracujá', 'Polpa de 2 maracujás'),
            ('Leite condensado', '1 lata de leite condensado'),
            ('Creme de leite', '1 caixa de creme de leite'),
        ],
        'Bata a polpa (sem sementes), o leite condensado e o creme de leite.\n'
        'Despeje em um refratário e cubra com as sementes cozidas com um pouco de açúcar.\n'
        'Leve à geladeira por 3 horas.',
    ),
    (
        'Risoto de cogumelos com parmesão', 'pratos', 50, 'media', '0.40',
        [
            ('Cogumelo', '300 g de cogumelos que estão perto de vencer'),
            ('Arroz', '2 xícaras de arroz arbóreo'),
            ('Queijo parmesão', '1/2 xícara de parmesão ralado'),
            ('Cebola', '1 cebola picada'),
        ],
        'Refogue a cebola e os cogumelos.\n'
        'Junte o arroz e vá adicionando caldo quente aos poucos, mexendo sempre.\n'
        'Quando o arroz estiver al dente, desligue e misture o parmesão.',
    ),
    (
        'Sopa de talos e cascas de legumes', 'sopas', 40, 'facil', '0.60',
        [
            ('Cenoura', 'Cascas de 3 cenouras'),
            ('Brócolis', 'Talos de 1 maço de brócolis'),
            ('Cebola', '1 cebola'),
            ('Batata', '2 batatas'),
        ],
        'Lave bem os talos e cascas.\n'
        'Refogue a cebola, junte tudo com água e cozinhe por 30 minutos.\n'
        'Bata no liquidificador e acerte o sal.',
    ),
]


class Command(BaseCommand):
    help = 'Cadastra as categorias e um catálogo inicial de receitas (as do Figma). A IA gera as demais.'

    def handle(self, *args, **options):
        categories = {}
        for name, slug in CATEGORIES:
            categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={'name': name})

        for title, cat, minutes, difficulty, kg, ingredients, preparation in RECIPES:
            recipe, created = Recipe.objects.update_or_create(
                title=title,
                defaults={
                    'category': categories[cat],
                    'prep_time_minutes': minutes,
                    'difficulty': difficulty,
                    'estimated_saved_kg': Decimal(kg),
                    'preparation': preparation,
                    'source': Recipe.SOURCE_CATALOG,
                },
            )
            recipe.ingredient_lines.all().delete()
            recipe.key_ingredients.clear()
            for order, (ingredient_name, line) in enumerate(ingredients):
                ingredient, _ = Ingredient.objects.get_or_create(name=ingredient_name)
                if order == 0:  # o primeiro ingrediente é o alimento que está sendo reaproveitado
                    recipe.key_ingredients.add(ingredient)
                RecipeIngredient.objects.create(recipe=recipe, description=line, order=order)

            self.stdout.write(f"{'Criada' if created else 'Atualizada'}: {title}")

        self.stdout.write(self.style.SUCCESS('Dados de exemplo cadastrados!'))
