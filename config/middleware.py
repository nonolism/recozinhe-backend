from django.conf import settings
from django.http import HttpResponse


class DevCorsMiddleware:
    """
    Só em desenvolvimento (DEBUG=True): permite que o app aberto no navegador
    (npx expo start --web) chame a API. No celular isso não é necessário.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.DEBUG:
            return self.get_response(request)

        if request.method == 'OPTIONS':
            response = HttpResponse()
        else:
            response = self.get_response(request)

        response['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, Accept'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
        return response
