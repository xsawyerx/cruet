#include "http.h"
#include <structmember.h>
#include <string.h>
#include <stdio.h>
#include <time.h>

/* Status text lookup */
static const char *
status_text(int code)
{
    switch (code) {
    case 200: return "OK";
    case 201: return "Created";
    case 204: return "No Content";
    case 301: return "Moved Permanently";
    case 302: return "Found";
    case 304: return "Not Modified";
    case 400: return "Bad Request";
    case 401: return "Unauthorized";
    case 403: return "Forbidden";
    case 404: return "Not Found";
    case 405: return "Method Not Allowed";
    case 500: return "Internal Server Error";
    case 502: return "Bad Gateway";
    case 503: return "Service Unavailable";
    default: return "Unknown";
    }
}

static int
CResponse_init(Cruet_CResponse *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"body", "status", "headers", "content_type", NULL};
    PyObject *body = NULL;
    PyObject *status_obj = NULL;
    PyObject *headers_dict = NULL;
    const char *content_type = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|OOOz", kwlist,
                                      &body, &status_obj, &headers_dict,
                                      &content_type))
        return -1;

    /* Default status */
    self->status_code = 200;

    if (status_obj && status_obj != Py_None) {
        if (PyLong_Check(status_obj)) {
            self->status_code = (int)PyLong_AsLong(status_obj);
        } else if (PyUnicode_Check(status_obj)) {
            /* Parse "200 OK" style */
            const char *s = PyUnicode_AsUTF8(status_obj);
            self->status_code = atoi(s);
        }
    }

    /* Build status text */
    char buf[64];
    snprintf(buf, sizeof(buf), "%d %s", self->status_code, status_text(self->status_code));
    self->status_text = strdup(buf);

    /* Body */
    if (body && body != Py_None) {
        if (PyBytes_Check(body)) {
            self->body = body;
            Py_INCREF(body);
        } else if (PyUnicode_Check(body)) {
            self->body = PyUnicode_AsEncodedString(body, "utf-8", "strict");
            if (!self->body) return -1;
        } else {
            PyErr_SetString(PyExc_TypeError, "body must be str or bytes");
            return -1;
        }
    } else {
        self->body = PyBytes_FromStringAndSize("", 0);
    }

    /* Headers */
    self->headers = PyObject_CallFunction((PyObject *)&Cruet_CHeadersType, NULL);
    if (!self->headers) return -1;

    if (headers_dict && headers_dict != Py_None && PyDict_Check(headers_dict)) {
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(headers_dict, &pos, &key, &value)) {
            PyObject_CallMethod(self->headers, "set", "OO", key, value);
        }
    }

    /* Set Content-Type */
    if (content_type) {
        PyObject_CallMethod(self->headers, "set", "ss", "Content-Type", content_type);
    } else {
        /* Check if Content-Type already set */
        PyObject *ct = PyObject_CallMethod(self->headers, "get", "s", "Content-Type");
        if (ct == Py_None) {
            Py_DECREF(ct);
            PyObject_CallMethod(self->headers, "set", "ss",
                                "Content-Type", "text/html; charset=utf-8");
        } else {
            Py_DECREF(ct);
        }
    }

    /* Set Content-Length */
    Py_ssize_t body_len = PyBytes_GET_SIZE(self->body);
    char cl_buf[32];
    snprintf(cl_buf, sizeof(cl_buf), "%zd", body_len);
    PyObject_CallMethod(self->headers, "set", "ss", "Content-Length", cl_buf);

    /* Cookie list */
    self->set_cookies = PyList_New(0);
    if (!self->set_cookies) return -1;

    return 0;
}

static void
CResponse_dealloc(Cruet_CResponse *self)
{
    Py_XDECREF(self->body);
    free(self->status_text);
    Py_XDECREF(self->headers);
    Py_XDECREF(self->set_cookies);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
CResponse_get_status_code(Cruet_CResponse *self, void *closure)
{
    return PyLong_FromLong(self->status_code);
}

static PyObject *
CResponse_get_status(Cruet_CResponse *self, void *closure)
{
    return PyUnicode_FromString(self->status_text);
}

static PyObject *
CResponse_get_headers(Cruet_CResponse *self, void *closure)
{
    Py_INCREF(self->headers);
    return self->headers;
}

static PyObject *
CResponse_get_content_type(Cruet_CResponse *self, void *closure)
{
    return PyObject_CallMethod(self->headers, "get", "ss", "Content-Type", "");
}

static int
CResponse_set_content_type(Cruet_CResponse *self, PyObject *value, void *closure)
{
    if (!PyUnicode_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "content_type must be a string");
        return -1;
    }
    PyObject *result = PyObject_CallMethod(self->headers, "set", "sO", "Content-Type", value);
    Py_XDECREF(result);
    return result ? 0 : -1;
}

static PyObject *
CResponse_get_data(Cruet_CResponse *self, void *closure)
{
    Py_INCREF(self->body);
    return self->body;
}

/* Helper to update status_text and Content-Length when status/data changes */
static void
update_status_text(Cruet_CResponse *self)
{
    free(self->status_text);
    char buf[64];
    snprintf(buf, sizeof(buf), "%d %s", self->status_code, status_text(self->status_code));
    self->status_text = strdup(buf);
}

static void
update_content_length(Cruet_CResponse *self)
{
    Py_ssize_t body_len = PyBytes_GET_SIZE(self->body);
    char cl_buf[32];
    snprintf(cl_buf, sizeof(cl_buf), "%zd", body_len);
    PyObject_CallMethod(self->headers, "set", "ss", "Content-Length", cl_buf);
}

static int
CResponse_set_status_code(Cruet_CResponse *self, PyObject *value, void *closure)
{
    if (!PyLong_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "status_code must be an integer");
        return -1;
    }
    self->status_code = (int)PyLong_AsLong(value);
    update_status_text(self);
    return 0;
}

static int
CResponse_set_status(Cruet_CResponse *self, PyObject *value, void *closure)
{
    if (!PyUnicode_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "status must be a string");
        return -1;
    }
    const char *s = PyUnicode_AsUTF8(value);
    self->status_code = atoi(s);
    free(self->status_text);
    self->status_text = strdup(s);
    return 0;
}

static int
CResponse_set_data(Cruet_CResponse *self, PyObject *value, void *closure)
{
    PyObject *new_body;
    if (PyBytes_Check(value)) {
        new_body = value;
        Py_INCREF(new_body);
    } else if (PyUnicode_Check(value)) {
        new_body = PyUnicode_AsEncodedString(value, "utf-8", "strict");
        if (!new_body) return -1;
    } else {
        PyErr_SetString(PyExc_TypeError, "data must be str or bytes");
        return -1;
    }
    Py_DECREF(self->body);
    self->body = new_body;
    update_content_length(self);
    return 0;
}

/* Method: get_data(as_text=False) */
static PyObject *
CResponse_method_get_data(Cruet_CResponse *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"as_text", NULL};
    int as_text = 0;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|p", kwlist, &as_text))
        return NULL;
    if (as_text) {
        return PyUnicode_FromEncodedObject(self->body, "utf-8", "replace");
    }
    Py_INCREF(self->body);
    return self->body;
}

/* Method: get_json() */
static PyObject *
CResponse_method_get_json(Cruet_CResponse *self, PyObject *Py_UNUSED(ignored))
{
    PyObject *json_mod = PyImport_ImportModule("json");
    if (!json_mod) return NULL;
    PyObject *str_data = PyUnicode_FromEncodedObject(self->body, "utf-8", "strict");
    if (!str_data) { Py_DECREF(json_mod); return NULL; }
    PyObject *result = PyObject_CallMethod(json_mod, "loads", "O", str_data);
    Py_DECREF(json_mod);
    Py_DECREF(str_data);
    return result;
}

/* Property: json (same as get_json) */
static PyObject *
CResponse_get_json(Cruet_CResponse *self, void *closure)
{
    return CResponse_method_get_json(self, NULL);
}

/* Property: is_json */
static PyObject *
CResponse_get_is_json(Cruet_CResponse *self, void *closure)
{
    PyObject *ct = PyObject_CallMethod(self->headers, "get", "ss", "Content-Type", "");
    if (!ct) return NULL;
    const char *ct_str = PyUnicode_AsUTF8(ct);
    int result = (ct_str && (strstr(ct_str, "application/json") || strstr(ct_str, "+json")));
    Py_DECREF(ct);
    if (result) Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

/* Property: mimetype */
static PyObject *
CResponse_get_mimetype(Cruet_CResponse *self, void *closure)
{
    PyObject *ct = PyObject_CallMethod(self->headers, "get", "ss", "Content-Type", "");
    if (!ct) return NULL;
    const char *ct_str = PyUnicode_AsUTF8(ct);
    if (!ct_str || !ct_str[0]) { return ct; }
    const char *semi = strchr(ct_str, ';');
    if (semi) {
        PyObject *result = PyUnicode_FromStringAndSize(ct_str, semi - ct_str);
        Py_DECREF(ct);
        return result;
    }
    return ct;
}

/* Property: content_length */
static PyObject *
CResponse_get_content_length(Cruet_CResponse *self, void *closure)
{
    return PyLong_FromSsize_t(PyBytes_GET_SIZE(self->body));
}

/* Property: location (get/set) */
static PyObject *
CResponse_get_location(Cruet_CResponse *self, void *closure)
{
    return PyObject_CallMethod(self->headers, "get", "sO", "Location", Py_None);
}

static int
CResponse_set_location(Cruet_CResponse *self, PyObject *value, void *closure)
{
    if (value == NULL || value == Py_None) {
        /* Delete Location header */
        PyObject *result = PyObject_CallMethod(self->headers, "__delitem__", "s", "Location");
        if (!result) { PyErr_Clear(); }
        else { Py_DECREF(result); }
        return 0;
    }
    if (!PyUnicode_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "location must be a string");
        return -1;
    }
    PyObject *result = PyObject_CallMethod(self->headers, "set", "sO", "Location", value);
    Py_XDECREF(result);
    return result ? 0 : -1;
}

static PyObject *
CResponse_set_cookie(Cruet_CResponse *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"key", "value", "max_age", "path", "domain",
                             "secure", "httponly", "samesite", NULL};
    const char *key, *value = "";
    PyObject *max_age_obj = Py_None;
    const char *path = "/";
    const char *domain = NULL;
    int secure = 0;
    int httponly = 0;
    const char *samesite = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|sOzzppz", kwlist,
                                      &key, &value, &max_age_obj, &path,
                                      &domain, &secure, &httponly, &samesite))
        return NULL;

    /* Build Set-Cookie header value */
    char buf[1024];
    int written = snprintf(buf, sizeof(buf), "%s=%s", key, value);

    if (path)
        written += snprintf(buf + written, sizeof(buf) - written, "; Path=%s", path);
    if (domain)
        written += snprintf(buf + written, sizeof(buf) - written, "; Domain=%s", domain);
    if (max_age_obj != Py_None) {
        long max_age = PyLong_AsLong(max_age_obj);
        if (max_age == -1 && PyErr_Occurred()) return NULL;
        written += snprintf(buf + written, sizeof(buf) - written, "; Max-Age=%ld", max_age);
    }
    if (secure)
        written += snprintf(buf + written, sizeof(buf) - written, "; Secure");
    if (httponly)
        written += snprintf(buf + written, sizeof(buf) - written, "; HttpOnly");
    if (samesite)
        written += snprintf(buf + written, sizeof(buf) - written, "; SameSite=%s", samesite);

    PyObject *cookie_str = PyUnicode_FromString(buf);
    if (!cookie_str) return NULL;
    PyList_Append(self->set_cookies, cookie_str);
    /* Also add to headers so getlist("Set-Cookie") works */
    PyObject_CallMethod(self->headers, "add", "sO", "Set-Cookie", cookie_str);
    Py_DECREF(cookie_str);

    Py_RETURN_NONE;
}

static PyObject *
CResponse_delete_cookie(Cruet_CResponse *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"key", "path", "domain", NULL};
    const char *key;
    const char *path = "/";
    const char *domain = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|zz", kwlist,
                                      &key, &path, &domain))
        return NULL;

    char buf[512];
    int written = snprintf(buf, sizeof(buf),
        "%s=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0", key);
    if (path)
        written += snprintf(buf + written, sizeof(buf) - written, "; Path=%s", path);
    if (domain)
        written += snprintf(buf + written, sizeof(buf) - written, "; Domain=%s", domain);

    PyObject *cookie_str = PyUnicode_FromString(buf);
    if (!cookie_str) return NULL;
    PyList_Append(self->set_cookies, cookie_str);
    PyObject_CallMethod(self->headers, "add", "sO", "Set-Cookie", cookie_str);
    Py_DECREF(cookie_str);

    Py_RETURN_NONE;
}

/* ---- ResponseIter: WSGI-compliant iterable with close() ---- */

typedef struct {
    PyObject_HEAD
    PyObject *body;     /* bytes object */
    int exhausted;      /* 1 after body has been yielded */
    int closed;
} ResponseIter;

static void
ResponseIter_dealloc(ResponseIter *self)
{
    Py_XDECREF(self->body);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
ResponseIter_iter(ResponseIter *self)
{
    Py_INCREF(self);
    return (PyObject *)self;
}

static PyObject *
ResponseIter_next(ResponseIter *self)
{
    if (self->closed || self->exhausted)
        return NULL;  /* StopIteration */
    self->exhausted = 1;
    Py_INCREF(self->body);
    return self->body;
}

static PyObject *
ResponseIter_close(ResponseIter *self, PyObject *Py_UNUSED(ignored))
{
    self->closed = 1;
    Py_RETURN_NONE;
}

static PyMethodDef ResponseIter_methods[] = {
    {"close", (PyCFunction)ResponseIter_close, METH_NOARGS, "Close the iterator."},
    {NULL}
};

PyTypeObject Cruet_ResponseIterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet._ResponseIter",
    .tp_basicsize = sizeof(ResponseIter),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_dealloc = (destructor)ResponseIter_dealloc,
    .tp_iter = (getiterfunc)ResponseIter_iter,
    .tp_iternext = (iternextfunc)ResponseIter_next,
    .tp_methods = ResponseIter_methods,
};

/*
 * WSGI callable: response(environ, start_response)
 * Returns an iterable of bytes with a close() method.
 */
static PyObject *
CResponse_call(Cruet_CResponse *self, PyObject *args, PyObject *kwargs)
{
    PyObject *environ, *start_response;
    if (!PyArg_ParseTuple(args, "OO", &environ, &start_response))
        return NULL;

    /* Build status string */
    PyObject *status_str = PyUnicode_FromString(self->status_text);
    if (!status_str) return NULL;

    /* Build headers list: list of (name, value) tuples */
    PyObject *header_list = PyList_New(0);
    if (!header_list) { Py_DECREF(status_str); return NULL; }

    /* Add headers from CHeaders */
    Cruet_CHeaders *hdrs = (Cruet_CHeaders *)self->headers;
    Py_ssize_t n = PyList_GET_SIZE(hdrs->items);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *tuple = PyList_GET_ITEM(hdrs->items, i);
        PyList_Append(header_list, tuple);
    }

    /* Add Set-Cookie headers */
    Py_ssize_t n_cookies = PyList_GET_SIZE(self->set_cookies);
    for (Py_ssize_t i = 0; i < n_cookies; i++) {
        PyObject *cookie_val = PyList_GET_ITEM(self->set_cookies, i);
        PyObject *tuple = PyTuple_Pack(2,
            PyUnicode_FromString("Set-Cookie"), cookie_val);
        PyList_Append(header_list, tuple);
        Py_DECREF(tuple);
    }

    /* Call start_response(status, headers) */
    PyObject *sr_result = PyObject_CallFunction(start_response, "OO",
                                                 status_str, header_list);
    Py_DECREF(status_str);
    Py_DECREF(header_list);
    if (!sr_result) return NULL;
    Py_DECREF(sr_result);

    /* Return a ResponseIter with close() for WSGI compliance */
    ResponseIter *it = PyObject_New(ResponseIter, &Cruet_ResponseIterType);
    if (!it) return NULL;
    Py_INCREF(self->body);
    it->body = self->body;
    it->exhausted = 0;
    it->closed = 0;
    return (PyObject *)it;
}

static PyGetSetDef CResponse_getset[] = {
    {"status_code", (getter)CResponse_get_status_code,
     (setter)CResponse_set_status_code, "HTTP status code", NULL},
    {"status", (getter)CResponse_get_status,
     (setter)CResponse_set_status, "HTTP status string", NULL},
    {"headers", (getter)CResponse_get_headers, NULL, "Response headers", NULL},
    {"content_type", (getter)CResponse_get_content_type,
     (setter)CResponse_set_content_type, "Content-Type", NULL},
    {"data", (getter)CResponse_get_data,
     (setter)CResponse_set_data, "Response body bytes", NULL},
    {"json", (getter)CResponse_get_json, NULL, "Parse body as JSON", NULL},
    {"is_json", (getter)CResponse_get_is_json, NULL, "Whether content is JSON", NULL},
    {"mimetype", (getter)CResponse_get_mimetype, NULL, "Content-Type without params", NULL},
    {"content_length", (getter)CResponse_get_content_length, NULL, "Body length", NULL},
    {"location", (getter)CResponse_get_location,
     (setter)CResponse_set_location, "Location header", NULL},
    {NULL}
};

static PyMethodDef CResponse_methods[] = {
    {"set_cookie", (PyCFunction)CResponse_set_cookie, METH_VARARGS | METH_KEYWORDS,
     "Set a cookie."},
    {"delete_cookie", (PyCFunction)CResponse_delete_cookie, METH_VARARGS | METH_KEYWORDS,
     "Delete a cookie."},
    {"get_data", (PyCFunction)CResponse_method_get_data, METH_VARARGS | METH_KEYWORDS,
     "Get response body. Args: as_text=False"},
    {"get_json", (PyCFunction)CResponse_method_get_json, METH_NOARGS,
     "Parse response body as JSON."},
    {NULL}
};

PyTypeObject Cruet_CResponseType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.CResponse",
    .tp_basicsize = sizeof(Cruet_CResponse),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)CResponse_init,
    .tp_dealloc = (destructor)CResponse_dealloc,
    .tp_getset = CResponse_getset,
    .tp_methods = CResponse_methods,
    .tp_call = (ternaryfunc)CResponse_call,
};
