/*
 * Kardex — comportamiento de interfaz.
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
  var elementoConFocoAntesDelModal = null;

  function elementosEnfocables(contenedor) {
    /* input[type=hidden] queda fuera: un navegador nunca le da foco de verdad
       (el csrfmiddlewaretoken de cada formulario es de ese tipo), así que
       incluirlo aquí hacía que .focus() fallara en silencio y el foco cayera
       en <body> sin ningún indicador visible. */
    var selector = 'a[href], button:not([disabled]), ' +
      'input:not([disabled]):not([type="hidden"]), ' +
      'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return Array.prototype.slice.call(contenedor.querySelectorAll(selector));
  }

  function cerrarModal() {
    var contenedor = document.getElementById("modal");
    if (contenedor) contenedor.innerHTML = "";
    if (elementoConFocoAntesDelModal && elementoConFocoAntesDelModal.focus) {
      elementoConFocoAntesDelModal.focus();
    }
    elementoConFocoAntesDelModal = null;
  }

  document.body.addEventListener("kardexCerrarModal", cerrarModal);

  document.addEventListener("click", function (evento) {
    if (evento.target.matches("[data-cerrar-modal]")) {
      evento.preventDefault();
      cerrarModal();
    }
  });

  /* El modal atrapa el foco: Tab no se escapa hacia la página de atrás. */
  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") {
      cerrarModal();
      return;
    }
    if (evento.key !== "Tab") return;

    var modal = document.querySelector(".modal-fondo .modal");
    if (!modal) return;

    var enfocables = elementosEnfocables(modal);
    if (!enfocables.length) return;

    var primero = enfocables[0];
    var ultimo = enfocables[enfocables.length - 1];

    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero.focus();
    }
  });

  /* Al insertar un modal nuevo en el DOM, se guarda el foco previo y se
     mueve al primer campo. */
  document.body.addEventListener("htmx:afterSwap", function (evento) {
    if (evento.detail.target.id !== "modal") return;
    var modal = evento.detail.target.querySelector(".modal");
    if (!modal) return;

    elementoConFocoAntesDelModal = document.activeElement;
    var enfocables = elementosEnfocables(modal);
    /* El primer campo del formulario, no el botón de cerrar del encabezado. */
    var primerCampo = enfocables.find(function (el) { return !el.matches(".modal__cerrar"); });
    var objetivo = primerCampo || enfocables[0];
    if (objetivo) objetivo.focus();
  });

  /* Atajo «/» para enfocar el buscador global (punto 2.5). */
  document.addEventListener("keydown", function (evento) {
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

  /* ---------------------------------------- Estado de carga en el botón */
  function botonQueDisparo(elt) {
    if (!elt) return null;
    if (elt.tagName === "BUTTON") return elt;
    if (elt.tagName === "FORM") return elt.querySelector('button[type="submit"]');
    return null;
  }

  document.body.addEventListener("htmx:beforeRequest", function (evento) {
    var boton = botonQueDisparo(evento.detail.elt);
    if (boton) boton.setAttribute("aria-busy", "true");
  });

  document.body.addEventListener("htmx:afterRequest", function (evento) {
    var boton = botonQueDisparo(evento.detail.elt);
    if (boton) boton.removeAttribute("aria-busy");
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
    var tabla = origen.closest("table");
    if (!tabla) return;

    if (origen.matches("[data-seleccionar-todo]")) {
      tabla.querySelectorAll("[data-seleccionar-fila]").forEach(function (casilla) {
        casilla.checked = origen.checked;
      });
    } else if (!origen.matches("[data-seleccionar-fila]")) {
      return;
    }

    var barra = document.getElementById("seleccion-barra");
    var contador = barra && barra.querySelector("[data-contador-seleccion]");
    if (!barra) return;
    var marcadas = tabla.querySelectorAll("[data-seleccionar-fila]:checked").length;
    barra.hidden = marcadas === 0;
    if (contador) {
      contador.textContent =
        marcadas === 1 ? "1 fila seleccionada" : marcadas + " filas seleccionadas";
    }
  });

  /* --------------------------------------------------- Tema claro / oscuro */
  var CLAVE_TEMA = "kardex-tema";

  function aplicarTema(tema) {
    document.documentElement.setAttribute("data-tema", tema);
    var interruptor = document.getElementById("interruptor-tema");
    if (interruptor) interruptor.setAttribute("aria-pressed", String(tema === "oscuro"));
  }

  /* Tema realmente en pantalla ahora mismo: la elección manual si existe,
     si no, la preferencia del sistema. Sin esto, alternar el tema por
     primera vez en un sistema que ya está en oscuro no hacía nada visible. */
  function temaEfectivo() {
    var explicito = document.documentElement.getAttribute("data-tema");
    if (explicito === "oscuro" || explicito === "claro") return explicito;
    var prefiereOscuro = window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefiereOscuro ? "oscuro" : "claro";
  }

  function alternarTema() {
    var siguiente = temaEfectivo() === "oscuro" ? "claro" : "oscuro";
    try {
      window.localStorage.setItem(CLAVE_TEMA, siguiente);
    } catch (error) {
      /* almacenamiento no disponible: el tema no se recuerda, pero cambia igual */
    }
    aplicarTema(siguiente);
  }

  document.addEventListener("click", function (evento) {
    if (evento.target.closest("#interruptor-tema")) alternarTema();
  });

  /* ------------------------------------------------ Barra lateral en móvil */
  function abrirLateral() {
    document.querySelector(".lateral").classList.add("lateral--abierta");
    document.querySelector(".velo-lateral").classList.add("velo-lateral--visible");
  }

  function cerrarLateral() {
    var lateral = document.querySelector(".lateral");
    var velo = document.querySelector(".velo-lateral");
    if (lateral) lateral.classList.remove("lateral--abierta");
    if (velo) velo.classList.remove("velo-lateral--visible");
  }

  document.addEventListener("click", function (evento) {
    if (evento.target.closest(".boton-menu")) abrirLateral();
    else if (evento.target.closest(".velo-lateral")) cerrarLateral();
    else if (evento.target.closest(".lateral .menu__enlace")) cerrarLateral();
  });

  /* ------------------------------------- Selector con búsqueda (punto 2.4) */
  document.addEventListener("input", function (evento) {
    if (!evento.target.matches("[data-combo-buscador]")) return;
    var campo = evento.target;
    var lista = document.getElementById(campo.getAttribute("data-combo-buscador"));
    if (!lista) return;
    var termino = campo.value.trim().toLowerCase();
    var visibles = 0;
    lista.querySelectorAll(".combo__opcion").forEach(function (opcion) {
      var coincide = opcion.textContent.toLowerCase().indexOf(termino) !== -1;
      opcion.hidden = !coincide;
      if (coincide) visibles += 1;
    });
    var vacio = lista.querySelector(".combo__vacio");
    if (vacio) vacio.hidden = visibles > 0;
    lista.hidden = false;
  });

  document.addEventListener("click", function (evento) {
    var opcion = evento.target.closest(".combo__opcion");
    if (!opcion) return;
    var combo = opcion.closest(".combo");
    var campoOculto = combo.querySelector('input[type="hidden"]');
    var campoTexto = combo.querySelector("[data-combo-buscador]");
    if (campoOculto) campoOculto.value = opcion.getAttribute("data-valor") || "";
    if (campoTexto) campoTexto.value = opcion.textContent.trim();
    var lista = combo.querySelector(".combo__lista");
    if (lista) lista.hidden = true;
    campoOculto && campoOculto.dispatchEvent(new Event("change", { bubbles: true }));
  });

  document.addEventListener("click", function (evento) {
    document.querySelectorAll(".combo__lista:not([hidden])").forEach(function (lista) {
      if (!lista.closest(".combo").contains(evento.target)) lista.hidden = true;
    });
  });

  /* ------------------------------------------------------------- Arranque */
  (function inicializarTema() {
    var guardado = null;
    try {
      guardado = window.localStorage.getItem(CLAVE_TEMA);
    } catch (error) {
      guardado = null;
    }
    if (guardado === "oscuro" || guardado === "claro") aplicarTema(guardado);
  })();
})();
