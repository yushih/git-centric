"""Transport-independent application functions.

Replace or extend this example with Git-centric operations.
"""


def greet(name: str = "world") -> str:
    """Return a greeting; reject empty names consistently across interfaces."""
    name = name.strip()
    if not name:
        raise ValueError("Name must not be blank")
    return f"Hello, {name}!"
