"""A referenced-but-undefined name is a NameError waiting for its first caller.

This exists because [[B271]]/[[B269]] shipped one: `save_life_path` called
`_life_path_step_input_to_domain`, which lived in `converters.py` and was never
imported. Every call carrying `steps` died — and the GM life-path editor always
sends `steps`, so it could not be saved at all.

Nothing else caught it, and that is the point:

* the **build** was green — it does not execute the function;
* the **schema check** was green — a GraphQL document validating against a schema
  proves nothing about the resolver body;
* the **test suite** was green — no test called this mutation with `steps`.

A NameError inside a function body is invisible until that exact line runs, so
the usual green signals are all silent. This scans instead of executing, so a
function nobody has exercised yet is still checked.

`__file__` and friends are allowed: they are module attributes resolved at runtime,
which a static scan cannot see.
"""

from __future__ import annotations

import builtins
import pathlib
import symtable

import transversal


def _module_attributes() -> set[str]:
    return {"__file__", "__name__", "__doc__", "__package__", "__path__",
            "__spec__", "__loader__", "__builtins__", "__debug__", "__class__"}


def test_no_referenced_name_is_undefined():
    root = pathlib.Path(transversal.__file__).parent
    allowed = _module_attributes()
    problems: list[str] = []

    for path in sorted(root.rglob("*.py")):
        try:
            table = symtable.symtable(path.read_text(), str(path), "exec")
        except SyntaxError as exc:  # a syntax error is the compiler's to report
            problems.append(f"{path.name}: {exc}")
            continue

        module_names = set(table.get_identifiers())

        def walk(scope, _path=path):
            for sym in scope.get_symbols():
                name = sym.get_name()
                if (sym.is_referenced() and sym.is_global()
                        and not sym.is_assigned()
                        and name not in module_names
                        and name not in allowed
                        and not hasattr(builtins, name)):
                    problems.append(f"{_path.name}: {scope.get_name()}() -> {name!r}")
            for child in scope.get_children():
                walk(child)

        walk(table)

    assert not problems, (
        "names referenced but never defined — these raise NameError the first time "
        "the line runs:\n  " + "\n  ".join(problems)
    )
