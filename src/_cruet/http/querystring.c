#include "http.h"
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

/* Decode a percent-encoded or +-encoded segment in-place */
static size_t
qs_decode(char *str, size_t len)
{
    size_t r = 0, w = 0;
    while (r < len) {
        if (str[r] == '%' && r + 2 < len) {
            char hi = str[r+1], lo = str[r+2];
            int hv = -1, lv = -1;
            if (hi >= '0' && hi <= '9') hv = hi - '0';
            else if (hi >= 'a' && hi <= 'f') hv = hi - 'a' + 10;
            else if (hi >= 'A' && hi <= 'F') hv = hi - 'A' + 10;
            if (lo >= '0' && lo <= '9') lv = lo - '0';
            else if (lo >= 'a' && lo <= 'f') lv = lo - 'a' + 10;
            else if (lo >= 'A' && lo <= 'F') lv = lo - 'A' + 10;
            if (hv >= 0 && lv >= 0) {
                str[w++] = (char)((hv << 4) | lv);
                r += 3;
                continue;
            }
        }
        if (str[r] == '+') {
            str[w++] = ' ';
            r++;
        } else {
            str[w++] = str[r++];
        }
    }
    return w;
}

/*
 * parse_qs(query_string) -> dict of {str: list[str]}
 */
PyObject *
cruet_parse_qs(PyObject *self, PyObject *args)
{
    const char *qs;
    Py_ssize_t qs_len;
    if (!PyArg_ParseTuple(args, "s#", &qs, &qs_len))
        return NULL;

    PyObject *result = PyDict_New();
    if (!result) return NULL;

    const char *p = qs;
    const char *end = qs + qs_len;

    while (p < end) {
        /* Find end of this key=value pair */
        const char *pair_end = p;
        while (pair_end < end && *pair_end != '&' && *pair_end != ';')
            pair_end++;

        if (pair_end > p) {
            /* Find the '=' */
            const char *eq = p;
            while (eq < pair_end && *eq != '=')
                eq++;

            /* Decode key */
            size_t key_raw_len = eq - p;
            char *key_buf = malloc(key_raw_len + 1);
            if (!key_buf) { Py_DECREF(result); return PyErr_NoMemory(); }
            memcpy(key_buf, p, key_raw_len);
            size_t key_len = qs_decode(key_buf, key_raw_len);

            /* Decode value */
            const char *val_start = (eq < pair_end) ? eq + 1 : pair_end;
            size_t val_raw_len = pair_end - val_start;
            char *val_buf = malloc(val_raw_len + 1);
            if (!val_buf) { free(key_buf); Py_DECREF(result); return PyErr_NoMemory(); }
            memcpy(val_buf, val_start, val_raw_len);
            size_t val_len = qs_decode(val_buf, val_raw_len);

            PyObject *key = PyUnicode_DecodeUTF8(key_buf, key_len, "surrogateescape");
            PyObject *val = PyUnicode_DecodeUTF8(val_buf, val_len, "surrogateescape");
            free(key_buf);
            free(val_buf);

            if (!key || !val) {
                Py_XDECREF(key);
                Py_XDECREF(val);
                Py_DECREF(result);
                return NULL;
            }

            /* Get or create the list */
            PyObject *existing = PyDict_GetItemWithError(result, key);
            if (existing) {
                PyList_Append(existing, val);
            } else {
                if (PyErr_Occurred()) {
                    Py_DECREF(key); Py_DECREF(val); Py_DECREF(result);
                    return NULL;
                }
                PyObject *list = PyList_New(1);
                Py_INCREF(val);
                PyList_SET_ITEM(list, 0, val);
                PyDict_SetItem(result, key, list);
                Py_DECREF(list);
            }

            Py_DECREF(key);
            Py_DECREF(val);
        }

        p = pair_end + 1; /* skip delimiter */
    }

    return result;
}
