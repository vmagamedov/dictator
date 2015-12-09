import string
import datetime
import collections
from functools import wraps
from itertools import imap, izip, chain


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
    return string


def _generative(func):
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
    @wraps(func)
    def wrapper(self):
        return func(self) if self.state is not None else u''
    return wrapper


_undefined = object()


class Base(object):
    __expect__ = ()

    name = None
    state = None
    valid = None
    errors = ()

    def __deserialize__(self, data):
        raise NotImplementedError

    def __serialize__(self):
        raise NotImplementedError

    def __import__(self, value):
        raise NotImplementedError

    def __export__(self):
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
        return self.__export__()

    @property
    def data(self):
        return self.__serialize__()

    @classmethod
    def with_value(cls, value):
        self = object.__new__(cls)
        self.__import__(value)
        return self

    @classmethod
    def without_value(cls, errors=None):
        self = object.__new__(cls)
        map(self.note_error, errors or ())
        return self

    def note_error(self, error):
        self.errors += (error,)
        self.valid = False

    @classmethod
    @_generative
    def named(cls, name):
        cls.name = name

    @classmethod
    @_generative
    def using(cls, **options):
        for name, value in options.iteritems():
            setattr(cls, name, value)

    @classmethod
    @_generative
    def expect(cls, *validators):
        cls.__expect__ = validators


class Scalar(Base):
    __apply__ = ()

    optional = False

    @classmethod
    @_generative
    def apply(cls, *functions):
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
    __apply__ = (string.strip,)

    @_accepts(unicode)
    @_empty_check
    def __deserialize__(self, data):
        self.state = data

    @_handle_empty
    def __serialize__(self):
        return unicode(self.state)


class Integer(Scalar):

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
    __value_type__ = String

    state = ()

    @classmethod
    @_generative
    def of(cls, value_type):
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
    __value_type__ = String

    state = ImmutableDict()

    @classmethod
    @_generative
    def of(cls, value_type):
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
    __value_types__ = ()

    state = ImmutableDict()

    missing = False
    unknown = False

    @classmethod
    @_generative
    def of(cls, *value_types):
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

    @classmethod
    def of(cls, *value_types):
        if len(value_types) == 1 and not value_types[0].name:
            return SimpleMapping.of(value_types[0])
        else:
            return DeclaredMapping.of(*value_types)


def one_of(values):
    values = set(values)

    def one_of_checker(el):
        if not el.value in values:
            el.note_error(N_(u'Wrong choice'))

    return one_of_checker


def get_errors(schema):
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
