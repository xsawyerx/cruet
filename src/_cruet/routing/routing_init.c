#include "routing.h"

#define REGISTER_TYPE(type) do { \
    if (PyType_Ready(&(type)) < 0) return -1; \
    Py_INCREF(&(type)); \
    if (PyModule_AddObject(module, (type).tp_name + sizeof("cruet._cruet.") - 1, \
                           (PyObject *)&(type)) < 0) { \
        Py_DECREF(&(type)); \
        return -1; \
    } \
} while (0)

int
Cruet_InitRouting(PyObject *module)
{
    /* Converters */
    REGISTER_TYPE(Cruet_StringConverterType);
    REGISTER_TYPE(Cruet_IntConverterType);
    REGISTER_TYPE(Cruet_FloatConverterType);
    REGISTER_TYPE(Cruet_UUIDConverterType);
    REGISTER_TYPE(Cruet_PathConverterType);
    REGISTER_TYPE(Cruet_AnyConverterType);

    /* Routing types */
    REGISTER_TYPE(Cruet_RuleType);
    REGISTER_TYPE(Cruet_MapType);
    REGISTER_TYPE(Cruet_MapAdapterType);

    return 0;
}
