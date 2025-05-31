from django.utils import timezone
from pytz import timezone as pytz_timezone
from django.http import JsonResponse

class PasswordDeadlineCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if response:
            return response
        return self.get_response(request)

    def process_request(self, request):
        user = request.user
        if user.is_authenticated:
            # Check nếu đã yêu cầu đổi mật khẩu mà chưa đổi trong thời gian cho phép
            if getattr(user, 'must_change_password', False):
                deadline = getattr(user, 'password_set_deadline', None)
                if deadline:
                    vn_now = timezone.now().astimezone(pytz_timezone('Asia/Ho_Chi_Minh'))
                    # So sánh deadline cũng phải đảm bảo deadline có timezone
                    if timezone.is_naive(deadline):
                        deadline = timezone.make_aware(deadline, timezone=pytz_timezone('Asia/Ho_Chi_Minh'))
                    if vn_now > deadline:
                        if not user.is_locked:
                            user.is_locked = True
                            user.save()
                        return JsonResponse({'detail': 'Tài khoản bị khoá do chưa đổi mật khẩu trong 24h.'}, status=403)
            if getattr(user, 'is_locked', False):
                return JsonResponse({'detail': 'Tài khoản đã bị khoá.'}, status=403)
