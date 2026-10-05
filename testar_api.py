"""
Testa o backend do ReCozinhe de ponta a ponta, do jeito que o app faria.

Como usar (com o servidor rodando em outro terminal: python manage.py runserver):

    python testar_api.py caminho/da/foto.jpg

Sem foto, ele cria uma imagem amarela chamada "banana.jpg" (funciona no modo demonstração).
"""
import io
import sys

import requests

BASE = "http://127.0.0.1:8000/api"
USUARIO = "teste"
SENHA = "Senha@Forte123"


def titulo(texto):
    print(f"\n=== {texto} " + "=" * (60 - len(texto)))


def checar(resposta, esperado=(200, 201)):
    if resposta.status_code not in esperado:
        print(f"ERRO {resposta.status_code}: {resposta.text[:500]}")
        sys.exit(1)
    return resposta


def main():
    try:
        requests.get(BASE + "/", timeout=5)
    except requests.ConnectionError:
        print("Não consegui falar com o servidor. Ele está rodando? (python manage.py runserver)")
        sys.exit(1)

    titulo("1. Login (cria a conta na primeira vez)")
    r = requests.post(f"{BASE}/login/", json={"username": USUARIO, "password": SENHA})
    if r.status_code == 401:
        r = checar(requests.post(f"{BASE}/register/", json={
            "username": USUARIO, "password": SENHA, "first_name": "Usuário", "last_name": "Teste",
        }))
        print("Conta criada.")
    token = checar(r).json()["token"]
    headers = {"Authorization": f"Token {token}"}
    print("Token:", token[:12] + "...")

    titulo("2. Enviando a foto para a IA")
    if len(sys.argv) > 1:
        foto = open(sys.argv[1], "rb")
        nome = sys.argv[1]
    else:
        from PIL import Image  # cria uma imagem de exemplo
        foto = io.BytesIO()
        Image.new("RGB", (200, 200), "yellow").save(foto, "JPEG")
        foto.seek(0)
        nome = "banana.jpg"
    r = checar(requests.post(f"{BASE}/photos/", headers=headers,
                             files={"image": (nome, foto, "image/jpeg")},
                             data={"source": "galeria"}, timeout=120))
    analise = r.json()
    print("Status:", analise["status"])
    if analise["ai_message"]:
        print("Mensagem:", analise["ai_message"])
    if analise["status"] != "identificado":
        print("A IA não identificou um alimento. Tente outra foto.")
        return
    print(f"Alimento: {analise['identified_ingredient']['name']} ({analise['confidence']}% de certeza)")
    print(f"Parte: {analise['food_part']} | Estado: {analise['condition']} | Peso: ~{analise['estimated_weight_g']} g")

    titulo("3. Receitas sugeridas")
    for receita in analise["suggested_recipes"]:
        origem = "IA" if receita["source"] == "ia" else "catálogo"
        print(f"- [{origem}] {receita['title']} ({receita['prep_time_minutes']} min, {receita['difficulty_display']})")

    titulo("4. Formas de reaproveitamento")
    for dica in analise["reuse_tips"]:
        print(f"- {dica['title']}: {dica['description']}")

    if analise["suggested_recipes"]:
        primeira = analise["suggested_recipes"][0]
        titulo("5. Receita aberta")
        receita = checar(requests.get(f"{BASE}/recipes/{primeira['id']}/", headers=headers)).json()
        print(receita["title"])
        print("Ingredientes:")
        for item in receita["ingredients"]:
            print("  •", item)
        print("Modo de preparo:")
        for n, passo in enumerate(receita["preparation_steps"], 1):
            print(f"  {n}. {passo}")

        titulo("6. Registrando 'Fiz essa receita'")
        r = checar(requests.post(f"{BASE}/reuses/", headers=headers,
                                 json={"recipe": primeira["id"], "photo": analise["id"]}))
        print(f"Reaproveitado: {r.json()['saved_kg']} kg")

    titulo("7. Perfil e impacto")
    stats = checar(requests.get(f"{BASE}/profile/", headers=headers)).json()["stats"]
    print(f"Total reaproveitado: {stats['saved_kg_total']} kg | Receitas feitas: {stats['recipes_cooked']}")
    print(f"Dias seguidos: {stats['streak_days']} | Meta do mês: {stats['monthly_goal_percent']}%")
    for conquista in stats["achievements"]:
        print(f"  [{'x' if conquista['unlocked'] else ' '}] {conquista['title']}")

    impacto = checar(requests.get(f"{BASE}/impact/", headers=headers)).json()
    print("Por mês:", ", ".join(f"{m['month']}: {m['saved_kg']} kg" for m in impacto["months"]))

    print("\nTudo certo! O backend respondeu em todas as etapas.")


if __name__ == "__main__":
    main()
