#include "routing.h"
#include <structmember.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>

/* ---- Method bitmask helpers ---- */

uint16_t
cruet_method_str_to_bit(const char *s, size_t len)
{
    switch (len) {
    case 3:
        if (s[0] == 'G' && s[1] == 'E' && s[2] == 'T')
            return CRUET_METHOD_GET;
        if (s[0] == 'P' && s[1] == 'U' && s[2] == 'T')
            return CRUET_METHOD_PUT;
        break;
    case 4:
        if (s[0] == 'H' && s[1] == 'E' && s[2] == 'A' && s[3] == 'D')
            return CRUET_METHOD_HEAD;
        if (s[0] == 'P' && s[1] == 'O' && s[2] == 'S' && s[3] == 'T')
            return CRUET_METHOD_POST;
        break;
    case 5:
        if (s[0] == 'P' && s[1] == 'A' && s[2] == 'T' && s[3] == 'C' && s[4] == 'H')
            return CRUET_METHOD_PATCH;
        if (s[0] == 'T' && s[1] == 'R' && s[2] == 'A' && s[3] == 'C' && s[4] == 'E')
            return CRUET_METHOD_TRACE;
        break;
    case 6:
        if (s[0] == 'D' && s[1] == 'E' && s[2] == 'L' && s[3] == 'E' &&
            s[4] == 'T' && s[5] == 'E')
            return CRUET_METHOD_DELETE;
        break;
    case 7:
        if (s[0] == 'O' && s[1] == 'P' && s[2] == 'T' && s[3] == 'I' &&
            s[4] == 'O' && s[5] == 'N' && s[6] == 'S')
            return CRUET_METHOD_OPTIONS;
        break;
    }
    return 0;
}

int
cruet_rule_has_method(Cruet_Rule *rule, uint16_t method_bit,
                       PyObject *method_py)
{
    if (method_bit != 0) {
        return (rule->methods_bitmask & method_bit) ? 1 : 0;
    }
    /* Non-standard method: check methods_extra frozenset */
    if (rule->methods_extra == NULL)
        return 0;
    return PySet_Contains(rule->methods_extra, method_py);
}

/* ---- Segment parsing helpers ---- */

static SegmentType
converter_name_to_type(const char *name, size_t len)
{
    if (len == 0 || (len == 6 && strncmp(name, "string", 6) == 0))
        return SEG_DYNAMIC_STRING;
    if (len == 3 && strncmp(name, "int", 3) == 0)
        return SEG_DYNAMIC_INT;
    if (len == 5 && strncmp(name, "float", 5) == 0)
        return SEG_DYNAMIC_FLOAT;
    if (len == 4 && strncmp(name, "uuid", 4) == 0)
        return SEG_DYNAMIC_UUID;
    if (len == 4 && strncmp(name, "path", 4) == 0)
        return SEG_DYNAMIC_PATH;
    if (len == 3 && strncmp(name, "any", 3) == 0)
        return SEG_DYNAMIC_ANY;
    return SEG_DYNAMIC_STRING; /* default */
}

static void
free_segment(RuleSegment *seg)
{
    free(seg->static_text);
    free(seg->var_name);
    Py_XDECREF(seg->any_items);
}

/*
 * Parse a rule string like "/user/<int:id>/post/<name>" into segments.
 * Segments are separated by the dynamic parts <...>.
 */
static int
parse_rule_segments(const char *rule, RuleSegment **out_segments, int *out_count)
{
    /* Count max segments (upper bound) */
    int max_segs = 1;
    for (const char *p = rule; *p; p++)
        if (*p == '<') max_segs += 2; /* static before + dynamic */

    RuleSegment *segs = calloc(max_segs, sizeof(RuleSegment));
    if (!segs) return -1;

    int n = 0;
    const char *p = rule;

    while (*p) {
        if (*p == '<') {
            /* Dynamic segment: parse <converter:name> or <name> or <any(a,b,c):name> */
            p++; /* skip '<' */
            const char *start = p;

            /* Find the closing '>' */
            while (*p && *p != '>') p++;
            if (!*p) { free(segs); return -1; } /* unclosed */

            size_t total_len = p - start;
            p++; /* skip '>' */

            /* Parse "converter:name" or "name" or "any(a,b,...):name" */
            const char *colon = NULL;
            const char *paren_open = NULL;
            const char *paren_close = NULL;
            for (const char *c = start; c < start + total_len; c++) {
                if (*c == '(' && !paren_open) paren_open = c;
                if (*c == ')' && paren_open) paren_close = c;
                if (*c == ':' && !colon && (!paren_open || paren_close)) colon = c;
            }

            const char *conv_name;
            size_t conv_len;
            const char *var_start;
            size_t var_len;

            if (colon) {
                conv_name = start;
                if (paren_open)
                    conv_len = paren_open - start;
                else
                    conv_len = colon - start;
                var_start = colon + 1;
                var_len = total_len - (colon + 1 - start);
            } else {
                conv_name = "";
                conv_len = 0;
                var_start = start;
                var_len = total_len;
            }

            segs[n].type = converter_name_to_type(conv_name, conv_len);
            segs[n].var_name = strndup(var_start, var_len);

            /* Parse any(...) items */
            if (paren_open && paren_close && segs[n].type == SEG_DYNAMIC_ANY) {
                const char *items_start = paren_open + 1;
                size_t items_len = paren_close - items_start;
                /* Parse comma-separated items */
                PyObject *item_list = PyList_New(0);
                const char *istart = items_start;
                for (const char *ic = items_start; ic <= items_start + items_len; ic++) {
                    if (ic == items_start + items_len || *ic == ',') {
                        /* trim whitespace */
                        const char *is = istart;
                        const char *ie = ic;
                        while (is < ie && isspace((unsigned char)*is)) is++;
                        while (ie > is && isspace((unsigned char)*(ie-1))) ie--;
                        if (ie > is) {
                            PyObject *s = PyUnicode_FromStringAndSize(is, ie - is);
                            PyList_Append(item_list, s);
                            Py_DECREF(s);
                        }
                        istart = ic + 1;
                    }
                }
                segs[n].any_items = PyList_AsTuple(item_list);
                Py_DECREF(item_list);
            }

            n++;
        } else {
            /* Static segment: collect until next '<' or end */
            const char *start = p;
            while (*p && *p != '<') p++;
            size_t slen = p - start;

            segs[n].type = SEG_STATIC;
            segs[n].static_text = strndup(start, slen);
            segs[n].static_len = slen;
            n++;
        }
    }

    *out_segments = segs;
    *out_count = n;
    return 0;
}

/* ---- Rule type methods ---- */

static int
Rule_init(Cruet_Rule *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"rule", "endpoint", "methods", "strict_slashes", NULL};
    const char *rule_str = NULL;
    const char *endpoint = NULL;
    PyObject *methods = NULL;
    int strict_slashes = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|sOp", kwlist,
                                      &rule_str, &endpoint, &methods,
                                      &strict_slashes))
        return -1;

    self->rule_str = strdup(rule_str);
    self->endpoint = endpoint ? strdup(endpoint) : NULL;
    self->strict_slashes = strict_slashes;

    /* Parse methods into bitmask + extras */
    self->methods_bitmask = 0;
    self->methods_extra = NULL;
    PyObject *extras_list = NULL; /* temporary list for non-standard methods */

    if (methods && methods != Py_None) {
        PyObject *iter = PyObject_GetIter(methods);
        if (!iter) return -1;
        PyObject *item;
        while ((item = PyIter_Next(iter)) != NULL) {
            /* Uppercase the method */
            PyObject *upper = PyObject_CallMethod(item, "upper", NULL);
            Py_DECREF(item);
            if (!upper) { Py_DECREF(iter); Py_XDECREF(extras_list); return -1; }

            const char *method_cstr = PyUnicode_AsUTF8(upper);
            if (!method_cstr) { Py_DECREF(upper); Py_DECREF(iter); Py_XDECREF(extras_list); return -1; }
            size_t method_len = strlen(method_cstr);

            uint16_t bit = cruet_method_str_to_bit(method_cstr, method_len);
            if (bit != 0) {
                self->methods_bitmask |= bit;
            } else {
                /* Non-standard method: add to extras list */
                if (!extras_list) {
                    extras_list = PyList_New(0);
                    if (!extras_list) { Py_DECREF(upper); Py_DECREF(iter); return -1; }
                }
                PyList_Append(extras_list, upper);
            }
            Py_DECREF(upper);
        }
        Py_DECREF(iter);
        if (PyErr_Occurred()) { Py_XDECREF(extras_list); return -1; }
    } else {
        /* Default: GET */
        self->methods_bitmask = CRUET_METHOD_GET;
    }

    /* Always add HEAD and OPTIONS */
    self->methods_bitmask |= CRUET_METHOD_HEAD | CRUET_METHOD_OPTIONS;

    /* Build methods_extra frozenset if there are non-standard methods */
    if (extras_list) {
        self->methods_extra = PyFrozenSet_New(extras_list);
        Py_DECREF(extras_list);
        if (!self->methods_extra) return -1;
    }

    /* Parse rule into segments */
    if (parse_rule_segments(rule_str, &self->segments, &self->n_segments) < 0) {
        PyErr_SetString(PyExc_ValueError, "Failed to parse rule pattern");
        return -1;
    }

    /* Check if all segments are static */
    self->is_static = 1;
    for (int i = 0; i < self->n_segments; i++) {
        if (self->segments[i].type != SEG_STATIC) {
            self->is_static = 0;
            break;
        }
    }

    return 0;
}

static void
Rule_dealloc(Cruet_Rule *self)
{
    free(self->rule_str);
    free(self->endpoint);
    Py_XDECREF(self->methods_extra);
    if (self->segments) {
        for (int i = 0; i < self->n_segments; i++)
            free_segment(&self->segments[i]);
        free(self->segments);
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
Rule_get_rule(Cruet_Rule *self, void *closure)
{
    return PyUnicode_FromString(self->rule_str);
}

static PyObject *
Rule_get_endpoint(Cruet_Rule *self, void *closure)
{
    if (self->endpoint)
        return PyUnicode_FromString(self->endpoint);
    Py_RETURN_NONE;
}

/* Reconstruct frozenset from bitmask + extras (only called from Python, not hot path) */
static PyObject *
Rule_get_methods(Cruet_Rule *self, void *closure)
{
    PyObject *method_set = PySet_New(NULL);
    if (!method_set) return NULL;

    static const struct { uint16_t bit; const char *name; } standard_methods[] = {
        { CRUET_METHOD_GET,     "GET" },
        { CRUET_METHOD_HEAD,    "HEAD" },
        { CRUET_METHOD_POST,    "POST" },
        { CRUET_METHOD_PUT,     "PUT" },
        { CRUET_METHOD_DELETE,  "DELETE" },
        { CRUET_METHOD_PATCH,   "PATCH" },
        { CRUET_METHOD_OPTIONS, "OPTIONS" },
        { CRUET_METHOD_TRACE,   "TRACE" },
    };

    for (size_t i = 0; i < sizeof(standard_methods) / sizeof(standard_methods[0]); i++) {
        if (self->methods_bitmask & standard_methods[i].bit) {
            PyObject *s = PyUnicode_FromString(standard_methods[i].name);
            if (!s) { Py_DECREF(method_set); return NULL; }
            PySet_Add(method_set, s);
            Py_DECREF(s);
        }
    }

    /* Add non-standard methods from extras frozenset */
    if (self->methods_extra) {
        PyObject *iter = PyObject_GetIter(self->methods_extra);
        if (!iter) { Py_DECREF(method_set); return NULL; }
        PyObject *item;
        while ((item = PyIter_Next(iter)) != NULL) {
            PySet_Add(method_set, item);
            Py_DECREF(item);
        }
        Py_DECREF(iter);
        if (PyErr_Occurred()) { Py_DECREF(method_set); return NULL; }
    }

    PyObject *result = PyFrozenSet_New(method_set);
    Py_DECREF(method_set);
    return result;
}

static PyObject *
Rule_get_strict_slashes(Cruet_Rule *self, void *closure)
{
    return PyBool_FromLong(self->strict_slashes);
}

/*
 * Convert a captured segment value using the segment's converter type.
 * Returns: new PyObject* on match, Py_None (new ref) on no-match, NULL on error.
 */
static PyObject *
convert_segment_value(RuleSegment *seg, const char *value, size_t len)
{
    char *tmp = strndup(value, len);
    if (!tmp) { PyErr_NoMemory(); return NULL; }

    PyObject *result = NULL;

    switch (seg->type) {
    case SEG_DYNAMIC_STRING:
        result = PyUnicode_FromStringAndSize(value, len);
        break;
    case SEG_DYNAMIC_INT: {
        /* Validate digits */
        for (size_t i = 0; i < len; i++) {
            if (tmp[i] < '0' || tmp[i] > '9') {
                free(tmp);
                Py_RETURN_NONE; /* not a match */
            }
        }
        long v = strtol(tmp, NULL, 10);
        result = PyLong_FromLong(v);
        break;
    }
    case SEG_DYNAMIC_FLOAT: {
        char *endptr;
        double v = strtod(tmp, &endptr);
        if (endptr != tmp + len) { free(tmp); Py_RETURN_NONE; }
        result = PyFloat_FromDouble(v);
        break;
    }
    case SEG_DYNAMIC_UUID: {
        /* Validate UUID format roughly: 8-4-4-4-12 hex */
        if (len != 36) { free(tmp); Py_RETURN_NONE; }
        for (size_t i = 0; i < 36; i++) {
            if (i == 8 || i == 13 || i == 18 || i == 23) {
                if (tmp[i] != '-') { free(tmp); Py_RETURN_NONE; }
            } else {
                char c = tmp[i];
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) {
                    free(tmp);
                    Py_RETURN_NONE;
                }
            }
        }
        /* Create uuid.UUID object */
        PyObject *uuid_mod = PyImport_ImportModule("uuid");
        if (!uuid_mod) { free(tmp); return NULL; }
        PyObject *uuid_cls = PyObject_GetAttrString(uuid_mod, "UUID");
        Py_DECREF(uuid_mod);
        if (!uuid_cls) { free(tmp); return NULL; }
        PyObject *str_arg = PyUnicode_FromStringAndSize(value, len);
        if (!str_arg) { Py_DECREF(uuid_cls); free(tmp); return NULL; }
        result = PyObject_CallOneArg(uuid_cls, str_arg);
        Py_DECREF(uuid_cls);
        Py_DECREF(str_arg);
        break;
    }
    case SEG_DYNAMIC_PATH:
        result = PyUnicode_FromStringAndSize(value, len);
        break;
    case SEG_DYNAMIC_ANY:
        if (seg->any_items) {
            PyObject *s = PyUnicode_FromStringAndSize(value, len);
            if (!s) { free(tmp); return NULL; }
            int found = PySequence_Contains(seg->any_items, s);
            if (found < 0) { Py_DECREF(s); free(tmp); return NULL; }
            if (found == 0) { Py_DECREF(s); free(tmp); Py_RETURN_NONE; }
            result = s;
        } else {
            result = PyUnicode_FromStringAndSize(value, len);
        }
        break;
    default:
        result = PyUnicode_FromStringAndSize(value, len);
        break;
    }

    free(tmp);
    return result;
}

/*
 * Match a path against this rule's segments.
 * Returns a dict of {name: value} on match, or Py_None (not an error) on no match.
 */
PyObject *
Cruet_Rule_match_internal(Cruet_Rule *self, const char *path, size_t path_len)
{
    PyObject *values = PyDict_New();
    if (!values) return NULL;

    const char *p = path;
    const char *path_end = path + path_len;

    for (int i = 0; i < self->n_segments; i++) {
        RuleSegment *seg = &self->segments[i];

        if (seg->type == SEG_STATIC) {
            /* Must match the static text exactly */
            if ((size_t)(path_end - p) < seg->static_len ||
                memcmp(p, seg->static_text, seg->static_len) != 0) {
                Py_DECREF(values);
                Py_RETURN_NONE;
            }
            p += seg->static_len;
        } else if (seg->type == SEG_DYNAMIC_PATH) {
            /* Path converter: consume until end (but before trailing static segments) */
            /* Look ahead for any trailing static text */
            size_t remaining = path_end - p;
            size_t trail = 0;
            for (int j = i + 1; j < self->n_segments; j++) {
                if (self->segments[j].type == SEG_STATIC)
                    trail += self->segments[j].static_len;
            }
            if (remaining <= trail) {
                Py_DECREF(values);
                Py_RETURN_NONE;
            }
            size_t capture_len = remaining - trail;
            if (capture_len == 0) {
                Py_DECREF(values);
                Py_RETURN_NONE;
            }

            PyObject *val = convert_segment_value(seg, p, capture_len);
            if (!val) { Py_DECREF(values); return NULL; }
            if (val == Py_None) { Py_DECREF(val); Py_DECREF(values); Py_RETURN_NONE; }

            PyObject *key = PyUnicode_FromString(seg->var_name);
            if (!key) { Py_DECREF(val); Py_DECREF(values); return NULL; }
            PyDict_SetItem(values, key, val);
            Py_DECREF(key);
            Py_DECREF(val);
            p += capture_len;
        } else {
            /* Non-path dynamic: consume until next '/' or end */
            const char *seg_start = p;
            while (p < path_end && *p != '/') p++;

            if (p == seg_start) {
                /* Empty segment */
                Py_DECREF(values);
                Py_RETURN_NONE;
            }

            PyObject *val = convert_segment_value(seg, seg_start, p - seg_start);
            if (!val) { Py_DECREF(values); return NULL; }
            if (val == Py_None) { Py_DECREF(val); Py_DECREF(values); Py_RETURN_NONE; }

            PyObject *key = PyUnicode_FromString(seg->var_name);
            if (!key) { Py_DECREF(val); Py_DECREF(values); return NULL; }
            PyDict_SetItem(values, key, val);
            Py_DECREF(key);
            Py_DECREF(val);
        }
    }

    /* Must have consumed entire path */
    if (p != path_end) {
        /* Handle strict_slashes=False: allow trailing slash */
        if (!self->strict_slashes && p + 1 == path_end && *p == '/') {
            return values;
        }
        Py_DECREF(values);
        Py_RETURN_NONE;
    }

    return values;
}

static PyObject *
Rule_match(Cruet_Rule *self, PyObject *args)
{
    const char *path;
    Py_ssize_t path_len;
    if (!PyArg_ParseTuple(args, "s#", &path, &path_len))
        return NULL;

    return Cruet_Rule_match_internal(self, path, (size_t)path_len);
}

static PyObject *
Rule_build(Cruet_Rule *self, PyObject *args)
{
    PyObject *values;
    if (!PyArg_ParseTuple(args, "O", &values))
        return NULL;

    /* Build URL from segments and values dict */
    PyObject *parts = PyList_New(0);
    if (!parts) return NULL;

    for (int i = 0; i < self->n_segments; i++) {
        RuleSegment *seg = &self->segments[i];
        if (seg->type == SEG_STATIC) {
            PyObject *s = PyUnicode_FromStringAndSize(seg->static_text, seg->static_len);
            if (!s) { Py_DECREF(parts); return NULL; }
            PyList_Append(parts, s);
            Py_DECREF(s);
        } else {
            PyObject *key = PyUnicode_FromString(seg->var_name);
            if (!key) { Py_DECREF(parts); return NULL; }
            PyObject *val = PyDict_GetItemWithError(values, key);
            Py_DECREF(key);
            if (!val) {
                if (!PyErr_Occurred())
                    PyErr_Format(PyExc_KeyError, "Missing argument: '%s'", seg->var_name);
                Py_DECREF(parts);
                return NULL;
            }
            PyObject *str_val = PyObject_Str(val);
            if (!str_val) { Py_DECREF(parts); return NULL; }
            PyList_Append(parts, str_val);
            Py_DECREF(str_val);
        }
    }

    PyObject *empty = PyUnicode_FromString("");
    PyObject *result = PyUnicode_Join(empty, parts);
    Py_DECREF(empty);
    Py_DECREF(parts);
    return result;
}

static PyMethodDef Rule_methods[] = {
    {"match", (PyCFunction)Rule_match, METH_VARARGS, "Match a path against this rule."},
    {"build", (PyCFunction)Rule_build, METH_VARARGS, "Build a URL from values dict."},
    {NULL}
};

static PyGetSetDef Rule_getset[] = {
    {"rule", (getter)Rule_get_rule, NULL, "The URL rule string", NULL},
    {"endpoint", (getter)Rule_get_endpoint, NULL, "The endpoint name", NULL},
    {"methods", (getter)Rule_get_methods, NULL, "Allowed HTTP methods", NULL},
    {"strict_slashes", (getter)Rule_get_strict_slashes, NULL, "Strict trailing slash mode", NULL},
    {NULL}
};

PyTypeObject Cruet_RuleType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.Rule",
    .tp_basicsize = sizeof(Cruet_Rule),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)Rule_init,
    .tp_dealloc = (destructor)Rule_dealloc,
    .tp_methods = Rule_methods,
    .tp_getset = Rule_getset,
};
