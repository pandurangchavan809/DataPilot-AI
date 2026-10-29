import pytest

from app.core.errors import UnsafeQueryError
from app.db.guard import validate_readonly_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM countries",
        "select country_name, gdp from countries order by gdp desc limit 5",
        "WITH t AS (SELECT continent, SUM(gdp) g FROM countries GROUP BY continent) SELECT * FROM t",
        "SELECT a FROM x UNION SELECT b FROM y",
        "SELECT * FROM countries WHERE country_name = 'Update Island'",
        "SELECT 1;",
        "-- comment\nSELECT 1",
    ],
)
def test_allows_read_queries(sql):
    assert validate_readonly_sql(sql, "sqlite", 100)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM countries",
        "UPDATE countries SET gdp = 0",
        "INSERT INTO countries VALUES (1)",
        "DROP TABLE countries",
        "ALTER TABLE countries ADD COLUMN x INT",
        "CREATE TABLE x (a INT)",
        "SELECT 1; DROP TABLE countries",
        "SELECT * INTO backup FROM countries",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE 'x.db' AS x",
        "SELECT load_extension('evil')",
        "SELECT pg_sleep(100)",
        "SELECT * FROM countries FOR UPDATE",
        "TRUNCATE countries",
        "",
        "   ",
    ],
)
def test_blocks_unsafe_queries(sql):
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql(sql, "sqlite" if "pg_" not in sql else "postgres", 100)


def test_adds_limit_when_missing():
    assert "LIMIT 50" in validate_readonly_sql("SELECT * FROM countries", "sqlite", 50).upper()


def test_keeps_existing_limit():
    sql = validate_readonly_sql("SELECT * FROM countries LIMIT 5", "sqlite", 50)
    assert "LIMIT 5" in sql and "LIMIT 50" not in sql


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_other_dialects(dialect):
    assert validate_readonly_sql("SELECT COUNT(*) FROM orders", dialect, 10)
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql("SELECT SLEEP(10)" if dialect == "mysql" else "SELECT pg_read_file('/etc/passwd')", dialect, 10)
