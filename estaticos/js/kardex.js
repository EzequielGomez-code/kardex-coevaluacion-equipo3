/*
 * Kardex — comportamiento de interfaz. Menos de 150 líneas (punto 3 del brief).
 * Todo lo que hay aquí es comodidad: la validación y los permisos que mandan
 * están en el servidor (Seguridad #4 y #9).
 */
(function () {
  "use strict";

  /* CSRF en cada petición de HTMX, incluidas las de formularios (Seguridad #2). */
  function galleta(nombre) {
    var partes = ("; " + document.cookie).split("; " + nombre + "=");
    return partes.length === 2 ? partes.pop().split(";").shift() : "";
  }

  document.body.addEventListener("htmx:configRequest", function (evento) {
    evento.detail.headers["X-CSRFToken"] = galleta("csrftoken");
  });

  /* ---------------------------------------------------------------- Toasts */
  function mostrarToast(texto, tipo) {
    var contenedor = document.getElementById("toasts");
    if (!contenedor || !texto) return;

    var toast = document.createElement("div");
    toast.className = "toast toast--" + (tipo || "ok");
    toast.setAttribute("role", "status");

    var cuerpo = document.createElement("div");
    cuerpo.className = "toast__texto";
    cuerpo.textContent = texto;

    var cerrar = document.createElement("button");
    cerrar.className = "toast__cerrar";
    cerrar.type = "button";
    cerrar.setAttribute("aria-label", "Cerrar aviso");
    cerrar.textContent = "×";
    cerrar.addEventListener("click", function () { toast.remove(); });

    toast.appendChild(cuerpo);
    toast.appendChild(cerrar);
    contenedor.appendChild(toast);
    window.setTimeout(function () { toast.remove(); }, 5000);
  }

  document.body.addEventListener("kardexToast", function (evento) {
    var datos = evento.detail || {};
    mostrarToast(datos.texto, datos.tipo);
  });

  /* ---------------------------------------------------------------- Modal */
  function cerrarModal() {
    var contenedor = document.getElementById("modal");
    if (contenedor) contenedor.innerHTML = "";
  }

  document.body.addEventListener("kardexCerrarModal", cerrarModal);

  document.addEventListener("click", function (evento) {
    if (evento.target.matches("[data-cerrar-modal]")) {
      evento.preventDefault();
      cerrarModal();
    }
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") cerrarModal();

    /* Atajo «/» para enfocar el buscador global (punto 5.4). */
    var enCampo = /^(INPUT|TEXTAREA|SELECT)$/.test(evento.target.tagName);
    if (evento.key === "/" && !enCampo && !evento.ctrlKey && !evento.metaKey) {
      var buscador = document.getElementById("buscador-global");
      if (buscador) {
        evento.preventDefault();
        buscador.focus();
        buscador.select();
      }
    }
  });

  /* ------------------------------------------- Reintento de red (HU-06) */
  var ultimoEnvioFallido = null;

  function avisarFalloDeRed(elemento) {
    var formulario = elemento.closest("form") || elemento;
    if (!formulario || formulario.querySelector(".aviso-red")) return;
    ultimoEnvioFallido = formulario;

    var aviso = document.createElement("div");
    aviso.className = "aviso-red";

    var texto = document.createElement("span");
    texto.textContent =
      "No se pudo enviar: sin conexión con el servidor. Sus datos siguen aquí.";

    var reintentar = document.createElement("button");
    reintentar.type = "button";
    reintentar.className = "boton boton--secundario";
    reintentar.textContent = "Reintentar";
    reintentar.addEventListener("click", function () {
      aviso.remove();
      if (ultimoEnvioFallido && window.htmx) {
        window.htmx.trigger(ultimoEnvioFallido, "submit");
      }
    });

    aviso.appendChild(texto);
    aviso.appendChild(reintentar);
    formulario.insertBefore(aviso, formulario.firstChild);
  }

  document.body.addEventListener("htmx:sendError", function (evento) {
    avisarFalloDeRed(evento.detail.elt);
  });
  document.body.addEventListener("htmx:timeout", function (evento) {
    avisarFalloDeRed(evento.detail.elt);
  });
  document.body.addEventListener("htmx:responseError", function (evento) {
    var codigo = evento.detail.xhr.status;
    if (codigo === 403) mostrarToast("Su rol no tiene permiso para esta acción.", "alerta");
    else if (codigo >= 500) mostrarToast("Error del servidor. Intente de nuevo.", "alerta");
  });

  /* ------------------------------------------- Selección múltiple en tablas */
  document.addEventListener("change", function (evento) {
    var origen = evento.target;
    if (!origen.matches("[data-seleccionar-todo]")) return;

    var tabla = origen.closest("table");
    if (!tabla) return;
    tabla.querySelectorAll("[data-seleccionar-fila]").forEach(function (casilla) {
      casilla.checked = origen.checked;
    });
    actualizarBarraSeleccion(tabla);
  });

  document.addEventListener("change", function (evento) {
    if (evento.target.matches("[data-seleccionar-fila]")) {
      actualizarBarraSeleccion(evento.target.closest("table"));
    }
  });

  function actualizarBarraSeleccion(tabla) {
    if (!tabla) return;
    var marcadas = tabla.querySelectorAll("[data-seleccionar-fila]:checked").length;
    var barra = document.getElementById("seleccion-barra");
    if (!barra) return;
    barra.hidden = marcadas === 0;
    var contador = barra.querySelector("[data-contador-seleccion]");
    if (contador) {
      contador.textContent =
        marcadas === 1 ? "1 fila seleccionada" : marcadas + " filas seleccionadas";
    }
  }
})();
