#include "http.h"
#include <structmember.h>
#include <string.h>

static int
CRequest_init(Cruet_CRequest *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"environ", NULL};
    PyObject *environ = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O", kwlist, &environ))
        return -1;

    if (!PyDict_Check(environ)) {
        PyErr_SetString(PyExc_TypeError, "environ must be a dict");
        return -1;
    }

    self->environ = environ;
    Py_INCREF(environ);
    self->cached_args = NULL;
    self->cached_headers = NULL;
    self->cached_data = NULL;
    self->cached_json = NULL;
    self->cached_form = NULL;
    self->cached_cookies = NULL;
    self->cached_files = NULL;
    self->json_loaded = 0;
    self->endpoint = Py_None;
    Py_INCREF(Py_None);
    self->view_args = Py_None;
    Py_INCREF(Py_None);
    self->blueprint = Py_None;
    Py_INCREF(Py_None);

    return 0;
}

static void
CRequest_dealloc(Cruet_CRequest *self)
{
    Py_XDECREF(self->environ);
    Py_XDECREF(self->cached_args);
    Py_XDECREF(self->cached_headers);
    Py_XDECREF(self->cached_data);
    Py_XDECREF(self->cached_json);
    Py_XDECREF(self->cached_form);
    Py_XDECREF(self->cached_cookies);
    Py_XDECREF(self->cached_files);
    Py_XDECREF(self->endpoint);
    Py_XDECREF(self->view_args);
    Py_XDECREF(self->blueprint);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* Helper: get string from environ */
static const char *
get_environ_str(PyObject *environ, const char *key, const char *default_val)
{
    PyObject *val = PyDict_GetItemString(environ, key);
    if (val && PyUnicode_Check(val))
        return PyUnicode_AsUTF8(val);
    return default_val;
}

static PyObject *
CRequest_get_method(Cruet_CRequest *self, void *closure)
{
    const char *method = get_environ_str(self->environ, "REQUEST_METHOD", "GET");
    return PyUnicode_FromString(method);
}

static PyObject *
CRequest_get_path(Cruet_CRequest *self, void *closure)
{
    const char *path = get_environ_str(self->environ, "PATH_INFO", "/");
    return PyUnicode_FromString(path);
}

static PyObject *
CRequest_get_query_string(Cruet_CRequest *self, void *closure)
{
    const char *qs = get_environ_str(self->environ, "QUERY_STRING", "");
    return PyUnicode_FromString(qs);
}

static PyObject *
CRequest_get_content_type(Cruet_CRequest *self, void *closure)
{
    const char *ct = get_environ_str(self->environ, "CONTENT_TYPE", "");
    return PyUnicode_FromString(ct);
}

static PyObject *
CRequest_get_host(Cruet_CRequest *self, void *closure)
{
    const char *host = get_environ_str(self->environ, "HTTP_HOST", NULL);
    if (host) return PyUnicode_FromString(host);
    /* Fallback to SERVER_NAME:SERVER_PORT */
    const char *name = get_environ_str(self->environ, "SERVER_NAME", "localhost");
    const char *port = get_environ_str(self->environ, "SERVER_PORT", "80");
    if (strcmp(port, "80") == 0 || strcmp(port, "443") == 0)
        return PyUnicode_FromString(name);
    return PyUnicode_FromFormat("%s:%s", name, port);
}

static PyObject *
CRequest_get_url(Cruet_CRequest *self, void *closure)
{
    PyObject *scheme_obj = PyDict_GetItemString(self->environ, "wsgi.url_scheme");
    const char *scheme = (scheme_obj && PyUnicode_Check(scheme_obj))
                         ? PyUnicode_AsUTF8(scheme_obj) : "http";

    PyObject *host_obj = CRequest_get_host(self, NULL);
    if (!host_obj) return NULL;
    const char *host = PyUnicode_AsUTF8(host_obj);

    PyObject *path_obj = CRequest_get_path(self, NULL);
    if (!path_obj) { Py_DECREF(host_obj); return NULL; }
    const char *path = PyUnicode_AsUTF8(path_obj);

    const char *qs = get_environ_str(self->environ, "QUERY_STRING", "");
    PyObject *result;
    if (qs[0])
        result = PyUnicode_FromFormat("%s://%s%s?%s", scheme, host, path, qs);
    else
        result = PyUnicode_FromFormat("%s://%s%s", scheme, host, path);

    Py_DECREF(host_obj);
    Py_DECREF(path_obj);
    return result;
}

static PyObject *
CRequest_get_base_url(Cruet_CRequest *self, void *closure)
{
    PyObject *scheme_obj = PyDict_GetItemString(self->environ, "wsgi.url_scheme");
    const char *scheme = (scheme_obj && PyUnicode_Check(scheme_obj))
                         ? PyUnicode_AsUTF8(scheme_obj) : "http";

    PyObject *host_obj = CRequest_get_host(self, NULL);
    if (!host_obj) return NULL;
    const char *host = PyUnicode_AsUTF8(host_obj);

    PyObject *path_obj = CRequest_get_path(self, NULL);
    if (!path_obj) { Py_DECREF(host_obj); return NULL; }
    const char *path = PyUnicode_AsUTF8(path_obj);

    PyObject *result = PyUnicode_FromFormat("%s://%s%s", scheme, host, path);
    Py_DECREF(host_obj);
    Py_DECREF(path_obj);
    return result;
}

static PyObject *
CRequest_get_is_json(Cruet_CRequest *self, void *closure)
{
    const char *ct = get_environ_str(self->environ, "CONTENT_TYPE", "");
    if (!ct[0]) Py_RETURN_FALSE;

    /* Check for "application/json" or "+json" */
    const char *json_ct = "application/json";
    size_t json_ct_len = strlen(json_ct);

    /* Case-insensitive prefix match */
    if (strncasecmp(ct, json_ct, json_ct_len) == 0)
        Py_RETURN_TRUE;

    /* Check for +json subtype */
    const char *plus_json = "+json";
    const char *found = strcasestr(ct, plus_json);
    if (found) Py_RETURN_TRUE;

    Py_RETURN_FALSE;
}

/* Helper: wrap a plain dict in cruet.wrappers.MultiDict */
static PyObject *
wrap_in_multidict(PyObject *plain_dict)
{
    PyObject *mod = PyImport_ImportModule("cruet.wrappers");
    if (!mod) return NULL;
    PyObject *cls = PyObject_GetAttrString(mod, "MultiDict");
    Py_DECREF(mod);
    if (!cls) return NULL;
    PyObject *result = PyObject_CallOneArg(cls, plain_dict);
    Py_DECREF(cls);
    return result;
}

/* Lazy property: args (parsed query string) */
static PyObject *
CRequest_get_args(Cruet_CRequest *self, void *closure)
{
    if (self->cached_args) {
        Py_INCREF(self->cached_args);
        return self->cached_args;
    }

    const char *qs = get_environ_str(self->environ, "QUERY_STRING", "");
    Py_ssize_t qs_len = (Py_ssize_t)strlen(qs);

    PyObject *parse_args = Py_BuildValue("(s#)", qs, qs_len);
    if (!parse_args) return NULL;

    PyObject *raw = cruet_parse_qs(NULL, parse_args);
    Py_DECREF(parse_args);
    if (!raw) return NULL;

    self->cached_args = wrap_in_multidict(raw);
    Py_DECREF(raw);
    if (!self->cached_args) return NULL;

    Py_INCREF(self->cached_args);
    return self->cached_args;
}

/* Lazy property: headers */
static PyObject *
CRequest_get_headers(Cruet_CRequest *self, void *closure)
{
    if (self->cached_headers) {
        Py_INCREF(self->cached_headers);
        return self->cached_headers;
    }

    /* Build CHeaders from environ HTTP_* keys */
    PyObject *items = PyList_New(0);
    if (!items) return NULL;

    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(self->environ, &pos, &key, &value)) {
        const char *key_str = PyUnicode_AsUTF8(key);
        if (!key_str) continue;

        const char *header_name = NULL;
        if (strncmp(key_str, "HTTP_", 5) == 0) {
            /* Convert HTTP_FOO_BAR -> Foo-Bar */
            header_name = key_str + 5;
        } else if (strcmp(key_str, "CONTENT_TYPE") == 0) {
            PyObject *tuple = PyTuple_Pack(2,
                PyUnicode_FromString("Content-Type"), value);
            PyList_Append(items, tuple);
            Py_DECREF(tuple);
            continue;
        } else if (strcmp(key_str, "CONTENT_LENGTH") == 0) {
            PyObject *tuple = PyTuple_Pack(2,
                PyUnicode_FromString("Content-Length"), value);
            PyList_Append(items, tuple);
            Py_DECREF(tuple);
            continue;
        } else {
            continue;
        }

        /* Convert UPPER_UNDERSCORE to Title-Case */
        size_t hlen = strlen(header_name);
        char *formatted = malloc(hlen + 1);
        if (!formatted) { Py_DECREF(items); return PyErr_NoMemory(); }
        int capitalize = 1;
        for (size_t i = 0; i < hlen; i++) {
            if (header_name[i] == '_') {
                formatted[i] = '-';
                capitalize = 1;
            } else if (capitalize) {
                formatted[i] = toupper((unsigned char)header_name[i]);
                capitalize = 0;
            } else {
                formatted[i] = tolower((unsigned char)header_name[i]);
            }
        }
        formatted[hlen] = '\0';

        PyObject *name_obj = PyUnicode_FromString(formatted);
        free(formatted);
        PyObject *tuple = PyTuple_Pack(2, name_obj, value);
        Py_DECREF(name_obj);
        PyList_Append(items, tuple);
        Py_DECREF(tuple);
    }

    /* Create CHeaders */
    PyObject *args = PyTuple_Pack(1, items);
    Py_DECREF(items);
    if (!args) return NULL;

    self->cached_headers = PyObject_Call((PyObject *)&Cruet_CHeadersType, args, NULL);
    Py_DECREF(args);
    if (!self->cached_headers) return NULL;

    Py_INCREF(self->cached_headers);
    return self->cached_headers;
}

/* Lazy property: data (raw request body bytes) */
static PyObject *
CRequest_get_data(Cruet_CRequest *self, void *closure)
{
    if (self->cached_data) {
        Py_INCREF(self->cached_data);
        return self->cached_data;
    }

    PyObject *wsgi_input = PyDict_GetItemString(self->environ, "wsgi.input");
    if (!wsgi_input) {
        self->cached_data = PyBytes_FromStringAndSize("", 0);
        Py_INCREF(self->cached_data);
        return self->cached_data;
    }

    /* Check Content-Length */
    PyObject *cl_obj = PyDict_GetItemString(self->environ, "CONTENT_LENGTH");
    if (cl_obj && PyUnicode_Check(cl_obj)) {
        const char *cl_str = PyUnicode_AsUTF8(cl_obj);
        long cl = strtol(cl_str, NULL, 10);
        if (cl > 0) {
            self->cached_data = PyObject_CallMethod(wsgi_input, "read", "l", cl);
        } else {
            self->cached_data = PyBytes_FromStringAndSize("", 0);
        }
    } else {
        self->cached_data = PyObject_CallMethod(wsgi_input, "read", NULL);
    }

    if (!self->cached_data)
        self->cached_data = PyBytes_FromStringAndSize("", 0);

    Py_INCREF(self->cached_data);
    return self->cached_data;
}

/* Lazy property: json (parsed JSON body) */
static PyObject *
CRequest_get_json(Cruet_CRequest *self, void *closure)
{
    if (self->json_loaded) {
        if (self->cached_json) {
            Py_INCREF(self->cached_json);
            return self->cached_json;
        }
        Py_RETURN_NONE;
    }

    self->json_loaded = 1;

    /* Check Content-Type */
    const char *ct = get_environ_str(self->environ, "CONTENT_TYPE", "");
    if (ct[0] && strncasecmp(ct, "application/json", 16) != 0 &&
        !strcasestr(ct, "+json")) {
        Py_RETURN_NONE;
    }

    /* Get body */
    PyObject *data = CRequest_get_data(self, NULL);
    if (!data) return NULL;

    /* Check if empty */
    Py_ssize_t data_len = PyBytes_GET_SIZE(data);
    Py_DECREF(data);
    if (data_len == 0) {
        Py_RETURN_NONE;
    }

    /* Parse JSON using json module */
    PyObject *json_mod = PyImport_ImportModule("json");
    if (!json_mod) return NULL;

    /* Get the cached_data bytes, decode to str for json.loads */
    PyObject *str_data = PyUnicode_FromEncodedObject(self->cached_data, "utf-8", "strict");
    if (!str_data) { Py_DECREF(json_mod); return NULL; }

    self->cached_json = PyObject_CallMethod(json_mod, "loads", "O", str_data);
    Py_DECREF(json_mod);
    Py_DECREF(str_data);

    if (!self->cached_json) return NULL; /* propagate ValueError/JSONDecodeError */

    Py_INCREF(self->cached_json);
    return self->cached_json;
}

/* Lazy property: form (parsed urlencoded form body) */
static PyObject *
CRequest_get_form(Cruet_CRequest *self, void *closure)
{
    if (self->cached_form) {
        Py_INCREF(self->cached_form);
        return self->cached_form;
    }

    const char *ct = get_environ_str(self->environ, "CONTENT_TYPE", "");
    if (strncasecmp(ct, "application/x-www-form-urlencoded", 33) != 0) {
        self->cached_form = PyDict_New();
        Py_INCREF(self->cached_form);
        return self->cached_form;
    }

    /* Get body */
    PyObject *data = CRequest_get_data(self, NULL);
    if (!data) return NULL;

    char *body_str;
    Py_ssize_t body_len;
    PyBytes_AsStringAndSize(self->cached_data, &body_str, &body_len);

    PyObject *parse_args = Py_BuildValue("(s#)", body_str, body_len);
    Py_DECREF(data);
    if (!parse_args) return NULL;

    PyObject *raw = cruet_parse_qs(NULL, parse_args);
    Py_DECREF(parse_args);
    if (!raw) return NULL;

    self->cached_form = wrap_in_multidict(raw);
    Py_DECREF(raw);
    if (!self->cached_form) return NULL;

    Py_INCREF(self->cached_form);
    return self->cached_form;
}

/* Lazy property: cookies (parsed from Cookie header) */
static PyObject *
CRequest_get_cookies(Cruet_CRequest *self, void *closure)
{
    if (self->cached_cookies) {
        Py_INCREF(self->cached_cookies);
        return self->cached_cookies;
    }

    const char *cookie_str = get_environ_str(self->environ, "HTTP_COOKIE", "");
    Py_ssize_t cookie_len = (Py_ssize_t)strlen(cookie_str);

    PyObject *parse_args = Py_BuildValue("(s#)", cookie_str, cookie_len);
    if (!parse_args) return NULL;

    PyObject *raw = cruet_parse_cookies(NULL, parse_args);
    Py_DECREF(parse_args);
    if (!raw) return NULL;

    self->cached_cookies = raw; /* plain dict, matches Flask's request.cookies */
    Py_INCREF(self->cached_cookies);
    return self->cached_cookies;
}

/* Lazy property: files (parsed from multipart/form-data body) */
static PyObject *
CRequest_get_files(Cruet_CRequest *self, void *closure)
{
    if (self->cached_files) {
        Py_INCREF(self->cached_files);
        return self->cached_files;
    }

    const char *ct = get_environ_str(self->environ, "CONTENT_TYPE", "");
    if (strncasecmp(ct, "multipart/form-data", 19) != 0) {
        self->cached_files = PyDict_New();
        Py_INCREF(self->cached_files);
        return self->cached_files;
    }

    /* Extract boundary from Content-Type */
    const char *bp = strcasestr(ct, "boundary=");
    if (!bp) {
        self->cached_files = PyDict_New();
        Py_INCREF(self->cached_files);
        return self->cached_files;
    }
    const char *boundary = bp + 9;
    /* Strip quotes if present */
    size_t blen = strlen(boundary);
    if (blen >= 2 && boundary[0] == '"' && boundary[blen - 1] == '"') {
        boundary++;
        blen -= 2;
    }

    /* Get body data */
    PyObject *data = CRequest_get_data(self, NULL);
    if (!data) return NULL;

    char *body_str;
    Py_ssize_t body_len;
    PyBytes_AsStringAndSize(self->cached_data, &body_str, &body_len);

    PyObject *parse_args = Py_BuildValue("(y#s#)", body_str, body_len,
                                          boundary, (Py_ssize_t)blen);
    Py_DECREF(data);
    if (!parse_args) return NULL;

    PyObject *result = cruet_parse_multipart(NULL, parse_args);
    Py_DECREF(parse_args);
    if (!result) return NULL;

    /* result is {"fields": dict, "files": dict} — we want just files */
    PyObject *files_dict = PyDict_GetItemString(result, "files"); /* borrowed */
    if (!files_dict) {
        Py_DECREF(result);
        self->cached_files = PyDict_New();
        Py_INCREF(self->cached_files);
        return self->cached_files;
    }

    Py_INCREF(files_dict);
    Py_DECREF(result);
    self->cached_files = files_dict;
    Py_INCREF(self->cached_files);
    return self->cached_files;
}

/* Property: remote_addr */
static PyObject *
CRequest_get_remote_addr(Cruet_CRequest *self, void *closure)
{
    const char *addr = get_environ_str(self->environ, "REMOTE_ADDR", "");
    return PyUnicode_FromString(addr);
}

/* Property: environ (the raw WSGI environ dict) */
static PyObject *
CRequest_get_environ(Cruet_CRequest *self, void *closure)
{
    Py_INCREF(self->environ);
    return self->environ;
}

/* Property: content_length */
static PyObject *
CRequest_get_content_length(Cruet_CRequest *self, void *closure)
{
    PyObject *cl_obj = PyDict_GetItemString(self->environ, "CONTENT_LENGTH");
    if (cl_obj && PyUnicode_Check(cl_obj)) {
        const char *cl_str = PyUnicode_AsUTF8(cl_obj);
        if (cl_str && cl_str[0]) {
            char *end;
            long val = strtol(cl_str, &end, 10);
            if (end != cl_str && val >= 0)
                return PyLong_FromLong(val);
        }
    }
    Py_RETURN_NONE;
}

/* Property: mimetype (Content-Type without parameters) */
static PyObject *
CRequest_get_mimetype(Cruet_CRequest *self, void *closure)
{
    const char *ct = get_environ_str(self->environ, "CONTENT_TYPE", "");
    if (!ct[0])
        return PyUnicode_FromString("");

    /* Find the semicolon that starts parameters */
    const char *semi = strchr(ct, ';');
    if (semi) {
        /* Trim trailing whitespace before semicolon */
        const char *end = semi;
        while (end > ct && (end[-1] == ' ' || end[-1] == '\t'))
            end--;
        return PyUnicode_FromStringAndSize(ct, end - ct);
    }
    return PyUnicode_FromString(ct);
}

/* Property: full_path (path + query string) */
static PyObject *
CRequest_get_full_path(Cruet_CRequest *self, void *closure)
{
    const char *path = get_environ_str(self->environ, "PATH_INFO", "/");
    const char *qs = get_environ_str(self->environ, "QUERY_STRING", "");
    if (qs[0])
        return PyUnicode_FromFormat("%s?%s", path, qs);
    return PyUnicode_FromFormat("%s?", path);
}

/* Property: scheme */
static PyObject *
CRequest_get_scheme(Cruet_CRequest *self, void *closure)
{
    PyObject *scheme_obj = PyDict_GetItemString(self->environ, "wsgi.url_scheme");
    if (scheme_obj && PyUnicode_Check(scheme_obj)) {
        Py_INCREF(scheme_obj);
        return scheme_obj;
    }
    return PyUnicode_FromString("http");
}

/* Property: is_secure */
static PyObject *
CRequest_get_is_secure(Cruet_CRequest *self, void *closure)
{
    PyObject *scheme_obj = PyDict_GetItemString(self->environ, "wsgi.url_scheme");
    if (scheme_obj && PyUnicode_Check(scheme_obj)) {
        const char *scheme = PyUnicode_AsUTF8(scheme_obj);
        if (scheme && strcasecmp(scheme, "https") == 0)
            Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

/* Property: referrer */
static PyObject *
CRequest_get_referrer(Cruet_CRequest *self, void *closure)
{
    PyObject *val = PyDict_GetItemString(self->environ, "HTTP_REFERER");
    if (val && PyUnicode_Check(val)) {
        Py_INCREF(val);
        return val;
    }
    Py_RETURN_NONE;
}

/* Property: user_agent (string, not parsed) */
static PyObject *
CRequest_get_user_agent(Cruet_CRequest *self, void *closure)
{
    const char *ua = get_environ_str(self->environ, "HTTP_USER_AGENT", "");
    return PyUnicode_FromString(ua);
}

/* Property: access_route (list of IPs from X-Forwarded-For + REMOTE_ADDR) */
static PyObject *
CRequest_get_access_route(Cruet_CRequest *self, void *closure)
{
    PyObject *result = PyList_New(0);
    if (!result) return NULL;

    const char *xff = get_environ_str(self->environ, "HTTP_X_FORWARDED_FOR", "");
    if (xff[0]) {
        /* Split by comma, strip whitespace */
        const char *p = xff;
        while (*p) {
            while (*p == ' ' || *p == ',') p++;
            if (!*p) break;
            const char *start = p;
            while (*p && *p != ',') p++;
            const char *end = p;
            while (end > start && end[-1] == ' ') end--;
            PyObject *s = PyUnicode_FromStringAndSize(start, end - start);
            if (!s) { Py_DECREF(result); return NULL; }
            PyList_Append(result, s);
            Py_DECREF(s);
        }
    }

    /* Always append REMOTE_ADDR as the last entry */
    const char *addr = get_environ_str(self->environ, "REMOTE_ADDR", "");
    if (addr[0]) {
        PyObject *s = PyUnicode_FromString(addr);
        if (!s) { Py_DECREF(result); return NULL; }
        PyList_Append(result, s);
        Py_DECREF(s);
    }

    return result;
}

/* Property: values (combined args + form) */
static PyObject *
CRequest_get_values(Cruet_CRequest *self, void *closure)
{
    /* Get args and form */
    PyObject *args = CRequest_get_args(self, NULL);
    if (!args) return NULL;
    PyObject *form = CRequest_get_form(self, NULL);
    if (!form) { Py_DECREF(args); return NULL; }

    /* Build a new MultiDict: start with form, update with args */
    PyObject *mod = PyImport_ImportModule("cruet.wrappers");
    if (!mod) { Py_DECREF(args); Py_DECREF(form); return NULL; }
    PyObject *cls = PyObject_GetAttrString(mod, "MultiDict");
    Py_DECREF(mod);
    if (!cls) { Py_DECREF(args); Py_DECREF(form); return NULL; }

    /* Create from args first, then merge form (form values take lower priority in Flask) */
    PyObject *combined = PyObject_CallOneArg(cls, args);
    Py_DECREF(cls);
    if (!combined) { Py_DECREF(args); Py_DECREF(form); return NULL; }

    /* Update with form data */
    PyObject *update_result = PyObject_CallMethod(combined, "update", "O", form);
    Py_DECREF(args);
    Py_DECREF(form);
    Py_XDECREF(update_result);

    return combined;
}

/* Property: endpoint (get/set) */
static PyObject *
CRequest_get_endpoint(Cruet_CRequest *self, void *closure)
{
    Py_INCREF(self->endpoint);
    return self->endpoint;
}

static int
CRequest_set_endpoint(Cruet_CRequest *self, PyObject *value, void *closure)
{
    PyObject *old = self->endpoint;
    if (value == NULL) value = Py_None;
    Py_INCREF(value);
    self->endpoint = value;
    Py_DECREF(old);
    return 0;
}

/* Property: view_args (get/set) */
static PyObject *
CRequest_get_view_args(Cruet_CRequest *self, void *closure)
{
    Py_INCREF(self->view_args);
    return self->view_args;
}

static int
CRequest_set_view_args(Cruet_CRequest *self, PyObject *value, void *closure)
{
    PyObject *old = self->view_args;
    if (value == NULL) value = Py_None;
    Py_INCREF(value);
    self->view_args = value;
    Py_DECREF(old);
    return 0;
}

/* Property: blueprint (get/set) */
static PyObject *
CRequest_get_blueprint(Cruet_CRequest *self, void *closure)
{
    Py_INCREF(self->blueprint);
    return self->blueprint;
}

static int
CRequest_set_blueprint(Cruet_CRequest *self, PyObject *value, void *closure)
{
    PyObject *old = self->blueprint;
    if (value == NULL) value = Py_None;
    Py_INCREF(value);
    self->blueprint = value;
    Py_DECREF(old);
    return 0;
}

/* Method: get_json(force=False, silent=False, cache=True) */
static PyObject *
CRequest_method_get_json(Cruet_CRequest *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"force", "silent", "cache", NULL};
    int force = 0, silent = 0, cache = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|ppp", kwlist,
                                      &force, &silent, &cache))
        return NULL;

    /* If force, skip content-type check */
    if (force || (!self->json_loaded)) {
        if (force) {
            /* Force: parse regardless of content-type */
            PyObject *data = CRequest_get_data(self, NULL);
            if (!data) {
                if (silent) { PyErr_Clear(); Py_RETURN_NONE; }
                return NULL;
            }

            Py_ssize_t data_len = PyBytes_GET_SIZE(data);
            Py_DECREF(data);
            if (data_len == 0) Py_RETURN_NONE;

            PyObject *json_mod = PyImport_ImportModule("json");
            if (!json_mod) {
                if (silent) { PyErr_Clear(); Py_RETURN_NONE; }
                return NULL;
            }

            PyObject *str_data = PyUnicode_FromEncodedObject(
                self->cached_data, "utf-8", "strict");
            if (!str_data) {
                Py_DECREF(json_mod);
                if (silent) { PyErr_Clear(); Py_RETURN_NONE; }
                return NULL;
            }

            PyObject *result = PyObject_CallMethod(json_mod, "loads", "O", str_data);
            Py_DECREF(json_mod);
            Py_DECREF(str_data);

            if (!result) {
                if (silent) { PyErr_Clear(); Py_RETURN_NONE; }
                return NULL;
            }

            if (cache) {
                Py_XDECREF(self->cached_json);
                self->cached_json = result;
                self->json_loaded = 1;
                Py_INCREF(result);
            }
            return result;
        }

        /* Not force: use the standard json property */
        PyObject *result = CRequest_get_json(self, NULL);
        if (!result) {
            if (silent) { PyErr_Clear(); Py_RETURN_NONE; }
            return NULL;
        }
        return result;
    }

    /* Already loaded */
    if (self->cached_json) {
        Py_INCREF(self->cached_json);
        return self->cached_json;
    }
    Py_RETURN_NONE;
}

/* Method: get_data(cache=True, as_text=False) */
static PyObject *
CRequest_method_get_data(Cruet_CRequest *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"cache", "as_text", NULL};
    int cache = 1, as_text = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|pp", kwlist,
                                      &cache, &as_text))
        return NULL;

    PyObject *data = CRequest_get_data(self, NULL);
    if (!data) return NULL;

    if (as_text) {
        PyObject *text = PyUnicode_FromEncodedObject(data, "utf-8", "replace");
        Py_DECREF(data);
        return text;
    }

    return data;
}

static PyMethodDef CRequest_methods[] = {
    {"get_json", (PyCFunction)CRequest_method_get_json,
     METH_VARARGS | METH_KEYWORDS,
     "Parse body as JSON. Args: force=False, silent=False, cache=True"},
    {"get_data", (PyCFunction)CRequest_method_get_data,
     METH_VARARGS | METH_KEYWORDS,
     "Get raw request data. Args: cache=True, as_text=False"},
    {NULL}
};

static PyGetSetDef CRequest_getset[] = {
    {"method", (getter)CRequest_get_method, NULL, "HTTP method", NULL},
    {"path", (getter)CRequest_get_path, NULL, "Request path", NULL},
    {"query_string", (getter)CRequest_get_query_string, NULL, "Query string", NULL},
    {"content_type", (getter)CRequest_get_content_type, NULL, "Content-Type header", NULL},
    {"host", (getter)CRequest_get_host, NULL, "Request host", NULL},
    {"url", (getter)CRequest_get_url, NULL, "Full request URL", NULL},
    {"base_url", (getter)CRequest_get_base_url, NULL, "Base URL (without query string)", NULL},
    {"is_json", (getter)CRequest_get_is_json, NULL, "Whether request is JSON", NULL},
    {"args", (getter)CRequest_get_args, NULL, "Parsed query string args", NULL},
    {"headers", (getter)CRequest_get_headers, NULL, "Request headers", NULL},
    {"data", (getter)CRequest_get_data, NULL, "Raw request body", NULL},
    {"json", (getter)CRequest_get_json, NULL, "Parsed JSON body", NULL},
    {"form", (getter)CRequest_get_form, NULL, "Parsed form data", NULL},
    {"cookies", (getter)CRequest_get_cookies, NULL, "Parsed cookies dict", NULL},
    {"files", (getter)CRequest_get_files, NULL, "Uploaded files from multipart/form-data", NULL},
    {"remote_addr", (getter)CRequest_get_remote_addr, NULL, "Client IP address", NULL},
    {"environ", (getter)CRequest_get_environ, NULL, "Raw WSGI environ dict", NULL},
    {"content_length", (getter)CRequest_get_content_length, NULL, "Content-Length as int or None", NULL},
    {"mimetype", (getter)CRequest_get_mimetype, NULL, "Content-Type without parameters", NULL},
    {"full_path", (getter)CRequest_get_full_path, NULL, "Path with query string", NULL},
    {"scheme", (getter)CRequest_get_scheme, NULL, "URL scheme (http/https)", NULL},
    {"is_secure", (getter)CRequest_get_is_secure, NULL, "True if HTTPS", NULL},
    {"referrer", (getter)CRequest_get_referrer, NULL, "Referer header or None", NULL},
    {"user_agent", (getter)CRequest_get_user_agent, NULL, "User-Agent string", NULL},
    {"access_route", (getter)CRequest_get_access_route, NULL, "List of IPs from X-Forwarded-For", NULL},
    {"values", (getter)CRequest_get_values, NULL, "Combined args + form", NULL},
    {"endpoint", (getter)CRequest_get_endpoint, (setter)CRequest_set_endpoint, "Matched endpoint name", NULL},
    {"view_args", (getter)CRequest_get_view_args, (setter)CRequest_set_view_args, "Matched URL parameters", NULL},
    {"blueprint", (getter)CRequest_get_blueprint, (setter)CRequest_set_blueprint, "Matched blueprint name", NULL},
    {NULL}
};

PyTypeObject Cruet_CRequestType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "cruet._cruet.CRequest",
    .tp_basicsize = sizeof(Cruet_CRequest),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)CRequest_init,
    .tp_dealloc = (destructor)CRequest_dealloc,
    .tp_getset = CRequest_getset,
    .tp_methods = CRequest_methods,
};
