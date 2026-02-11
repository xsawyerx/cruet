/*
 * wsgi.c — WSGI environ construction and response formatting in C.
 *
 * These functions implement the data transformation between the C HTTP parser
 * output and the WSGI protocol (PEP 3333), without depending on any cruet
 * Python code.  This keeps the WSGI server cleanly separated from the Flask-
 * compatible application layer.
 */

#include "server.h"
#include <string.h>
#include <ctype.h>

/* ------------------------------------------------------------------ */
/* build_environ — construct a WSGI environ dict from parsed request   */
/* ------------------------------------------------------------------ */

/*
 * Internal C-callable version.
 *   parsed:      dict from parse_http_request (method, path, query_string,
 *                version, headers, body)
 *   client_addr: tuple (host_str, port_int)
 *   server_addr: tuple (host_str, port_int)
 *
 * Returns a new dict (WSGI environ) or NULL on error.
 */
PyObject *
Cruet_build_environ(PyObject *parsed, PyObject *client_addr,
                     PyObject *server_addr)
{
    PyObject *environ = PyDict_New();
    if (!environ) return NULL;

    /* --- Scalar fields from parsed dict (borrowed refs) --- */

    PyObject *method = PyDict_GetItemString(parsed, "method");
    PyObject *path   = PyDict_GetItemString(parsed, "path");
    PyObject *qs     = PyDict_GetItemString(parsed, "query_string");
    PyObject *ver    = PyDict_GetItemString(parsed, "version");
    PyObject *body   = PyDict_GetItemString(parsed, "body");

    if (!method || !path || !ver) {
        PyErr_SetString(PyExc_KeyError,
                        "parsed request missing method/path/version");
        Py_DECREF(environ);
        return NULL;
    }

    /* REQUEST_METHOD, SCRIPT_NAME, PATH_INFO, QUERY_STRING */
    PyDict_SetItemString(environ, "REQUEST_METHOD", method);
    PyObject *empty = PyUnicode_FromString("");
    if (!empty) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "SCRIPT_NAME", empty);
    Py_DECREF(empty);
    PyDict_SetItemString(environ, "PATH_INFO", path);
    if (qs) {
        PyDict_SetItemString(environ, "QUERY_STRING", qs);
    } else {
        PyObject *qs_empty = PyUnicode_FromString("");
        if (!qs_empty) { Py_DECREF(environ); return NULL; }
        PyDict_SetItemString(environ, "QUERY_STRING", qs_empty);
        Py_DECREF(qs_empty);
    }

    /* SERVER_NAME, SERVER_PORT, SERVER_PROTOCOL */
    PyObject *srv_name = PyTuple_GetItem(server_addr, 0); /* borrowed */
    PyObject *srv_port_int = PyTuple_GetItem(server_addr, 1); /* borrowed */
    if (!srv_name || !srv_port_int) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "SERVER_NAME", srv_name);
    PyObject *srv_port_str = PyObject_Str(srv_port_int);
    if (!srv_port_str) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "SERVER_PORT", srv_port_str);
    Py_DECREF(srv_port_str);
    PyDict_SetItemString(environ, "SERVER_PROTOCOL", ver);

    /* wsgi.version = (1, 0) */
    PyObject *wsgi_ver = Py_BuildValue("(ii)", 1, 0);
    if (!wsgi_ver) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "wsgi.version", wsgi_ver);
    Py_DECREF(wsgi_ver);

    /* wsgi.url_scheme = "http" */
    PyObject *scheme = PyUnicode_FromString("http");
    if (!scheme) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "wsgi.url_scheme", scheme);
    Py_DECREF(scheme);

    /* wsgi.input = io.BytesIO(body) */
    PyObject *io_mod = PyImport_ImportModule("io");
    if (!io_mod) { Py_DECREF(environ); return NULL; }
    PyObject *body_bytes = body ? body : PyBytes_FromStringAndSize("", 0);
    if (!body && !body_bytes) { Py_DECREF(io_mod); Py_DECREF(environ); return NULL; }
    PyObject *bytes_io = PyObject_CallMethod(io_mod, "BytesIO", "O",
                                             body ? body : body_bytes);
    if (!body) Py_DECREF(body_bytes);
    Py_DECREF(io_mod);
    if (!bytes_io) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "wsgi.input", bytes_io);
    Py_DECREF(bytes_io);

    /* wsgi.errors = sys.stderr */
    PyObject *sys_mod = PyImport_ImportModule("sys");
    if (!sys_mod) { Py_DECREF(environ); return NULL; }
    PyObject *stderr_obj = PyObject_GetAttrString(sys_mod, "stderr");
    Py_DECREF(sys_mod);
    if (!stderr_obj) { Py_DECREF(environ); return NULL; }
    PyDict_SetItemString(environ, "wsgi.errors", stderr_obj);
    Py_DECREF(stderr_obj);

    /* wsgi.multithread, wsgi.multiprocess, wsgi.run_once */
    PyDict_SetItemString(environ, "wsgi.multithread", Py_False);
    PyDict_SetItemString(environ, "wsgi.multiprocess", Py_True);
    PyDict_SetItemString(environ, "wsgi.run_once", Py_False);

    /* REMOTE_ADDR, REMOTE_PORT */
    if (client_addr && client_addr != Py_None) {
        PyObject *raddr = PyTuple_GetItem(client_addr, 0);
        PyObject *rport_int = PyTuple_GetItem(client_addr, 1);
        if (raddr) PyDict_SetItemString(environ, "REMOTE_ADDR", raddr);
        if (rport_int) {
            PyObject *rport_str = PyObject_Str(rport_int);
            if (rport_str) {
                PyDict_SetItemString(environ, "REMOTE_PORT", rport_str);
                Py_DECREF(rport_str);
            }
        }
    } else {
        PyObject *e = PyUnicode_FromString("");
        if (e) {
            PyDict_SetItemString(environ, "REMOTE_ADDR", e);
            PyDict_SetItemString(environ, "REMOTE_PORT", e);
            Py_DECREF(e);
        }
    }

    /* --- Map request headers to HTTP_* environ keys --- */

    PyObject *headers = PyDict_GetItemString(parsed, "headers"); /* borrowed */
    if (headers && PyDict_Check(headers)) {
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(headers, &pos, &key, &value)) {
            const char *name = PyUnicode_AsUTF8(key);
            if (!name) continue;

            /* Uppercase + replace '-' with '_' */
            size_t nlen = strlen(name);
            char upper[256];
            if (nlen >= sizeof(upper)) continue; /* skip absurdly long names */
            for (size_t i = 0; i < nlen; i++) {
                char c = name[i];
                if (c == '-') upper[i] = '_';
                else upper[i] = (c >= 'a' && c <= 'z') ? c - 32 : c;
            }
            upper[nlen] = '\0';

            if (strcmp(upper, "CONTENT_TYPE") == 0) {
                PyDict_SetItemString(environ, "CONTENT_TYPE", value);
            } else if (strcmp(upper, "CONTENT_LENGTH") == 0) {
                PyDict_SetItemString(environ, "CONTENT_LENGTH", value);
            } else if (strcmp(upper, "HOST") == 0) {
                PyDict_SetItemString(environ, "HTTP_HOST", value);
            } else {
                /* HTTP_{NAME} */
                char envkey[270]; /* "HTTP_" + 256 + nul */
                snprintf(envkey, sizeof(envkey), "HTTP_%s", upper);
                PyDict_SetItemString(environ, envkey, value);
            }
        }
    }

    /* Ensure HTTP_HOST is set */
    PyObject *http_host_key = PyUnicode_FromString("HTTP_HOST");
    if (!http_host_key) { Py_DECREF(environ); return NULL; }
    int has_host = PyDict_Contains(environ, http_host_key);
    Py_DECREF(http_host_key);
    if (has_host <= 0) {
        const char *sname = PyUnicode_AsUTF8(srv_name);
        long sport = PyLong_AsLong(srv_port_int);
        if (sname && sport >= 0) {
            char hostbuf[300];
            snprintf(hostbuf, sizeof(hostbuf), "%s:%ld", sname, sport);
            PyObject *host_val = PyUnicode_FromString(hostbuf);
            if (host_val) {
                PyDict_SetItemString(environ, "HTTP_HOST", host_val);
                Py_DECREF(host_val);
            }
        }
    }

    return environ;
}

/* Python-callable wrapper */
static PyObject *
cruet_build_environ(PyObject *self, PyObject *args)
{
    PyObject *parsed, *client_addr, *server_addr;
    if (!PyArg_ParseTuple(args, "OOO", &parsed, &client_addr, &server_addr))
        return NULL;
    return Cruet_build_environ(parsed, client_addr, server_addr);
}

/* ------------------------------------------------------------------ */
/* format_response — serialize WSGI output to HTTP/1.1 bytes           */
/* ------------------------------------------------------------------ */

/*
 * Internal C-callable version.
 *   status:     str like "200 OK"
 *   headers:    list of (name, value) tuples
 *   body_parts: iterable of bytes
 *
 * Returns a new bytes object or NULL on error.
 */
PyObject *
Cruet_format_response(PyObject *status, PyObject *headers,
                       PyObject *body_parts)
{
    /* --- Build header block --- */

    /* "HTTP/1.1 " + status + "\r\n" */
    const char *status_str = PyUnicode_AsUTF8(status);
    if (!status_str) return NULL;

    /* Estimate header size: status line + headers + blank line */
    size_t hdr_cap = 32 + strlen(status_str);

    /* Count headers for capacity estimate */
    Py_ssize_t n_headers = PyList_Check(headers) ? PyList_GET_SIZE(headers) : 0;
    hdr_cap += (size_t)n_headers * 64; /* rough estimate per header */

    char *hdr_buf = (char *)malloc(hdr_cap);
    if (!hdr_buf) return PyErr_NoMemory();

    size_t hdr_len = 0;

    /* Status line */
    int written = snprintf(hdr_buf + hdr_len, hdr_cap - hdr_len,
                           "HTTP/1.1 %s\r\n", status_str);
    hdr_len += (size_t)written;

    /* Headers */
    for (Py_ssize_t i = 0; i < n_headers; i++) {
        PyObject *tuple = PyList_GET_ITEM(headers, i);
        PyObject *hname = PyTuple_GetItem(tuple, 0);
        PyObject *hval  = PyTuple_GetItem(tuple, 1);
        if (!hname || !hval) { free(hdr_buf); return NULL; }

        const char *ns = PyUnicode_AsUTF8(hname);
        const char *vs = PyUnicode_AsUTF8(hval);
        if (!ns || !vs) { free(hdr_buf); return NULL; }

        size_t needed = strlen(ns) + strlen(vs) + 5; /* ": " + "\r\n" + nul */
        if (hdr_len + needed > hdr_cap) {
            hdr_cap = (hdr_len + needed) * 2;
            char *new_buf = (char *)realloc(hdr_buf, hdr_cap);
            if (!new_buf) { free(hdr_buf); return PyErr_NoMemory(); }
            hdr_buf = new_buf;
        }

        written = snprintf(hdr_buf + hdr_len, hdr_cap - hdr_len,
                           "%s: %s\r\n", ns, vs);
        hdr_len += (size_t)written;
    }

    /* Blank line */
    if (hdr_len + 3 > hdr_cap) {
        hdr_cap = hdr_len + 4;
        char *new_buf = (char *)realloc(hdr_buf, hdr_cap);
        if (!new_buf) { free(hdr_buf); return PyErr_NoMemory(); }
        hdr_buf = new_buf;
    }
    memcpy(hdr_buf + hdr_len, "\r\n", 2);
    hdr_len += 2;

    /* --- Collect body parts --- */

    PyObject *body_list = PySequence_List(body_parts);
    if (!body_list) { free(hdr_buf); return NULL; }

    /* Calculate total body size */
    size_t body_len = 0;
    Py_ssize_t n_parts = PyList_GET_SIZE(body_list);
    for (Py_ssize_t i = 0; i < n_parts; i++) {
        PyObject *part = PyList_GET_ITEM(body_list, i);
        if (PyBytes_Check(part)) {
            body_len += (size_t)PyBytes_GET_SIZE(part);
        }
    }

    /* Allocate final buffer: header + body */
    size_t total = hdr_len + body_len;
    char *result_buf = (char *)malloc(total);
    if (!result_buf) {
        free(hdr_buf);
        Py_DECREF(body_list);
        return PyErr_NoMemory();
    }

    /* Copy header */
    memcpy(result_buf, hdr_buf, hdr_len);
    free(hdr_buf);

    /* Copy body parts */
    size_t offset = hdr_len;
    for (Py_ssize_t i = 0; i < n_parts; i++) {
        PyObject *part = PyList_GET_ITEM(body_list, i);
        if (PyBytes_Check(part)) {
            Py_ssize_t plen = PyBytes_GET_SIZE(part);
            memcpy(result_buf + offset, PyBytes_AS_STRING(part), (size_t)plen);
            offset += (size_t)plen;
        }
    }
    Py_DECREF(body_list);

    PyObject *result = PyBytes_FromStringAndSize(result_buf, (Py_ssize_t)total);
    free(result_buf);
    return result;
}

/* Python-callable wrapper */
static PyObject *
cruet_format_response(PyObject *self, PyObject *args)
{
    PyObject *status, *headers, *body_parts;
    if (!PyArg_ParseTuple(args, "OOO", &status, &headers, &body_parts))
        return NULL;
    return Cruet_format_response(status, headers, body_parts);
}

/* ------------------------------------------------------------------ */
/* Method table for registration                                       */
/* ------------------------------------------------------------------ */

PyMethodDef cruet_wsgi_methods[] = {
    {"build_environ", cruet_build_environ, METH_VARARGS,
     "Build a WSGI environ dict from a parsed HTTP request."},
    {"format_response", cruet_format_response, METH_VARARGS,
     "Format a WSGI response as HTTP/1.1 bytes."},
    {NULL}
};
