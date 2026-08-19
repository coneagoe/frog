# Selected-Table Clean Restore Safety Design

## Goal

Prevent `db_export.sh --clean --table NAME` and
`db_import.sh --clean --table NAME` from silently removing foreign-key
constraints owned by unselected tables. Replace the obsolete
matching-run-only backup/restore documentation with the actual unified Paper
Trading enum and selected-table restore behavior.

## Selected-Table Clean Behavior

For a selected-table clean operation, the scripts will inspect PostgreSQL for
foreign keys whose referenced table is the selected table and whose owning
table is different from the selected table.

When any such inbound foreign key exists, the operation will fail before its
drop or restore phase. The error will identify the selected table and instruct
the operator to use a full business-database clean restore or an explicitly
managed recovery procedure. It will not drop the selected table, truncate any
table, drop a foreign-key constraint, or import the dump.

This applies equally to clean dump generation and clean import because both
currently embed destructive drop statements. A selected table with no inbound
foreign keys retains the existing drop-and-restore behavior.

## Full Clean Behavior

Full business-database clean export/import remains unchanged. It retains the
current reverse business-table drop ordering and enum cleanup rules because all
managed dependent tables are intentionally included in that operation.

## Documentation

The Paper Trading operations guide will have one authoritative backup/restore
description. It will list the governed enum catalog, describe duplicate-safe
enum creation for selected-table dumps, state that shared types are retained,
and document that selected-table clean operations are rejected when unselected
tables have inbound foreign keys. It will remove the obsolete claim that only
`paper_matching_runs` is enum-aware.

## Verification

Script tests will assert that the generated metadata query and clean command
reject a selected table with an unselected inbound foreign key. PostgreSQL
integration coverage, gated by `TEST_POSTGRESQL_URL`, will create
`paper_orders` plus unselected dependent tables, execute each selected-table
clean path, assert the command fails before mutation, and verify the dependent
foreign keys remain present. Existing full-clean and enum-order tests verify
that the full restore path is unchanged.
