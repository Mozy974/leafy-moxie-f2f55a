import time
import logging
from flask import request, jsonify
from functools import wraps

# Logger dédié à la sécurité / performance
logger = logging.getLogger("app.security")


def slow_request_guard(threshold_seconds=10):
    """
    Décorateur Flask qui surveille les requêtes lentes.
    Équivalent du TimeoutGuardMiddleware Starlette, adapté pour Flask.
    
    Usage:
        @app.route('/api/lourd')
        @slow_request_guard(threshold_seconds=5)
        def ma_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            start_time = time.time()
            try:
                response = f(*args, **kwargs)
                process_time = time.time() - start_time

                if process_time > threshold_seconds:
                    logger.warning(
                        f"⚠️ Requête lente détectée: {request.path} "
                        f"[{request.method}] - {process_time:.2f}s"
                    )

                return response

            except Exception as e:
                process_time = time.time() - start_time
                logger.error(
                    f"🚨 Échec critique sur {request.path} "
                    f"après {process_time:.2f}s : {str(e)}"
                )
                return jsonify({
                    "status": "optimization_needed",
                    "message": "Cette requête est trop lourde pour le moteur actuel.",
                    "suggestion": "Essayez de filtrer vos données ou d'utiliser l'export asynchrone."
                }), 503

        return wrapped
    return decorator


class GlobalTimeoutLogger:
    """
    Middleware WSGI global pour Flask.
    Logue TOUTES les requêtes lentes sans avoir à décorer chaque route.
    
    Usage dans app.py:
        from middleware import GlobalTimeoutLogger
        app.wsgi_app = GlobalTimeoutLogger(app.wsgi_app, threshold_seconds=10)
    """
    def __init__(self, wsgi_app, threshold_seconds=10):
        self.wsgi_app = wsgi_app
        self.threshold = threshold_seconds

    def __call__(self, environ, start_response):
        start_time = time.time()
        path = environ.get('PATH_INFO', '?')
        method = environ.get('REQUEST_METHOD', '?')

        try:
            result = self.wsgi_app(environ, start_response)
            process_time = time.time() - start_time

            if process_time > self.threshold:
                logger.warning(
                    f"⚠️ Requête lente: [{method}] {path} - {process_time:.2f}s"
                )

            return result

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"🚨 Erreur WSGI sur [{method}] {path} "
                f"après {process_time:.2f}s : {str(e)}"
            )
            raise
