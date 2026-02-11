#include "routing.h"
#include <structmember.h>
#include <string.h>
#include <stdlib.h>

/* ========== C hash table for static index ========== */

#define STATIC_INDEX_INITIAL_CAP 16
#define STATIC_INDEX_LOAD_FACTOR 70 /* percent */

static uint64_t
fnv1a_hash(const char *data, size_t len)
{
    uint64_t h = 14695981039346656037ULL;
    for (size_t i = 0; i < len; i++) {
        h ^= (uint8_t)data[i];
        h *= 1099511628211ULL;
    }
    return h;
}

static int
static_index_init(Cruet_StaticIndex *idx)
{
    idx->capacity = STATIC_INDEX_INITIAL_CAP;
    idx->count = 0;
    idx->entries = calloc(idx->capacity, sizeof(Cruet_StaticEntry));
    return idx->entries ? 0 : -1;
}

static void
static_index_free(Cruet_StaticIndex *idx)
{
    if (idx->entries) {
        for (size_t i = 0; i < idx->capacity; i++) {
            if (idx->entries[i].occupied)
                free(idx->entries[i].key);
        }
        free(idx->entries);
        idx->entries = NULL;
    }
    idx->capacity = 0;
    idx->count = 0;
}

/* Find slot for key. Returns pointer to entry (may be empty). */
static Cruet_StaticEntry *
static_index_find_slot(Cruet_StaticEntry *entries, size_t capacity,
                       const char *key, size_t key_len)
{
    uint64_t h = fnv1a_hash(key, key_len);
    size_t idx = (size_t)(h % capacity);
    for (;;) {
        Cruet_StaticEntry *e = &entries[idx];
        if (!e->occupied)
            return e;
        if (e->key_len == key_len && memcmp(e->key, key, key_len) == 0)
            return e;
        idx = (idx + 1) % capacity;
    }
}

static int
static_index_grow(Cruet_StaticIndex *idx)
{
    size_t new_cap = idx->capacity * 2;
    Cruet_StaticEntry *new_entries = calloc(new_cap, sizeof(Cruet_StaticEntry));
    if (!new_entries) return -1;

    for (size_t i = 0; i < idx->capacity; i++) {
        Cruet_StaticEntry *old = &idx->entries[i];
        if (old->occupied) {
            Cruet_StaticEntry *slot = static_index_find_slot(
                new_entries, new_cap, old->key, old->key_len);
            *slot = *old;
        }
    }
    free(idx->entries);
    idx->entries = new_entries;
    idx->capacity = new_cap;
    return 0;
}

static int
static_index_insert(Cruet_StaticIndex *idx, const char *key, size_t key_len,
                    Cruet_Rule *rule)
{
    /* Grow if load factor exceeded */
    if ((idx->count + 1) * 100 > idx->capacity * STATIC_INDEX_LOAD_FACTOR) {
        if (static_index_grow(idx) < 0)
            return -1;
    }

    Cruet_StaticEntry *slot = static_index_find_slot(
        idx->entries, idx->capacity, key, key_len);
    if (slot->occupied)
        return 0; /* duplicate key: keep first rule */

    slot->key = strndup(key, key_len);
    if (!slot->key) return -1;
    slot->key_len = key_len;
    slot->rule = rule; /* borrowed ref */
    slot->occupied = 1;
    idx->count++;
    return 0;
}

/* Lookup a key. Returns the rule or NULL if not found. */
static Cruet_Rule *
static_index_lookup(Cruet_StaticIndex *idx, const char *key, size_t key_len)
{
    if (idx->count == 0)
        return NULL;
    Cruet_StaticEntry *slot = static_index_find_slot(
        idx->entries, idx->capacity, key, key_len);
    if (slot->occupied)
        return slot->rule;
    return NULL;
}

/* ========== Map ========== */

static int
Map_init(Cruet_Map *self, PyObject *args, PyObject *kwargs)
{
    self->rules = PyList_New(0);
    if (!self->rules) return -1;

    if (static_index_init(&self->static_index) < 0) {
        Py_DECREF(self->rules);
        self->rules = NULL;
        return -1;
    }

    self->dynamic_rules = NULL;
    self->n_dynamic = 0;
    self->dynamic_cap = 0;

    return 0;
}

static void
Map_dealloc(Cruet_Map *self)
{
    Py_XDECREF(self->rules);
    static_index_free(&self->static_index);
    free(self->dynamic_rules);
    self->dynamic_rules = NULL;
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
Map_add(Cruet_Map *self, PyObject *args)
{
    PyObject *rule;
    if (!PyArg_ParseTuple(args, "O!", &Cruet_RuleType, &rule))
        return NULL;
    if (PyList_Append(self->rules, rule) < 0)
        return NULL;

    Cruet_Rule *r = (Cruet_Rule *)rule;

    if (r->is_static && r->rule_str) {
        size_t key_len = strlen(r->rule_str);
        if (static_index_insert(&self->static_index, r->rule_str, key_len, r) < 0) {
            PyErr_NoMemory();
            return NULL;
        }
    }

    if (!r->is_static) {
        /* Append to C array, grow if needed */
        if (self->n_dynamic >= self->dynamic_cap) {
            Py_ssize_t new_cap = self->dynamic_cap == 0 ? 16 : self->dynamic_cap * 2;
            Cruet_Rule **new_arr = realloc(self->dynamic_rules,
                                            new_cap * sizeof(Cruet_Rule *));
            if (!new_arr) {
                PyErr_NoMemory();
                return NULL;
            }
            self->dynamic_rules = new_arr;
            self->dynamic_cap = new_cap;
        }
        self->dynamic_rules[self->n_dynamic++] = r; /* borrowed ref */
    }

    Py_RETURN_NONE;
}

static PyObject *
Map_bind(Cruet_Map *self, PyObject *args)
{
    const char *server_name;
    if (!PyArg_ParseTuple(args, "s", &server_name))
        return NULL;

    Cruet_MapAdapter *adapter = PyObject_New(Cruet_MapAdapter, &Cruet_MapAdapterType);
    if (!adapter) return NULL;

    adapter->map = self;
    Py_INCREF(self);
    adapter->server_name = strdup(server_name);

    return (PyObject *)adapter;
}

static PyMethodDef Map_methods[] = {
    {"add", (PyCFunction)Map_add, METH_VARARGS, "Add a Rule to the map."},
    {"bind", (PyCFunction)Map_bind, METH_VARARGS, "Bind map to a server name, returning a MapAdapter."},
    {NULL}
};

PyTypeObject Cruet_MapType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.Map",
    .tp_basicsize = sizeof(Cruet_Map),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)Map_init,
    .tp_dealloc = (destructor)Map_dealloc,
    .tp_methods = Map_methods,
};

/* ========== MapAdapter ========== */

static void
MapAdapter_dealloc(Cruet_MapAdapter *self)
{
    Py_XDECREF((PyObject *)self->map);
    free(self->server_name);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
MapAdapter_match(Cruet_MapAdapter *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"path", "method", NULL};
    const char *path;
    Py_ssize_t path_len;
    const char *method = "GET";

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#|s", kwlist,
                                      &path, &path_len, &method))
        return NULL;

    /* 1. Uppercase method in stack buffer (no PyUnicode_FromString) */
    char method_upper[32];
    size_t mlen = strlen(method);
    if (mlen >= sizeof(method_upper)) mlen = sizeof(method_upper) - 1;
    for (size_t i = 0; i < mlen; i++)
        method_upper[i] = (method[i] >= 'a' && method[i] <= 'z')
                          ? method[i] - 32 : method[i];
    method_upper[mlen] = '\0';

    /* 2. Get method bit (pure C) */
    uint16_t method_bit = cruet_method_str_to_bit(method_upper, mlen);

    /* For non-standard methods, we need a Python string for fallback.
     * Create eagerly when method_bit == 0. */
    PyObject *method_py = NULL;
    if (method_bit == 0) {
        method_py = PyUnicode_FromString(method_upper);
        if (!method_py) return NULL;
    }

    int method_matched_any = 0;

    /* 3. Fast path: static index lookup with raw C string */
    Cruet_Rule *static_rule = static_index_lookup(
        &self->map->static_index, path, (size_t)path_len);

    if (static_rule) {
        int has = cruet_rule_has_method(static_rule, method_bit, method_py);
        if (has < 0) goto error;
        if (has) {
            Py_XDECREF(method_py);
            PyObject *endpoint = PyUnicode_FromString(
                static_rule->endpoint ? static_rule->endpoint : "");
            if (!endpoint) return NULL;
            PyObject *values = PyDict_New();
            if (!values) { Py_DECREF(endpoint); return NULL; }
            PyObject *tuple = PyTuple_Pack(2, endpoint, values);
            Py_DECREF(endpoint);
            Py_DECREF(values);
            return tuple;
        }
        method_matched_any = 1;
    }

    /* 4. Trailing-slash alternate lookup using stack buffer */
    if (!static_rule) {
        char alt_buf[4096];
        const char *alt_key = NULL;
        size_t alt_len = 0;

        if (path_len > 1 && path[path_len - 1] == '/') {
            alt_key = path;
            alt_len = (size_t)(path_len - 1);
        } else if ((size_t)path_len + 1 < sizeof(alt_buf)) {
            memcpy(alt_buf, path, (size_t)path_len);
            alt_buf[path_len] = '/';
            alt_buf[path_len + 1] = '\0';
            alt_key = alt_buf;
            alt_len = (size_t)path_len + 1;
        }

        if (alt_key) {
            Cruet_Rule *alt_rule = static_index_lookup(
                &self->map->static_index, alt_key, alt_len);
            if (alt_rule && !alt_rule->strict_slashes) {
                int has = cruet_rule_has_method(alt_rule, method_bit, method_py);
                if (has < 0) goto error;
                if (has) {
                    Py_XDECREF(method_py);
                    PyObject *endpoint = PyUnicode_FromString(
                        alt_rule->endpoint ? alt_rule->endpoint : "");
                    if (!endpoint) return NULL;
                    PyObject *values = PyDict_New();
                    if (!values) { Py_DECREF(endpoint); return NULL; }
                    PyObject *tuple = PyTuple_Pack(2, endpoint, values);
                    Py_DECREF(endpoint);
                    Py_DECREF(values);
                    return tuple;
                }
                method_matched_any = 1;
            }
        }
    }

    /* 5. Slow path: iterate C array of dynamic rules */
    for (Py_ssize_t i = 0; i < self->map->n_dynamic; i++) {
        Cruet_Rule *rule = self->map->dynamic_rules[i];

        PyObject *result = Cruet_Rule_match_internal(rule, path, (size_t)path_len);
        if (!result) goto error;

        if (result == Py_None) {
            Py_DECREF(result);
            continue;
        }

        /* Path matched! Check method */
        int has = cruet_rule_has_method(rule, method_bit, method_py);
        if (has < 0) { Py_DECREF(result); goto error; }
        if (!has) {
            method_matched_any = 1;
            Py_DECREF(result);
            continue;
        }

        /* Full match */
        Py_XDECREF(method_py);
        PyObject *endpoint = PyUnicode_FromString(rule->endpoint ? rule->endpoint : "");
        if (!endpoint) { Py_DECREF(result); return NULL; }
        PyObject *tuple = PyTuple_Pack(2, endpoint, result);
        Py_DECREF(endpoint);
        Py_DECREF(result);
        return tuple;
    }

    Py_XDECREF(method_py);

    if (method_matched_any)
        PyErr_SetString(PyExc_LookupError, "405 Method Not Allowed");
    else
        PyErr_SetString(PyExc_LookupError, "404 Not Found");
    return NULL;

error:
    Py_XDECREF(method_py);
    return NULL;
}

static PyObject *
MapAdapter_build(Cruet_MapAdapter *self, PyObject *args)
{
    const char *endpoint;
    PyObject *values;
    if (!PyArg_ParseTuple(args, "sO", &endpoint, &values))
        return NULL;

    Py_ssize_t n_rules = PyList_GET_SIZE(self->map->rules);
    for (Py_ssize_t i = 0; i < n_rules; i++) {
        Cruet_Rule *rule = (Cruet_Rule *)PyList_GET_ITEM(self->map->rules, i);
        if (rule->endpoint && strcmp(rule->endpoint, endpoint) == 0) {
            return PyObject_CallMethod((PyObject *)rule, "build", "O", values);
        }
    }

    PyErr_Format(PyExc_LookupError, "No rule for endpoint '%s'", endpoint);
    return NULL;
}

static PyMethodDef MapAdapter_methods[] = {
    {"match", (PyCFunction)MapAdapter_match, METH_VARARGS | METH_KEYWORDS,
     "Match a path and method, returning (endpoint, values)."},
    {"build", (PyCFunction)MapAdapter_build, METH_VARARGS,
     "Build a URL for an endpoint with values."},
    {NULL}
};

PyTypeObject Cruet_MapAdapterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.MapAdapter",
    .tp_basicsize = sizeof(Cruet_MapAdapter),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_dealloc = (destructor)MapAdapter_dealloc,
    .tp_methods = MapAdapter_methods,
};
