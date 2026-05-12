"""Handles CrateDB interactions."""

from __future__ import annotations

import re
import typing as t
from builtins import issubclass  # noqa: A004
from contextlib import contextmanager
from datetime import datetime
from functools import cached_property

import sqlalchemy as sa
from singer_sdk.sql.connector import JSONSchemaToSQL
from sqlalchemy_cratedb.type.array import _ObjectArray
from sqlalchemy_cratedb.type.object import ObjectTypeImpl
from target_postgres.connector import NOTYPE, PostgresConnector
from verlib2 import Version

from target_cratedb.sqlalchemy.patch import polyfill_refresh_after_dml_engine


class CrateDBConnector(PostgresConnector):
    """Set up SQLAlchemy and database utilities."""

    allow_column_add: bool = True  # Whether ADD COLUMN is supported.
    allow_column_rename: bool = False  # Whether RENAME COLUMN is supported.
    allow_column_alter: bool = False  # Whether altering column types is supported.
    allow_merge_upsert: bool = False  # Whether MERGE UPSERT is supported.
    allow_temp_tables: bool = False  # Whether temp tables are supported.

    def create_engine(self) -> sa.Engine:
        """
        Create an SQLAlchemy engine object.

        Note: Needs to be patched to establish a polyfill which will synchronize write operations.
        """
        engine = super().create_engine()
        polyfill_refresh_after_dml_engine(engine)
        return engine

    @contextmanager
    def _connect(self) -> t.Iterator[sa.engine.Connection]:
        """
        Connect to the database.

        Note: Needs to be overwritten to perform a CrateDB version check.
        """
        engine = self._engine
        with engine.connect().execution_options() as conn:
            self._check_cratedb_620(conn)
            yield conn
        engine.dispose()

    def _check_cratedb_620(self, conn: sa.Connection):
        """
        Fail if the CrateDB version is lower than 6.2.

        -- https://github.com/crate/crate/issues/15161
        """
        with conn.begin():
            version_raw = conn.exec_driver_sql("SELECT version()").scalar_one()
        matches = re.match(r"^CrateDB (\d+\.\d+\.\d+).*", version_raw)
        if not matches:
            raise ConnectionError("Unable to inquire CrateDB version")
        cratedb_version = matches.group(1)
        if Version(cratedb_version) < Version("6.2"):
            raise ConnectionError("The connector requires CrateDB 6.2 or higher")

    @cached_property
    def jsonschema_to_sql(self) -> JSONSchemaToSQL:
        """
        Return a JSONSchemaToSQL instance with custom type handling.

        Note: Needs to be patched to supply handler for `ObjectTypeImpl`.
        """
        to_sql = super().jsonschema_to_sql
        to_sql.register_type_handler("integer", sa.BIGINT)
        to_sql.register_type_handler("object", ObjectTypeImpl)
        return to_sql

    @staticmethod
    def pick_best_sql_type(sql_type_array: list):
        """Select the best SQL type from an array of instances of SQL type classes.

        Note: Needs to be patched to supply handler for `ObjectTypeImpl`.

        Args:
            sql_type_array: The array of instances of SQL type classes.

        Returns:
            An instance of the best SQL type class based on defined precedence order.
        """
        precedence_order = [
            sa.ARRAY,
            # NOTE: Adjustment for CrateDB.
            ObjectTypeImpl,
            sa.TEXT,
            sa.TIMESTAMP,
            sa.DATETIME,
            sa.DATE,
            sa.TIME,
            sa.DECIMAL,
            sa.FLOAT,
            sa.BIGINT,
            sa.INTEGER,
            sa.BOOLEAN,
            NOTYPE,
        ]

        for sql_type in precedence_order:
            for obj in sql_type_array:
                if isinstance(obj, sql_type):
                    return obj
        return sa.TEXT()

    def _sort_types(
        self,
        sql_types: t.Iterable[sa.types.TypeEngine],
    ) -> list[sa.types.TypeEngine]:
        """Return the input types sorted from most to least compatible.

        Note: Needs to be patched to supply handlers for `_ObjectArray` and `NOTYPE`.

        For example, [Smallint, Integer, Datetime, String, Double] would become
        [Unicode, String, Double, Integer, Smallint, Datetime].

        String types will be listed first, then decimal types, then integer types,
        then bool types, and finally datetime and date. Higher precision, scale, and
        length will be sorted earlier.

        Args:
            sql_types (List[sqlalchemy.types.TypeEngine]): [description]

        Returns:
            The sorted list.
        """

        def _get_type_sort_key(
            sql_type: sa.types.TypeEngine,
        ) -> tuple[int, int]:
            # return rank, with higher numbers ranking first

            _len = int(getattr(sql_type, "length", 0) or 0)

            if isinstance(sql_type, _ObjectArray):
                return 0, _len
            if isinstance(sql_type, NOTYPE):
                return 0, _len

            if not hasattr(sql_type, "python_type"):
                raise TypeError(f"Resolving type for sort key failed: {sql_type}")

            _pytype = t.cast(type, sql_type.python_type)
            if issubclass(_pytype, (str, bytes)):
                return 900, _len
            if issubclass(_pytype, datetime):
                return 600, _len
            if issubclass(_pytype, float):
                return 400, _len
            if issubclass(_pytype, int):
                return 300, _len

            return 0, _len

        return sorted(sql_types, key=_get_type_sort_key, reverse=True)

    def copy_table_structure(
        self,
        full_table_name: str,
        from_table: sa.Table,
        connection: sa.engine.Connection,
        as_temp_table: bool = False,
    ) -> sa.Table:
        """Copy table structure.

        Note: Needs to be patched to prevent `Primary key columns cannot be nullable` errors.

        Args:
            full_table_name: the target table name potentially including schema
            from_table: the  source table
            connection: the database connection.
            as_temp_table: True to create a temp table.

        Returns:
            The new table object.
        """
        _, schema_name, table_name = self.parse_full_table_name(full_table_name)
        meta = sa.MetaData(schema=schema_name)
        columns = []
        if self.table_exists(full_table_name=full_table_name):
            raise RuntimeError("Table already exists")
        column: sa.Column
        for column in from_table.columns:
            # CrateDB: Prevent `Primary key columns cannot be nullable` errors.
            if column.primary_key and column.nullable:
                column.nullable = False
            columns.append(column._copy())
        new_table = sa.Table(table_name, meta, *columns)
        new_table.create(bind=connection)
        return new_table

    def prepare_schema(self, schema_name: str) -> None:
        """
        Don't emit `CREATE SCHEMA` statements to CrateDB.
        """
        pass
