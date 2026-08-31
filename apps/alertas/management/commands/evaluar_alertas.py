"""
Comando de gestión: evalúa todas las reglas de alerta activas.

Pensado para un ping externo (cron-job.org, UptimeRobot…), porque el plan
gratuito de Render no trae tareas programadas. También lo usa el botón
«Evaluar ahora» de la pantalla de alertas.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.alertas.services import ServicioEvaluador


class Command(BaseCommand):
    """Recorre el inventario contra cada regla activa y abre o cierra alertas."""

    help = "Evalúa todas las reglas de alerta activas contra el inventario actual."

    def handle(self, *args, **options):
        evaluadas = ServicioEvaluador.evaluar_todo()
        self.stdout.write(self.style.SUCCESS(f"Reglas evaluadas: {evaluadas}"))
