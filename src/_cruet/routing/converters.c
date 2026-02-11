#include "routing.h"
#include <structmember.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

/* ========== StringConverter ========== */

typedef struct {
    PyObject_HEAD
    int minlength;
    int maxlength;
    int length; /* 0 = not set */
} StringConverterObj;

static int
StringConverter_init(StringConverterObj *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"minlength", "maxlength", "length", NULL};
    self->minlength = 1;
    self->maxlength = 0; /* 0 = unlimited */
    self->length = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|iii", kwlist,
                                      &self->minlength, &self->maxlength,
                                      &self->length))
        return -1;
    return 0;
}

static PyObject *
StringConverter_convert(StringConverterObj *self, PyObject *args)
{
    const char *value;
    Py_ssize_t len;
    if (!PyArg_ParseTuple(args, "s#", &value, &len))
        return NULL;

    if (self->length > 0) {
        if (len != self->length) {
            PyErr_Format(PyExc_ValueError,
                         "String length %zd does not match required %d",
                         len, self->length);
            return NULL;
        }
    } else {
        if (len < self->minlength) {
            PyErr_Format(PyExc_ValueError,
                         "String too short: %zd < %d", len, self->minlength);
            return NULL;
        }
        if (self->maxlength > 0 && len > self->maxlength) {
            PyErr_Format(PyExc_ValueError,
                         "String too long: %zd > %d", len, self->maxlength);
            return NULL;
        }
    }
    return PyUnicode_FromStringAndSize(value, len);
}

static PyObject *
StringConverter_to_url(StringConverterObj *self, PyObject *args)
{
    PyObject *value;
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;
    return PyObject_Str(value);
}

static PyObject *
StringConverter_get_regex(StringConverterObj *self, void *closure)
{
    char buf[64];
    if (self->length > 0)
        snprintf(buf, sizeof(buf), "[^/]{%d}", self->length);
    else if (self->maxlength > 0)
        snprintf(buf, sizeof(buf), "[^/]{%d,%d}", self->minlength, self->maxlength);
    else
        snprintf(buf, sizeof(buf), "[^/]+");
    return PyUnicode_FromString(buf);
}

static PyMethodDef StringConverter_methods[] = {
    {"convert", (PyCFunction)StringConverter_convert, METH_VARARGS, NULL},
    {"to_url", (PyCFunction)StringConverter_to_url, METH_VARARGS, NULL},
    {NULL}
};

static PyGetSetDef StringConverter_getset[] = {
    {"regex", (getter)StringConverter_get_regex, NULL, "regex pattern", NULL},
    {NULL}
};

PyTypeObject Cruet_StringConverterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.StringConverter",
    .tp_basicsize = sizeof(StringConverterObj),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)StringConverter_init,
    .tp_methods = StringConverter_methods,
    .tp_getset = StringConverter_getset,
};

/* ========== IntConverter ========== */

typedef struct {
    PyObject_HEAD
    int fixed_digits;
    int min_val;
    int max_val;
    int has_min;
    int has_max;
} IntConverterObj;

static int
IntConverter_init(IntConverterObj *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"fixed_digits", "min", "max", NULL};
    self->fixed_digits = 0;
    self->has_min = 0;
    self->has_max = 0;
    self->min_val = 0;
    self->max_val = 0;
    PyObject *min_obj = Py_None, *max_obj = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|iOO", kwlist,
                                      &self->fixed_digits, &min_obj, &max_obj))
        return -1;

    if (min_obj != Py_None) {
        self->min_val = (int)PyLong_AsLong(min_obj);
        if (PyErr_Occurred()) return -1;
        self->has_min = 1;
    }
    if (max_obj != Py_None) {
        self->max_val = (int)PyLong_AsLong(max_obj);
        if (PyErr_Occurred()) return -1;
        self->has_max = 1;
    }
    return 0;
}

static PyObject *
IntConverter_convert(IntConverterObj *self, PyObject *args)
{
    const char *value;
    Py_ssize_t len;
    if (!PyArg_ParseTuple(args, "s#", &value, &len))
        return NULL;

    /* Check for non-numeric or negative */
    for (Py_ssize_t i = 0; i < len; i++) {
        if (value[i] < '0' || value[i] > '9') {
            PyErr_SetString(PyExc_ValueError, "Not a valid integer");
            return NULL;
        }
    }

    if (self->fixed_digits > 0 && len != self->fixed_digits) {
        PyErr_Format(PyExc_ValueError,
                     "Expected %d digits, got %zd", self->fixed_digits, len);
        return NULL;
    }

    long result = strtol(value, NULL, 10);

    if (self->has_min && result < self->min_val) {
        PyErr_Format(PyExc_ValueError,
                     "%ld is less than minimum %d", result, self->min_val);
        return NULL;
    }
    if (self->has_max && result > self->max_val) {
        PyErr_Format(PyExc_ValueError,
                     "%ld is greater than maximum %d", result, self->max_val);
        return NULL;
    }

    return PyLong_FromLong(result);
}

static PyObject *
IntConverter_to_url(IntConverterObj *self, PyObject *args)
{
    PyObject *value;
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;
    return PyObject_Str(value);
}

static PyObject *
IntConverter_get_regex(IntConverterObj *self, void *closure)
{
    if (self->fixed_digits > 0) {
        char buf[32];
        snprintf(buf, sizeof(buf), "\\d{%d}", self->fixed_digits);
        return PyUnicode_FromString(buf);
    }
    return PyUnicode_FromString("\\d+");
}

static PyMethodDef IntConverter_methods[] = {
    {"convert", (PyCFunction)IntConverter_convert, METH_VARARGS, NULL},
    {"to_url", (PyCFunction)IntConverter_to_url, METH_VARARGS, NULL},
    {NULL}
};

static PyGetSetDef IntConverter_getset[] = {
    {"regex", (getter)IntConverter_get_regex, NULL, "regex pattern", NULL},
    {NULL}
};

PyTypeObject Cruet_IntConverterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.IntConverter",
    .tp_basicsize = sizeof(IntConverterObj),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)IntConverter_init,
    .tp_methods = IntConverter_methods,
    .tp_getset = IntConverter_getset,
};

/* ========== FloatConverter ========== */

typedef struct {
    PyObject_HEAD
    double min_val;
    double max_val;
    int has_min;
    int has_max;
} FloatConverterObj;

static int
FloatConverter_init(FloatConverterObj *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"min", "max", NULL};
    self->has_min = 0;
    self->has_max = 0;
    PyObject *min_obj = Py_None, *max_obj = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|OO", kwlist,
                                      &min_obj, &max_obj))
        return -1;

    if (min_obj != Py_None) {
        self->min_val = PyFloat_AsDouble(min_obj);
        if (PyErr_Occurred()) return -1;
        self->has_min = 1;
    }
    if (max_obj != Py_None) {
        self->max_val = PyFloat_AsDouble(max_obj);
        if (PyErr_Occurred()) return -1;
        self->has_max = 1;
    }
    return 0;
}

static PyObject *
FloatConverter_convert(FloatConverterObj *self, PyObject *args)
{
    const char *value;
    Py_ssize_t len;
    if (!PyArg_ParseTuple(args, "s#", &value, &len))
        return NULL;

    char *endptr;
    double result = strtod(value, &endptr);
    if (endptr == value || endptr != value + len) {
        PyErr_SetString(PyExc_ValueError, "Not a valid float");
        return NULL;
    }

    if (self->has_min && result < self->min_val) {
        PyErr_Format(PyExc_ValueError,
                     "%f is less than minimum %f", result, self->min_val);
        return NULL;
    }
    if (self->has_max && result > self->max_val) {
        PyErr_Format(PyExc_ValueError,
                     "%f is greater than maximum %f", result, self->max_val);
        return NULL;
    }

    return PyFloat_FromDouble(result);
}

static PyObject *
FloatConverter_to_url(FloatConverterObj *self, PyObject *args)
{
    PyObject *value;
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;
    double d = PyFloat_AsDouble(value);
    if (PyErr_Occurred()) return NULL;
    char buf[64];
    snprintf(buf, sizeof(buf), "%g", d);
    /* Ensure there's a decimal point */
    if (!strchr(buf, '.') && !strchr(buf, 'e')) {
        size_t l = strlen(buf);
        buf[l] = '.';
        buf[l+1] = '0';
        buf[l+2] = '\0';
    }
    return PyUnicode_FromString(buf);
}

static PyObject *
FloatConverter_get_regex(FloatConverterObj *self, void *closure)
{
    return PyUnicode_FromString("\\d+\\.\\d+");
}

static PyMethodDef FloatConverter_methods[] = {
    {"convert", (PyCFunction)FloatConverter_convert, METH_VARARGS, NULL},
    {"to_url", (PyCFunction)FloatConverter_to_url, METH_VARARGS, NULL},
    {NULL}
};

static PyGetSetDef FloatConverter_getset[] = {
    {"regex", (getter)FloatConverter_get_regex, NULL, "regex pattern", NULL},
    {NULL}
};

PyTypeObject Cruet_FloatConverterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.FloatConverter",
    .tp_basicsize = sizeof(FloatConverterObj),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)FloatConverter_init,
    .tp_methods = FloatConverter_methods,
    .tp_getset = FloatConverter_getset,
};

/* ========== UUIDConverter ========== */

typedef struct {
    PyObject_HEAD
} UUIDConverterObj;

static PyObject *
UUIDConverter_convert(UUIDConverterObj *self, PyObject *args)
{
    const char *value;
    if (!PyArg_ParseTuple(args, "s", &value))
        return NULL;

    PyObject *uuid_mod = PyImport_ImportModule("uuid");
    if (!uuid_mod) return NULL;
    PyObject *uuid_cls = PyObject_GetAttrString(uuid_mod, "UUID");
    Py_DECREF(uuid_mod);
    if (!uuid_cls) return NULL;

    PyObject *str_arg = PyUnicode_FromString(value);
    if (!str_arg) { Py_DECREF(uuid_cls); return NULL; }

    PyObject *result = PyObject_CallOneArg(uuid_cls, str_arg);
    Py_DECREF(uuid_cls);
    Py_DECREF(str_arg);
    if (!result) {
        PyErr_SetString(PyExc_ValueError, "Not a valid UUID");
        return NULL;
    }
    return result;
}

static PyObject *
UUIDConverter_to_url(UUIDConverterObj *self, PyObject *args)
{
    PyObject *value;
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;
    return PyObject_Str(value);
}

static PyObject *
UUIDConverter_get_regex(UUIDConverterObj *self, void *closure)
{
    return PyUnicode_FromString("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
}

static PyMethodDef UUIDConverter_methods[] = {
    {"convert", (PyCFunction)UUIDConverter_convert, METH_VARARGS, NULL},
    {"to_url", (PyCFunction)UUIDConverter_to_url, METH_VARARGS, NULL},
    {NULL}
};

static PyGetSetDef UUIDConverter_getset[] = {
    {"regex", (getter)UUIDConverter_get_regex, NULL, "regex pattern", NULL},
    {NULL}
};

PyTypeObject Cruet_UUIDConverterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.UUIDConverter",
    .tp_basicsize = sizeof(UUIDConverterObj),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_methods = UUIDConverter_methods,
    .tp_getset = UUIDConverter_getset,
};

/* ========== PathConverter ========== */

typedef struct {
    PyObject_HEAD
} PathConverterObj;

static PyObject *
PathConverter_convert(PathConverterObj *self, PyObject *args)
{
    const char *value;
    Py_ssize_t len;
    if (!PyArg_ParseTuple(args, "s#", &value, &len))
        return NULL;
    return PyUnicode_FromStringAndSize(value, len);
}

static PyObject *
PathConverter_to_url(PathConverterObj *self, PyObject *args)
{
    PyObject *value;
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;
    return PyObject_Str(value);
}

static PyObject *
PathConverter_get_regex(PathConverterObj *self, void *closure)
{
    return PyUnicode_FromString("[^/].*?");
}

static PyMethodDef PathConverter_methods[] = {
    {"convert", (PyCFunction)PathConverter_convert, METH_VARARGS, NULL},
    {"to_url", (PyCFunction)PathConverter_to_url, METH_VARARGS, NULL},
    {NULL}
};

static PyGetSetDef PathConverter_getset[] = {
    {"regex", (getter)PathConverter_get_regex, NULL, "regex pattern", NULL},
    {NULL}
};

PyTypeObject Cruet_PathConverterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.PathConverter",
    .tp_basicsize = sizeof(PathConverterObj),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_methods = PathConverter_methods,
    .tp_getset = PathConverter_getset,
};

/* ========== AnyConverter ========== */

typedef struct {
    PyObject_HEAD
    PyObject *items;  /* tuple of allowed string values */
} AnyConverterObj;

static int
AnyConverter_init(AnyConverterObj *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"items", NULL};
    PyObject *items = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O", kwlist, &items))
        return -1;

    if (items) {
        self->items = PySequence_Tuple(items);
        if (!self->items) return -1;
    } else {
        self->items = PyTuple_New(0);
    }
    return 0;
}

static void
AnyConverter_dealloc(AnyConverterObj *self)
{
    Py_XDECREF(self->items);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
AnyConverter_convert(AnyConverterObj *self, PyObject *args)
{
    const char *value;
    if (!PyArg_ParseTuple(args, "s", &value))
        return NULL;

    PyObject *val_str = PyUnicode_FromString(value);
    if (!val_str) return NULL;

    int found = PySequence_Contains(self->items, val_str);
    if (found < 0) { Py_DECREF(val_str); return NULL; }
    if (!found) {
        Py_DECREF(val_str);
        PyErr_Format(PyExc_ValueError, "'%s' is not one of the allowed values", value);
        return NULL;
    }
    return val_str;
}

static PyObject *
AnyConverter_to_url(AnyConverterObj *self, PyObject *args)
{
    PyObject *value;
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;
    return PyObject_Str(value);
}

static PyObject *
AnyConverter_get_regex(AnyConverterObj *self, void *closure)
{
    Py_ssize_t n = PyTuple_GET_SIZE(self->items);
    if (n == 0)
        return PyUnicode_FromString("");

    /* Build "item1|item2|item3" */
    PyObject *sep = PyUnicode_FromString("|");
    if (!sep) return NULL;
    PyObject *result = PyUnicode_Join(sep, self->items);
    Py_DECREF(sep);
    return result;
}

static PyMethodDef AnyConverter_methods[] = {
    {"convert", (PyCFunction)AnyConverter_convert, METH_VARARGS, NULL},
    {"to_url", (PyCFunction)AnyConverter_to_url, METH_VARARGS, NULL},
    {NULL}
};

static PyGetSetDef AnyConverter_getset[] = {
    {"regex", (getter)AnyConverter_get_regex, NULL, "regex pattern", NULL},
    {NULL}
};

PyTypeObject Cruet_AnyConverterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.AnyConverter",
    .tp_basicsize = sizeof(AnyConverterObj),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)AnyConverter_init,
    .tp_dealloc = (destructor)AnyConverter_dealloc,
    .tp_methods = AnyConverter_methods,
    .tp_getset = AnyConverter_getset,
};
