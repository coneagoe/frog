# Airflow SQLAlchemy ORM Compatibility Design

## Problem

The Airflow 2.9.2 image provides SQLAlchemy 1.4, while repository ORM models
import `sqlalchemy.orm.mapped_column`, which exists only in SQLAlchemy 2.0.
Because the repository is bind-mounted into the Airflow containers, DAG
parsing imports these models against Airflow's SQLAlchemy runtime and fails
before the DAG can load.

## Decision

Add one small compatibility module under `storage/model/` that exports
`Mapped` and a `mapped_column` callable. It uses SQLAlchemy 2.x's native
`mapped_column` when available and falls back to SQLAlchemy 1.4's `Column`
when it is not. Update the three repository ORM modules that currently import
the 2.x-only symbol to use this local compatibility boundary.

The helper will preserve the existing call signatures used by the models,
including positional SQL types and keyword arguments such as `nullable`,
`default`, `server_default`, `index`, and `comment`. No SQLAlchemy version
will be forced into the Airflow image.

## Testing

Add a focused regression test that loads the compatibility module with a
simulated SQLAlchemy ORM namespace lacking `mapped_column`, verifies the
fallback resolves to `Column`, and imports the affected model modules through
that compatibility path. Run the existing blackroom storage tests and the
project's relevant lint/type checks afterward.

## Scope

In scope: the compatibility helper, three model imports, and regression test.
Out of scope: changing Airflow's base image, changing the repository's
SQLAlchemy 2.x dependency, or migrating unrelated legacy ORM modules.
