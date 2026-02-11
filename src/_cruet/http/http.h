#ifndef CRUET_HTTP_H
#define CRUET_HTTP_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* CHeaders - case-insensitive header container */
typedef struct {
    PyObject_HEAD
    PyObject *items;    /* list of (name, value) tuples - preserves order and multi-values */
} Cruet_CHeaders;

extern PyTypeObject Cruet_CHeadersType;

/* CRequest - wraps WSGI environ */
typedef struct {
    PyObject_HEAD
    PyObject *environ;
    /* Lazy cached properties */
    PyObject *cached_args;
    PyObject *cached_headers;
    PyObject *cached_data;
    PyObject *cached_json;
    PyObject *cached_form;
    PyObject *cached_cookies;
    PyObject *cached_files;
    int json_loaded;
    /* Set during dispatch */
    PyObject *endpoint;     /* str or None */
    PyObject *view_args;    /* dict or None */
    PyObject *blueprint;    /* str or None */
} Cruet_CRequest;

extern PyTypeObject Cruet_CRequestType;

/* CResponse - WSGI response object */
typedef struct {
    PyObject_HEAD
    PyObject *body;          /* bytes */
    int status_code;
    char *status_text;       /* e.g. "200 OK" */
    PyObject *headers;       /* CHeaders */
    PyObject *set_cookies;   /* list of Set-Cookie header strings */
} Cruet_CResponse;

extern PyTypeObject Cruet_CResponseType;

/* ResponseIter - WSGI response iterator with close() */
extern PyTypeObject Cruet_ResponseIterType;

/* Utility functions exposed to Python */
PyObject *cruet_parse_qs(PyObject *self, PyObject *args);
PyObject *cruet_parse_cookies(PyObject *self, PyObject *args);
PyObject *cruet_parse_multipart(PyObject *self, PyObject *args);

#endif
