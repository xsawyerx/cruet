#include "module.h"

/* Forward declarations for sub-module init functions */
int Cruet_InitRouting(PyObject *module);
int Cruet_InitHTTP(PyObject *module);
int Cruet_InitServer(PyObject *module);

static PyObject *
cruet_version(PyObject *self, PyObject *args)
{
    return PyUnicode_FromString(CRUET_VERSION);
}

static PyMethodDef cruet_methods[] = {
    {"version", cruet_version, METH_NOARGS, "Return the cruet version string."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cruet_module = {
    PyModuleDef_HEAD_INIT,
    "cruet._cruet",
    "cruet C extension module — high-performance routing, HTTP, and server.",
    -1,
    cruet_methods
};

PyMODINIT_FUNC
PyInit__cruet(void)
{
    PyObject *m = PyModule_Create(&cruet_module);
    if (m == NULL)
        return NULL;

    if (PyModule_AddStringConstant(m, "__version__", CRUET_VERSION) < 0)
        goto error;

    /* Initialize routing sub-components */
    if (Cruet_InitRouting(m) < 0)
        goto error;

    /* Initialize HTTP sub-components */
    if (Cruet_InitHTTP(m) < 0)
        goto error;

    /* Initialize server sub-components */
    if (Cruet_InitServer(m) < 0)
        goto error;

    return m;

error:
    Py_DECREF(m);
    return NULL;
}
