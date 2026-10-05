# ReCozinhe — Backend

O ReCozinhe é um app contra o desperdício de alimentos. O usuário fotografa (ou escolhe da galeria) um alimento,
ou parte dele, que iria para o lixo. A **IA identifica o alimento** e devolve **receitas e formas de reaproveitamento**.
O app também **acompanha o impacto**: quantos kg o usuário já reaproveitou ao longo do tempo.

API em **Django + Django REST Framework** .
A IA é o **Google Gemini**, que tem cota gratuita.

## Como rodar

```bash
python -m venv venv
venv\Scripts\activate                # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # Mac/Linux: cp .env.example .env
python manage.py migrate
python manage.py popular_dados       # categorias + catálogo inicial de receitas
python manage.py createsuperuser     # opcional, para usar o /admin
python manage.py runserver 0.0.0.0:8000   # o 0.0.0.0 deixa o celular acessar (app recozinhe-app)
```

Testes: `python manage.py test` (não gastam cota da IA: usam o modo demonstração e respostas simuladas).

## Como testar

Com o servidor rodando (`python manage.py runserver`), há três jeitos:

1. **Script pronto:** em outro terminal, `python testar_api.py caminho/da/foto.jpg`. Ele faz login, envia a foto,
   mostra o alimento, as receitas, as dicas, registra um reaproveitamento e mostra o perfil.
2. **Navegador:** entre em http://127.0.0.1:8000/api-auth/login/ e depois navegue por http://127.0.0.1:8000/api/.
   Em `/api/photos/` há um formulário para enviar uma foto.
3. **Testes automáticos:** `python manage.py test`.

O painel http://127.0.0.1:8000/admin/ (com o usuário do `createsuperuser`) mostra tudo o que foi salvo no banco.

## Configurando a IA gratuita (Google Gemini)

1. Entre em https://aistudio.google.com/apikey com uma conta Google e clique em **Create API key**.
2. Cole a chave no `.env`: `GEMINI_API_KEY=sua-chave`.
3. Reinicie o `runserver`.

| Variável | Padrão | Para que serve |
|---|---|---|
| `GEMINI_API_KEY` | vazio | Chave do Google AI Studio |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Modelo usado; troque se o Google renomear ou se acabar a cota de um modelo |
| `AI_PROVIDER` | `auto` | `auto` = Gemini se houver chave, senão demonstração · `gemini` · `demo` |
| `AI_RECIPES_PER_PHOTO` | `3` | Quantas receitas a IA gera por foto |
| `AI_DAILY_LIMIT_PER_USER` | `20` | Fotos por usuário por dia, para não estourar a cota gratuita |

**Modo demonstração:** sem chave, o backend não chama a IA e responde com dados prontos. Ele reconhece fotos cujo
nome do arquivo (ou o campo `ingredient_name`) tenha *banana*, *limao*, *cenoura* ou *pao*.

## Como a IA é usada

Cada foto gera **uma única chamada** ao Gemini (economiza cota). A foto é reduzida para no máximo 1024 px, e a IA
devolve um JSON com formato fixo (`apirecozinhe/ai.py`):

- se é alimento, qual é, qual parte (casca, talo...), estado, certeza (0–100) e peso aproximado;
- receitas que reaproveitam esse alimento (título, categoria, tempo, dificuldade, ingredientes, passos);
- formas de reaproveitamento que não são receitas (congelar, caldo, compostagem).

O backend salva as receitas geradas como `Recipe` com `source="ia"` e junta as receitas do catálogo que usam o mesmo
alimento. Se o alimento parecer estragado, a IA não sugere receitas, só descarte correto. Se a IA falhar (sem
internet, cota esgotada), a foto fica com `status="falhou"` e a mensagem explica o motivo.

## Endpoints por tela

Envie o token em todas as rotas, exceto login e cadastro: `Authorization: Token <token>`.

| Tela | Método e rota | O que faz |
|---|---|---|
| Login | `POST /api/login/` | `{username, password}` → `{token, ...}` |
| Criar conta | `POST /api/register/` | `{username, password, email?, first_name?, last_name?}` |
| Câmera / galeria | `POST /api/photos/` (multipart) | `image` + `source` (`camera` ou `galeria`) + `ingredient_name` opcional. Já devolve o alimento, as receitas e as dicas |
| Tela inicial | `GET /api/photos/latest/` | Card "Identificado agora" (204 se não houver) |
| Resultado de uma foto | `GET /api/photos/{id}/` | Alimento, `suggested_recipes` e `reuse_tips` |
| "Gerar outras receitas" | `POST /api/photos/{id}/regenerate/` | A IA cria receitas novas, sem repetir as anteriores |
| Histórico de Fotos | `GET /api/photos/` · `DELETE /api/photos/{id}/` | Fotos do usuário, mais recentes primeiro |
| Receitas sugeridas | `GET /api/recipes/suggested/?photo=&category=&search=` | Receitas das últimas fotos (ou de uma foto) |
| Receitas (abas e busca) | `GET /api/recipes/?category=doces&search=limão&source=ia` | Catálogo + receitas da IA do próprio usuário |
| Receita aberta | `GET /api/recipes/{id}/` | Ingredientes e passos em listas |
| Abas | `GET /api/categories/` | Sopas, Petiscos, Doces, Bebidas, Pratos |
| "Fiz essa receita" / "Segui essa dica" | `POST /api/reuses/` | `{recipe?, tip?, photo?, saved_kg?, reused_at?}`. Sem `saved_kg`, usa o peso estimado pela IA |
| Perfil | `GET /api/profile/` · `PATCH /api/profile/` | Dados + `stats` (kg salvos, receitas feitas, dias seguidos, % da meta, conquistas) |
| Impacto | `GET /api/impact/?months=6` | kg reaproveitados mês a mês + alimentos mais salvos, para um gráfico |

## Modelos

| Model | Representa |
|---|---|
| `User` | Usuário, com avatar e meta mensal em kg |
| `Category` | Abas das receitas |
| `Ingredient` | Alimento identificado pela IA |
| `Recipe` + `RecipeIngredient` | Receita (do catálogo ou gerada pela IA), linhas de ingredientes e passos |
| `Photo` | Foto, status da análise, alimento, parte, estado, certeza, peso estimado e receitas sugeridas |
| `ReuseTip` | Forma de reaproveitamento sugerida para uma foto |
| `Reuse` | Registro de que o usuário reaproveitou algo; base do acompanhamento de impacto |

## Arquivos principais

- `apirecozinhe/ai.py` — tudo que fala com a IA (prompt, formato JSON, modo demonstração)
- `apirecozinhe/services.py` — regras: processar foto, salvar receitas, estatísticas e impacto
- `apirecozinhe/models.py`, `serializers.py`, `views.py`, `config/urls.py` — a API
