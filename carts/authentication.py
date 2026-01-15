# products/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions

class MicroserviceJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        """
        Instead of fetching user from local DB, create a dummy user
        using the user_id from the token.
        """
        user_id = validated_token.get('user_id')
        if not user_id:
            raise exceptions.AuthenticationFailed("User ID not found in token")

        # Create a minimal user object
        user = type('User', (), {})()
        user.id = user_id
        user.is_authenticated = True
        return user
