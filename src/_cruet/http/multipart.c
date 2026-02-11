#include "http.h"
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

/*
 * parse_multipart(body_bytes, boundary_str)
 * -> {"fields": {name: value}, "files": {name: {filename, content_type, data}}}
 */

/* Find needle in haystack (binary safe) */
static const char *
memmem_safe(const char *haystack, size_t hlen, const char *needle, size_t nlen)
{
    if (nlen == 0) return haystack;
    if (nlen > hlen) return NULL;
    for (size_t i = 0; i <= hlen - nlen; i++) {
        if (memcmp(haystack + i, needle, nlen) == 0)
            return haystack + i;
    }
    return NULL;
}

/* Extract a header value from part headers. Returns NULL if not found. */
static const char *
get_part_header(const char *headers, size_t hlen, const char *name, size_t *vlen)
{
    size_t nlen = strlen(name);
    const char *p = headers;
    const char *end = headers + hlen;

    while (p < end) {
        /* Find line end */
        const char *line_end = memmem_safe(p, end - p, "\r\n", 2);
        if (!line_end) line_end = end;
        size_t line_len = line_end - p;

        /* Check if line starts with header name (case-insensitive) */
        if (line_len > nlen + 1 && p[nlen] == ':') {
            int match = 1;
            for (size_t i = 0; i < nlen; i++) {
                if (tolower((unsigned char)p[i]) != tolower((unsigned char)name[i])) {
                    match = 0;
                    break;
                }
            }
            if (match) {
                const char *val = p + nlen + 1;
                while (val < line_end && (*val == ' ' || *val == '\t')) val++;
                *vlen = line_end - val;
                return val;
            }
        }

        p = line_end + 2; /* skip \r\n */
    }
    return NULL;
}

/* Extract a parameter from a header value, e.g. name="foo" from Content-Disposition */
static char *
extract_param(const char *header, size_t hlen, const char *param)
{
    size_t plen = strlen(param);
    const char *p = header;
    const char *end = header + hlen;

    while (p + plen + 1 < end) {
        /* Look for param= or param=" */
        if (strncasecmp(p, param, plen) == 0 && p[plen] == '=') {
            p += plen + 1;
            if (*p == '"') {
                p++;
                const char *q = memchr(p, '"', end - p);
                if (!q) return NULL;
                return strndup(p, q - p);
            } else {
                const char *q = p;
                while (q < end && *q != ';' && *q != ' ' && *q != '\r')
                    q++;
                return strndup(p, q - p);
            }
        }
        p++;
    }
    return NULL;
}

PyObject *
cruet_parse_multipart(PyObject *self, PyObject *args)
{
    const char *body;
    Py_ssize_t body_len;
    const char *boundary;
    Py_ssize_t boundary_len;

    if (!PyArg_ParseTuple(args, "y#s#", &body, &body_len, &boundary, &boundary_len))
        return NULL;

    PyObject *fields = PyDict_New();
    PyObject *files = PyDict_New();
    if (!fields || !files) {
        Py_XDECREF(fields);
        Py_XDECREF(files);
        return NULL;
    }

    /* Build full boundary markers */
    char *delim = malloc(boundary_len + 4 + 1);
    if (!delim) { Py_DECREF(fields); Py_DECREF(files); return PyErr_NoMemory(); }
    delim[0] = '-';
    delim[1] = '-';
    memcpy(delim + 2, boundary, boundary_len);
    size_t delim_len = boundary_len + 2;
    delim[delim_len] = '\0';

    /* Find first boundary */
    const char *p = memmem_safe(body, body_len, delim, delim_len);
    if (!p) {
        free(delim);
        goto done;
    }
    p += delim_len;
    /* Skip \r\n after boundary */
    if (p + 2 <= body + body_len && p[0] == '\r' && p[1] == '\n')
        p += 2;

    while (p < body + body_len) {
        /* Find next boundary */
        const char *next = memmem_safe(p, body + body_len - p, delim, delim_len);
        if (!next) {
            /* No more boundaries -- treat rest as last part */
            next = body + body_len;
        }

        /* Part data is from p to next */
        size_t part_len = next - p;
        if (part_len < 4) break; /* too small */

        /* Remove trailing \r\n before boundary */
        if (part_len >= 2 && p[part_len - 2] == '\r' && p[part_len - 1] == '\n')
            part_len -= 2;

        /* Split headers from body at \r\n\r\n */
        const char *header_end = memmem_safe(p, part_len, "\r\n\r\n", 4);
        if (!header_end) break;

        size_t headers_len = header_end - p;
        const char *part_body = header_end + 4;
        size_t part_body_len = part_len - headers_len - 4;

        /* Parse Content-Disposition */
        size_t cd_len;
        const char *cd = get_part_header(p, headers_len, "Content-Disposition", &cd_len);
        if (!cd) goto next_part;

        char *name = extract_param(cd, cd_len, "name");
        if (!name) goto next_part;

        char *filename = extract_param(cd, cd_len, "filename");

        if (filename) {
            /* File upload */
            size_t ct_len;
            const char *ct = get_part_header(p, headers_len, "Content-Type", &ct_len);
            const char *ct_str = "application/octet-stream";
            char *ct_dup = NULL;
            if (ct) {
                ct_dup = strndup(ct, ct_len);
                ct_str = ct_dup;
            }

            PyObject *file_dict = PyDict_New();
            PyObject *fn_obj = PyUnicode_DecodeLatin1(filename, strlen(filename), NULL);
            PyObject *ct_obj = PyUnicode_DecodeLatin1(ct_str, strlen(ct_str), NULL);
            PyObject *data_obj = PyBytes_FromStringAndSize(part_body, part_body_len);

            PyDict_SetItemString(file_dict, "filename", fn_obj);
            PyDict_SetItemString(file_dict, "content_type", ct_obj);
            PyDict_SetItemString(file_dict, "data", data_obj);

            PyObject *name_obj = PyUnicode_DecodeLatin1(name, strlen(name), NULL);
            PyDict_SetItem(files, name_obj, file_dict);

            Py_DECREF(name_obj);
            Py_DECREF(fn_obj);
            Py_DECREF(ct_obj);
            Py_DECREF(data_obj);
            Py_DECREF(file_dict);
            free(ct_dup);
            free(filename);
        } else {
            /* Form field */
            PyObject *name_obj = PyUnicode_DecodeLatin1(name, strlen(name), NULL);
            PyObject *val_obj = PyUnicode_DecodeUTF8(part_body, part_body_len, "surrogateescape");
            PyDict_SetItem(fields, name_obj, val_obj);
            Py_DECREF(name_obj);
            Py_DECREF(val_obj);
        }

        free(name);

next_part:
        /* Move past the next boundary */
        p = next + delim_len;
        /* Check for -- (final boundary) */
        if (p + 2 <= body + body_len && p[0] == '-' && p[1] == '-')
            break;
        /* Skip \r\n */
        if (p + 2 <= body + body_len && p[0] == '\r' && p[1] == '\n')
            p += 2;
    }

    free(delim);

done:;
    PyObject *result = PyDict_New();
    PyDict_SetItemString(result, "fields", fields);
    PyDict_SetItemString(result, "files", files);
    Py_DECREF(fields);
    Py_DECREF(files);
    return result;
}
