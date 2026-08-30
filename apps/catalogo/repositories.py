"""
Repositorios de Catálogo — los construye Arturo.

Regla de capas (punto 3 del brief): esta es la ÚNICA capa que puede tocar el
ORM de esta app. Un repositorio no decide nada; recibe criterios ya resueltos
y devuelve objetos o conjuntos de consulta.

Modelo a seguir, tomado de ``apps.nucleo.repositories``::

    class RepositorioArticulos:
        '''Acceso a datos de Articulo.'''

        @staticmethod
        def listar(busqueda: str = "") -> QuerySet[Articulo]:
            '''Devuelve los artículos filtrados por texto.'''
            consulta = Articulo.objects.select_related("categoria")
            if busqueda:
                consulta = consulta.filter(nombre__icontains=busqueda)
            return consulta.order_by("sku")
"""

# TODO(Arturo): agregar los repositorios de esta app.
