"""sales lot snapshot

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# DDL вынесен в константу, потому что тесты поднимают эту же таблицу в тестовой
# базе. Второй копии DDL быть не должно: она разошлась бы с миграцией молча.
SALES_LOT_DDL = (
    # Снимок инвентаря Copart: только те 17 колонок CSV, которые читает бот.
    # Таблица целиком перезаписывается каждой загрузкой и истории не хранит,
    # поэтому ни первичного ключа, ни ограничений на строки здесь нет: фид
    # приходит от чужой системы и не обязан быть без дубликатов.
    #
    # Текстовые колонки хранят значение CSV дословно — карточка авто
    # отрисовывает год и пробег как есть, и разобранное число изменило бы
    # подпись под фотографией. Разобранные значения лежат отдельно и нужны
    # только для фильтрации, наружу они не уходят.
    """
    CREATE TABLE sales_lot (
        make TEXT NOT NULL,
        model_group TEXT,
        model_detail TEXT,
        year_text TEXT,
        odometer_text TEXT,
        sale_date TEXT,
        buy_now_text TEXT,
        lot_number TEXT,
        color TEXT,
        engine TEXT,
        drive TEXT,
        transmission TEXT,
        fuel_type TEXT,
        image_url TEXT,
        damage_description TEXT,
        trim TEXT,
        body_style TEXT,
        year INTEGER,
        odometer NUMERIC,
        buy_now_price INTEGER NOT NULL DEFAULT 0
    );
    """,
    # Поиск по заявке всегда начинается с марки и диапазона годов.
    """
    CREATE INDEX idx_sales_lot_make_year
    ON sales_lot(make, year);
    """,
    # Прогревочная рассылка берёт только свежие лоты с ценой BUY NOW.
    """
    CREATE INDEX idx_sales_lot_nurture
    ON sales_lot(year)
    WHERE buy_now_price > 0;
    """,
)


def upgrade() -> None:
    for statement in SALES_LOT_DDL:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sales_lot CASCADE;")
