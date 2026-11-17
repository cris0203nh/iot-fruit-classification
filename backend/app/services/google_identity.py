"""ID tokens Google: claves públicas fijas, RS256 y claims obligatorios."""
import os
import re
from functools import lru_cache
import jwt
from fastapi import HTTPException


def client_id():
    return os.getenv('AGROSCAN_GOOGLE_CLIENT_ID', '').strip()


def normalized_email(value):
    if not isinstance(value, str):
        raise ValueError('Correo inválido.')
    email = value.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError('Correo inválido.')
    return email


@lru_cache(maxsize=1)
def google_keys():
    return jwt.PyJWKClient('https://www.googleapis.com/oauth2/v3/certs', timeout=5, lifespan=300)


def verify_google_token(credential):
    audience = client_id()
    if not audience:
        raise HTTPException(503, 'Google no está configurado. Usa el acceso tradicional.')
    try:
        header = jwt.get_unverified_header(credential)
        if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str) or not 1 <= len(header['kid']) <= 128:
            raise ValueError('Cabecera inválida')
        key = google_keys().get_signing_key_from_jwt(credential).key
        claims = jwt.decode(credential, key, algorithms=['RS256'], audience=audience,
            issuer=['accounts.google.com', 'https://accounts.google.com'],
            options={'require': ['iss','aud','sub','exp','iat','nonce','email','email_verified'], 'strict_aud': True})
        if not isinstance(claims['sub'], str) or not claims['sub'].strip() or len(claims['sub']) > 255:
            raise ValueError('Identidad inválida')
        if type(claims['exp']) is not int or type(claims['iat']) is not int or claims['exp'] <= claims['iat']:
            raise ValueError('Fechas inválidas')
        if claims['email_verified'] is not True or claims.get('azp', audience) != audience:
            raise ValueError('Credencial inválida')
        if not isinstance(claims['nonce'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', claims['nonce']):
            raise ValueError('Desafío inválido')
        claims['email'] = normalized_email(claims['email'])
        return claims
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, 'No se pudo verificar Google. Reintenta más tarde.') from None
    except (jwt.InvalidTokenError, jwt.PyJWKClientError, ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Credencial de Google inválida.') from None
