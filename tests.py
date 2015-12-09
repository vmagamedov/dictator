from dictator import Mapping, Sequence, String, Integer
from dictator import one_of, get_errors


def inc(x):
    return x + 1


Schema = Mapping.of(
    String.named('foo').expect(one_of(['one', 'two', 'three'])),
    Integer.named('bar').apply(inc),
    String.named('baz').using(optional=True),
    Sequence.named('list').of(Mapping.of(Integer)),
)


schema = Schema({
    'foo': u'one',
    'bar': u'3',
    'baz': u'',
    'list': [
        {'x': u'1', 'y': u'2'},
        {'x': u'3', 'y': u'4'},
    ],
})

expected_value = {
    'foo': u'one',
    'bar': 4,
    'baz': None,
    'list': [{'y': 2, 'x': 1}, {'y': 4, 'x': 3}],
}

assert schema.valid, get_errors(schema)
assert schema.value == expected_value, schema.value


invalid_schema = Schema({})

expected_errors = {
    'items': {
        'foo': {'errors': (u'Missing value',)},
        'bar': {'errors': (u'Missing value',)},
        'baz': {'errors': (u'Missing value',)},
        'list': {
            'items': [],
            'errors': (u'Missing value',),
        },
    },
    'errors': (u'Missing keys',),
}

assert not invalid_schema.valid
assert get_errors(invalid_schema) == expected_errors, get_errors(invalid_schema)
