# alock v.1.0.4

## About

This is an inter-process, named, asyncronous lock library, closely based on [ilock](https://github.com/symonsoft/ilock). It provides only one class `ALock` with a very simple interface.

## Examples

Here's a basic example:

```python
from alock import ALock

async with ALock('Unique lock name'):
  # The code should be run as a system-wide single instance
  ...
```

## License

BSD
