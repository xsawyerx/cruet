#include "http.h"
#include <structmember.h>
#include <string.h>
#include <ctype.h>

/* Helper: case-insensitive string compare for header names */
static int
header_name_eq(PyObject *a, PyObject *b)
{
    Py_ssize_t la, lb;
    const char *sa = PyUnicode_AsUTF8AndSize(a, &la);
    const char *sb = PyUnicode_AsUTF8AndSize(b, &lb);
    if (la != lb) return 0;
    for (Py_ssize_t i = 0; i < la; i++) {
        if (tolower((unsigned char)sa[i]) != tolower((unsigned char)sb[i]))
            return 0;
    }
    return 1;
}

static int
CHeaders_init(Cruet_CHeaders *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"items", NULL};
    PyObject *items = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O", kwlist, &items))
        return -1;

    self->items = PyList_New(0);
    if (!self->items) return -1;

    if (items == NULL || items == Py_None)
        return 0;

    if (PyDict_Check(items)) {
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(items, &pos, &key, &value)) {
            PyObject *tuple = PyTuple_Pack(2, key, value);
            if (!tuple) return -1;
            PyList_Append(self->items, tuple);
            Py_DECREF(tuple);
        }
    } else if (PyList_Check(items) || PyTuple_Check(items)) {
        PyObject *iter = PyObject_GetIter(items);
        if (!iter) return -1;
        PyObject *item;
        while ((item = PyIter_Next(iter)) != NULL) {
            if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 2) {
                Py_DECREF(item);
                Py_DECREF(iter);
                PyErr_SetString(PyExc_TypeError, "Items must be 2-tuples");
                return -1;
            }
            PyList_Append(self->items, item);
            Py_DECREF(item);
        }
        Py_DECREF(iter);
        if (PyErr_Occurred()) return -1;
    }

    return 0;
}

static void
CHeaders_dealloc(Cruet_CHeaders *self)
{
    Py_XDECREF(self->items);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
CHeaders_get(Cruet_CHeaders *self, PyObject *args)
{
    PyObject *name;
    PyObject *default_val = Py_None;
    if (!PyArg_ParseTuple(args, "O|O", &name, &default_val))
        return NULL;

    Py_ssize_t n = PyList_GET_SIZE(self->items);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *tuple = PyList_GET_ITEM(self->items, i);
        PyObject *key = PyTuple_GET_ITEM(tuple, 0);
        if (header_name_eq(key, name)) {
            PyObject *val = PyTuple_GET_ITEM(tuple, 1);
            Py_INCREF(val);
            return val;
        }
    }

    Py_INCREF(default_val);
    return default_val;
}

static PyObject *
CHeaders_getlist(Cruet_CHeaders *self, PyObject *args)
{
    PyObject *name;
    if (!PyArg_ParseTuple(args, "O", &name))
        return NULL;

    PyObject *result = PyList_New(0);
    if (!result) return NULL;

    Py_ssize_t n = PyList_GET_SIZE(self->items);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *tuple = PyList_GET_ITEM(self->items, i);
        PyObject *key = PyTuple_GET_ITEM(tuple, 0);
        if (header_name_eq(key, name)) {
            PyObject *val = PyTuple_GET_ITEM(tuple, 1);
            PyList_Append(result, val);
        }
    }

    return result;
}

static PyObject *
CHeaders_set(Cruet_CHeaders *self, PyObject *args)
{
    PyObject *name, *value;
    if (!PyArg_ParseTuple(args, "OO", &name, &value))
        return NULL;

    /* Remove all existing entries with this name */
    Py_ssize_t n = PyList_GET_SIZE(self->items);
    for (Py_ssize_t i = n - 1; i >= 0; i--) {
        PyObject *tuple = PyList_GET_ITEM(self->items, i);
        PyObject *key = PyTuple_GET_ITEM(tuple, 0);
        if (header_name_eq(key, name)) {
            PyList_SetSlice(self->items, i, i + 1, NULL);
        }
    }

    /* Add the new entry */
    PyObject *tuple = PyTuple_Pack(2, name, value);
    if (!tuple) return NULL;
    PyList_Append(self->items, tuple);
    Py_DECREF(tuple);

    Py_RETURN_NONE;
}

static PyObject *
CHeaders_add(Cruet_CHeaders *self, PyObject *args)
{
    PyObject *name, *value;
    if (!PyArg_ParseTuple(args, "OO", &name, &value))
        return NULL;

    PyObject *tuple = PyTuple_Pack(2, name, value);
    if (!tuple) return NULL;
    PyList_Append(self->items, tuple);
    Py_DECREF(tuple);

    Py_RETURN_NONE;
}

static Py_ssize_t
CHeaders_length(Cruet_CHeaders *self)
{
    return PyList_GET_SIZE(self->items);
}

static int
CHeaders_contains(Cruet_CHeaders *self, PyObject *name)
{
    Py_ssize_t n = PyList_GET_SIZE(self->items);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *tuple = PyList_GET_ITEM(self->items, i);
        PyObject *key = PyTuple_GET_ITEM(tuple, 0);
        if (header_name_eq(key, name))
            return 1;
    }
    return 0;
}

static PyObject *
CHeaders_iter(Cruet_CHeaders *self)
{
    return PyObject_GetIter(self->items);
}

static PySequenceMethods CHeaders_as_sequence = {
    .sq_length = (lenfunc)CHeaders_length,
    .sq_contains = (objobjproc)CHeaders_contains,
};

/* __getitem__: headers["Name"] -> first value or KeyError */
static PyObject *
CHeaders_subscript(Cruet_CHeaders *self, PyObject *name)
{
    Py_ssize_t n = PyList_GET_SIZE(self->items);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *tuple = PyList_GET_ITEM(self->items, i);
        PyObject *key = PyTuple_GET_ITEM(tuple, 0);
        if (header_name_eq(key, name)) {
            PyObject *val = PyTuple_GET_ITEM(tuple, 1);
            Py_INCREF(val);
            return val;
        }
    }
    PyErr_SetObject(PyExc_KeyError, name);
    return NULL;
}

/* __setitem__: headers["Name"] = "val" -> set (replace all) */
static int
CHeaders_ass_subscript(Cruet_CHeaders *self, PyObject *name, PyObject *value)
{
    if (value == NULL) {
        /* __delitem__: remove all entries with this name */
        Py_ssize_t n = PyList_GET_SIZE(self->items);
        for (Py_ssize_t i = n - 1; i >= 0; i--) {
            PyObject *tuple = PyList_GET_ITEM(self->items, i);
            PyObject *key = PyTuple_GET_ITEM(tuple, 0);
            if (header_name_eq(key, name)) {
                PyList_SetSlice(self->items, i, i + 1, NULL);
            }
        }
        return 0;
    }

    /* Remove all existing entries then add */
    Py_ssize_t n = PyList_GET_SIZE(self->items);
    for (Py_ssize_t i = n - 1; i >= 0; i--) {
        PyObject *tuple = PyList_GET_ITEM(self->items, i);
        PyObject *key = PyTuple_GET_ITEM(tuple, 0);
        if (header_name_eq(key, name)) {
            PyList_SetSlice(self->items, i, i + 1, NULL);
        }
    }

    PyObject *tuple = PyTuple_Pack(2, name, value);
    if (!tuple) return -1;
    PyList_Append(self->items, tuple);
    Py_DECREF(tuple);
    return 0;
}

static PyMappingMethods CHeaders_as_mapping = {
    .mp_length = (lenfunc)CHeaders_length,
    .mp_subscript = (binaryfunc)CHeaders_subscript,
    .mp_ass_subscript = (objobjargproc)CHeaders_ass_subscript,
};

static PyMethodDef CHeaders_methods[] = {
    {"get", (PyCFunction)CHeaders_get, METH_VARARGS, "Get first value for a header name."},
    {"getlist", (PyCFunction)CHeaders_getlist, METH_VARARGS, "Get all values for a header name."},
    {"set", (PyCFunction)CHeaders_set, METH_VARARGS, "Set header, replacing all existing values."},
    {"add", (PyCFunction)CHeaders_add, METH_VARARGS, "Add a header value (allows multi-value)."},
    {NULL}
};

PyTypeObject Cruet_CHeadersType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.CHeaders",
    .tp_basicsize = sizeof(Cruet_CHeaders),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)CHeaders_init,
    .tp_dealloc = (destructor)CHeaders_dealloc,
    .tp_methods = CHeaders_methods,
    .tp_as_sequence = &CHeaders_as_sequence,
    .tp_as_mapping = &CHeaders_as_mapping,
    .tp_iter = (getiterfunc)CHeaders_iter,
};
