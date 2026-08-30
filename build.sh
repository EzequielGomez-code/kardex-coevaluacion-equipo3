#!/usr/bin/env bash
# Guion de construcción que ejecuta Render en cada despliegue.
# Punto 7 del brief: instalar dependencias, recolectar estáticos y migrar.

# Cualquier error detiene el despliegue: más vale no desplegar que desplegar roto.
set -o errexit

echo "==> Instalando dependencias"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Recolectando archivos estáticos (los sirve WhiteNoise)"
python manage.py collectstatic --no-input

echo "==> Aplicando migraciones en Neon"
python manage.py migrate --no-input

# La siembra es idempotente: se puede correr en cada despliegue sin duplicar.
# Se salta sola si la variable SEMBRAR_AL_DESPLEGAR no está en "true".
if [ "${SEMBRAR_AL_DESPLEGAR}" = "true" ]; then
  echo "==> Sembrando datos iniciales"
  python manage.py sembrar
fi

echo "==> Construcción terminada"
