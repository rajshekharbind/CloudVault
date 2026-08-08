def user_context(request):
    if request.user.is_authenticated:
        return {
            'user_storage_used_fmt': request.user.formatted_used(),
            'user_storage_quota_fmt': request.user.formatted_quota(),
            'user_storage_free_fmt': request.user.formatted_free(),
            'user_storage_pct': request.user.get_used_percentage(),
        }
    return {
        'user_storage_used_fmt': '0 B',
        'user_storage_quota_fmt': '15 GB',
        'user_storage_free_fmt': '15 GB',
        'user_storage_pct': 0,
    }
