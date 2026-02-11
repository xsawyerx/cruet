#include "http.h"

#define REGISTER_TYPE(type) do { \
    if (PyType_Ready(&(type)) < 0) return -1; \
    Py_INCREF(&(type)); \
    if (PyModule_AddObject(module, (type).tp_name + sizeof("cruet._cruet.") - 1, \
                           (PyObject *)&(type)) < 0) { \
        Py_DECREF(&(type)); \
        return -1; \
    } \
} while (0)

static PyMethodDef http_functions[] = {
    {"parse_qs", cruet_parse_qs, METH_VARARGS, "Parse a query string into a dict."},
    {"parse_cookies", cruet_parse_cookies, METH_VARARGS, "Parse a Cookie header into a dict."},
    {"parse_multipart", cruet_parse_multipart, METH_VARARGS, "Parse multipart/form-data body."},
    {NULL}
};

int
Cruet_InitHTTP(PyObject *module)
{
    REGISTER_TYPE(Cruet_CHeadersType);
    REGISTER_TYPE(Cruet_CRequestType);
    REGISTER_TYPE(Cruet_CResponseType);
    REGISTER_TYPE(Cruet_ResponseIterType);

    /* Add module-level functions */
    for (PyMethodDef *m = http_functions; m->ml_name != NULL; m++) {
        PyObject *func = PyCFunction_New(m, module);
        if (!func) return -1;
        if (PyModule_AddObject(module, m->ml_name, func) < 0) {
            Py_DECREF(func);
            return -1;
        }
    }

    return 0;
}
