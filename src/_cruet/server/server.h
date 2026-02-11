#ifndef CRUET_SERVER_H
#define CRUET_SERVER_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* HTTP parser: parse raw request bytes into a Python dict */
PyObject *cruet_parse_http_request(PyObject *self, PyObject *args);

/* WSGI helpers: environ construction and response formatting (wsgi.c) */
PyObject *Cruet_build_environ(PyObject *parsed, PyObject *client_addr,
                               PyObject *server_addr);
PyObject *Cruet_format_response(PyObject *status, PyObject *headers,
                                 PyObject *body_parts);
extern PyMethodDef cruet_wsgi_methods[];

#ifdef CRUET_HAS_LIBEVENT

#include <event2/event.h>
#include <event2/listener.h>
#include <event2/bufferevent.h>
#include <event2/buffer.h>
#include <sys/un.h>
#include <limits.h>
#include "../util/buffer.h"

typedef enum { CRUET_SOCK_TCP, CRUET_SOCK_UNIX } Cruet_SocketType;

typedef struct {
    Cruet_SocketType socket_type;
    char host[256];
    int port;
    char unix_path[PATH_MAX];
    mode_t unix_mode;           /* default 0666 */
    int backlog;                /* default 1024 */
    double read_timeout;        /* seconds, default 30 */
    double write_timeout;       /* seconds, default 30 */
    size_t max_request_size;    /* bytes, default 1MB */
} Cruet_ServerConfig;

typedef enum {
    CONN_READING, CONN_PROCESSING, CONN_WRITING, CONN_CLOSING
} Cruet_ConnState;

/* Forward declarations */
struct Cruet_Worker;

typedef struct {
    Cruet_ConnState state;
    struct bufferevent *bev;
    struct event_base *base;
    Cruet_Buffer read_buf;
    char *response_data;        /* malloc'd, freed after write */
    size_t response_len;
    int keep_alive;
    PyObject *app;              /* borrowed ref */
    Cruet_ServerConfig *config;
    struct Cruet_Worker *worker;
    char remote_addr[64];
    int remote_port;
} Cruet_Connection;

typedef struct Cruet_Worker {
    struct event_base *base;
    struct evconnlistener *listener;
    struct event *sig_int;
    struct event *sig_term;
    PyObject *app;              /* borrowed ref */
    Cruet_ServerConfig *config;
    int active_connections;
} Cruet_Worker;

/* Python-callable event loop function */
PyObject *cruet_run_event_loop(PyObject *self, PyObject *args, PyObject *kw);

#endif /* CRUET_HAS_LIBEVENT */

#endif /* CRUET_SERVER_H */
