from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    storage_used_formatted = serializers.ReadOnlyField(source='formatted_used')
    storage_quota_formatted = serializers.ReadOnlyField(source='formatted_quota')
    used_percentage = serializers.ReadOnlyField(source='get_used_percentage')

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile_picture', 'phone_number', 'bio', 'storage_quota',
            'storage_used', 'storage_used_formatted', 'storage_quota_formatted',
            'used_percentage', 'is_email_verified', 'is_staff', 'is_superuser'
        ]
        read_only_fields = ['id', 'storage_quota', 'storage_used', 'is_staff', 'is_superuser']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm', 'first_name', 'last_name']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user
