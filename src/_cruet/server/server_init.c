#include "server.h"

static PyMethodDef server_functions[] = {
    {"parse_http_request", cruet_parse_http_request, METH_VARARGS,
     "Parse a raw HTTP/1.1 request into a dict."},
#ifdef CRUET_HAS_LIBEVENT
    {"run_event_loop", (PyCFunction)cruet_run_event_loop,
     METH_VARARGS | METH_KEYWORDS,
     "Run a libevent2-based async WSGI server event loop."},
#endif
    {NULL}
};

static int
register_methods(PyObject *module, PyMethodDef *methods)
{
    for (PyMethodDef *m = methods; m->ml_name != NULL; m++) {
        PyObject *func = PyCFunction_New(m, module);
        if (!func) return -1;
        if (PyModule_AddObject(module, m->ml_name, func) < 0) {
            Py_DECREF(func);
            return -1;
        }
    }
    return 0;
}

int
Cruet_InitServer(PyObject *module)
{
    if (register_methods(module, server_functions) < 0)
        return -1;
    if (register_methods(module, cruet_wsgi_methods) < 0)
        return -1;
    return 0;
}
