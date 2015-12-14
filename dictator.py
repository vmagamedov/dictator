"""
    dictator
    ~~~~~~~~

    Structured data validation library.

    :copyright: (c) 2015 by Vladimir Magamedov.
    :license: BSD, see LICENSE.txt for more details.
"""
import string
import datetime
import collections
from functools import wraps
from itertools import imap, izip, chain


__all__ = ('Boolean', 'String', 'Integer', 'Date', 'Datetime',
           'Sequence', 'SimpleMapping', 'DeclaredMapping', 'Mapping',
           'one_of', 'get_errors')


class ImmutableDict(dict):
    _hash = None

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(frozenset(self.items()))
        return self._hash

    def _immutable(self):
        raise TypeError("{} object is immutable"
                        .format(self.__class__.__name__))

    __delitem__ = __setitem__ = _immutable
    clear = pop = popitem = setdefault = update = _immutable


def N_(string):
    """Marks strings for further translation."""
    return string


def _generative(func):
    """Decorator, which wraps method to call it in the context
    of the copied class to provide methods chaining and immutability
    for the original class."""
    @wraps(func)
    def wrapper(cls, *args, **kwargs):
        if not hasattr(cls, '__subclassed__'):
            # subclass
            cls = type(cls.__name__, (cls,), {'__subclassed__': True})
        else:
            # copy
            cls = type(cls.__name__, cls.__bases__, dict(cls.__dict__))
        func(cls, *args, **kwargs)
        return cls
    return wrapper


def _accepts(*types):
    """Verifies incoming value type."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, data):
            if not isinstance(data, types):
                self.note_error(N_(u'Invalid type'))
            else:
                return func(self, data)
        return wrapper
    return decorator


def _empty_check(func):
    """Checks for empty values."""
    @wraps(func)
    def wrapper(self, data):
        if not data.strip():
            if self.optional:
                pass
            else:
                self.note_error(N_(u'Empty value'))
        else:
            return func(self, data)
    return wrapper


def _handle_empty(func):
    """Handles `None` values, they are serialized as empty values."""
    @wraps(func)
    def wrapper(self):
        return func(self) if self.state is not None else u''
    return wrapper


_undefined = object()


class Base(object):
    __expect__ = ()

    #: name of the element, if it is a part of the mapping.
    name = None

    #: internal value representation.
    state = None

    #: `True` if deserialization and validation was successful,
    #: `False` if there was any kind of error, `None` if element
    #: was instantiated in other way. See also `with_value` and
    #: `without_value` methods.
    valid = None

    #: list of deserialization and validation errors.
    errors = ()

    def __deserialize__(self, data):
        """To deserialize string values into pythonic types."""
        raise NotImplementedError

    def __serialize__(self):
        """To serialize pythonic types into string values."""
        raise NotImplementedError

    def __import__(self, value):
        """To initialize `dictator` schema instance from pythonic
        data structure."""
        raise NotImplementedError

    def __export__(self):
        """To export `dictator` schema instance as pythonic data
        structure."""
        raise NotImplementedError

    def __validate__(self):
        value = self.__export__()
        if value is not None:
            self.valid = True  # this can be changed later by validators
            for validator in self.__expect__:
                validator(self)

    def __new__(cls, data):
        self = object.__new__(cls)
        self.__deserialize__(data)
        return self

    def __init__(self, data):
        self.__validate__()

    @property
    def value(self):
        """Returns deserialized and validated pythonic data structure,
        represented by this schema type."""
        return self.__export__()

    @property
    def data(self):
        """Returns data structure, with scalar values serialized to
        strings."""
        return self.__serialize__()

    @classmethod
    def with_value(cls, value):
        """Initializes schema type with pythonic value, without
        running deserialization and validation."""
        self = object.__new__(cls)
        self.__import__(value)
        return self

    @classmethod
    def without_value(cls, errors=None):
        """Initializes schema type without value, as empty.
        Optionally list of errors can be provided, this will also
        mark this schema instance as non valid."""
        self = object.__new__(cls)
        map(self.note_error, errors or ())
        return self

    def note_error(self, error):
        """Adds error for this element."""
        self.errors += (error,)
        self.valid = False

    @classmethod
    @_generative
    def named(cls, name):
        """Returns named schema type."""
        cls.name = name

    @classmethod
    @_generative
    def using(cls, **options):
        """Returns schema type with modified options, provided
        using keyword arguments."""
        for name, value in options.iteritems():
            setattr(cls, name, value)

    @classmethod
    @_generative
    def expect(cls, *validators):
        """Returns schema type with specified value validating
        functions."""
        cls.__expect__ = validators


class Scalar(Base):
    __apply__ = ()

    #: option, when `True`, this type will be able to receive
    #: empty value.
    optional = False

    @classmethod
    @_generative
    def apply(cls, *functions):
        """Returns schema type with specified in arguments value
        modification functions. They are called after deserialization
        and before validation."""
        cls.__apply__ = functions

    def __init__(self, data):
        value = self.__export__()
        if value is not None:
            for function in self.__apply__:
                value = function(value)
            self.__import__(value)
        super(Scalar, self).__init__(data)

    def __export__(self):
        return self.state

    def __import__(self, value):
        self.state = value


class Boolean(Scalar):
    """Deserializes boolean type.

    `True` values: "1", "true", "True", "t" or "on".

    `False` values: "0", "false", "False", "f" or "off".
    """

    @_accepts(unicode)
    @_empty_check
    def __deserialize__(self, data):
        if data in (u'1', u'true', u'True', u't', u'on'):
            self.state = True
        elif data in (u'0', u'false', u'False', u'f', u'off'):
            self.state = False
        else:
            self.note_error(N_(u'Invalid value'))

    @_handle_empty
    def __serialize__(self):
        return u'true' if self.state else u'false'


class String(Scalar):
    """Deserializes string type.

    NOTE: it contains one default value modifier: `strip` function.
    """
    __apply__ = (string.strip,)

    @_accepts(unicode)
    @_empty_check
    def __deserialize__(self, data):
        self.state = data

    @_handle_empty
    def __serialize__(self):
        return unicode(self.state)


class Integer(Scalar):
    """Deserializes integer type."""

    @_accepts(unicode)
    @_empty_check
    def __deserialize__(self, data):
        try:
            self.state = int(data)
        except ValueError:
            self.note_error(N_(u'Invalid value'))

    @_handle_empty
    def __serialize__(self):
        return unicode(self.state)


class Date(Scalar):
    """Deserializes dates into `datetime.date` type."""

    #: option, provides format for date parsing and formatting.
    date_format = '%Y-%m-%d'

    @_accepts(unicode)
    @_empty_check
    def __deserialize__(self, data):
        try:
            dt = datetime.datetime.strptime(data, self.date_format)
            self.state = dt.date()
        except ValueError:
            self.note_error(N_(u'Invalid value'))

    @_handle_empty
    def __serialize__(self):
        return unicode(self.state.strftime(self.date_format))


class Datetime(Scalar):
    """Deserializes date/time into `datetime.datetime` type."""

    #: option, provides format for date/time parsing and formatting.
    datetime_format = '%Y-%m-%dT%H:%M:%S'

    @_accepts(unicode)
    @_empty_check
    def __deserialize__(self, data):
        try:
            self.state = datetime.datetime.strptime(data, self.datetime_format)
        except ValueError:
            self.note_error(N_(u'Invalid value'))

    @_handle_empty
    def __serialize__(self):
        return unicode(self.state.strftime(self.datetime_format))


class Container(Base):

    @classmethod
    @_generative
    def of(cls, *args, **kwargs):
        raise NotImplementedError

    def __getitem__(self, key):
        raise NotImplementedError


class Sequence(Container):
    """Represents sequence of items.

    By default it represents a sequence of strings.
    """

    __value_type__ = String

    state = ()

    @classmethod
    @_generative
    def of(cls, value_type):
        """Returns `Sequence` schema type with specified item type."""
        cls.__value_type__ = value_type

    def __validate__(self):
        super(Sequence, self).__validate__()
        items_iterator = chain(self.state, [self])
        self.valid = all(item.valid for item in items_iterator)

    def __export__(self):
        return [item.__export__() for item in self.state]

    def __import__(self, value):
        self.state = tuple(imap(self.__value_type__.with_value, value))

    @_accepts(collections.Sequence)
    def __deserialize__(self, data):
        self.state = tuple(imap(self.__value_type__, data))

    def __serialize__(self):
        return [item.__serialize__() for item in self.state]

    def __getitem__(self, index):
        return self.state[index]


class SimpleMapping(Container):
    """Represents mapping of strings to values.

    By default it represents a mapping of strings to strings.
    """
    __value_type__ = String

    state = ImmutableDict()

    @classmethod
    @_generative
    def of(cls, value_type):
        """Returns `SimpleMapping` schema type with specified value type."""
        cls.__value_type__ = value_type

    def __validate__(self):
        super(SimpleMapping, self).__validate__()
        items_iterator = chain(self.state.itervalues(), [self])
        self.valid = all(item.valid for item in items_iterator)

    def __export__(self):
        return {k: v.__export__() for k, v in self.state.iteritems()}

    def __import__(self, value):
        keys, values = zip(*value.iteritems()) or ([], [])
        values_iterator = imap(self.__value_type__.with_value, values)
        self.state = ImmutableDict(izip(keys, values_iterator))

    @_accepts(collections.Mapping)
    def __deserialize__(self, data):
        keys, values_data = zip(*data.iteritems()) or ([], [])
        values_iterator = imap(self.__value_type__, values_data)
        self.state = ImmutableDict(izip(keys, values_iterator))

    def __serialize__(self):
        return {k: v.__serialize__() for k, v in self.state.iteritems()}

    def __getitem__(self, key):
        return self.state[key]


class DeclaredMapping(Container):
    """Represents mapping with predefined keys and value types."""

    __value_types__ = ()

    state = ImmutableDict()

    #: option, when `False`, which is by default, any missing key
    #: will flag an error.
    missing = False

    #: option, when `False`, which is by default, any unknown key
    #: will flag an error.
    unknown = False

    @classmethod
    @_generative
    def of(cls, *value_types):
        """Returns `DeclaredMapping` with specified named value types."""
        cls.__value_types__ = tuple(value_types)

    def __validate__(self):
        super(DeclaredMapping, self).__validate__()
        items_iterator = chain(self.state.itervalues(), [self])
        self.valid = all(item.valid is not False for item in items_iterator)

    def __import__(self, value):
        state = {}
        for value_type in self.__value_types__:
            item_value = value.get(value_type.name, None)
            if item_value is None:
                state[value_type.name] = value_type.without_value()
            else:
                state[value_type.name] = value_type.with_value(item_value)
        self.state = ImmutableDict(state)

    def __export__(self):
        return {k: v.__export__() for k, v in self.state.iteritems()}

    @_accepts(collections.Mapping)
    def __deserialize__(self, data):
        defined_keys = set(t.name for t in self.__value_types__)
        provided_keys = set(data.iterkeys())

        missing_keys = defined_keys - provided_keys
        if missing_keys and not self.missing:
            self.note_error(N_(u'Missing keys'))

        unknown_keys = provided_keys - defined_keys
        if unknown_keys and not self.unknown:
            self.note_error(N_(u'Unknown keys'))

        state = {}
        for value_type in self.__value_types__:
            value_data = data.get(value_type.name, _undefined)
            if value_data is _undefined:
                errors = () if self.missing else (N_(u'Missing value'),)
                state[value_type.name] = value_type.without_value(errors)
            else:
                state[value_type.name] = value_type(value_data)
        self.state = ImmutableDict(state)

    def __serialize__(self):
        return {k: v.__serialize__() for k, v in self.state.iteritems()}

    def __getitem__(self, key):
        return self.state[key]


class Mapping(Container):
    """Works like a factory for `SimpleMapping` and `DeclaredMapping`."""

    @classmethod
    def of(cls, *value_types):
        """Returns `SimpleMapping` or `DeclaredMapping` depending on
        provided value types.

        If there is only one type provided and it does not have a name,
        then `SimpleMapping` will be returned, otherwise
        `DeclaredMapping` will be returned.
        """
        if len(value_types) == 1 and not value_types[0].name:
            return SimpleMapping.of(value_types[0])
        else:
            return DeclaredMapping.of(*value_types)


def one_of(values):
    """Checks that element's value is one of the provided values."""
    values = set(values)

    def one_of_checker(el):
        if el.value not in values:
            el.note_error(N_(u'Wrong choice'))

    return one_of_checker


def get_errors(schema):
    """Walks through the schema instance to collect all errors."""
    if isinstance(schema, Container):
        if isinstance(schema.state, tuple):
            return {'errors': schema.errors,
                    'items': map(get_errors, schema.state)}
        elif isinstance(schema.state, dict):
            keys, values = zip(*schema.state.iteritems())
            values = imap(get_errors, values)
            return {'errors': schema.errors,
                    'items': dict(izip(keys, values))}
        else:
            raise TypeError('Unknown collection type: %r' % type(schema))
    else:
        return {'errors': schema.errors}
