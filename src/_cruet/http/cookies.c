#include "http.h"
#include <string.h>
#include <ctype.h>

/*
 * parse_cookies(cookie_header_string) -> dict of {str: str}
 * Parses a Cookie: header value like "name1=val1; name2=val2"
 */
PyObject *
cruet_parse_cookies(PyObject *self, PyObject *args)
{
    const char *cookie_str;
    Py_ssize_t cookie_len;
    if (!PyArg_ParseTuple(args, "s#", &cookie_str, &cookie_len))
        return NULL;

    PyObject *result = PyDict_New();
    if (!result) return NULL;

    const char *p = cookie_str;
    const char *end = cookie_str + cookie_len;

    while (p < end) {
        /* Skip whitespace and semicolons */
        while (p < end && (*p == ' ' || *p == '\t' || *p == ';'))
            p++;
        if (p >= end) break;

        /* Find the '=' */
        const char *name_start = p;
        while (p < end && *p != '=' && *p != ';')
            p++;

        if (p >= end || *p != '=') {
            /* No '=', skip this malformed entry */
            while (p < end && *p != ';') p++;
            continue;
        }

        /* Trim trailing whitespace from name */
        const char *name_end = p;
        while (name_end > name_start && (*(name_end-1) == ' ' || *(name_end-1) == '\t'))
            name_end--;

        p++; /* skip '=' */

        /* Parse value - handle quoted strings */
        const char *val_start;
        const char *val_end;

        /* Skip leading whitespace */
        while (p < end && (*p == ' ' || *p == '\t'))
            p++;

        if (p < end && *p == '"') {
            /* Quoted value */
            p++; /* skip opening quote */
            val_start = p;
            while (p < end && *p != '"')
                p++;
            val_end = p;
            if (p < end) p++; /* skip closing quote */
        } else {
            val_start = p;
            while (p < end && *p != ';')
                p++;
            val_end = p;
            /* Trim trailing whitespace from value */
            while (val_end > val_start && (*(val_end-1) == ' ' || *(val_end-1) == '\t'))
                val_end--;
        }

        if (name_end > name_start) {
            PyObject *key = PyUnicode_DecodeLatin1(name_start, name_end - name_start, NULL);
            PyObject *val = PyUnicode_DecodeLatin1(val_start, val_end - val_start, NULL);
            if (key && val)
                PyDict_SetItem(result, key, val);
            Py_XDECREF(key);
            Py_XDECREF(val);
        }
    }

    return result;
}
