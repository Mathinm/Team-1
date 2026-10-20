"""Create stores and store-scoped product master data.

Revision ID: 0001_stores_products
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_stores_products"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_stores_name_nonempty"),
    )
    op.create_index("ix_stores_id", "stores", ["id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("shelf_life_days", sa.Integer(), nullable=False),
        sa.Column("storage_type", sa.String(length=40), nullable=False),
        sa.Column("min_temperature", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_temperature", sa.Numeric(5, 2), nullable=False),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("shelf_life_days > 0", name="ck_products_shelf_life_positive"),
        sa.CheckConstraint("cost_price >= 0", name="ck_products_cost_nonnegative"),
        sa.CheckConstraint("selling_price > 0", name="ck_products_selling_positive"),
        sa.CheckConstraint("low_stock_threshold >= 0", name="ck_products_threshold_nonnegative"),
        sa.CheckConstraint("min_temperature < max_temperature", name="ck_products_temperature_range"),
        sa.CheckConstraint("unit IN ('kg', 'piece', 'litre')", name="ck_products_unit"),
    )
    op.create_index("ix_products_id", "products", ["id"])
    op.create_index("ix_products_store_id", "products", ["store_id"])


def downgrade():
    op.drop_index("ix_products_store_id", table_name="products")
    op.drop_index("ix_products_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_stores_id", table_name="stores")
    op.drop_table("stores")
