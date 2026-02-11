#include "server.h"
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

/*
 * Zero-copy HTTP/1.1 request parser.
 * Parses request line + headers in a single pass.
 * Returns a Python dict with: method, path, query_string, version, headers, body, keep_alive
 * Returns None if the input is incomplete/malformed.
 */

/* Find \r\n in buffer */
static const char *
find_crlf(const char *buf, size_t len)
{
    for (size_t i = 0; i + 1 < len; i++) {
        if (buf[i] == '\r' && buf[i + 1] == '\n')
            return buf + i;
    }
    return NULL;
}

PyObject *
cruet_parse_http_request(PyObject *self, PyObject *args)
{
    const char *data;
    Py_ssize_t data_len;

    if (!PyArg_ParseTuple(args, "y#", &data, &data_len))
        return NULL;

    if (data_len == 0)
        Py_RETURN_NONE;

    /* Find end of request line */
    const char *line_end = find_crlf(data, data_len);
    if (!line_end) {
        /* Incomplete request line */
        Py_RETURN_NONE;
    }

    /* Parse request line: METHOD SP PATH SP VERSION */
    const char *method_start = data;
    const char *p = data;

    /* Find method end (first space) */
    while (p < line_end && *p != ' ') p++;
    if (p >= line_end) Py_RETURN_NONE;
    size_t method_len = p - method_start;

    p++; /* skip space */
    const char *uri_start = p;

    /* Find URI end (next space) */
    while (p < line_end && *p != ' ') p++;
    if (p >= line_end) Py_RETURN_NONE;
    size_t uri_len = p - uri_start;

    p++; /* skip space */
    const char *version_start = p;
    size_t version_len = line_end - version_start;

    /* Validate version roughly */
    if (version_len < 6) Py_RETURN_NONE; /* at least "HTTP/X" */

    /* Split URI into path and query string */
    const char *query_start = NULL;
    size_t path_len = uri_len;
    size_t query_len = 0;
    for (size_t i = 0; i < uri_len; i++) {
        if (uri_start[i] == '?') {
            path_len = i;
            query_start = uri_start + i + 1;
            query_len = uri_len - i - 1;
            break;
        }
    }

    /* Create result dict */
    PyObject *result = PyDict_New();
    if (!result) return NULL;

    PyObject *method = PyUnicode_DecodeLatin1(method_start, method_len, NULL);
    PyObject *path = PyUnicode_DecodeLatin1(uri_start, path_len, NULL);
    PyObject *version = PyUnicode_DecodeLatin1(version_start, version_len, NULL);
    PyObject *qs = query_start
        ? PyUnicode_DecodeLatin1(query_start, query_len, NULL)
        : PyUnicode_FromString("");

    PyDict_SetItemString(result, "method", method);
    PyDict_SetItemString(result, "path", path);
    PyDict_SetItemString(result, "version", version);
    PyDict_SetItemString(result, "query_string", qs);
    Py_DECREF(method);
    Py_DECREF(path);
    Py_DECREF(version);
    Py_DECREF(qs);

    /* Parse headers */
    PyObject *headers = PyDict_New();
    if (!headers) { Py_DECREF(result); return NULL; }

    const char *hp = line_end + 2; /* skip \r\n after request line */
    int keep_alive = 1; /* default for HTTP/1.1 */
    long content_length = -1;

    while (hp < data + data_len) {
        /* Find end of this header line */
        const char *hline_end = find_crlf(hp, data + data_len - hp);
        if (!hline_end) break;

        /* Empty line = end of headers */
        if (hline_end == hp) {
            hp = hline_end + 2;
            break;
        }

        /* Find colon separator */
        const char *colon = hp;
        while (colon < hline_end && *colon != ':') colon++;
        if (colon >= hline_end) {
            hp = hline_end + 2;
            continue; /* malformed header, skip */
        }

        /* Header name */
        size_t hname_len = colon - hp;

        /* Header value (skip leading whitespace) */
        const char *hval = colon + 1;
        while (hval < hline_end && (*hval == ' ' || *hval == '\t')) hval++;
        size_t hval_len = hline_end - hval;

        PyObject *hname = PyUnicode_DecodeLatin1(hp, hname_len, NULL);
        PyObject *hvalue = PyUnicode_DecodeLatin1(hval, hval_len, NULL);
        PyDict_SetItem(headers, hname, hvalue);

        /* Check for Content-Length */
        if (hname_len == 14 && strncasecmp(hp, "Content-Length", 14) == 0) {
            char tmp[32];
            if (hval_len < sizeof(tmp)) {
                memcpy(tmp, hval, hval_len);
                tmp[hval_len] = '\0';
                content_length = strtol(tmp, NULL, 10);
            }
        }

        /* Check for Connection: close */
        if (hname_len == 10 && strncasecmp(hp, "Connection", 10) == 0) {
            if (hval_len == 5 && strncasecmp(hval, "close", 5) == 0)
                keep_alive = 0;
        }

        Py_DECREF(hname);
        Py_DECREF(hvalue);
        hp = hline_end + 2;
    }

    PyDict_SetItemString(result, "headers", headers);
    Py_DECREF(headers);

    /* Body */
    PyObject *body;
    if (content_length > 0 && hp + content_length <= data + data_len) {
        body = PyBytes_FromStringAndSize(hp, content_length);
    } else if (content_length == 0 || content_length == -1) {
        body = PyBytes_FromStringAndSize("", 0);
    } else {
        /* Incomplete body - return what we have */
        size_t available = data + data_len - hp;
        body = PyBytes_FromStringAndSize(hp, available);
    }
    PyDict_SetItemString(result, "body", body);
    Py_DECREF(body);

    /* Keep-alive flag */
    PyObject *ka = keep_alive ? Py_True : Py_False;
    Py_INCREF(ka);
    PyDict_SetItemString(result, "keep_alive", ka);
    Py_DECREF(ka);

    return result;
}
