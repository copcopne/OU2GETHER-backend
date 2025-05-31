from django.utils import timezone
from django.http import JsonResponse

class PasswordDeadlineCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            if getattr(user, 'must_change_password', False):
                deadline = getattr(user, 'password_set_deadline', None)
                if deadline and timezone.now() > deadline:
                    user.is_locked = True
                    user.save()
                    return JsonResponse({'detail': 'Tài khoản bị khoá do chưa đổi mật khẩu trong 24h.'}, status=403)
            if user.is_locked:
                return JsonResponse({'detail': 'Tài khoản đã bị khoá.'}, status=403)

        return self.get_response(request)
