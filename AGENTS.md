# AGENTS.md

## Workflow

This API is under heavy development and there is a lot of iterations happening until
we first deploy it. Priority should be given to decissions currently specified, and not
to legacy code or naming conventions. architecture.md and docs should be used for reference,
and only when there is a conflict we should discuss.

Don't make tests for legacy, and don't keep compatibility with previous iterations of this API, as
it's not deployed anywhere yet.

The biggests firsts commits have been done already, so once a batch has been done, ask the user if he
wants to stage the code. If there is only one piece of work (not multiple features to be commited separately)
stage directly. NEVER commit.

Make sure that the code runs, and that no images are left stale. There should be a series of profiles
that keep the API simple to rebuild (not having stale images) if there is a change in one.

If there are changes to the endpoints, add examples in `meshtastic_things/mesh_things/examples/` (they go
through the mesh-things client, and a test runs each one) AND update the docs folder, as well as architecture.

Any change to the API's schema (an endpoint, a parameter, a serializer field, or even a docstring) raises
`__version__` in `meshtastic_things/mesh_things/src/mesh_things/__init__.py` and is followed by
`scripts/regen-client-schema.sh`, so the mesh-things package stays in sync. CI fails otherwise.

## Comments and Docstrings

Keep comments and docstrings concise, purposeful, and non-verbose.

### General Rules

- Prefer clear, self-explanatory code over explanatory comments.
- Add comments only when they provide context that cannot be understood from the code.
- Do not comment on obvious operations or restate what the code does.
- Keep comments short—ideally one sentence or a few lines.
- Use complete sentences and correct punctuation.
- Remove outdated comments when changing code.
- Do not leave commented-out code in the repository.
- Avoid TODO comments unless they include a clear, actionable task.

### Inline Comments

Use inline comments sparingly and only to explain:

- Why an unusual approach is necessary.
- A non-obvious business rule.
- A workaround for a library, platform, or tooling limitation.
- Important performance, security, or compatibility considerations.

Prefer:

```python
# Retry because the upstream service may temporarily reject requests.
```

Avoid:

```python
# Increment i by 1
i += 1
```

### Docstrings

- Use docstrings for public modules, classes, functions, and methods.
- Keep simple docstrings to one concise sentence.
- Describe purpose and behavior, not implementation details.
- Document parameters, return values, exceptions, and side effects only when they are not obvious.
- Do not repeat type information already provided by type annotations unless additional clarification is useful.
- Keep docstrings updated when behavior changes.

Prefer:

```python
def calculate_total(items: list[Item]) -> Decimal:
    """Return the total price of all items, including applicable discounts."""
```

For more complex APIs:

```python
def fetch_user(user_id: str, timeout: float = 5.0) -> User:
    """Fetch a user by ID.

    Args:
        user_id: Unique identifier of the user.
        timeout: Maximum request duration in seconds.

    Returns:
        The matching user.

    Raises:
        UserNotFoundError: If no user exists with the given ID.
        TimeoutError: If the request exceeds the timeout.
    """
```

### Style

- Follow the documentation conventions already used by the project.
- Use the language's standard docstring format where one exists.
- Avoid unnecessary headings, examples, background information, or repetition.
- Write for the next developer who needs to understand the code quickly.

## API Endpoint Docstrings

View docstrings are published: drf-spectacular turns them into the operation
descriptions in the OpenAPI schema and the Swagger UI. They are read by API
consumers, not only by the next developer, so they are written as documentation
rather than as implementation notes.

### Rules

- Describe what the endpoint does and what it returns, from the caller's point
  of view.
- Aim for a useful level of correctness without being overly technical.
- Do not restate the HTTP method or path. The schema already shows them.
- Do not reference other source files, management commands, or files under
  `docs/`. Anything worth knowing must be stated in plain terms instead.
- Do not use em dashes.
- Avoid shorthand framings like "what exists" or "what the values were". They
  read as unprofessional in a published document.
- Keep the operational facts a caller cannot guess: rollback behaviour,
  credentials shown only once, superuser-only writes, responses that
  deliberately reveal nothing, and results that stay empty until something else
  has run.

### Parameters

Do not describe several parameters in a narrative paragraph. List them in an
`Args:` section, following the same PEP 257 convention used elsewhere in this
file, one entry per parameter, giving the default and the accepted values where
they are not obvious.

Keep worked examples out of the docstring and put them in the docs folder
instead, alongside the endpoint they belong to.

Prefer:

```python
class TimeseriesView(APIView):
    """Return a device's readings for one measurement over a time range.

    Args:
        measurement: Measurement to read, for example `environment_metrics`. Required.
        field: Single field within the measurement. Defaults to every field.
        start: Start of the range, as a relative duration. Defaults to `-1h`.
    """
```

Avoid:

```python
class TimeseriesView(APIView):
    """Return a device's readings for one measurement over a time range.

    `measurement` is required. Narrow the result with `field`, move the window
    with `start` and `stop`, and downsample by passing `window` together with
    an aggregate in `agg`.
    """
```

### Document every operation

drf-spectacular falls back to the class docstring when a method has none, so on
a view with several methods one class docstring is silently reused as the
description for all of them. Give each method its own docstring, and leave the
class docstring off unless it applies to every method.

Prefer:

```python
class OwnerListCreateView(APIView):
    def get(self, request):
        """List registered owners. Email addresses are not included."""

    def post(self, request):
        """Register an owner and return its API key.

        The key is shown in this response and cannot be retrieved again
        afterwards.
        """
```

Avoid:

```python
class OwnerListCreateView(APIView):
    """POST /owners is the only unauthenticated write on this API"""
```
