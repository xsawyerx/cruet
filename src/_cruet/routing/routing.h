#ifndef CRUET_ROUTING_H
#define CRUET_ROUTING_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

/* Converter types */
extern PyTypeObject Cruet_StringConverterType;
extern PyTypeObject Cruet_IntConverterType;
extern PyTypeObject Cruet_FloatConverterType;
extern PyTypeObject Cruet_UUIDConverterType;
extern PyTypeObject Cruet_PathConverterType;
extern PyTypeObject Cruet_AnyConverterType;

/* Rule, Map, MapAdapter types */
extern PyTypeObject Cruet_RuleType;
extern PyTypeObject Cruet_MapType;
extern PyTypeObject Cruet_MapAdapterType;

/* ---- Method bitmask constants ---- */
#define CRUET_METHOD_GET     0x01
#define CRUET_METHOD_HEAD    0x02
#define CRUET_METHOD_POST    0x04
#define CRUET_METHOD_PUT     0x08
#define CRUET_METHOD_DELETE  0x10
#define CRUET_METHOD_PATCH   0x20
#define CRUET_METHOD_OPTIONS 0x40
#define CRUET_METHOD_TRACE   0x80

/* Segment types for compiled rules */
typedef enum {
    SEG_STATIC,
    SEG_DYNAMIC_STRING,
    SEG_DYNAMIC_INT,
    SEG_DYNAMIC_FLOAT,
    SEG_DYNAMIC_UUID,
    SEG_DYNAMIC_PATH,
    SEG_DYNAMIC_ANY,
} SegmentType;

typedef struct {
    SegmentType type;
    char *static_text;         /* for SEG_STATIC */
    size_t static_len;
    char *var_name;            /* for dynamic segments */
    /* converter params */
    int int_min, int_max;
    int int_fixed_digits;
    double float_min, float_max;
    int has_int_min, has_int_max;
    int has_float_min, has_float_max;
    int str_minlength, str_maxlength, str_length;
    PyObject *any_items;       /* tuple of allowed values for any converter */
} RuleSegment;

/* Rule object */
typedef struct {
    PyObject_HEAD
    char *rule_str;
    char *endpoint;
    uint16_t methods_bitmask;  /* standard methods as bits */
    PyObject *methods_extra;   /* frozenset of non-standard methods, or NULL */
    int strict_slashes;
    RuleSegment *segments;
    int n_segments;
    int is_static;             /* true if no dynamic segments */
} Cruet_Rule;

/* Convert an uppercase method string to its bitmask bit, or 0 if unknown. */
uint16_t cruet_method_str_to_bit(const char *s, size_t len);

/* Check if a rule allows a given method.
 * If method_bit != 0, uses pure bitmask test.
 * If method_bit == 0 (non-standard method), falls back to PySet_Contains
 * on rule->methods_extra with method_py.
 * Returns 1 on match, 0 on no match, -1 on error. */
int cruet_rule_has_method(Cruet_Rule *rule, uint16_t method_bit,
                           PyObject *method_py);

/* ---- C hash table for static route index ---- */

typedef struct {
    char *key;              /* strdup'd path string */
    size_t key_len;
    Cruet_Rule *rule;      /* borrowed ref (kept alive by Map.rules PyList) */
    int occupied;
} Cruet_StaticEntry;

typedef struct {
    Cruet_StaticEntry *entries;
    size_t capacity;
    size_t count;
} Cruet_StaticIndex;

/* Map object */
typedef struct {
    PyObject_HEAD
    PyObject *rules;            /* list of Rule objects (all rules) */
    Cruet_StaticIndex static_index;  /* C hash table for static rules */
    Cruet_Rule **dynamic_rules;      /* C array of borrowed pointers */
    Py_ssize_t n_dynamic;
    Py_ssize_t dynamic_cap;
} Cruet_Map;

/* MapAdapter object */
typedef struct {
    PyObject_HEAD
    Cruet_Map *map;
    char *server_name;
} Cruet_MapAdapter;

/* Internal C-level rule matching (avoids Python method dispatch overhead) */
PyObject *Cruet_Rule_match_internal(Cruet_Rule *self, const char *path, size_t path_len);

#endif
