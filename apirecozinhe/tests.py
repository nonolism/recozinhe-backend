import io
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from apirecozinhe import ai
from apirecozinhe.models import *

MEDIA = tempfile.mkdtemp()

GEMINI_ANSWER = {
    'is_food': True,
    'food': {'name': 'casca de abóbora', 'part': 'casca', 'condition': 'boa para consumo',
             'confidence': 94, 'estimated_weight_g': 400, 'safe_to_eat': True},
    'message': '',
    'recipes': [
        {'title': 'Chips de casca de abóbora', 'description': 'Crocante de forno', 'category': 'petiscos',
         'prep_time_minutes': 30, 'difficulty': 'facil',
         'ingredients': ['Cascas de 1 abóbora', 'Azeite', 'Sal'], 'steps': ['Corte.', 'Tempere.', 'Asse.']},
        {'title': 'Receita incompleta', 'description': '', 'category': 'sopas', 'prep_time_minutes': 10,
         'difficulty': 'facil', 'ingredients': [], 'steps': []},
    ],
    'reuse_tips': [{'title': 'Caldo', 'description': 'Ferva as cascas para fazer caldo.'}],
}


def fake_image(name='foto.jpg', size=(10, 10)):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'yellow').save(buffer, 'JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


@override_settings(MEDIA_ROOT=MEDIA, AI_PROVIDER='demo', AI_DAILY_LIMIT_PER_USER=5)
class ReCozinheApiTests(APITestCase):

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        call_command('popular_dados', stdout=io.StringIO())
        res = self.client.post('/api/register/', {
            'username': 'daniel', 'password': 'Senha@Forte123', 'first_name': 'Daniel', 'last_name': 'Luca',
        })
        self.assertEqual(res.status_code, 201)
        self.user = User.objects.get(username='daniel')
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + res.data['token'])

    def send_photo(self, name='foto.jpg', **extra):
        return self.client.post('/api/photos/', {'image': fake_image(name), **extra}, format='multipart')

    # ---------------- autenticação ----------------
    def test_login_and_auth(self):
        self.client.credentials()
        self.assertEqual(self.client.get('/api/recipes/').status_code, 401)
        ok = self.client.post('/api/login/', {'username': 'daniel', 'password': 'Senha@Forte123'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post('/api/login/', {'username': 'daniel', 'password': 'x'}).status_code, 401)

    # ---------------- identificação por imagem ----------------
    def test_photo_demo_mode_identifies_and_suggests(self):
        res = self.send_photo('limao-siciliano.jpg', source='galeria')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'identificado')
        self.assertEqual(res.data['source'], 'galeria')
        self.assertEqual(res.data['identified_ingredient']['name'], 'Limão Siciliano')

        titles = [r['title'] for r in res.data['suggested_recipes']]
        self.assertIn('Geleia rápida de limão siciliano', titles)      # do catálogo
        self.assertIn('Bolo de limão siciliano', titles)               # "gerada" pela IA
        self.assertEqual(len(res.data['reuse_tips']), 2)

        self.assertEqual(self.client.get('/api/photos/latest/').data['id'], res.data['id'])
        sugeridas = self.client.get('/api/recipes/suggested/?category=doces').data
        self.assertTrue(all(r['category']['slug'] == 'doces' for r in sugeridas))

    def test_photo_not_food(self):
        res = self.send_photo('cadeira.jpg')
        self.assertEqual(res.data['status'], 'nao_alimento')
        self.assertEqual(res.data['suggested_recipes'], [])
        self.assertEqual(self.client.get('/api/photos/latest/').status_code, 204)

    def test_user_hint(self):
        res = self.send_photo('IMG_001.jpg', ingredient_name='banana')
        self.assertEqual(res.data['identified_ingredient']['name'], 'Banana')

    @override_settings(AI_PROVIDER='gemini', GEMINI_API_KEY='chave-teste')
    def test_gemini_answer_is_saved(self):
        with mock.patch.object(ai, '_call_gemini', return_value=GEMINI_ANSWER) as call:
            res = self.client.post('/api/photos/', {'image': fake_image(size=(3000, 2000))}, format='multipart')

        sent_image = call.call_args.kwargs['contents'][0]
        self.assertLessEqual(max(Image.open(io.BytesIO(sent_image.inline_data.data)).size), 1024)

        self.assertEqual(res.data['identified_ingredient']['name'], 'Casca De Abóbora')
        self.assertEqual(res.data['confidence'], 94)
        self.assertEqual(res.data['estimated_weight_g'], 400)
        self.assertEqual([r['title'] for r in res.data['suggested_recipes']], ['Chips de casca de abóbora'])

        recipe = Recipe.objects.get(title='Chips de casca de abóbora')
        detail = self.client.get(f'/api/recipes/{recipe.id}/').data
        self.assertEqual(detail['source'], 'ia')
        self.assertEqual(detail['preparation_steps'], ['Corte.', 'Tempere.', 'Asse.'])
        self.assertIsNotNone(detail['image'])  # usa a foto do usuário

    @override_settings(AI_PROVIDER='gemini', GEMINI_API_KEY='chave-teste')
    def test_ai_failure_is_reported(self):
        with mock.patch.object(ai, '_call_gemini', side_effect=ai.AIError('Limite gratuito da IA atingido.')):
            res = self.send_photo()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'falhou')
        self.assertIn('Limite', res.data['ai_message'])

    def test_daily_limit(self):
        for _ in range(5):
            self.send_photo('banana.jpg')
        self.assertEqual(self.send_photo('banana.jpg').status_code, 429)

    def test_regenerate(self):
        photo_id = self.send_photo('banana.jpg').data['id']
        res = self.client.post(f'/api/photos/{photo_id}/regenerate/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data[0]['title'], 'Bolo de banana 3')

    def test_ai_recipes_are_private(self):
        photo_id = self.send_photo('banana.jpg').data['id']
        recipe_id = Photo.objects.get(pk=photo_id).generated_recipes.first().id

        outro = User.objects.create_user('outro', password='x')
        self.client.force_authenticate(outro)
        self.assertEqual(self.client.get(f'/api/recipes/{recipe_id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/photos/').data, [])
        self.assertEqual(self.client.post('/api/reuses/', {'recipe': recipe_id}).status_code, 400)

    # ---------------- receitas ----------------
    def test_recipes_filter_and_search(self):
        doces = self.client.get('/api/recipes/?category=doces').data
        self.assertTrue(doces and all(r['category']['slug'] == 'doces' for r in doces))
        busca = self.client.get('/api/recipes/?search=maracujá').data
        self.assertEqual([r['title'] for r in busca], ['Mousse de maracujá com cobertura'])

    # ---------------- impacto ----------------
    def test_impact(self):
        photo = self.send_photo('banana.jpg').data
        tip_id = photo['reuse_tips'][0]['id']

        res = self.client.post('/api/reuses/', {'tip': tip_id})       # usa o peso estimado pela IA
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['saved_kg'], '0.25')

        recipe = Recipe.objects.get(title__startswith='Geleia')
        today = timezone.localdate()
        for i in range(3):
            Reuse.objects.create(user=self.user, recipe=recipe, saved_kg='0.80', reused_at=today - timedelta(days=i))

        stats = self.client.get('/api/profile/').data['stats']
        self.assertEqual(stats['recipes_cooked'], 3)
        self.assertEqual(stats['streak_days'], 3)
        self.assertEqual(str(stats['saved_kg_total']), '2.65')
        self.assertTrue(all(a['unlocked'] for a in stats['achievements']))

        impact = self.client.get('/api/impact/').data
        self.assertEqual(len(impact['months']), 6)
        self.assertEqual(impact['months'][-1]['month'], today.strftime('%Y-%m'))
        self.assertEqual(impact['top_foods'][0]['food'], 'Banana')

    def test_reuse_requires_something(self):
        self.assertEqual(self.client.post('/api/reuses/', {}).status_code, 400)
