from django.apps import AppConfig


class MillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'milling'

    def ready(self):
        import milling.signals
