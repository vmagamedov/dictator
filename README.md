# Dictator

Data validation library

### Why another validation library?

To exploit simple yet powerful idea in order to provide predictable validation
with safety in mind.

### Example

```python
Schema = Mapping.of(String.named('foo'),
                    Sequence.named('bar').of(Integer))

schema = Schema({'foo': u'Some text',
                 'bar': [u'1', u'2', u'3']})

assert schema.value == {'foo': u'Some text', 'bar': [1, 2, 3]}
```

Syntax is heavily inspired by `flatland`. 

### Idea

Think about validation schema as a data type, which can contain other
data types. This looks similar to algebraic data types. Validation - is an
instantiation of this data type using input data structure. Instance of this
data type is a validated data structure with easily introspectable errors
and decoded pythonic values.

### How it works

Classes in Python has two interesting methods: `__new__` and `__init__`.

`__new__` method of the schema classes is responsible in decoding of input
values, and if value can be decoded, instance will be created. Schema instances
creation is done from top level element to the all nested elements, while
decoding is possible.

Then, when all possible instances were created in top-down fashion, validation
process is started using bottom-up strategy in the `__init__` method.

Input data structure is considered valid, obviously, when all validated nested
elements are also valid.
