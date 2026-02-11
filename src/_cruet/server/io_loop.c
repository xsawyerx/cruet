/*
 * io_loop.c — libevent2-based async WSGI server event loop.
 *
 * Entirely inside #ifdef CRUET_HAS_LIBEVENT so the file compiles to
 * nothing when libevent is not available.
 */

#include "server.h"

#ifdef CRUET_HAS_LIBEVENT

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/stat.h>
#include <errno.h>
#include <signal.h>

/* ------------------------------------------------------------------ */
/* Forward declarations                                                */
/* ------------------------------------------------------------------ */
static void accept_conn_cb(struct evconnlistener *listener, evutil_socket_t fd,
                           struct sockaddr *addr, int socklen, void *ctx);
static void read_cb(struct bufferevent *bev, void *ctx);
static void write_cb(struct bufferevent *bev, void *ctx);
static void event_cb(struct bufferevent *bev, short what, void *ctx);
static void signal_cb(evutil_socket_t sig, short events, void *ctx);
static void conn_close(Cruet_Connection *conn);
static void send_error_response(Cruet_Connection *conn, int code,
                                const char *reason);
static int  process_request(Cruet_Connection *conn, PyObject *parsed);

/* ------------------------------------------------------------------ */
/* StartResponseData — stores (status, headers) from start_response()  */
/* ------------------------------------------------------------------ */
typedef struct {
    PyObject *status;       /* str: "200 OK" */
    PyObject *headers;      /* list of (name, value) tuples */
} StartResponseData;

static PyObject *
c_start_response(PyObject *capsule, PyObject *args)
{
    StartResponseData *srd = (StartResponseData *)PyCapsule_GetPointer(
        capsule, "cruet.start_response_data");
    if (!srd)
        return NULL;

    PyObject *status = NULL;
    PyObject *headers = NULL;
    PyObject *exc_info = NULL;

    if (!PyArg_ParseTuple(args, "OO|O", &status, &headers, &exc_info))
        return NULL;

    Py_XDECREF(srd->status);
    Py_XDECREF(srd->headers);
    Py_INCREF(status);
    Py_INCREF(headers);
    srd->status = status;
    srd->headers = headers;

    Py_RETURN_NONE;
}

static PyMethodDef c_start_response_def = {
    "start_response", c_start_response, METH_VARARGS,
    "WSGI start_response callable."
};

static void
start_response_data_destructor(PyObject *capsule)
{
    StartResponseData *srd = (StartResponseData *)PyCapsule_GetPointer(
        capsule, "cruet.start_response_data");
    if (srd) {
        Py_XDECREF(srd->status);
        Py_XDECREF(srd->headers);
        free(srd);
    }
}

/* ------------------------------------------------------------------ */
/* accept_conn_cb — new client connected                               */
/* ------------------------------------------------------------------ */
static void
accept_conn_cb(struct evconnlistener *listener, evutil_socket_t fd,
               struct sockaddr *addr, int socklen, void *ctx)
{
    Cruet_Worker *worker = (Cruet_Worker *)ctx;
    struct event_base *base = worker->base;

    Cruet_Connection *conn = calloc(1, sizeof(Cruet_Connection));
    if (!conn) {
        close(fd);
        return;
    }

    conn->state = CONN_READING;
    conn->base = base;
    conn->app = worker->app;
    conn->config = worker->config;
    conn->worker = worker;
    conn->keep_alive = 1;
    cruet_buf_init(&conn->read_buf);

    /* Extract client address */
    if (addr->sa_family == AF_INET) {
        struct sockaddr_in *sin = (struct sockaddr_in *)addr;
        inet_ntop(AF_INET, &sin->sin_addr, conn->remote_addr,
                  sizeof(conn->remote_addr));
        conn->remote_port = ntohs(sin->sin_port);
    } else if (addr->sa_family == AF_UNIX) {
        strncpy(conn->remote_addr, "unix", sizeof(conn->remote_addr) - 1);
        conn->remote_port = 0;
    } else {
        strncpy(conn->remote_addr, "unknown", sizeof(conn->remote_addr) - 1);
        conn->remote_port = 0;
    }

    struct bufferevent *bev = bufferevent_socket_new(
        base, fd, BEV_OPT_CLOSE_ON_FREE);
    if (!bev) {
        cruet_buf_free(&conn->read_buf);
        free(conn);
        close(fd);
        return;
    }
    conn->bev = bev;

    bufferevent_setcb(bev, read_cb, write_cb, event_cb, conn);

    /* Set timeouts */
    struct timeval tv_read, tv_write;
    tv_read.tv_sec = (long)conn->config->read_timeout;
    tv_read.tv_usec = (long)((conn->config->read_timeout - tv_read.tv_sec) * 1e6);
    tv_write.tv_sec = (long)conn->config->write_timeout;
    tv_write.tv_usec = (long)((conn->config->write_timeout - tv_write.tv_sec) * 1e6);
    bufferevent_set_timeouts(bev, &tv_read, &tv_write);

    bufferevent_enable(bev, EV_READ);
    worker->active_connections++;
}

/* ------------------------------------------------------------------ */
/* read_cb — data available from client                                */
/* ------------------------------------------------------------------ */
static void
read_cb(struct bufferevent *bev, void *ctx)
{
    Cruet_Connection *conn = (Cruet_Connection *)ctx;

    if (conn->state != CONN_READING)
        return;

    struct evbuffer *input = bufferevent_get_input(bev);
    size_t avail = evbuffer_get_length(input);
    if (avail == 0)
        return;

    /* Drain into our read buffer */
    if (cruet_buf_grow(&conn->read_buf, avail) < 0) {
        send_error_response(conn, 500, "Internal Server Error");
        return;
    }
    evbuffer_remove(input, conn->read_buf.data + conn->read_buf.len, avail);
    conn->read_buf.len += avail;

    /* Check max_request_size */
    if (conn->read_buf.len > conn->config->max_request_size) {
        send_error_response(conn, 413, "Request Entity Too Large");
        return;
    }

    /* Parse HTTP request — need the GIL */
    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *data_bytes = PyBytes_FromStringAndSize(
        conn->read_buf.data, (Py_ssize_t)conn->read_buf.len);
    if (!data_bytes) {
        PyGILState_Release(gstate);
        send_error_response(conn, 500, "Internal Server Error");
        return;
    }

    PyObject *parse_args = PyTuple_Pack(1, data_bytes);
    Py_DECREF(data_bytes);
    if (!parse_args) {
        PyGILState_Release(gstate);
        send_error_response(conn, 500, "Internal Server Error");
        return;
    }

    PyObject *parsed = cruet_parse_http_request(NULL, parse_args);
    Py_DECREF(parse_args);

    if (!parsed) {
        /* Python exception in parser */
        PyErr_Clear();
        PyGILState_Release(gstate);
        send_error_response(conn, 400, "Bad Request");
        return;
    }

    if (parsed == Py_None) {
        /* Incomplete request, keep reading */
        Py_DECREF(parsed);
        PyGILState_Release(gstate);
        return;
    }

    /* Check if body is complete */
    PyObject *headers_dict = PyDict_GetItemString(parsed, "headers");
    if (headers_dict) {
        PyObject *cl_obj = PyDict_GetItemString(headers_dict, "Content-Length");
        if (!cl_obj) {
            /* Try case-insensitive */
            PyObject *key, *value;
            Py_ssize_t pos = 0;
            while (PyDict_Next(headers_dict, &pos, &key, &value)) {
                const char *k = PyUnicode_AsUTF8(key);
                if (k && strcasecmp(k, "Content-Length") == 0) {
                    cl_obj = value;
                    break;
                }
            }
        }
        if (cl_obj) {
            const char *cl_str = PyUnicode_AsUTF8(cl_obj);
            if (cl_str) {
                long expected_cl = strtol(cl_str, NULL, 10);
                PyObject *body_obj = PyDict_GetItemString(parsed, "body");
                if (expected_cl > 0 && body_obj) {
                    Py_ssize_t body_len = PyBytes_GET_SIZE(body_obj);
                    if (body_len < expected_cl) {
                        /* Body incomplete, keep reading */
                        Py_DECREF(parsed);
                        PyGILState_Release(gstate);
                        return;
                    }
                }
            }
        }
    }

    /* Complete request — disable reading, process it */
    bufferevent_disable(bev, EV_READ);
    conn->state = CONN_PROCESSING;

    /* Check keep_alive from parsed result */
    PyObject *ka = PyDict_GetItemString(parsed, "keep_alive");
    if (ka && ka == Py_False) {
        conn->keep_alive = 0;
    }

    int rc = process_request(conn, parsed);
    Py_DECREF(parsed);
    PyGILState_Release(gstate);

    if (rc < 0) {
        send_error_response(conn, 500, "Internal Server Error");
    }
}

/* ------------------------------------------------------------------ */
/* process_request — GIL is held                                       */
/* ------------------------------------------------------------------ */
static int
process_request(Cruet_Connection *conn, PyObject *parsed)
{
    /* Build environ — direct C call, no Python import needed */
    PyObject *client_addr = Py_BuildValue("(si)", conn->remote_addr,
                                          conn->remote_port);
    if (!client_addr)
        return -1;

    /* Determine server_addr */
    PyObject *server_addr;
    if (conn->config->socket_type == CRUET_SOCK_TCP) {
        server_addr = Py_BuildValue("(si)", conn->config->host,
                                    conn->config->port);
    } else {
        server_addr = Py_BuildValue("(si)", conn->config->unix_path, 0);
    }
    if (!server_addr) {
        Py_DECREF(client_addr);
        return -1;
    }

    PyObject *environ = Cruet_build_environ(parsed, client_addr, server_addr);
    Py_DECREF(client_addr);
    Py_DECREF(server_addr);
    if (!environ) {
        PyErr_Print();
        return -1;
    }

    /* Create start_response callable */
    StartResponseData *srd = calloc(1, sizeof(StartResponseData));
    if (!srd) {
        Py_DECREF(environ);
        return -1;
    }
    srd->status = NULL;
    srd->headers = NULL;

    PyObject *capsule = PyCapsule_New(srd, "cruet.start_response_data",
                                      start_response_data_destructor);
    if (!capsule) {
        free(srd);
        Py_DECREF(environ);
        return -1;
    }

    PyObject *start_resp_func = PyCFunction_New(&c_start_response_def, capsule);
    if (!start_resp_func) {
        Py_DECREF(capsule);
        Py_DECREF(environ);
        return -1;
    }

    /* Call app(environ, start_response) — pure WSGI, no cruet dependency */
    PyObject *body_iter = PyObject_CallFunctionObjArgs(
        conn->app, environ, start_resp_func, NULL);
    Py_DECREF(environ);

    if (!body_iter) {
        PyErr_Print();
        Py_DECREF(start_resp_func);
        Py_DECREF(capsule);
        return -1;
    }

    /* Build response — direct C call */
    PyObject *status = srd->status;
    PyObject *headers = srd->headers;

    if (!status || !headers) {
        /* start_response was never called */
        Py_DECREF(body_iter);
        Py_DECREF(start_resp_func);
        Py_DECREF(capsule);
        return -1;
    }

    PyObject *response_bytes = Cruet_format_response(status, headers,
                                                       body_iter);

    /* Call close() on body_iter if it has one (PEP 3333) */
    if (PyObject_HasAttrString(body_iter, "close")) {
        PyObject *close_result = PyObject_CallMethod(body_iter, "close", NULL);
        Py_XDECREF(close_result);
    }

    Py_DECREF(body_iter);
    Py_DECREF(start_resp_func);
    Py_DECREF(capsule);

    if (!response_bytes) {
        PyErr_Print();
        return -1;
    }

    /* Copy response bytes and write to bufferevent */
    char *resp_data;
    Py_ssize_t resp_len;
    if (PyBytes_AsStringAndSize(response_bytes, &resp_data, &resp_len) < 0) {
        Py_DECREF(response_bytes);
        return -1;
    }

    conn->response_data = malloc((size_t)resp_len);
    if (!conn->response_data) {
        Py_DECREF(response_bytes);
        return -1;
    }
    memcpy(conn->response_data, resp_data, (size_t)resp_len);
    conn->response_len = (size_t)resp_len;
    Py_DECREF(response_bytes);

    /* Queue the response */
    conn->state = CONN_WRITING;
    bufferevent_write(conn->bev, conn->response_data, conn->response_len);

    return 0;
}

/* ------------------------------------------------------------------ */
/* write_cb — output buffer flushed                                    */
/* ------------------------------------------------------------------ */
static void
write_cb(struct bufferevent *bev, void *ctx)
{
    Cruet_Connection *conn = (Cruet_Connection *)ctx;

    if (conn->state != CONN_WRITING)
        return;

    struct evbuffer *output = bufferevent_get_output(bev);
    if (evbuffer_get_length(output) > 0)
        return; /* still flushing */

    /* Response fully sent */
    free(conn->response_data);
    conn->response_data = NULL;
    conn->response_len = 0;

    if (conn->keep_alive) {
        /* Reset for next request */
        conn->state = CONN_READING;
        conn->read_buf.len = 0;
        conn->keep_alive = 1;
        bufferevent_enable(bev, EV_READ);
    } else {
        conn_close(conn);
    }
}

/* ------------------------------------------------------------------ */
/* event_cb — error / timeout / EOF                                    */
/* ------------------------------------------------------------------ */
static void
event_cb(struct bufferevent *bev, short what, void *ctx)
{
    Cruet_Connection *conn = (Cruet_Connection *)ctx;

    if (what & (BEV_EVENT_ERROR | BEV_EVENT_TIMEOUT | BEV_EVENT_EOF)) {
        conn_close(conn);
    }
}

/* ------------------------------------------------------------------ */
/* conn_close — clean up a connection                                  */
/* ------------------------------------------------------------------ */
static void
conn_close(Cruet_Connection *conn)
{
    if (conn->state == CONN_CLOSING)
        return;
    conn->state = CONN_CLOSING;

    cruet_buf_free(&conn->read_buf);
    free(conn->response_data);
    conn->response_data = NULL;

    if (conn->bev) {
        bufferevent_free(conn->bev); /* closes the fd */
        conn->bev = NULL;
    }

    if (conn->worker)
        conn->worker->active_connections--;

    free(conn);
}

/* ------------------------------------------------------------------ */
/* send_error_response — pre-WSGI error (400, 413, 500, etc.)          */
/* ------------------------------------------------------------------ */
static void
send_error_response(Cruet_Connection *conn, int code, const char *reason)
{
    char buf[256];
    int len = snprintf(buf, sizeof(buf),
        "HTTP/1.1 %d %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        code, reason);

    conn->keep_alive = 0;
    conn->state = CONN_WRITING;
    bufferevent_write(conn->bev, buf, (size_t)len);
}

/* ------------------------------------------------------------------ */
/* signal_cb — SIGINT/SIGTERM                                          */
/* ------------------------------------------------------------------ */
static void
signal_cb(evutil_socket_t sig, short events, void *ctx)
{
    Cruet_Worker *worker = (Cruet_Worker *)ctx;
    (void)events;

    /* Stop accepting new connections */
    if (worker->listener) {
        evconnlistener_disable(worker->listener);
    }

    /* Exit the event loop */
    struct timeval five_sec = {5, 0};
    if (worker->active_connections == 0) {
        event_base_loopexit(worker->base, NULL);
    } else {
        event_base_loopexit(worker->base, &five_sec);
    }
}

/* ------------------------------------------------------------------ */
/* cruet_run_event_loop — Python-callable main entry                  */
/* ------------------------------------------------------------------ */
PyObject *
cruet_run_event_loop(PyObject *self, PyObject *args, PyObject *kw)
{
    static char *kwlist[] = {
        "app", "host", "port", "unix_path", "backlog",
        "read_timeout", "write_timeout", "max_request_size",
        "listen_fd", NULL
    };

    PyObject *app = NULL;
    const char *host = "127.0.0.1";
    int port = 8000;
    const char *unix_path = NULL;
    int backlog = 1024;
    double read_timeout = 30.0;
    double write_timeout = 30.0;
    Py_ssize_t max_request_size = 1048576; /* 1 MB */
    int listen_fd = -1;

    if (!PyArg_ParseTupleAndKeywords(args, kw, "O|siziddni", kwlist,
            &app, &host, &port, &unix_path, &backlog,
            &read_timeout, &write_timeout, &max_request_size,
            &listen_fd))
        return NULL;

    if (!PyCallable_Check(app)) {
        PyErr_SetString(PyExc_TypeError, "app must be callable");
        return NULL;
    }

    /* Build config */
    Cruet_ServerConfig config;
    memset(&config, 0, sizeof(config));

    if (unix_path && unix_path[0]) {
        config.socket_type = CRUET_SOCK_UNIX;
        strncpy(config.unix_path, unix_path, PATH_MAX - 1);
        config.unix_mode = 0666;
    } else {
        config.socket_type = CRUET_SOCK_TCP;
        strncpy(config.host, host, sizeof(config.host) - 1);
        config.port = port;
    }
    config.backlog = backlog;
    config.read_timeout = read_timeout;
    config.write_timeout = write_timeout;
    config.max_request_size = (size_t)max_request_size;

    /* Create event base */
    struct event_base *base = event_base_new();
    if (!base) {
        PyErr_SetString(PyExc_RuntimeError, "event_base_new() failed");
        return NULL;
    }

    /* Build worker struct */
    Cruet_Worker worker;
    memset(&worker, 0, sizeof(worker));
    worker.base = base;
    worker.app = app;
    worker.config = &config;

    /* Create listener */
    struct evconnlistener *listener = NULL;

    if (listen_fd >= 0) {
        /* Use pre-created listening socket fd */
        listener = evconnlistener_new(
            base, accept_conn_cb, &worker,
            LEV_OPT_REUSEABLE | LEV_OPT_CLOSE_ON_FREE,
            -1, listen_fd);
    } else if (config.socket_type == CRUET_SOCK_UNIX) {
        /* UNIX socket */
        struct sockaddr_un sun_addr;
        memset(&sun_addr, 0, sizeof(sun_addr));
        sun_addr.sun_family = AF_UNIX;
        strncpy(sun_addr.sun_path, config.unix_path,
                sizeof(sun_addr.sun_path) - 1);

        /* Unlink stale socket file */
        unlink(config.unix_path);

        listener = evconnlistener_new_bind(
            base, accept_conn_cb, &worker,
            LEV_OPT_REUSEABLE | LEV_OPT_CLOSE_ON_FREE,
            config.backlog,
            (struct sockaddr *)&sun_addr, sizeof(sun_addr));

        if (listener) {
            chmod(config.unix_path, config.unix_mode);
        }
    } else {
        /* TCP socket */
        struct sockaddr_in sin_addr;
        memset(&sin_addr, 0, sizeof(sin_addr));
        sin_addr.sin_family = AF_INET;
        sin_addr.sin_port = htons((uint16_t)config.port);
        if (inet_pton(AF_INET, config.host, &sin_addr.sin_addr) <= 0) {
            sin_addr.sin_addr.s_addr = INADDR_ANY;
        }

        listener = evconnlistener_new_bind(
            base, accept_conn_cb, &worker,
            LEV_OPT_REUSEABLE | LEV_OPT_CLOSE_ON_FREE,
            config.backlog,
            (struct sockaddr *)&sin_addr, sizeof(sin_addr));
    }

    if (!listener) {
        event_base_free(base);
        PyErr_SetString(PyExc_OSError, "Failed to create listener");
        return NULL;
    }
    worker.listener = listener;

    /* Register signal handlers */
    struct event *sig_int = evsignal_new(base, SIGINT, signal_cb, &worker);
    struct event *sig_term = evsignal_new(base, SIGTERM, signal_cb, &worker);
    if (sig_int) event_add(sig_int, NULL);
    if (sig_term) event_add(sig_term, NULL);
    worker.sig_int = sig_int;
    worker.sig_term = sig_term;

    /* Run the event loop — release the GIL */
    Py_BEGIN_ALLOW_THREADS
    event_base_dispatch(base);
    Py_END_ALLOW_THREADS

    /* Cleanup */
    if (sig_int) event_free(sig_int);
    if (sig_term) event_free(sig_term);
    evconnlistener_free(listener);
    event_base_free(base);

    /* Unlink UNIX socket */
    if (config.socket_type == CRUET_SOCK_UNIX) {
        unlink(config.unix_path);
    }

    Py_RETURN_NONE;
}

#endif /* CRUET_HAS_LIBEVENT */
